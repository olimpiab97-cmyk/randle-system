#!/usr/bin/env python3
"""Parser-backed draft selection engine for synthetic specification fixtures.

The engine refuses production roots through ``inventory_generator_DRAFT``.  It
is specification evidence, not the future operational capture script.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from boundary_verifier_DRAFT import (
    QUESTIONED_TESTS,
    BoundaryError,
    artifact_key,
    canonical_repository_path,
    ensure_all_questioned_tests,
    is_test_candidate,
    require,
    semantic_identity,
    stored_json_bytes,
    validate_registries,
    validate_rule_registry,
    validate_terminal_dispositions,
)
from inventory_generator_DRAFT import assert_synthetic_root, enumerate_inventory, extended_length_path


DRAFT_SELECTION_VERSION = "2.0.0-DRAFT"
PYTHON_PARSER = "python-ast-closure-2.0.0-DRAFT"
POWERSHELL_PARSER = "powershell-literal-reference-1.0.0-DRAFT"
SHELL_PARSER = "shell-launch-reference-1.0.0-DRAFT"
JSON_CONFIG_PARSER = "json-config-reference-1.0.0-DRAFT"
YAML_CONFIG_PARSER = "yaml-config-reference-1.0.0-DRAFT"
TOML_CONFIG_PARSER = "toml-config-reference-1.0.0-DRAFT"
INI_CONFIG_PARSER = "ini-config-reference-1.0.0-DRAFT"

DYNAMIC_IMPORT_NAMES = {"__import__", "importlib.import_module"}
SUBPROCESS_NAMES = {"subprocess.call", "subprocess.check_call", "subprocess.check_output", "subprocess.Popen", "subprocess.run", "os.system"}
FILE_CALL_NAMES = {"open", "Path", "pathlib.Path", "io.open"}
STATIC_CALLS = {"render_template", "flask.render_template", "send_static_file", "pkgutil.get_data", "load_resource", "load_template", "load_asset"}
REPLAY_CALLS = {"load_replay", "open_replay", "register_replay", "register_scenario", "load_scenario"}
MODULE_REGISTRATION_CALLS = {"load_plugin", "register_plugin", "register_handler", "register_factory", "load_factory", "load_handler", "registry.load"}
ROUTE_CALL_SUFFIXES = {"route", "add_url_rule", "register_route"}
PATH_SUFFIXES = (".py", ".ps1", ".bat", ".cmd", ".sh", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".txt", ".html", ".css", ".js", ".csv", ".jsonl", ".pine")
CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
LAUNCH_SUFFIXES = {".ps1", ".bat", ".cmd", ".sh"}
STANDARD_LIBRARY = set(getattr(sys, "stdlib_module_names", ())) | {"os", "sys", "pathlib", "json", "re", "typing", "collections", "subprocess", "unittest", "importlib", "io"}


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
    return ".".join(parts) or None


def _module_map(paths: Sequence[str]) -> dict[str, str]:
    candidates: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        module = _module_name(path)
        if module:
            candidates[module].append(path)
    ambiguous = {module: values for module, values in candidates.items() if len(values) > 1}
    if ambiguous:
        raise BoundaryError("AMBIGUOUS_MODULE_MAP", repr(ambiguous))
    return {module: values[0] for module, values in candidates.items()}


def _resolve_import_names(current_path: str, node: ast.ImportFrom) -> list[str]:
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
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [value for item in node.elts for value in _literal_strings(item)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal_strings(node.left), _literal_strings(node.right)
        return [a + b for a in left for b in right]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left, right = _literal_strings(node.left), _literal_strings(node.right)
        return [a.rstrip("/\\") + "/" + b.lstrip("/\\") for a in left for b in right]
    if isinstance(node, ast.Call) and _call_name(node.func) in {"os.path.join", "posixpath.join", "ntpath.join", "Path", "pathlib.Path"}:
        parts = [_literal_strings(arg) for arg in node.args]
        if parts and all(part for part in parts):
            values = [""]
            for choices in parts:
                joined: list[str] = []
                for prefix in values:
                    for choice in choices:
                        joined.append((prefix.rstrip("/\\") + "/" + choice.lstrip("/\\")).strip("/"))
                values = joined
            return values
    return []


def _read_text(path: Path, relative: str) -> str:
    try:
        return Path(extended_length_path(path)).read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BoundaryError("UNSUPPORTED_SOURCE_ENCODING", relative) from exc


def _source_location(path: str, line: int | str) -> str:
    return f"{path}:{line}"


def _edge(
    source: str,
    language: str,
    parser: str,
    location: str,
    edge_type: str,
    rule_id: str,
    declared: str,
    target: str | None,
    resolution: str,
    disposition: str,
    evidence: Sequence[str],
) -> dict[str, Any]:
    return {
        "source_path": source,
        "source_language_or_format": language,
        "parser": parser,
        "source_location": location,
        "edge_type": edge_type,
        "rule_id": rule_id,
        "literal_or_declared_target": declared,
        "canonical_resolved_target": target,
        "resolution_status": resolution,
        "evidence": list(evidence),
        "terminal_disposition": disposition,
    }


def _repo_candidate(source: str, literal: str, path_set: set[str]) -> str | None:
    candidate = literal.replace("\\", "/").strip()
    while candidate.startswith("./"):
        candidate = candidate[2:]
    candidates = [candidate]
    parent = PurePosixPath(source).parent.as_posix()
    if parent != ".":
        candidates.append(f"{parent}/{candidate}")
    for value in candidates:
        try:
            canonical = canonical_repository_path(value)
        except BoundaryError:
            continue
        if canonical in path_set:
            return canonical
    return None


def _looks_like_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return "/" in normalized or normalized.casefold().endswith(PATH_SUFFIXES)


def _dynamic_declaration(configuration: Mapping[str, Any], source: str, call: str) -> Mapping[str, Any] | None:
    matches = [
        item
        for item in configuration["discovery_policy"]["governed_dynamic_dependencies"]
        if item["source_path"] == source and item["call_name"] == call
    ]
    require(len(matches) <= 1, "AMBIGUOUS_DYNAMIC_DECLARATION", f"{source}:{call}")
    return matches[0] if matches else None


def _resolve_module_edge(
    source: str,
    line: int,
    module: str,
    edge_type: str,
    parser: str,
    module_to_path: Mapping[str, str],
    configuration: Mapping[str, Any],
) -> dict[str, Any]:
    target = module_to_path.get(module)
    if target:
        return _edge(source, "python", parser, _source_location(source, line), edge_type, "RUNTIME_CLOSURE", module, target, "RESOLVED_REPOSITORY", "INCLUDE", [f"AST:{source}:{line}"])
    top = module.split(".", 1)[0]
    if top in STANDARD_LIBRARY:
        return _edge(source, "python", parser, _source_location(source, line), edge_type, "EXTERNAL_DEPENDENCY_BIND", module, f"python-stdlib::{module}", "RESOLVED_ENVIRONMENT", "SEPARATE_AND_BIND", ["FREEZE:python_version"])
    declarations = configuration["discovery_policy"]["governed_external_dependencies"]
    match = next((item for item in declarations if item.get("module") == module or item.get("module") == top), None)
    if match:
        target_key = artifact_key("external-root-relative", match["path"], match["external_root_id"])
        return _edge(source, "python", parser, _source_location(source, line), edge_type, "EXTERNAL_DEPENDENCY_BIND", module, target_key, "RESOLVED_EXTERNAL", "SEPARATE_AND_BIND", match["evidence"])
    return _edge(source, "python", parser, _source_location(source, line), edge_type, "RUNTIME_CLOSURE", module, None, "UNRESOLVED", "INCLUDE", [f"AST:{source}:{line}"])


def _resolve_path_edge(
    source: str,
    line: int | str,
    literal: str,
    edge_type: str,
    rule_id: str,
    parser: str,
    language: str,
    path_set: set[str],
    *,
    required: bool = True,
) -> dict[str, Any] | None:
    if not _looks_like_path(literal):
        return None
    target = _repo_candidate(source, literal, path_set)
    if target:
        return _edge(source, language, parser, _source_location(source, line), edge_type, rule_id, literal, target, "RESOLVED_REPOSITORY", "INCLUDE", [f"LITERAL:{source}:{line}"])
    return _edge(source, language, parser, _source_location(source, line), edge_type, rule_id, literal, None, "UNRESOLVED" if required else "IGNORED_NONPATH", "INCLUDE", [f"LITERAL:{source}:{line}"])


def _python_edges(
    root: Path,
    path: str,
    path_set: set[str],
    module_to_path: Mapping[str, str],
    configuration: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = _read_text(root.joinpath(*path.split("/")), path)
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        raise BoundaryError("SOURCE_PARSE_ERROR", f"{path}:{exc.lineno}") from exc
    edges: list[dict[str, Any]] = []
    fixture_names: set[str] = set()
    used_fixtures: set[str] = set()
    test_functions = 0
    markers: set[str] = set()
    parameterized = 0
    parameter_names: set[str] = set()
    unittest_relationship = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append(_resolve_module_edge(path, node.lineno, alias.name, "PYTHON_ABSOLUTE_IMPORT", PYTHON_PARSER, module_to_path, configuration))
        elif isinstance(node, ast.ImportFrom):
            for module in _resolve_import_names(path, node):
                edges.append(_resolve_module_edge(path, node.lineno, module, "PYTHON_RELATIVE_IMPORT" if node.level else "PYTHON_ABSOLUTE_IMPORT", PYTHON_PARSER, module_to_path, configuration))
        if isinstance(node, ast.ClassDef) and any((_call_name(base) or "").endswith("TestCase") for base in node.bases):
            unittest_relationship = True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = {_call_name(item.func) if isinstance(item, ast.Call) else _call_name(item) for item in node.decorator_list}
            if any(name and name.endswith("fixture") for name in decorators):
                fixture_names.add(node.name)
            if node.name.startswith("test"):
                test_functions += 1
                used_fixtures.update(arg.arg for arg in node.args.args if arg.arg not in {"self", "cls"})
            for item in node.decorator_list:
                name = _call_name(item.func) if isinstance(item, ast.Call) else _call_name(item)
                if name and "pytest.mark" in name:
                    markers.add(name)
                if name and name.endswith("parametrize"):
                    parameterized += 1
                    if isinstance(item, ast.Call) and item.args:
                        for raw_names in _literal_strings(item.args[0]):
                            parameter_names.update(name.strip() for name in raw_names.split(",") if name.strip())
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "pytest_plugins" for target in targets):
                value = node.value
                for module in _literal_strings(value):
                    edges.append(_resolve_module_edge(path, node.lineno, module, "PYTEST_PLUGIN", PYTHON_PARSER, module_to_path, configuration))
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func) or ""
        if name in DYNAMIC_IMPORT_NAMES:
            literals = _literal_strings(node.args[0]) if node.args else []
            if literals:
                for module in literals:
                    edge = _resolve_module_edge(path, node.lineno, module, "PYTHON_DYNAMIC_IMPORT", PYTHON_PARSER, module_to_path, configuration)
                    if edge["resolution_status"] == "UNRESOLVED":
                        edge["rule_id"] = "DYNAMIC_DECLARATION_REQUIRED"
                    edges.append(edge)
            else:
                declaration = _dynamic_declaration(configuration, path, name)
                if declaration:
                    edge = _resolve_module_edge(path, node.lineno, declaration["target_module"], "GOVERNED_DYNAMIC_IMPORT", PYTHON_PARSER, module_to_path, configuration)
                    edge["evidence"] = declaration["evidence"]
                    edges.append(edge)
                else:
                    edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "PYTHON_DYNAMIC_IMPORT", "DYNAMIC_DECLARATION_REQUIRED", name, None, "UNRESOLVED", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
        elif name in SUBPROCESS_NAMES:
            literals = [value for arg in node.args for value in _literal_strings(arg)]
            if not literals:
                edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "SUBPROCESS_TARGET", "RUNTIME_CLOSURE", name, None, "UNRESOLVED", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
            for literal in literals:
                candidate = _resolve_path_edge(path, node.lineno, literal, "SUBPROCESS_TARGET", "RUNTIME_CLOSURE", PYTHON_PARSER, "python", path_set)
                if candidate:
                    edges.append(candidate)
        elif name in FILE_CALL_NAMES and node.args:
            literals = _literal_strings(node.args[0])
            if not literals and name in {"open", "io.open"}:
                edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "FILE_OPEN_TARGET", "RUNTIME_CLOSURE", name, None, "UNRESOLVED", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
            for literal in literals:
                candidate = _resolve_path_edge(path, node.lineno, literal, "FILE_OPEN_TARGET", "RUNTIME_CLOSURE", PYTHON_PARSER, "python", path_set)
                if candidate:
                    edges.append(candidate)
        elif name in STATIC_CALLS | REPLAY_CALLS:
            literals = [value for arg in node.args for value in _literal_strings(arg)]
            if not literals:
                edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "STATIC_OR_REPLAY_TARGET", "TEST_SUPPORT_CLOSURE" if name in REPLAY_CALLS else "RUNTIME_CLOSURE", name, None, "UNRESOLVED", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
            for literal in literals:
                candidate = _resolve_path_edge(path, node.lineno, literal, "REPLAY_OR_SCENARIO_TARGET" if name in REPLAY_CALLS else "STATIC_ASSET_TARGET", "TEST_SUPPORT_CLOSURE" if name in REPLAY_CALLS else "RUNTIME_CLOSURE", PYTHON_PARSER, "python", path_set)
                if candidate:
                    edges.append(candidate)
        elif name in MODULE_REGISTRATION_CALLS:
            literals = [value for arg in node.args for value in _literal_strings(arg)]
            if not literals:
                edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "PLUGIN_HANDLER_FACTORY", "RUNTIME_CLOSURE", name, None, "UNRESOLVED", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
            else:
                module = literals[-1]
                edge = _resolve_module_edge(path, node.lineno, module, "PLUGIN_HANDLER_FACTORY", PYTHON_PARSER, module_to_path, configuration)
                if edge["resolution_status"] == "UNRESOLVED":
                    path_edge = _resolve_path_edge(path, node.lineno, module, "PLUGIN_HANDLER_FACTORY", "RUNTIME_CLOSURE", PYTHON_PARSER, "python", path_set)
                    if path_edge:
                        edge = path_edge
                edges.append(edge)
        elif any(name.endswith("." + suffix) or name == suffix for suffix in ROUTE_CALL_SUFFIXES):
            handler_literals = [value for arg in node.args[1:] for value in _literal_strings(arg)]
            handler_literals = [value for value in handler_literals if not value.startswith("/")]
            if handler_literals:
                for handler in handler_literals:
                    edges.append(_resolve_module_edge(path, node.lineno, handler, "ROUTE_TARGET", PYTHON_PARSER, module_to_path, configuration))
            else:
                edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "ROUTE_REGISTRATION", "RUNTIME_CLOSURE", name, path, "RESOLVED_SELF", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
        elif name.endswith("usefixtures"):
            used_fixtures.update(value for arg in node.args for value in _literal_strings(arg))
    for fixture in sorted(used_fixtures - parameter_names):
        status = "RESOLVED_SELF" if fixture in fixture_names else "DECLARED_FIXTURE_REFERENCE"
        edges.append(_edge(path, "python", PYTHON_PARSER, f"{path}:fixture:{fixture}", "PYTEST_FIXTURE_RELATIONSHIP", "TEST_SUPPORT_CLOSURE", fixture, path if fixture in fixture_names else f"fixture::{fixture}", status, "INCLUDE", [f"PYTEST_FIXTURE:{path}:{fixture}"]))
    if unittest_relationship:
        edges.append(_edge(path, "python", PYTHON_PARSER, f"{path}:unittest", "UNITTEST_DISCOVERY", "PRODUCTION_TEST_CLOSURE", "unittest.TestCase", path, "RESOLVED_SELF", "INCLUDE", [f"UNITTEST:{path}"]))
    if parameterized:
        edges.append(_edge(path, "python", PYTHON_PARSER, f"{path}:parametrize", "PYTEST_PARAMETERIZATION", "PRODUCTION_TEST_CLOSURE", str(parameterized), path, "RESOLVED_SELF", "INCLUDE", [f"PYTEST_PARAMETRIZE:{path}"]))
    metadata = {
        "source_text": source,
        "is_test": is_test_candidate(path, source),
        "test_functions": test_functions,
        "pytest_markers": sorted(markers),
        "fixture_names": sorted(fixture_names),
    }
    return edges, metadata


def _launch_edges(root: Path, path: str, path_set: set[str]) -> list[dict[str, Any]]:
    text = _read_text(root.joinpath(*path.split("/")), path)
    suffix = PurePosixPath(path).suffix.casefold()
    parser, language = (POWERSHELL_PARSER, "powershell") if suffix == ".ps1" else (SHELL_PARSER, "batch" if suffix in {".bat", ".cmd"} else "shell")
    edges: list[dict[str, Any]] = []
    quote_pattern = re.compile(r"(?i)(?:^|\s)(?:python(?:\.exe)?\s+|py\s+|-file\s+|call\s+|bash\s+|sh\s+|\.\s+|&\s*)[\"']?([^\"'\s;|]+\.(?:py|ps1|bat|cmd|sh|json|yaml|yml|toml|ini|cfg))[\"']?")
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "REM ", "::")):
            continue
        matches = quote_pattern.findall(line)
        command_like = bool(re.search(r"(?i)\b(?:python|py|powershell|pwsh|bash|sh|call|-file)\b|(?:^|\s)[.&]\s+", line))
        if command_like and not matches and ("$" in line or "%" in line or "$(" in line):
            edges.append(_edge(path, language, parser, _source_location(path, number), "LAUNCHER_DYNAMIC_TARGET", "LAUNCH_CLOSURE", stripped, None, "UNRESOLVED", "INCLUDE", [f"LAUNCH:{path}:{number}"]))
        for literal in matches:
            candidate = _resolve_path_edge(path, number, literal, "LAUNCHER_TARGET", "LAUNCH_CLOSURE", parser, language, path_set)
            if candidate:
                edges.append(candidate)
    return edges


def _walk_config_values(value: Any, location: str = "$") -> Iterable[tuple[str, str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_config_values(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_config_values(child, f"{location}[{index}]")
    elif isinstance(value, str):
        yield location, location.rsplit(".", 1)[-1].casefold(), value


def _parse_simple_config(text: str, path: str, suffix: str) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";", "[")):
            continue
        separator = ":" if suffix in {".yaml", ".yml"} else "="
        if separator not in stripped:
            raise BoundaryError("CONFIG_PARSE_ERROR", f"{path}:{number}")
        key, value = stripped.split(separator, 1)
        value = value.strip().strip("\"'")
        results.append((f"{path}:{number}", key.strip().casefold(), value))
    return results


def _config_edges(root: Path, path: str, path_set: set[str], module_to_path: Mapping[str, str], configuration: Mapping[str, Any]) -> list[dict[str, Any]]:
    text = _read_text(root.joinpath(*path.split("/")), path)
    suffix = PurePosixPath(path).suffix.casefold()
    if suffix == ".json":
        try:
            values = list(_walk_config_values(json.loads(text)))
        except json.JSONDecodeError as exc:
            raise BoundaryError("CONFIG_PARSE_ERROR", f"{path}:{exc.lineno}") from exc
        parser = JSON_CONFIG_PARSER
    else:
        values = _parse_simple_config(text, path, suffix)
        parser = YAML_CONFIG_PARSER if suffix in {".yaml", ".yml"} else TOML_CONFIG_PARSER if suffix == ".toml" else INI_CONFIG_PARSER
    edges: list[dict[str, Any]] = []
    for location, key, value in values:
        if any(token in key for token in ("module", "plugin", "handler", "factory")):
            edge = _resolve_module_edge(path, int(location.rsplit(":", 1)[-1]) if ":" in location and location.rsplit(":", 1)[-1].isdigit() else 1, value, "CONFIG_MODULE_REFERENCE", parser, module_to_path, configuration)
            edge["source_location"] = location
            edges.append(edge)
        elif any(token in key for token in ("path", "file", "config", "asset", "template", "fixture", "replay", "scenario", "script", "target")) or _looks_like_path(value):
            edge = _resolve_path_edge(path, location, value, "CONFIG_FILE_REFERENCE", "RUNTIME_CLOSURE", parser, "configuration", path_set)
            if edge:
                edges.append(edge)
    return edges


def _class_for_path(path: str, include_entries: Mapping[str, Mapping[str, Any]], test_metadata: Mapping[str, Mapping[str, Any]]) -> str:
    if path in include_entries:
        return include_entries[path]["class"]
    if path in test_metadata and test_metadata[path]["is_test"]:
        return "production-test"
    suffix = PurePosixPath(path).suffix.casefold()
    if suffix == ".py":
        return "runtime-support-module"
    if suffix in LAUNCH_SUFFIXES:
        return "launch-and-startup-script"
    if suffix in CONFIG_SUFFIXES:
        return "production-configuration"
    if path.startswith("Architecture/"):
        return "governance-only"
    if path.startswith("Backups/") or path.startswith("EntryAgent_laptop_backup/"):
        return "backup"
    if "__pycache__" in path.split("/") or suffix == ".pyc" or path.startswith(".pytest_cache/"):
        return "cache"
    if suffix == ".log":
        return "log"
    if suffix == ".db":
        return "runtime-database"
    return "unknown"


def _matching_exclusion(path: str, exclusions: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    matches = [entry for entry in exclusions if _exclusion_matches_local(path, entry)]
    require(len(matches) <= 1, "MULTIPLE_EXCLUSIONS", path)
    return matches[0] if matches else None


def _exclusion_matches_local(path: str, entry: Mapping[str, Any]) -> bool:
    target, match_type = entry["path_or_pattern"], entry["match_type"]
    if match_type == "exact":
        return path == target
    if match_type == "prefix":
        return path.startswith(target.rstrip("/") + "/")
    if match_type == "suffix":
        return path.endswith(target)
    if match_type == "segment":
        return target in path.split("/")
    if match_type == "glob":
        import fnmatch
        return fnmatch.fnmatchcase(path, target)
    return False


def derive_repository_selection(
    root: Path,
    include_registry: Mapping[str, Any],
    exclusion_registry: Mapping[str, Any],
    rule_registry: Mapping[str, Any],
    configuration: Mapping[str, Any],
    *,
    capture_mode: bool = False,
    accepted_review_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    assert_synthetic_root(root)
    rules = validate_rule_registry(rule_registry)
    includes, exclusions = validate_registries(
        include_registry,
        exclusion_registry,
        rules,
        capture_mode=capture_mode,
        accepted_review_binding=accepted_review_binding,
    )
    inventory = enumerate_inventory(root)
    paths = [item["canonical_path"] for item in inventory["artifacts"]]
    path_set = set(paths)
    repository_includes = {key: entry for key, entry in includes.items() if entry["path_kind"] == "repository-relative"}
    missing = sorted(path for path in repository_includes if path not in path_set)
    require(not missing, "MISSING_REQUIRED_PATH", repr(missing))
    module_to_path = _module_map(paths)
    edges_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    test_metadata: dict[str, dict[str, Any]] = {}
    for path in paths:
        suffix = PurePosixPath(path).suffix.casefold()
        if suffix == ".py":
            edges, metadata = _python_edges(root, path, path_set, module_to_path, configuration)
            edges_by_source[path].extend(edges)
            test_metadata[path] = metadata
        elif suffix in LAUNCH_SUFFIXES:
            edges_by_source[path].extend(_launch_edges(root, path, path_set))
        elif suffix in CONFIG_SUFFIXES:
            edges_by_source[path].extend(_config_edges(root, path, path_set, module_to_path, configuration))

    fixture_owners: dict[str, list[str]] = defaultdict(list)
    for owner_path, metadata in test_metadata.items():
        for fixture_name in metadata["fixture_names"]:
            fixture_owners[fixture_name].append(owner_path)
    for source_path, edges in edges_by_source.items():
        for edge in edges:
            if edge["resolution_status"] != "DECLARED_FIXTURE_REFERENCE":
                continue
            owners = sorted(fixture_owners.get(edge["literal_or_declared_target"], []))
            if len(owners) == 1:
                edge["canonical_resolved_target"] = owners[0]
                edge["resolution_status"] = "RESOLVED_FIXTURE_PROVIDER"
                edge["evidence"] = [*edge["evidence"], f"FIXTURE_PROVIDER:{owners[0]}"]
            elif not owners:
                edge["canonical_resolved_target"] = None
                edge["resolution_status"] = "UNRESOLVED"
            else:
                raise BoundaryError("AMBIGUOUS_FIXTURE_PROVIDER", f"{source_path}:{edge['literal_or_declared_target']}:{owners}")

    selected = set(repository_includes)
    selected_reason: dict[str, tuple[str, list[str]]] = {
        path: (entry["selection_rule_id"], list(entry["evidence_references"])) for path, entry in repository_includes.items()
    }
    changed = True
    while changed:
        changed = False
        for source in tuple(selected):
            for edge in edges_by_source.get(source, []):
                if edge["resolution_status"] == "UNRESOLVED":
                    raise BoundaryError("UNRESOLVED_DEPENDENCY", f"{edge['source_location']}:{edge['literal_or_declared_target']}")
                target = edge["canonical_resolved_target"]
                if target in path_set and target not in selected:
                    selected.add(target)
                    selected_reason[target] = (edge["rule_id"], list(edge["evidence"]))
                    changed = True
        for path, metadata in test_metadata.items():
            if path in selected or not metadata["is_test"]:
                continue
            category = next((item for item in configuration["test_discovery_policy"]["governed_categories"] if item["path"] == path), None)
            references_selected = any(edge["canonical_resolved_target"] in selected for edge in edges_by_source.get(path, []))
            if references_selected or category:
                selected.add(path)
                evidence = [f"TEST_RELATION:{path}"] if references_selected else list(category["evidence"])
                selected_reason[path] = ("PRODUCTION_TEST_CLOSURE", evidence)
                changed = True

    external_keys: list[str] = []
    for key, entry in includes.items():
        if entry["path_kind"] == "external-root-relative":
            external_keys.append(key)
    for source in selected:
        for edge in edges_by_source.get(source, []):
            if edge["resolution_status"] in {"RESOLVED_EXTERNAL", "RESOLVED_ENVIRONMENT"} and edge["canonical_resolved_target"]:
                external_keys.append(edge["canonical_resolved_target"])
    external_keys = sorted(set(external_keys), key=lambda item: item.encode("utf-8"))

    dispositions: list[dict[str, Any]] = []
    obligations: list[dict[str, Any]] = []
    exclusion_registry_identity = semantic_identity(exclusion_registry)
    for path in paths:
        path_class = _class_for_path(path, repository_includes, test_metadata)
        exclusion = _matching_exclusion(path, exclusions)
        if path in selected:
            require(exclusion is None, "DEPENDENCY_TO_EXCLUSION_CONFLICT", path)
            entry = repository_includes.get(path)
            rule_id, evidence = selected_reason[path]
            authority = entry["authority_status"] if entry else "DERIVED_PRODUCTION_RELEVANCE"
            rationale = entry["rationale"] if entry else "Derived through the fixed-point dependency or production-test closure from a governed selected source."
            capture_form = entry["required_capture_form"] if entry else "RAW_AND_GIT_OBJECT"
            existence = entry["expected_existence_state"] if entry else "MUST_EXIST_AT_FREEZE"
            disposition = "INCLUDE"
            exclusion_identity = None
            separate_identity = None
            binding_ids: list[str] = []
        elif exclusion:
            rule = rules[exclusion["exclusion_rule_id"]]
            disposition = rule["disposition"]
            require(disposition in {"EXCLUDE", "SEPARATE_AND_BIND"}, "NONTERMINAL_EXCLUSION_RULE", exclusion["entry_id"])
            rule_id = exclusion["exclusion_rule_id"]
            evidence = list(exclusion["evidence"])
            authority = exclusion["authority"]
            rationale = exclusion["rationale"]
            existence = "MAY_EXIST_CLASSIFIED"
            exclusion_identity = semantic_identity(exclusion) if disposition == "EXCLUDE" else None
            separate_identity = exclusion_registry_identity if disposition == "SEPARATE_AND_BIND" else None
            capture_form = "NO_CONTENT_EXCLUSION" if disposition == "EXCLUDE" else "SEPARATE_CONTENT_BINDING"
            binding_ids = []
            if disposition == "SEPARATE_AND_BIND":
                oid = "BIND-" + semantic_identity({"path": path, "rule": rule_id})[:20]
                binding_ids = [oid]
                obligations.append({
                    "obligation_id": oid,
                    "artifact_key": path,
                    "canonical_path": path,
                    "role": path_class,
                    "authority": authority,
                    "required_fields": ["canonical_path", "role", "byte_size", "sha256", "git_blob", "authority_status", "immutability_status", "required_for_recovery", "source_attempt", "capture_pass", "semantic_purpose"],
                    "evidence": evidence,
                })
        elif path in test_metadata and test_metadata[path]["is_test"]:
            raise BoundaryError("UNKNOWN_TEST_DISPOSITION", path)
        else:
            raise BoundaryError("UNKNOWN_FILE_CLASS", f"{path}:{path_class}")
        dispositions.append({
            "artifact_key": path,
            "canonical_path": path,
            "path_kind": "repository-relative",
            "artifact_class": path_class,
            "terminal_disposition": disposition,
            "governing_rule": rule_id,
            "authority": authority,
            "rationale": rationale,
            "evidence": evidence,
            "capture_form": capture_form,
            "existence_state": existence,
            "external_root_id": None,
            "binding_obligation_ids": binding_ids,
            "exclusion_review_identity": exclusion_identity,
            "separate_evidence_registry_identity": separate_identity,
        })

    for key in external_keys:
        if "::" not in key:
            root_id, rel = "environment", key
        else:
            root_id, rel = key.split("::", 1)
        entry = includes.get(key)
        if entry:
            disposition = "INCLUDE"
            rule_id = entry["selection_rule_id"]
            authority = entry["authority_status"]
            rationale = entry["rationale"]
            evidence = list(entry["evidence_references"])
            capture_form = entry["required_capture_form"]
            existence = entry["expected_existence_state"]
            binding_ids = []
            separate_identity = None
        else:
            disposition = "SEPARATE_AND_BIND"
            rule_id = "EXTERNAL_DEPENDENCY_BIND"
            authority = "FROZEN_EXTERNAL_DEPENDENCY"
            rationale = "External runtime or environment dependency reached through a selected dependency edge and requiring a complete separate binding."
            evidence = ["DEPENDENCY_EDGE:external"]
            capture_form = "SEPARATE_CONTENT_BINDING"
            existence = "MUST_EXIST_AT_FREEZE"
            oid = "BIND-" + semantic_identity({"path": key, "rule": rule_id})[:20]
            binding_ids = [oid]
            separate_identity = semantic_identity(configuration["discovery_policy"]["governed_external_dependencies"])
            obligations.append({
                "obligation_id": oid,
                "artifact_key": key,
                "canonical_path": rel,
                "role": "external-runtime-dependency",
                "authority": authority,
                "required_fields": ["canonical_path", "role", "byte_size", "sha256", "git_blob", "authority_status", "immutability_status", "required_for_recovery", "source_attempt", "capture_pass", "semantic_purpose"],
                "evidence": evidence,
            })
        dispositions.append({
            "artifact_key": key,
            "canonical_path": rel,
            "path_kind": "external-root-relative",
            "artifact_class": entry["class"] if entry else "external-runtime-dependency",
            "terminal_disposition": disposition,
            "governing_rule": rule_id,
            "authority": authority,
            "rationale": rationale,
            "evidence": evidence,
            "capture_form": capture_form,
            "existence_state": existence,
            "external_root_id": root_id,
            "binding_obligation_ids": binding_ids,
            "exclusion_review_identity": None,
            "separate_evidence_registry_identity": separate_identity,
        })

    universe = sorted([*paths, *external_keys], key=lambda item: item.encode("utf-8"))
    dispositions.sort(key=lambda item: item["artifact_key"].encode("utf-8"))
    obligations.sort(key=lambda item: item["obligation_id"])
    sets = validate_terminal_dispositions(universe, dispositions, obligations)
    ensure_all_questioned_tests(sets["INCLUDE"])
    relevant_edges = sorted(
        [edge for source in selected for edge in edges_by_source.get(source, [])],
        key=lambda item: (item["source_path"], item["source_location"], item["edge_type"], item["literal_or_declared_target"]),
    )
    return {
        "schema_version": "2.0.0-DRAFT",
        "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
        "draft_selection_version": DRAFT_SELECTION_VERSION,
        "enumeration_universe": universe,
        "dependency_edges": relevant_edges,
        "terminal_dispositions": dispositions,
        "binding_obligations": obligations,
        "included_paths": sets["INCLUDE"],
        "excluded_paths": sets["EXCLUDE"],
        "separately_bound_paths": sets["SEPARATE_AND_BIND"],
        "included_set_sha256": semantic_identity(sets["INCLUDE"]),
        "excluded_set_sha256": semantic_identity(sets["EXCLUDE"]),
        "separately_bound_set_sha256": semantic_identity(sets["SEPARATE_AND_BIND"]),
        "disposition_set_sha256": semantic_identity(dispositions),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--include-registry", type=Path, required=True)
    parser.add_argument("--exclusion-registry", type=Path, required=True)
    parser.add_argument("--rule-registry", type=Path, required=True)
    parser.add_argument("--configuration", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = derive_repository_selection(
            args.fixture_root,
            json.loads(args.include_registry.read_text(encoding="utf-8")),
            json.loads(args.exclusion_registry.read_text(encoding="utf-8")),
            json.loads(args.rule_registry.read_text(encoding="utf-8")),
            json.loads(args.configuration.read_text(encoding="utf-8")),
        )
    except (BoundaryError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(stored_json_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
