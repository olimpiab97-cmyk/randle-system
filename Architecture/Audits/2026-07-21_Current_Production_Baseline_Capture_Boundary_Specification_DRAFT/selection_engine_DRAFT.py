#!/usr/bin/env python3
"""Draft AST selection engine for synthetic boundary-specification fixtures.

This is not an authorized production capture script. Its CLI requires the same
synthetic-root marker and production-root refusal as the draft inventory tool.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from boundary_verifier_DRAFT import (
    BoundaryError,
    canonical_repository_path,
    derive_selection,
    is_test_candidate,
    stored_json_bytes,
)
from inventory_generator_DRAFT import assert_synthetic_root, enumerate_inventory, extended_length_path


DRAFT_SELECTION_VERSION = "0.1.0-DRAFT"
DYNAMIC_IMPORT_NAMES = {"__import__", "importlib.import_module"}
SUBPROCESS_NAMES = {"subprocess.call", "subprocess.check_call", "subprocess.check_output", "subprocess.Popen", "subprocess.run"}
FILE_CALL_NAMES = {"open", "Path", "pathlib.Path"}


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _module_name(path: str) -> str | None:
    if not path.endswith(".py"):
        return None
    parts = list(PurePosixPath(path).parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _resolve_import(current_path: str, node: ast.ImportFrom) -> list[str]:
    current_module = _module_name(current_path) or ""
    package = current_module.split(".")[:-1]
    if node.level:
        keep = len(package) - node.level + 1
        if keep < 0:
            raise BoundaryError("AMBIGUOUS_IMPORT", f"{current_path}:{node.lineno}")
        base = package[:keep]
    else:
        base = []
    if node.module:
        base.extend(node.module.split("."))
    prefix = ".".join(base)
    results = [prefix] if prefix else []
    for alias in node.names:
        if alias.name != "*":
            results.append(".".join(part for part in (prefix, alias.name) if part))
    return results


def _literal_strings(node: ast.AST) -> list[str]:
    values: list[str] = []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        values.append(node.value)
    elif isinstance(node, (ast.List, ast.Tuple)):
        for item in node.elts:
            values.extend(_literal_strings(item))
    return values


def _read_text(path: Path, relative: str) -> str:
    try:
        data = Path(extended_length_path(path)).read_bytes()
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BoundaryError("UNSUPPORTED_SOURCE_ENCODING", relative) from exc


def derive_repository_records(
    root: Path,
    include_registry: Mapping[str, Any],
    exclusion_registry: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Derive path records and dependency edges from a synthetic repository."""

    assert_synthetic_root(root)
    inventory = enumerate_inventory(root)
    paths = [item["canonical_path"] for item in inventory["artifacts"]]
    path_set = set(paths)
    include_entries = {
        entry["path"]: entry
        for entry in include_registry["entries"]
        if entry["path_kind"] == "repository-relative"
    }
    module_to_path = {
        module: path
        for path in paths
        if (module := _module_name(path)) is not None
    }
    imports: dict[str, set[str]] = {path: set() for path in paths}
    literal_targets: dict[str, set[str]] = {path: set() for path in paths}
    edges: list[dict[str, Any]] = []

    for path in paths:
        if not path.endswith(".py"):
            continue
        source = _read_text(root.joinpath(*path.split("/")), path)
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            raise BoundaryError("SOURCE_PARSE_ERROR", f"{path}:{exc.lineno}") from exc
        for node in ast.walk(tree):
            module_names: list[str] = []
            if isinstance(node, ast.Import):
                module_names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module_names = _resolve_import(path, node)
            for module_name in module_names:
                target = module_to_path.get(module_name)
                if target is not None:
                    imports[path].add(target)
                    edges.append({"edge_type": "AST_IMPORT", "source": path, "source_line": node.lineno, "target": target})

            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node.func)
            if name in DYNAMIC_IMPORT_NAMES:
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    raise BoundaryError("UNRESOLVED_DYNAMIC_DEPENDENCY", f"{path}:{node.lineno}:{name}")
                target = module_to_path.get(node.args[0].value)
                if target is None:
                    raise BoundaryError("UNRESOLVED_DYNAMIC_DEPENDENCY", f"{path}:{node.lineno}:{node.args[0].value}")
                imports[path].add(target)
                edges.append({"edge_type": "DYNAMIC_IMPORT", "source": path, "source_line": node.lineno, "target": target})
            elif name in SUBPROCESS_NAMES:
                if not node.args:
                    raise BoundaryError("UNRESOLVED_DYNAMIC_DEPENDENCY", f"{path}:{node.lineno}:{name}")
                strings = _literal_strings(node.args[0])
                if not strings:
                    raise BoundaryError("UNRESOLVED_DYNAMIC_DEPENDENCY", f"{path}:{node.lineno}:{name}")
                for literal in strings:
                    candidate = literal.replace("\\", "/")
                    if candidate in path_set:
                        literal_targets[path].add(candidate)
                        edges.append({"edge_type": "SUBPROCESS_TARGET", "source": path, "source_line": node.lineno, "target": candidate})
            elif name in FILE_CALL_NAMES and node.args:
                for literal in _literal_strings(node.args[0]):
                    candidate = literal.replace("\\", "/")
                    if candidate in path_set:
                        literal_targets[path].add(candidate)
                        edges.append({"edge_type": "LITERAL_FILE_TARGET", "source": path, "source_line": node.lineno, "target": candidate})

    selected = set(include_entries)
    changed = True
    while changed:
        changed = False
        for source in tuple(selected):
            for target in imports.get(source, set()) | literal_targets.get(source, set()):
                if target not in selected:
                    selected.add(target)
                    changed = True
        for path in paths:
            if is_test_candidate(path) and (imports[path] | literal_targets[path]) & selected and path not in selected:
                selected.add(path)
                changed = True

    records: list[dict[str, Any]] = []
    for path in paths:
        entry = include_entries.get(path)
        if entry:
            path_class = entry["class"]
        elif is_test_candidate(path):
            path_class = "production-test"
        elif path.endswith(".py"):
            path_class = "runtime-support-module"
        else:
            path_class = "unclassified"
        signals: list[str] = []
        if path in include_entries:
            signals.append("governed_production_recovery")
        elif path in selected and is_test_candidate(path):
            signals.append("imports_captured_runtime")
        elif path in selected:
            signals.append("imports_captured_runtime")
        records.append({"class": path_class, "path": canonical_repository_path(path), "signals": signals})
    return records, sorted(edges, key=lambda item: (item["source"], item["source_line"], item["edge_type"], item["target"]))


def derive_repository_selection(
    root: Path,
    include_registry: Mapping[str, Any],
    exclusion_registry: Mapping[str, Any],
    rule_registry: Mapping[str, Any],
) -> dict[str, Any]:
    records, edges = derive_repository_records(root, include_registry, exclusion_registry)
    selected = derive_selection(records, include_registry, exclusion_registry, rule_registry)
    return {
        "draft_selection_version": DRAFT_SELECTION_VERSION,
        "dependency_edges": edges,
        "path_records": records,
        "selected_paths": selected,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--include-registry", type=Path, required=True)
    parser.add_argument("--exclusion-registry", type=Path, required=True)
    parser.add_argument("--rule-registry", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = derive_repository_selection(
            args.fixture_root,
            json.loads(args.include_registry.read_text(encoding="utf-8")),
            json.loads(args.exclusion_registry.read_text(encoding="utf-8")),
            json.loads(args.rule_registry.read_text(encoding="utf-8")),
        )
    except (BoundaryError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(stored_json_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
