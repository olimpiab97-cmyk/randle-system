#!/usr/bin/env python3
"""R6 immutable authority, environment, access, registry, trace, and trust verifier."""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import importlib.metadata
import json
import marshal
import os
import platform
import re
import subprocess
import sys
import types
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from governed_file_access_DRAFT import read_binary


PACKAGE_RELATIVE = (
    "Architecture/Audits/"
    "2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT"
)
BINDINGS_PATH = f"{PACKAGE_RELATIVE}/r6_authority_bindings_DRAFT.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
_ENVIRONMENT_VERIFIED = False


class R6AuthorityError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


def require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise R6AuthorityError(code, detail)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_identity(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    require_plain_data(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def semantic_identity(value: Any) -> str:
    return sha256(canonical_json_bytes(value))


def _reject_duplicate(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise R6AuthorityError("CANONICAL_DUPLICATE_KEY", key)
        result[key] = value
    return result


def require_plain_data(value: Any, pointer: str = "$") -> None:
    if value is None or type(value) in (str, int, bool):
        return
    if type(value) is dict:
        for key, child in value.items():
            require(type(key) is str, "AUTHORITY_NON_PLAIN_KEY", pointer)
            require_plain_data(child, f"{pointer}.{key}")
        return
    if type(value) is list:
        for index, child in enumerate(value):
            require_plain_data(child, f"{pointer}[{index}]")
        return
    raise R6AuthorityError("AUTHORITY_NON_PLAIN_TYPE", f"{pointer}:{type(value).__name__}")


def _require_nfc(value: Any, pointer: str = "$") -> None:
    if type(value) is str:
        require(unicodedata.normalize("NFC", value) == value, "CANONICAL_NON_NFC", pointer)
    elif type(value) is list:
        for index, child in enumerate(value):
            _require_nfc(child, f"{pointer}[{index}]")
    elif type(value) is dict:
        for key, child in value.items():
            require(unicodedata.normalize("NFC", key) == key, "CANONICAL_NON_NFC", f"{pointer}.<key>")
            _require_nfc(child, f"{pointer}.{key}")


def strict_json_loads(data: bytes) -> Any:
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise R6AuthorityError("CANONICAL_UTF8", str(exc)) from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate,
            parse_float=lambda _: (_ for _ in ()).throw(R6AuthorityError("CANONICAL_FLOAT_FORBIDDEN")),
            parse_constant=lambda _: (_ for _ in ()).throw(R6AuthorityError("CANONICAL_CONSTANT_FORBIDDEN")),
        )
    except R6AuthorityError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise R6AuthorityError("CANONICAL_JSON_INVALID", str(exc)) from exc
    require_plain_data(value)
    _require_nfc(value)
    require(canonical_json_bytes(value) == data, "CANONICAL_BYTES")
    return value


def freeze(value: Any) -> Any:
    require_plain_data(value)
    if type(value) is dict:
        return MappingProxyType({key: freeze(child) for key, child in value.items()})
    if type(value) is list:
        return tuple(freeze(child) for child in value)
    return value


def thaw(value: Any) -> Any:
    if type(value) is MappingProxyType:
        return {key: thaw(child) for key, child in value.items()}
    if type(value) is tuple:
        return [thaw(child) for child in value]
    return value


def parse_timestamp(value: Any, label: str) -> dt.datetime:
    require(type(value) is str, "TIMESTAMP_TYPE", label)
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise R6AuthorityError("TIMESTAMP_INVALID", label) from exc
    require(parsed.tzinfo is not None, "TIMESTAMP_TIMEZONE", label)
    return parsed


def git_object_bytes(repository: Path, authority_ref: str, relative: str) -> bytes:
    process = subprocess.run(
        ["git", "-c", "core.longpaths=true", "-c", f"safe.directory={repository.as_posix()}", "-C", str(repository), "show", f"{authority_ref}:{relative}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    require(process.returncode == 0, "GIT_OBJECT_READ", f"{relative}:{process.stderr.decode('utf-8','replace')}")
    return process.stdout


def resolve_commit(repository: Path, authority_ref: str) -> str:
    process = subprocess.run(
        ["git", "-c", "core.longpaths=true", "-c", f"safe.directory={repository.as_posix()}", "-C", str(repository), "rev-parse", f"{authority_ref}^{{commit}}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    require(process.returncode == 0, "SPECIFICATION_COMMIT_UNRESOLVED")
    value = process.stdout.decode("ascii", "strict").strip()
    require(bool(HEX40.fullmatch(value)), "SPECIFICATION_COMMIT_FORMAT")
    return value


def verify_validator_environment(lock_bytes: bytes) -> Mapping[str, Any]:
    global _ENVIRONMENT_VERIFIED
    lock = strict_json_loads(lock_bytes)
    require(lock["schema_version"] == "6.0.0-DRAFT", "VALIDATOR_LOCK_VERSION")
    require(platform.python_version() == lock["python_version"], "VALIDATOR_PYTHON_VERSION")
    observed: dict[str, str] = {}
    for name, version in lock["required_distributions"].items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise R6AuthorityError("VALIDATOR_DISTRIBUTION_MISSING", name) from exc
        require(actual == version, "VALIDATOR_DISTRIBUTION_VERSION", f"{name}:{actual}!={version}")
        observed[name] = actual
    require(lock["unapproved_parser_dependencies"] == [], "VALIDATOR_UNAPPROVED_DEPENDENCY")
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise R6AuthorityError("VALIDATOR_IMPORT_FAILED", str(exc)) from exc
    checker = FormatChecker()
    supported = set(checker.checkers)
    missing = sorted(set(lock["required_formats"]) - supported)
    require(not missing, "VALIDATOR_FORMAT_CAPABILITY_MISSING", ",".join(missing))
    Draft202012Validator.check_schema({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"})
    _ENVIRONMENT_VERIFIED = True
    receipt = {
        "schema_version": "6.0.0-DRAFT",
        "status": "PASS",
        "python_version": platform.python_version(),
        "distributions": dict(sorted(observed.items())),
        "format_checker": "ENABLED",
        "supported_required_formats": sorted(lock["required_formats"]),
        "normalization": f"unicodedata-{unicodedata.unidata_version}-NFC",
        "lock_identity": sha256(lock_bytes),
    }
    return freeze(receipt)


def validate_json_schema(schema: Any, instance: Any, label: str) -> None:
    require(_ENVIRONMENT_VERIFIED, "VALIDATOR_ENVIRONMENT_NOT_VERIFIED")
    from jsonschema import Draft202012Validator, FormatChecker
    plain_schema = thaw(schema) if type(schema) is MappingProxyType else schema
    plain_instance = thaw(instance) if type(instance) is MappingProxyType else instance
    require_plain_data(plain_schema)
    require_plain_data(plain_instance)
    try:
        Draft202012Validator.check_schema(plain_schema)
        errors = sorted(Draft202012Validator(plain_schema, format_checker=FormatChecker()).iter_errors(plain_instance), key=lambda item: list(item.absolute_path))
    except Exception as exc:
        raise R6AuthorityError("SCHEMA_INVALID", f"{label}:{exc}") from exc
    require(not errors, "SCHEMA_INSTANCE_INVALID", f"{label}:{errors[0].message if errors else ''}")


@dataclass(frozen=True)
class BoundBytes:
    role: str
    path: str
    raw: bytes
    raw_sha256: str
    git_blob: str


class AuthorityRepository:
    """Rebind every authority from immutable bytes at each decision; values are never cached."""

    def __init__(self, repository: Path, authority_ref: str, *, worktree_mode: bool = False) -> None:
        require(_ENVIRONMENT_VERIFIED, "VALIDATOR_ENVIRONMENT_NOT_VERIFIED")
        self.repository = repository.resolve()
        self.authority_ref = authority_ref
        self.worktree_mode = worktree_mode
        self.commit = "WORKTREE-CANDIDATE" if worktree_mode else resolve_commit(repository, authority_ref)
        raw = self._read_unbound(BINDINGS_PATH)
        bindings_value = strict_json_loads(raw)
        require(bindings_value["schema_version"] == "6.0.0-DRAFT", "AUTHORITY_BINDING_VERSION")
        require(bindings_value["accepted_parent"] == "c211870a8183e8f3e9ea9bf17fa34288b2c3000e", "AUTHORITY_PARENT")
        self._bindings = {item["role"]: item for item in bindings_value["bindings"]}
        require(len(self._bindings) == len(bindings_value["bindings"]), "AUTHORITY_ROLE_DUPLICATE")
        self.binding_identity = sha256(raw)

    def _read_unbound(self, relative: str) -> bytes:
        if self.worktree_mode:
            return read_binary(self.repository / Path(relative), allow_reparse=False).data
        return git_object_bytes(self.repository, self.authority_ref, relative)

    def load_bytes(self, role: str) -> BoundBytes:
        binding = self._bindings.get(role)
        require(type(binding) is dict, "AUTHORITY_ROLE_UNKNOWN", role)
        raw = self._read_unbound(binding["path"])
        observed_sha = sha256(raw)
        observed_blob = git_blob_identity(raw)
        require(observed_sha == binding["raw_sha256"], "AUTHORITY_RAW_MISMATCH", role)
        require(observed_blob == binding["git_blob"], "AUTHORITY_BLOB_MISMATCH", role)
        return BoundBytes(role, binding["path"], raw, observed_sha, observed_blob)

    def load_json(self, role: str) -> Any:
        bound = self.load_bytes(role)
        value = strict_json_loads(bound.raw)
        schema_role = self._bindings[role].get("schema_role")
        if schema_role:
            schema = strict_json_loads(self.load_bytes(schema_role).raw)
            validate_json_schema(schema, value, role)
        return freeze(value)

    def binding(self, role: str) -> Mapping[str, Any]:
        require(role in self._bindings, "AUTHORITY_ROLE_UNKNOWN", role)
        return freeze(json.loads(json.dumps(self._bindings[role])))

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(sorted(self._bindings))

    @property
    def identity(self) -> str:
        return semantic_identity([
            {"role": role, "path": self._bindings[role]["path"], "raw_sha256": self._bindings[role]["raw_sha256"], "git_blob": self._bindings[role]["git_blob"]}
            for role in sorted(self._bindings)
        ])


def code_object_fingerprint(code: types.CodeType) -> str:
    def stable(current: types.CodeType) -> Any:
        constants = []
        for item in current.co_consts:
            if isinstance(item, types.CodeType):
                constants.append({"code": stable(item)})
            elif item is None or type(item) in (str, int, bool, bytes):
                constants.append(item.hex() if type(item) is bytes else item)
            else:
                constants.append(type(item).__name__)
        return {
            "bytecode": current.co_code.hex(), "constants": constants, "names": list(current.co_names),
            "varnames": list(current.co_varnames), "freevars": list(current.co_freevars), "cellvars": list(current.co_cellvars),
            "argcount": current.co_argcount, "posonlyargcount": current.co_posonlyargcount,
            "kwonlyargcount": current.co_kwonlyargcount, "flags": current.co_flags,
        }
    return semantic_identity(stable(code))


def source_function_fingerprint(data: bytes, symbol: str) -> str:
    tree_code = compile(data.decode("utf-8", "strict"), "<R6-AUTHORITY>", "exec", dont_inherit=True)
    pending = [tree_code]
    while pending:
        current = pending.pop()
        if current.co_name == symbol:
            return code_object_fingerprint(current)
        pending.extend(item for item in current.co_consts if isinstance(item, types.CodeType))
    raise R6AuthorityError("CODE_SYMBOL_MISSING", symbol)


FORBIDDEN_SURFACES = {
    "builtins.open", "io.open", "os.open", "os.scandir", "os.listdir", "os.walk", "os.stat", "os.lstat",
    "pathlib.Path.glob", "pathlib.Path.rglob", "pathlib.Path.iterdir", "pathlib.Path.read_bytes", "pathlib.Path.read_text",
    "win32file.CreateFile", "ctypes.windll.kernel32.CreateFileW",
}


def _constant(node: ast.AST, values: Mapping[str, Any]) -> tuple[bool, Any]:
    if isinstance(node, ast.Constant) and type(node.value) in (str, int, bool, type(None)):
        return True, node.value
    if isinstance(node, ast.Name) and node.id in values:
        return True, values[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left_ok, left = _constant(node.left, values)
        right_ok, right = _constant(node.right, values)
        if left_ok and right_ok and type(left) is type(right) and type(left) in (str, tuple, list):
            return True, left + right
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for part in node.values:
            if isinstance(part, ast.Constant) and type(part.value) is str:
                parts.append(part.value)
            elif isinstance(part, ast.FormattedValue):
                ok, value = _constant(part.value, values)
                if not ok or type(value) not in (str, int, bool):
                    return False, None
                parts.append(str(value))
            else:
                return False, None
        return True, "".join(parts)
    if isinstance(node, (ast.Tuple, ast.List)):
        result = []
        for item in node.elts:
            ok, value = _constant(item, values)
            if not ok:
                return False, None
            result.append(value)
        return True, tuple(result) if isinstance(node, ast.Tuple) else result
    if isinstance(node, ast.Dict):
        result: dict[Any, Any] = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                return False, None
            key_ok, key = _constant(key_node, values)
            value_ok, value = _constant(value_node, values)
            if not key_ok or not value_ok:
                return False, None
            result[key] = value
        return True, result
    if isinstance(node, ast.Subscript):
        base_ok, base = _constant(node.value, values)
        key_ok, key = _constant(node.slice, values)
        if base_ok and key_ok and type(base) in (dict, list, tuple):
            try:
                return True, base[key]
            except (KeyError, IndexError, TypeError):
                pass
    return False, None


def _attribute_name(node: ast.AST, aliases: Mapping[str, set[str]], constants: Mapping[str, Any]) -> set[str]:
    if isinstance(node, ast.Name):
        if node.id == "__builtins__":
            return {"builtins"}
        return aliases.get(node.id, {node.id})
    if isinstance(node, ast.Attribute):
        return {f"{base}.{node.attr}" for base in _attribute_name(node.value, aliases, constants)}
    if isinstance(node, ast.Subscript):
        bases = _attribute_name(node.value, aliases, constants)
        ok, key = _constant(node.slice, constants)
        if ok and type(key) is str:
            return {f"{base}.{key}" for base in bases}
    if isinstance(node, ast.Call):
        targets = _attribute_name(node.func, aliases, constants)
        if targets & {"getattr", "builtins.getattr"} and len(node.args) >= 2:
            bases = _attribute_name(node.args[0], aliases, constants)
            ok, name = _constant(node.args[1], constants)
            if not ok or type(name) is not str:
                raise R6AuthorityError("ACCESS_DYNAMIC_NAME_UNRESOLVED")
            return {f"{base}.{name}" for base in bases}
        if targets & {"importlib.import_module"} and node.args:
            ok, name = _constant(node.args[0], constants)
            if not ok or type(name) is not str:
                raise R6AuthorityError("ACCESS_DYNAMIC_IMPORT_UNRESOLVED")
            return {name}
        if targets & {"functools.partial"} and node.args:
            return _attribute_name(node.args[0], aliases, constants)
    return set()


def resolved_call_surfaces(data: bytes) -> set[str]:
    try:
        tree = ast.parse(data.decode("utf-8", "strict"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise R6AuthorityError("ACCESS_SOURCE_INVALID", str(exc)) from exc
    aliases: dict[str, set[str]] = {}
    constants: dict[str, Any] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = {item.name}
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = {f"{node.module}.{item.name}"}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value_node = node.value
                if value_node is None:
                    continue
                ok, value = _constant(value_node, constants)
                names = _attribute_name(value_node, aliases, constants)
                for target in targets:
                    if isinstance(target, ast.Name):
                        if ok and constants.get(target.id) != value:
                            constants[target.id] = value
                            changed = True
                        if names and aliases.get(target.id) != names:
                            aliases[target.id] = names
                            changed = True
                if isinstance(value_node, (ast.Lambda, ast.FunctionDef)):
                    pass
    surfaces: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            names = _attribute_name(node.func, aliases, constants)
            surfaces.update(names)
        elif isinstance(node, (ast.FunctionDef, ast.Lambda)):
            defaults = list(getattr(node.args, "defaults", [])) + [item for item in getattr(node.args, "kw_defaults", []) if item]
            for default in defaults:
                surfaces.update(_attribute_name(default, aliases, constants))
    # Bytecode names close AST spelling gaps; unknown authority primitives fail closed.
    compiled = compile(data.decode("utf-8", "strict"), "<R6-AUDIT>", "exec", dont_inherit=True)
    pending = [compiled]
    while pending:
        code = pending.pop()
        names = set(code.co_names)
        if "open" in names and not any(item.endswith(".open") for item in surfaces):
            surfaces.add("UNRESOLVED.open")
        if "scandir" in names and not any(item.endswith(".scandir") for item in surfaces):
            surfaces.add("UNRESOLVED.scandir")
        pending.extend(item for item in code.co_consts if isinstance(item, types.CodeType))
    return surfaces


def audit_authority_source(data: bytes, approved: Mapping[str, Any] | None = None) -> str:
    surfaces = resolved_call_surfaces(data)
    prohibited = sorted(surface for surface in surfaces if surface in FORBIDDEN_SURFACES or surface.startswith("UNRESOLVED."))
    if prohibited:
        if approved is None:
            raise R6AuthorityError("AUTHORITY_ACCESS_SURFACE_FORBIDDEN", ",".join(prohibited))
        require(approved["raw_sha256"] == sha256(data), "ACCESS_APPROVED_RAW_MISMATCH")
        require(approved["git_blob"] == git_blob_identity(data), "ACCESS_APPROVED_BLOB_MISMATCH")
        require(approved["module_role"] == "GOVERNED_PRIMARY_FILE_ACCESS", "ACCESS_APPROVED_ROLE")
    return semantic_identity({"source": sha256(data), "surfaces": sorted(surfaces), "approved": approved["authority_id"] if approved else None})


MANDATORY_TESTS = (
    "test_command_center_listener_watchdog.py",
    "test_offline_replay.py",
    "test_kpi_liquidity_atr_distance_report.py",
    "test_tick_receiver_pipeline.py",
    "test_tick_receiver_throughput.py",
)


def _matches_exclusion(path: str, exclusion: Mapping[str, Any]) -> bool:
    value = exclusion["path_or_pattern"]
    mode = exclusion["match_type"]
    if mode == "exact":
        return path == value
    if mode == "prefix":
        return path == value or path.startswith(value.rstrip("/") + "/")
    if mode == "suffix":
        return path.endswith(value)
    if mode == "segment":
        return value in path.split("/")
    return False


def verify_mandatory_tests(authorities: AuthorityRepository, physical_root: Path) -> Mapping[str, Any]:
    include = authorities.load_json("include_registry")
    exclusion = authorities.load_json("exclusion_registry")
    rules = authorities.load_json("selection_rule_registry")
    universe = authorities.load_json("governed_authority_universe")
    authority = authorities.load_json("mandatory_test_authority")
    names = tuple(item["path"] for item in authority["tests"])
    require(names == MANDATORY_TESTS, "MANDATORY_TEST_AUTHORITY_SET")
    include_by_path = {item["path"]: item for item in include["entries"]}
    rule_by_id = {item["rule_id"]: item for item in rules["rules"]}
    universe_paths = tuple(item["path"] for item in universe["mandatory_tests"])
    require(universe_paths == MANDATORY_TESTS, "MANDATORY_TEST_UNIVERSE_SET")
    observed: list[dict[str, Any]] = []
    for item in authority["tests"]:
        path = item["path"]
        require(path in include_by_path, "MANDATORY_TEST_INCLUDE_MISSING", path)
        include_item = include_by_path[path]
        require(include_item["path"] == path, "MANDATORY_TEST_PATH_CASE", path)
        require(include_item["selection_rule_id"] == "PRODUCTION_TEST_CLOSURE", "MANDATORY_TEST_INCLUDE_RULE", path)
        require("PRODUCTION_TEST_CLOSURE" in rule_by_id, "MANDATORY_TEST_RULE_MISSING")
        require(rule_by_id["PRODUCTION_TEST_CLOSURE"]["class"] == "production-test", "MANDATORY_TEST_RULE_CLASS")
        require(not any(_matches_exclusion(path, candidate) for candidate in exclusion["entries"]), "MANDATORY_TEST_EXCLUDED", path)
        observation = read_binary(physical_root / path, allow_reparse=False)
        require(observation.byte_size == item["byte_size"], "MANDATORY_TEST_SIZE", path)
        require(observation.sha256 == item["raw_sha256"], "MANDATORY_TEST_CONTENT", path)
        observed.append({"path": path, "byte_size": observation.byte_size, "raw_sha256": observation.sha256})
    receipt = {
        "schema_version": "6.0.0-DRAFT",
        "status": "PASS",
        "physical_root_policy": authority["physical_root_policy"],
        "tests": observed,
        "include_registry_identity": authorities.load_bytes("include_registry").raw_sha256,
        "exclusion_registry_identity": authorities.load_bytes("exclusion_registry").raw_sha256,
        "rule_registry_identity": authorities.load_bytes("selection_rule_registry").raw_sha256,
        "universe_identity": authorities.load_bytes("governed_authority_universe").raw_sha256,
        "mandatory_authority_identity": authorities.load_bytes("mandatory_test_authority").raw_sha256,
    }
    return freeze(receipt)


def _clauses(specification: bytes) -> dict[str, str]:
    text = specification.decode("utf-8", "strict")
    result: dict[str, str] = {}
    for match in re.finditer(r"^### \[(CPB-R6-\d{2})\] (.+?)\n\n(.+?)(?=\n### \[CPB-R6-|\Z)", text, re.M | re.S):
        result[match.group(1)] = match.group(3).strip()
    return result


def validate_traceability(authorities: AuthorityRepository, run_id: str, events: Sequence[Mapping[str, Any]], observations: Sequence[Mapping[str, Any]]) -> str:
    matrix = authorities.load_json("semantic_traceability")
    specification = authorities.load_bytes("specification")
    clauses = _clauses(specification.raw)
    definitions = authorities.load_json("case_definitions")
    expectations = authorities.load_json("independent_expectations")
    case_by_id = {item["case_id"]: item for item in definitions["cases"]}
    expectation_by_id = {item["case_id"]: item for item in expectations["cases"]}
    event_by_id = {item["case_id"]: item for item in events}
    observation_by_id = {item["case_id"]: item for item in observations}
    require(len(event_by_id) == len(events), "TRACE_EVENT_DUPLICATE")
    require(len(observation_by_id) == len(observations), "TRACE_OBSERVATION_DUPLICATE")
    source = authorities.load_bytes("r6_enforcement_code")
    symbols = {node.name for node in ast.walk(ast.parse(source.raw.decode("utf-8"))) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    schema_paths = {authorities.binding(role)["path"] for role in authorities.roles if role.endswith("_schema")}
    mapped_cases: set[str] = set()
    for row in matrix["rows"]:
        clause = row["clause_id"]
        require(clause in clauses, "TRACE_CLAUSE_MISSING", clause)
        require(sha256(clauses[clause].encode("utf-8")) == row["clause_sha256"], "TRACE_CLAUSE_HASH", clause)
        require(row["schema_path"] in schema_paths, "TRACE_SCHEMA_POINTER", clause)
        require(row["rule_id"] in matrix["rule_set"], "TRACE_RULE", clause)
        require(row["implementing_source"] == authorities.binding("r6_enforcement_code")["path"], "TRACE_SOURCE", clause)
        require(row["implementing_symbol"] in symbols, "TRACE_SYMBOL", clause)
        require(row["function_code_blob"] == source.git_blob, "TRACE_CODE_BLOB", clause)
        for case_key in ("positive_case", "mutation_case"):
            case_id = row[case_key]
            require(case_id in case_by_id and case_id in expectation_by_id, "TRACE_CASE", case_id)
            require(case_id in event_by_id and case_id in observation_by_id, "TRACE_CURRENT_EVIDENCE", case_id)
            event = event_by_id[case_id]
            observation = observation_by_id[case_id]
            expectation = expectation_by_id[case_id]
            require(event["run_id"] == run_id and observation["run_id"] == run_id, "TRACE_PRIOR_RUN", case_id)
            require(event["enforcing_function"] == expectation["expected_enforcing_function"], "TRACE_EXPECTED_SURFACE", case_id)
            require(observation["observed_enforcing_function"] == event["enforcing_function"], "TRACE_OBSERVED_SURFACE", case_id)
            require(observation["observed_code"] == expectation["expected_code"], "TRACE_RESULT_CODE", case_id)
            require(observation["event_identity"] == event["event_hash"], "TRACE_EVENT_IDENTITY", case_id)
            mapped_cases.add(case_id)
        require(row["future_obligation"] in matrix["future_obligations"], "TRACE_FUTURE_OBLIGATION", clause)
    require(set(matrix["reverse_case_mapping"]) == mapped_cases, "TRACE_REVERSE_MAPPING")
    return semantic_identity(thaw(matrix))


def validate_review_receipt(authorities: AuthorityRepository, receipt: Any) -> str:
    require_plain_data(receipt)
    trust = authorities.load_json("reviewer_trust_root")
    issuance = authorities.load_json("review_issuance_evidence")
    schema = authorities.load_json("future_review_receipt_schema")
    validate_json_schema(schema, receipt, "future_review_receipt")
    for field in (
        "reviewed_package_identity", "manifest_identity", "script_identity", "accepted_specification_identity",
        "reviewer_identity", "reviewer_persona", "reviewer_capability", "decision", "issued_timestamp",
        "compatibility_result", "authorization_boundaries", "issuer", "issuance_event_identity",
    ):
        require(receipt[field] == thaw(issuance[field]), "REVIEW_ISSUANCE_MISMATCH", field)
    require(receipt["trust_root_identity"] == authorities.load_bytes("reviewer_trust_root").raw_sha256, "REVIEW_TRUST_ROOT")
    require(issuance["reviewer_identity"] == trust["reviewer_identity"], "REVIEWER_IDENTITY")
    require(issuance["reviewer_persona"] == trust["reviewer_persona"], "REVIEWER_PERSONA")
    require(issuance["reviewer_capability"] in trust["capabilities"], "REVIEWER_CAPABILITY")
    require(issuance["issuer"] == trust["trusted_issuer"], "REVIEW_ISSUER")
    issued = parse_timestamp(issuance["issued_timestamp"], "review issued")
    require(parse_timestamp(trust["valid_from"], "review valid_from") <= issued <= parse_timestamp(trust["valid_until"], "review valid_until"), "REVIEW_TIME_WINDOW")
    require(issuance["decision"] == "ACCEPT", "REVIEW_DECISION")
    require(issuance["independence_proof"] == "INDEPENDENT_REVIEWER_NOT_PACKAGE_AUTHOR", "REVIEW_INDEPENDENCE")
    return semantic_identity(thaw(issuance))


def validate_compatibility(authorities: AuthorityRepository, claim: Any) -> str:
    require_plain_data(claim)
    trust = authorities.load_json("compatibility_trust_root")
    evidence = authorities.load_json("compatibility_evidence")
    schema = authorities.load_json("compatibility_evidence_schema")
    validate_json_schema(schema, claim, "compatibility_evidence")
    require(canonical_json_bytes(claim) == canonical_json_bytes(thaw(evidence)), "COMPATIBILITY_EVIDENCE_BYTES")
    require(evidence["issuer"] == trust["issuer_identity"], "COMPATIBILITY_ISSUER")
    require("ISSUE_COMPATIBILITY" in trust["capabilities"], "COMPATIBILITY_CAPABILITY")
    issued = parse_timestamp(evidence["issued_timestamp"], "compatibility issued")
    require(parse_timestamp(trust["valid_from"], "compat valid_from") <= issued <= parse_timestamp(trust["valid_until"], "compat valid_until"), "COMPATIBILITY_TIME_WINDOW")
    require(evidence["verifier_code_identity"] == trust["verifier_code_identity"], "COMPATIBILITY_VERIFIER")
    require(evidence["interface_version"] == trust["future_package_interface"], "COMPATIBILITY_INTERFACE")
    schema_roles = sorted(thaw(trust["required_schema_roles"]))
    authority_roles = sorted(thaw(trust["required_authority_roles"]))
    require(all(role in authorities.roles and role.endswith("_schema") for role in schema_roles), "COMPATIBILITY_SCHEMA_ROLE")
    require(all(role in authorities.roles for role in authority_roles), "COMPATIBILITY_AUTHORITY_ROLE")
    require(semantic_identity(schema_roles) == trust["required_schema_set_identity"], "COMPATIBILITY_SCHEMA_SET")
    require(semantic_identity(authority_roles) == trust["required_authority_set_identity"], "COMPATIBILITY_AUTHORITY_SET")
    require(evidence["schema_set_identity"] == trust["required_schema_set_identity"], "COMPATIBILITY_SCHEMA_SET")
    require(evidence["authority_set_identity"] == trust["required_authority_set_identity"], "COMPATIBILITY_AUTHORITY_SET")
    require(evidence["compatibility_state"] == "COMPATIBLE_WITH_ACCEPTED_SPECIFICATION", "COMPATIBILITY_STATE")
    require(bool(evidence["findings"]) and bool(evidence["evidence_attachments"]), "COMPATIBILITY_EVIDENCE_MISSING")
    return semantic_identity(thaw(evidence))


PROOF_WORDS = re.compile(r"\b(demonstrated|enforced|proven|verified|closed|resolved|completed|satisfied|guaranteed|established|independently bound|independently accepted|production ready|approval granted|authorized|permitted|cleared)\b", re.I)
PROTECTED = re.compile(r"\b(baseline capture|operational capture(?:-script)? work|merge|canonical incorporation|production implementation|deployment|restart|runtime migration|NQ cutover|paper trading|live(?:-money)? trading|Phase 3C2|Phase 3C1-R11|Bucket 0|Bucket 1)\b", re.I)
WITHHOLDING = re.compile(r"\b(not authorized|remains? withheld|pending independent review|remains? blocked|remains? incomplete|not demonstrated|rejected)\b", re.I)
CLAIM_TAG = re.compile(r"\[CLAIM:(R6-[A-Z0-9-]+)\]")


def validate_document_text(text: str, evidence: Mapping[str, str]) -> None:
    require(type(text) is str, "DOCUMENT_TEXT_TYPE")
    for line in text.splitlines():
        if PROTECTED.search(line) and PROOF_WORDS.search(line) and not WITHHOLDING.search(line):
            raise R6AuthorityError("DOCUMENT_AUTHORIZATION_LEAKAGE", line.strip())
        if PROOF_WORDS.search(line):
            if WITHHOLDING.search(line) or "independent review rejected" in line.lower() or "may not" in line.lower():
                continue
            tag = CLAIM_TAG.search(line)
            require(tag is not None, "DOCUMENT_UNSUPPORTED_CLAIM", line.strip())
            require(tag.group(1) in evidence, "DOCUMENT_CLAIM_EVIDENCE_MISSING", tag.group(1))


def validate_documents(authorities: AuthorityRepository, claim_evidence: Mapping[str, str]) -> str:
    policy = authorities.load_json("document_claim_evidence")
    required = {item["claim_id"] for item in policy["claims"]}
    require(set(claim_evidence) == required, "DOCUMENT_EVIDENCE_SET")
    for role in ("architecture_impact", "canonical_delta", "remediation_report"):
        text = authorities.load_bytes(role).raw.decode("utf-8", "strict")
        validate_document_text(text, claim_evidence)
    return semantic_identity({"policy": thaw(policy), "evidence": dict(sorted(claim_evidence.items()))})
