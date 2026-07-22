#!/usr/bin/env python3
"""Parser-backed draft selection engine for synthetic specification fixtures.

The engine refuses production roots through ``inventory_generator_DRAFT``.  It
is specification evidence, not the future operational capture script.
"""

from __future__ import annotations

import argparse
import ast
import configparser
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

try:
    import yaml
except ImportError:  # fail closed when YAML is governed but the pinned parser is absent
    yaml = None

from boundary_verifier_DRAFT import (
    QUESTIONED_TESTS,
    BoundaryError,
    artifact_key,
    canonical_repository_path,
    ensure_all_questioned_tests,
    is_test_candidate,
    require,
    semantic_identity,
    strict_json_loads,
    stored_json_bytes,
    validate_registries,
    validate_boundary_configuration,
    validate_questioned_test_authority,
    validate_rule_registry,
    validate_terminal_dispositions,
    validate_terminal_result,
)
from inventory_generator_DRAFT import assert_governed_read_only_root, assert_synthetic_root, enumerate_inventory, extended_length_path


DRAFT_SELECTION_VERSION = "4.0.0-DRAFT"
PYTHON_PARSER = "python-ast-closure/4.0.0-DRAFT"
POWERSHELL_PARSER = "System.Management.Automation.Language.Parser/5.1"
CMD_PARSER = "randle-cmd-bounded-grammar/1.0.0-DRAFT"
SHELL_PARSER = "randle-posix-shell-bounded-grammar/1.0.0-DRAFT"
JSON_CONFIG_PARSER = "python-json/3.12"
YAML_CONFIG_PARSER = "PyYAML-SafeLoader/6.0.2"
TOML_CONFIG_PARSER = "python-tomllib/3.12"
INI_CONFIG_PARSER = "python-configparser/3.12"


def _git_blob_identity(data: bytes, object_format: str) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    if object_format == "sha1":
        return hashlib.sha1(header + data).hexdigest()
    if object_format == "sha256":
        return hashlib.sha256(header + data).hexdigest()
    raise BoundaryError("UNSUPPORTED_GIT_OBJECT_FORMAT", object_format)

DYNAMIC_IMPORT_NAMES = {"__import__", "importlib.import_module"}
SUBPROCESS_NAMES = {"subprocess.call", "subprocess.check_call", "subprocess.check_output", "subprocess.Popen", "subprocess.run", "os.system"}
FILE_CALL_NAMES = {"open", "Path", "pathlib.Path", "io.open"}
STATIC_CALLS = {
    "render_template", "flask.render_template", "send_static_file", "pkgutil.get_data",
    "pkg_resources.resource_filename", "pkg_resources.resource_stream",
    "importlib.resources.files", "importlib.resources.open_binary", "importlib.resources.open_text",
    "importlib.resources.read_binary", "importlib.resources.read_text",
    "load_resource", "load_template", "load_asset",
}
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
    # ``from package import symbol`` always executes the package/module named
    # by ``node.module``.  The imported name may be a symbol rather than a
    # submodule and therefore must not be fabricated as a module dependency.
    return [prefix] if prefix else []


def _literal_strings(node: ast.AST, constants: Mapping[str, list[str]] | None = None) -> list[str]:
    constants = constants or {}
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name):
        return list(constants.get(node.id, ()))
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [value for item in node.elts for value in _literal_strings(item, constants)]
    if isinstance(node, ast.JoinedStr):
        pieces: list[list[str]] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                pieces.append([value.value])
            elif isinstance(value, ast.FormattedValue):
                resolved = _literal_strings(value.value, constants)
                if not resolved:
                    return []
                pieces.append(resolved)
        combined = [""]
        for choices in pieces:
            combined = [prefix + choice for prefix in combined for choice in choices]
        return combined
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal_strings(node.left, constants), _literal_strings(node.right, constants)
        return [a + b for a in left for b in right]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left, right = _literal_strings(node.left, constants), _literal_strings(node.right, constants)
        return [a.rstrip("/\\") + "/" + b.lstrip("/\\") for a in left for b in right]
    if isinstance(node, ast.Call) and _call_name(node.func) in {"os.path.join", "posixpath.join", "ntpath.join", "Path", "pathlib.Path"}:
        parts = [_literal_strings(arg, constants) for arg in node.args]
        if parts and all(part for part in parts):
            values = [""]
            for choices in parts:
                joined: list[str] = []
                for prefix in values:
                    for choice in choices:
                        joined.append((prefix.rstrip("/\\") + "/" + choice.lstrip("/\\")).strip("/"))
                values = joined
            return values
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
        base = _literal_strings(node.func.value, constants)
        parts = [base, *(_literal_strings(arg, constants) for arg in node.args)]
        if parts and all(parts):
            values = [""]
            for choices in parts:
                values = [(prefix.rstrip("/\\") + "/" + choice.lstrip("/\\")).strip("/") for prefix in values for choice in choices]
            return values
    return []


def _constant_bindings(tree: ast.Module) -> dict[str, list[str]]:
    constants: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = _literal_strings(node.value, constants)
            for target in targets:
                if isinstance(target, ast.Name):
                    if value:
                        constants[target.id] = value
                    else:
                        constants.pop(target.id, None)
    return constants


def _call_path_literals(node: ast.Call, constants: Mapping[str, list[str]]) -> list[str]:
    values: list[str] = []
    if node.args:
        values.extend(_literal_strings(node.args[0], constants))
    for keyword in node.keywords:
        if keyword.arg in {"file", "filename", "path", "target", "executable", "cwd"}:
            values.extend(_literal_strings(keyword.value, constants))
    return list(dict.fromkeys(values))


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
    parser_name, _, parser_version = parser.partition("/")
    return {
        "source_path": source,
        "source_language_or_format": language,
        "parser": parser,
        "parser_name": parser_name,
        "parser_version": parser_version or "GOVERNED_EMBEDDED_VERSION",
        "source_location": location,
        "edge_type": edge_type,
        "rule_id": rule_id,
        "literal_or_declared_target": declared,
        "target_expression": declared,
        "canonical_resolved_target": target,
        "resolution_status": resolution,
        "evidence": list(evidence),
        "terminal_disposition": disposition,
        "disposition_obligation": {
            "INCLUDE": "CAPTURE_RAW_AND_GIT_IDENTITIES",
            "EXCLUDE": "PRESERVE_EXCLUSION_RECORD",
            "SEPARATE_AND_BIND": "BIND_EXTERNAL_EVIDENCE",
        }[disposition],
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


def _dynamic_declaration(configuration: Mapping[str, Any], source: str, call: str, line: int, column: int) -> Mapping[str, Any] | None:
    matches = [
        item
        for item in configuration["discovery_policy"]["governed_dynamic_dependencies"]
        if item["source_path"] == source and item["call_name"] == call and item["line"] == line and item["column"] == column
    ]
    require(len(matches) <= 1, "AMBIGUOUS_DYNAMIC_DECLARATION", f"{source}:{line}:{column}:{call}")
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
    if not isinstance(literal, str) or not literal.strip():
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
    constants = _constant_bindings(tree)
    defined_symbols = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
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
            bases = _resolve_import_names(path, node)
            for module in bases:
                edges.append(_resolve_module_edge(path, node.lineno, module, "PYTHON_RELATIVE_IMPORT" if node.level else "PYTHON_ABSOLUTE_IMPORT", PYTHON_PARSER, module_to_path, configuration))
                for alias in node.names:
                    candidate = f"{module}.{alias.name}" if alias.name != "*" else ""
                    if candidate in module_to_path:
                        edges.append(_resolve_module_edge(path, node.lineno, candidate, "PYTHON_IMPORTED_SUBMODULE", PYTHON_PARSER, module_to_path, configuration))
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
                        for raw_names in _literal_strings(item.args[0], constants):
                            parameter_names.update(name.strip() for name in raw_names.split(",") if name.strip())
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "pytest_plugins" for target in targets):
                value = node.value
                for module in _literal_strings(value, constants):
                    edges.append(_resolve_module_edge(path, node.lineno, module, "PYTEST_PLUGIN", PYTHON_PARSER, module_to_path, configuration))
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func) or ""
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"read_text", "read_bytes", "write_text", "write_bytes", "open"}:
            literals = _literal_strings(node.func.value, constants)
            if not literals:
                edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "PATH_RESOURCE_TARGET", "RUNTIME_CLOSURE", node.func.attr, None, "UNRESOLVED", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
            for literal in literals:
                candidate = _resolve_path_edge(path, node.lineno, literal, "PATH_RESOURCE_TARGET", "RUNTIME_CLOSURE", PYTHON_PARSER, "python", path_set)
                if candidate:
                    edges.append(candidate)
            continue
        if name in DYNAMIC_IMPORT_NAMES:
            literals = _literal_strings(node.args[0], constants) if node.args else []
            if literals:
                for module in literals:
                    edge = _resolve_module_edge(path, node.lineno, module, "PYTHON_DYNAMIC_IMPORT", PYTHON_PARSER, module_to_path, configuration)
                    if edge["resolution_status"] == "UNRESOLVED":
                        edge["rule_id"] = "DYNAMIC_DECLARATION_REQUIRED"
                    edges.append(edge)
            else:
                declaration = _dynamic_declaration(configuration, path, name, node.lineno, node.col_offset)
                if declaration:
                    edge = _resolve_module_edge(path, node.lineno, declaration["target_module"], "GOVERNED_DYNAMIC_IMPORT", PYTHON_PARSER, module_to_path, configuration)
                    edge["evidence"] = declaration["evidence"]
                    edges.append(edge)
                else:
                    edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "PYTHON_DYNAMIC_IMPORT", "DYNAMIC_DECLARATION_REQUIRED", name, None, "UNRESOLVED", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
        elif name in SUBPROCESS_NAMES:
            literals = _call_path_literals(node, constants)
            if len(literals) == 1 and any(character.isspace() for character in literals[0]):
                try:
                    literals = shlex.split(literals[0], posix=os.name != "nt")
                except ValueError:
                    literals = []
            if literals and PurePosixPath(literals[0].replace("\\", "/")).name.casefold() in {"python", "python.exe", "py", "py.exe", "powershell", "powershell.exe", "pwsh", "bash", "sh"}:
                literals = literals[1:2]
            elif len(literals) > 1:
                literals = literals[:1]
            if not literals:
                edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "SUBPROCESS_TARGET", "RUNTIME_CLOSURE", name, None, "UNRESOLVED", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
            for literal in literals:
                candidate = _resolve_path_edge(path, node.lineno, literal, "SUBPROCESS_TARGET", "RUNTIME_CLOSURE", PYTHON_PARSER, "python", path_set)
                if candidate:
                    edges.append(candidate)
        elif name in FILE_CALL_NAMES and (node.args or node.keywords):
            literals = _call_path_literals(node, constants)
            if not literals:
                edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "FILE_OPEN_TARGET", "RUNTIME_CLOSURE", name, None, "UNRESOLVED", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
            for literal in literals:
                candidate = _resolve_path_edge(path, node.lineno, literal, "FILE_OPEN_TARGET", "RUNTIME_CLOSURE", PYTHON_PARSER, "python", path_set)
                if candidate:
                    edges.append(candidate)
        elif name in STATIC_CALLS | REPLAY_CALLS:
            literals = [value for arg in node.args for value in _literal_strings(arg, constants)]
            if not literals:
                edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "STATIC_OR_REPLAY_TARGET", "TEST_SUPPORT_CLOSURE" if name in REPLAY_CALLS else "RUNTIME_CLOSURE", name, None, "UNRESOLVED", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
            for literal in literals:
                candidate = _resolve_path_edge(path, node.lineno, literal, "REPLAY_OR_SCENARIO_TARGET" if name in REPLAY_CALLS else "STATIC_ASSET_TARGET", "TEST_SUPPORT_CLOSURE" if name in REPLAY_CALLS else "RUNTIME_CLOSURE", PYTHON_PARSER, "python", path_set)
                if candidate:
                    edges.append(candidate)
        elif name in MODULE_REGISTRATION_CALLS:
            literals = [value for arg in node.args for value in _literal_strings(arg, constants)]
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
            handler_nodes = list(node.args[2:3] if name.endswith("add_url_rule") else node.args[1:])
            handler_literals = [value for arg in handler_nodes for value in _literal_strings(arg, constants)]
            handler_literals = [value for value in handler_literals if not value.startswith("/")]
            if handler_literals:
                for handler in handler_literals:
                    edges.append(_resolve_module_edge(path, node.lineno, handler, "ROUTE_TARGET", PYTHON_PARSER, module_to_path, configuration))
            else:
                named_handlers = [item.id for item in handler_nodes if isinstance(item, ast.Name)]
                if named_handlers:
                    for handler in named_handlers:
                        edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "ROUTE_HANDLER_TARGET", "RUNTIME_CLOSURE", handler, path if handler in defined_symbols else None, "RESOLVED_SELF" if handler in defined_symbols else "UNRESOLVED", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
                else:
                    edges.append(_edge(path, "python", PYTHON_PARSER, _source_location(path, node.lineno), "ROUTE_REGISTRATION", "RUNTIME_CLOSURE", name, path, "RESOLVED_SELF", "INCLUDE", [f"AST:{path}:{node.lineno}"]))
        elif name.endswith("usefixtures"):
            used_fixtures.update(value for arg in node.args for value in _literal_strings(arg, constants))
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


def _powershell_commands(source_path: Path, governed_path: str) -> list[dict[str, Any]]:
    script = r'''$tokens=$null;$errors=$null;$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:RANDLE_PS_PARSE_PATH,[ref]$tokens,[ref]$errors);if($errors.Count){$errors|ForEach-Object{$_.ToString()}|Write-Error;exit 3};@($ast.FindAll({param($n)$n -is [System.Management.Automation.Language.CommandAst]},$true)|ForEach-Object{[pscustomobject]@{line=$_.Extent.StartLineNumber;text=$_.Extent.Text;elements=@($_.CommandElements|ForEach-Object{$_.Extent.Text})}})|ConvertTo-Json -Compress -Depth 6'''
    env = os.environ.copy()
    env["RANDLE_PS_PARSE_PATH"] = extended_length_path(source_path)
    process = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, env=env, check=False)
    require(process.returncode == 0, "SOURCE_PARSE_ERROR", f"{governed_path}:{process.stderr.strip()}")
    if not process.stdout.strip():
        return []
    parsed = json.loads(process.stdout)
    return parsed if isinstance(parsed, list) else [parsed]


def _lex_launch_lines(text: str, governed_path: str, *, posix: bool) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.casefold().startswith(("#", "rem ", "::")):
            continue
        unsupported = r"\$\(|`|\|\||&&|(?<!\|)\|(?!\|)|[<>]|\b(?:if|for|while|until|case|function|goto)\b"
        require(re.search(unsupported, stripped, flags=re.IGNORECASE) is None, "UNSUPPORTED_LAUNCHER_GRAMMAR", f"{governed_path}:{number}")
        try:
            elements = shlex.split(line, posix=posix)
        except ValueError as exc:
            raise BoundaryError("SOURCE_PARSE_ERROR", f"{governed_path}:{number}:{exc}") from exc
        records.append({"line": number, "text": stripped, "elements": elements})
    return records


def _launch_edges(root: Path, path: str, path_set: set[str]) -> list[dict[str, Any]]:
    source_path = root.joinpath(*path.split("/"))
    text = _read_text(source_path, path)
    suffix = PurePosixPath(path).suffix.casefold()
    if suffix == ".ps1":
        parser, language, records = POWERSHELL_PARSER, "powershell", _powershell_commands(source_path, path)
    elif suffix in {".bat", ".cmd"}:
        parser, language, records = CMD_PARSER, "batch", _lex_launch_lines(text, path, posix=False)
    else:
        parser, language, records = SHELL_PARSER, "shell", _lex_launch_lines(text, path, posix=True)
    edges: list[dict[str, Any]] = []
    command_names = {"python", "python.exe", "py", "py.exe", "powershell", "powershell.exe", "pwsh", "bash", "sh", "call", ".", "&"}
    powershell_path_commands = {"start-process", "import-module", "get-content", "set-content", "test-path", "invoke-expression"}
    for record in records:
        elements = [str(item).strip("\"'") for item in record["elements"]]
        command_text = str(record.get("text", "")).lstrip()
        invocation_operator = bool(re.match(r"^[&.]\s+", command_text))
        command_like = invocation_operator or any(item.casefold() in command_names or item.casefold() == "-file" for item in elements)
        candidates = [item for item in elements if _looks_like_path(item)]
        if elements:
            command = elements[0].casefold()
            if command in {".", "&", "call"} and len(elements) > 1:
                candidates.append(elements[1])
            elif command in powershell_path_commands:
                parameter_names = {"-filepath", "-literalpath", "-path", "-name"}
                selected = None
                for index, item in enumerate(elements[:-1]):
                    if item.casefold() in parameter_names:
                        selected = elements[index + 1]
                        break
                if selected is None and len(elements) > 1:
                    selected = elements[1]
                if selected:
                    candidates.append(selected)
            elif command in command_names:
                offset = 2 if len(elements) > 2 and elements[1].casefold() in {"-file", "-command"} else 1
                if len(elements) > offset:
                    candidates.append(elements[offset])
        candidates = list(dict.fromkeys(item for item in candidates if item and not item.startswith("-")))
        dynamic = [item for item in elements if re.search(r"\$\w+|\$\(|%[^%]+%|![^!]+!", item)]
        if command_like and dynamic:
            edges.append(_edge(path, language, parser, _source_location(path, record["line"]), "LAUNCHER_DYNAMIC_TARGET", "LAUNCH_CLOSURE", " ".join(dynamic), None, "UNRESOLVED", "INCLUDE", [f"PARSER:{parser}:{path}:{record['line']}"]))
        for literal in candidates:
            if literal in dynamic:
                continue
            candidate = _resolve_path_edge(path, record["line"], literal, "LAUNCHER_TARGET", "LAUNCH_CLOSURE", parser, language, path_set)
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


def _config_edges(root: Path, path: str, path_set: set[str], module_to_path: Mapping[str, str], configuration: Mapping[str, Any]) -> list[dict[str, Any]]:
    text = _read_text(root.joinpath(*path.split("/")), path)
    suffix = PurePosixPath(path).suffix.casefold()
    if suffix == ".json":
        try:
            values = list(_walk_config_values(strict_json_loads(text.encode("utf-8"))))
        except BoundaryError as exc:
            raise BoundaryError("CONFIG_PARSE_ERROR", f"{path}:{exc}") from exc
        parser = JSON_CONFIG_PARSER
    elif suffix in {".yaml", ".yml"}:
        require(yaml is not None, "CONFIG_PARSER_UNAVAILABLE", f"{path}:PyYAML==6.0.2")
        try:
            parsed_yaml = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise BoundaryError("CONFIG_PARSE_ERROR", f"{path}:{exc}") from exc
        values = list(_walk_config_values(parsed_yaml))
        parser = YAML_CONFIG_PARSER
    elif suffix == ".toml":
        try:
            values = list(_walk_config_values(tomllib.loads(text)))
        except tomllib.TOMLDecodeError as exc:
            raise BoundaryError("CONFIG_PARSE_ERROR", f"{path}:{exc}") from exc
        parser = TOML_CONFIG_PARSER
    else:
        parser_config = configparser.ConfigParser(interpolation=None, strict=True)
        try:
            parser_config.read_string(text)
        except configparser.Error as exc:
            raise BoundaryError("CONFIG_PARSE_ERROR", f"{path}:{exc}") from exc
        values = []
        for section in parser_config.sections():
            for key, value in parser_config.items(section):
                values.append((f"{path}:[{section}].{key}", key.casefold(), value))
        parser = INI_CONFIG_PARSER
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
    authority_universe: Mapping[str, Any],
    capture_mode: bool = False,
    accepted_review_binding: Mapping[str, Any] | None = None,
    registry_bindings: Mapping[str, str] | None = None,
    governed_repository_commit: str | None = None,
) -> dict[str, Any]:
    fixture_mode = (root / ".boundary_fixture_root").is_file()
    if fixture_mode:
        assert_synthetic_root(root)
    else:
        require(governed_repository_commit is not None, "GOVERNED_REPOSITORY_COMMIT_REQUIRED", str(root))
        assert_governed_read_only_root(root, governed_repository_commit)
    validate_boundary_configuration(configuration, authority_universe)
    rules = validate_rule_registry(rule_registry)
    includes, exclusions = validate_registries(
        include_registry,
        exclusion_registry,
        rules,
        authority_universe=authority_universe,
        capture_mode=capture_mode,
        accepted_review_binding=accepted_review_binding,
    )
    inventory = enumerate_inventory(root, require_fixture_marker=fixture_mode)
    require(isinstance(registry_bindings, Mapping), "MISSING_REGISTRY_BLOB_AUTHORITY", "selection")
    required_registry_bindings = {
        "include_registry_blob",
        "exclusion_registry_blob",
        "selection_rule_registry_blob",
        "boundary_configuration_blob",
    }
    require(set(registry_bindings) == required_registry_bindings, "REGISTRY_BLOB_AUTHORITY_SET", repr(sorted(set(registry_bindings) ^ required_registry_bindings)))
    for binding_name, binding_value in registry_bindings.items():
        require(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", binding_value or "") is not None, "INVALID_REGISTRY_BLOB", binding_name)
    object_formats = {"sha1" if len(value) == 40 else "sha256" for value in registry_bindings.values()}
    require(len(object_formats) == 1, "REGISTRY_BLOB_OBJECT_FORMAT", repr(sorted(object_formats)))
    object_format = next(iter(object_formats))
    registry_documents = {
        "include_registry_blob": include_registry,
        "exclusion_registry_blob": exclusion_registry,
        "selection_rule_registry_blob": rule_registry,
        "boundary_configuration_blob": configuration,
    }
    for binding_name, document in registry_documents.items():
        require(_git_blob_identity(stored_json_bytes(document), object_format) == registry_bindings[binding_name], "REGISTRY_DOCUMENT_BLOB_MISMATCH", binding_name)
    paths = [item["canonical_path"] for item in inventory["artifacts"]]
    inventory_by_path = {item["canonical_path"]: item for item in inventory["artifacts"]}
    path_set = set(paths)
    repository_includes = {key: entry for key, entry in includes.items() if entry["path_kind"] == "repository-relative"}
    missing = sorted(path for path in repository_includes if path not in path_set)
    require(not missing, "MISSING_REQUIRED_PATH", repr(missing))
    required_tombstones = sorted(path for path in repository_includes if inventory_by_path[path].get("existence_state") == "TOMBSTONE" and repository_includes[path]["expected_existence_state"] == "MUST_EXIST_AT_FREEZE")
    require(not required_tombstones, "REQUIRED_PATH_DELETED", repr(required_tombstones))
    validate_questioned_test_authority(
        repository_includes,
        exclusions,
        authority_universe,
        frozen_content_identities={path: inventory_by_path[path] for path in QUESTIONED_TESTS if path in inventory_by_path},
    )
    module_to_path = _module_map(paths)
    edges_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    test_metadata: dict[str, dict[str, Any]] = {}
    for path in paths:
        if inventory_by_path[path].get("existence_state") == "TOMBSTONE":
            continue
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
            "rule_registry_blob": registry_bindings["selection_rule_registry_blob"],
            "authority": authority,
            "authority_identity": semantic_identity(authority),
            "rationale": rationale,
            "evidence": evidence,
            "evidence_identities": [semantic_identity(item) for item in evidence],
            "source_identity": semantic_identity({
                "canonical_path": path,
                "existence_state": inventory_by_path[path].get("existence_state", "PRESENT"),
                "raw_sha256": inventory_by_path[path].get("raw_sha256"),
                "parent_git_blob": inventory_by_path[path].get("parent_git_blob"),
                "index_git_blob": inventory_by_path[path].get("index_git_blob"),
                "computed_git_blob": inventory_by_path[path].get("computed_git_blob"),
            }),
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
            "rule_registry_blob": registry_bindings["selection_rule_registry_blob"],
            "authority": authority,
            "authority_identity": semantic_identity(authority),
            "rationale": rationale,
            "evidence": evidence,
            "evidence_identities": [semantic_identity(item) for item in evidence],
            "source_identity": semantic_identity(entry if entry is not None else {"artifact_key": key, "dependency": "external"}),
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
    for mandatory_path in QUESTIONED_TESTS:
        metadata = test_metadata.get(mandatory_path, {})
        require(metadata.get("is_test") is True and bool(metadata.get("test_functions")), "QUESTIONED_TEST_RELEVANCE_SIGNAL", mandatory_path)
    relevant_edges = sorted(
        [edge for source in selected for edge in edges_by_source.get(source, [])],
        key=lambda item: (item["source_path"], item["source_location"], item["edge_type"], item["literal_or_declared_target"]),
    )
    result = {
        "schema_version": "2.0.0-DRAFT",
        "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
        "draft_selection_version": DRAFT_SELECTION_VERSION,
        "inventory": inventory,
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
        "enumeration_universe_sha256": semantic_identity(universe),
        "binding_obligation_set_sha256": semantic_identity(obligations),
        "include_registry_blob": registry_bindings["include_registry_blob"],
        "exclusion_registry_blob": registry_bindings["exclusion_registry_blob"],
        "selection_rule_registry_blob": registry_bindings["selection_rule_registry_blob"],
        "boundary_configuration_blob": registry_bindings["boundary_configuration_blob"],
    }
    validate_terminal_result(result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--include-registry", type=Path, required=True)
    parser.add_argument("--exclusion-registry", type=Path, required=True)
    parser.add_argument("--rule-registry", type=Path, required=True)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--authority-universe", type=Path, required=True)
    parser.add_argument("--registry-bindings", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = derive_repository_selection(
            args.fixture_root,
            json.loads(args.include_registry.read_text(encoding="utf-8")),
            json.loads(args.exclusion_registry.read_text(encoding="utf-8")),
            json.loads(args.rule_registry.read_text(encoding="utf-8")),
            json.loads(args.configuration.read_text(encoding="utf-8")),
            authority_universe=json.loads(args.authority_universe.read_text(encoding="utf-8")),
            registry_bindings=json.loads(args.registry_bindings.read_text(encoding="utf-8")),
        )
    except (BoundaryError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(stored_json_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
