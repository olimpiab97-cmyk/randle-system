#!/usr/bin/env python3
"""R5 authority verifier.

This module verifies draft specification-package authority only.  It performs no
production capture and grants no operational authority.
"""

from __future__ import annotations

import ast
import builtins
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import types
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from governed_file_access_DRAFT import (
    ByteObservation,
    git_object_bytes,
    git_tree_entries,
    read_binary,
    write_disposable_binary,
)


PACKAGE_RELATIVE = (
    "Architecture/Audits/"
    "2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT"
)
R4_COMMIT = "a385534a770f47c7545d0d59a67510adf7564c24"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


class R5AuthorityError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


def require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise R5AuthorityError(code, detail)


def _reject_duplicate(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise R5AuthorityError("JSON_DUPLICATE_KEY", key)
        result[key] = value
    return result


def require_plain_data(value: Any, pointer: str = "$") -> None:
    """Reject polymorphic caller behavior recursively before semantic use."""
    value_type = type(value)
    if value_type is dict:
        for key, child in value.items():
            require(type(key) is str, "AUTHORITY_NON_PLAIN_TYPE", f"{pointer}.<key>")
            require_plain_data(child, f"{pointer}.{key}")
        return
    if value_type is list:
        for index, child in enumerate(value):
            require_plain_data(child, f"{pointer}[{index}]")
        return
    if value_type in {str, int, bool, type(None)}:
        return
    raise R5AuthorityError("AUTHORITY_NON_PLAIN_TYPE", f"{pointer}:{value_type.__module__}.{value_type.__qualname__}")


def _require_nfc(value: Any, pointer: str = "$") -> None:
    if type(value) is str:
        require(unicodedata.normalize("NFC", value) == value, "JSON_NON_NFC", pointer)
    elif type(value) is dict:
        for key, child in value.items():
            require(unicodedata.normalize("NFC", key) == key, "JSON_NON_NFC", f"{pointer}.<key>")
            _require_nfc(child, f"{pointer}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _require_nfc(child, f"{pointer}[{index}]")


def strict_json_loads(data: bytes) -> Any:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise R5AuthorityError("JSON_UTF8", str(exc)) from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate,
            parse_float=lambda token: (_ for _ in ()).throw(R5AuthorityError("JSON_FLOAT_FORBIDDEN", token)),
            parse_constant=lambda token: (_ for _ in ()).throw(R5AuthorityError("JSON_CONSTANT_FORBIDDEN", token)),
        )
    except R5AuthorityError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise R5AuthorityError("JSON_INVALID", str(exc)) from exc
    require_plain_data(value)
    _require_nfc(value)
    require(canonical_json_bytes(value) == data, "JSON_NOT_CANONICAL")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    require_plain_data(value)
    _require_nfc(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_identity(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def semantic_identity(value: Any) -> str:
    return sha256(canonical_json_bytes(value))


def parse_timestamp(value: Any, label: str) -> dt.datetime:
    require(type(value) is str and RFC3339.fullmatch(value) is not None, "TIMESTAMP_FORMAT", label)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise R5AuthorityError("TIMESTAMP_FORMAT", label) from exc
    require(parsed.tzinfo is not None, "TIMESTAMP_TIMEZONE", label)
    return parsed.astimezone(dt.timezone.utc)


@dataclass(frozen=True)
class BoundDocument:
    role: str
    path: str
    raw: bytes
    value: Any
    sha256: str
    git_blob: str
    semantic_sha256: str


class AuthorityRepository:
    """Loads accepted R5 authority strictly from immutable Git-object bytes."""

    def __init__(self, repository: Path, authority_ref: str, *, allow_staged: bool = False) -> None:
        self.repository = repository
        self.authority_ref = authority_ref
        self.allow_staged = allow_staged
        binding_path = f"{PACKAGE_RELATIVE}/r5_authority_bindings_DRAFT.json"
        binding = self._read(binding_path)
        self.binding_raw = binding.data
        self.binding_value = strict_json_loads(binding.data)
        require(type(self.binding_value) is dict, "BINDING_NOT_OBJECT")
        require(self.binding_value.get("schema_version") == "7.0.0-DRAFT", "BINDING_SCHEMA_VERSION")
        items = self.binding_value.get("bindings")
        require(type(items) is list, "BINDING_LIST")
        self._bindings: dict[str, dict[str, Any]] = {}
        for item in items:
            require(type(item) is dict, "BINDING_ITEM")
            role = item.get("role")
            require(type(role) is str and role not in self._bindings, "BINDING_ROLE", str(role))
            self._bindings[role] = item
        self._cache: dict[str, BoundDocument] = {}

    def _read(self, path: str) -> ByteObservation:
        if self.allow_staged:
            command = [
                "git", "-c", "core.longpaths=true", "-c", f"safe.directory={self.repository.as_posix()}",
                "-C", os.fspath(self.repository), "show", f":{path}",
            ]
            completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if completed.returncode:
                raise R5AuthorityError("GIT_OBJECT_READ", f"{path}:{completed.stderr.decode('utf-8', 'replace')}")
            raw = completed.stdout
            return ByteObservation(
                source_kind="STAGED_GIT_BLOB_BYTES",
                canonical_path=path,
                data=raw,
                sha256=sha256(raw),
                byte_size=len(raw),
                git_blob=git_blob_identity(raw),
            )
        return git_object_bytes(self.repository, self.authority_ref, path)

    def load(self, role: str) -> BoundDocument:
        if role in self._cache:
            return self._cache[role]
        binding = self._bindings.get(role)
        require(binding is not None, "AUTHORITY_ROLE_UNKNOWN", role)
        path = binding.get("path")
        require(type(path) is str and path.startswith("Architecture/") and ".." not in path.split("/"), "AUTHORITY_PATH", role)
        observed = self._read(path)
        require(observed.sha256 == binding.get("raw_sha256"), "AUTHORITY_RAW_SHA256", role)
        require(observed.git_blob == binding.get("git_blob"), "AUTHORITY_GIT_BLOB", role)
        value = strict_json_loads(observed.data) if path.endswith(".json") else observed.data
        semantic = semantic_identity(value) if type(value) is not bytes else sha256(value)
        require(semantic == binding.get("semantic_sha256"), "AUTHORITY_SEMANTIC_SHA256", role)
        schema_role = binding.get("schema_role")
        if schema_role is not None:
            schema = self.load(schema_role).value
            validate_json_schema(schema, value, role)
        document = BoundDocument(role, path, observed.data, value, observed.sha256, observed.git_blob, semantic)
        self._cache[role] = document
        return document

    @property
    def identity(self) -> str:
        return semantic_identity(self.binding_value)


def validate_json_schema(schema: Any, instance: Any, label: str) -> None:
    require_plain_data(schema)
    require_plain_data(instance)
    try:
        import jsonschema
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise R5AuthorityError("VALIDATOR_ENVIRONMENT", str(exc)) from exc
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    except jsonschema.exceptions.SchemaError as exc:
        raise R5AuthorityError("SCHEMA_INVALID", f"{label}:{exc.message}") from exc
    if errors:
        first = errors[0]
        pointer = "/" + "/".join(str(item) for item in first.absolute_path)
        raise R5AuthorityError("INSTANCE_SCHEMA_INVALID", f"{label}:{pointer}:{first.message}")


# ---------- resolved authority-access auditing ----------

FORBIDDEN_SURFACES = {
    "builtins.open", "io.open", "os.open", "os.scandir", "os.listdir", "os.walk",
    "os.stat", "os.lstat", "pathlib.Path.glob", "pathlib.Path.rglob", "pathlib.Path.iterdir",
    "pathlib.Path.read_bytes", "pathlib.Path.read_text", "pathlib.Path.stat", "pathlib.Path.lstat",
}
APPROVED_ACCESS_MODULES = {
    "governed_file_access_DRAFT.py",
    "inventory_generator_DRAFT.py",
}


def _attribute_name(node: ast.AST, env: Mapping[str, set[str]]) -> set[str]:
    if isinstance(node, ast.Name):
        if node.id == "__builtins__":
            return {"builtins"}
        return set(env.get(node.id, {node.id}))
    if isinstance(node, ast.Attribute):
        return {f"{base}.{node.attr}" for base in _attribute_name(node.value, env)}
    if isinstance(node, ast.Subscript):
        bases = _attribute_name(node.value, env)
        key = node.slice.value if isinstance(node.slice, ast.Constant) else None
        if type(key) is str:
            return {f"{base}.{key}" for base in bases}
    if isinstance(node, ast.Lambda):
        return _called_surfaces(node.body, env)
    if isinstance(node, ast.Dict):
        result: set[str] = set()
        for value in node.values:
            result |= _attribute_name(value, env)
        return result
    if isinstance(node, ast.Call):
        target = _attribute_name(node.func, env)
        if target & {"getattr", "builtins.getattr"} and len(node.args) >= 2:
            key = node.args[1].value if isinstance(node.args[1], ast.Constant) else None
            if type(key) is str:
                return {f"{base}.{key}" for base in _attribute_name(node.args[0], env)}
        if target & {"importlib.import_module"} and node.args:
            name = node.args[0].value if isinstance(node.args[0], ast.Constant) else None
            if type(name) is str:
                return {name}
        if target & {"functools.partial", "partial"} and node.args:
            return _attribute_name(node.args[0], env)
        result: set[str] = set()
        for name in target:
            result |= env.get(name, {name})
        return result
    return set()


def _called_surfaces(node: ast.AST, env: Mapping[str, set[str]]) -> set[str]:
    result: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            result |= _attribute_name(child.func, env)
    return result


def audit_authority_source_resolved(data: bytes, module_name: str) -> str:
    """Resolve imports, aliases, dynamic lookup, wrappers and captured callables."""
    try:
        source = data.decode("utf-8", errors="strict")
        tree = ast.parse(source, filename=module_name)
    except (UnicodeError, SyntaxError) as exc:
        raise R5AuthorityError("ACCESS_AUDIT_PARSE", f"{module_name}:{exc}") from exc
    if Path(module_name).name in APPROVED_ACCESS_MODULES:
        return semantic_identity({"module": module_name, "approved_surface": True, "violations": []})
    env: dict[str, set[str]] = {
        "open": {"builtins.open"},
        "getattr": {"builtins.getattr"},
    }
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for item in node.names:
                env[item.asname or item.name.split(".")[0]] = {item.name}
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for item in node.names:
                env[item.asname or item.name] = {f"{module}.{item.name}".strip(".")}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            resolved = _attribute_name(value, env) if value is not None else set()
            for target in targets:
                if isinstance(target, ast.Name):
                    env[target.id] = resolved
    # Resolve local wrapper summaries to a fixed point, including defaults and closures.
    for _ in range(max(1, len(functions) + 1)):
        changed = False
        for name, node in functions.items():
            summary = _called_surfaces(node, env)
            for default in [*node.args.defaults, *[item for item in node.args.kw_defaults if item is not None]]:
                summary |= _attribute_name(default, env)
            if env.get(name) != summary:
                env[name] = summary
                changed = True
        if not changed:
            break
    violations: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        resolved = _attribute_name(node.func, env)
        prohibited = sorted(surface for surface in resolved if surface in FORBIDDEN_SURFACES)
        if prohibited:
            violations.append({"line": node.lineno, "surfaces": prohibited})
    # Bytecode/name inventory closes simple dynamic references not visible as direct calls.
    try:
        compiled = compile(tree, module_name, "exec", dont_inherit=True, optimize=0)
    except Exception as exc:
        raise R5AuthorityError("ACCESS_AUDIT_COMPILE", f"{module_name}:{exc}") from exc
    bytecode_names: set[str] = set()
    stack = [compiled]
    while stack:
        code = stack.pop()
        bytecode_names.update(code.co_names)
        stack.extend(item for item in code.co_consts if isinstance(item, types.CodeType))
    suspicious = sorted(bytecode_names & {"open", "scandir", "listdir", "read_bytes", "read_text", "rglob"})
    if suspicious and not violations:
        violations.append({"line": 0, "surfaces": [f"BYTECODE_REFERENCE:{name}" for name in suspicious]})
    require(not violations, "UNMANAGED_AUTHORITY_ACCESS", json.dumps(violations, sort_keys=True))
    return semantic_identity({"module": module_name, "bytecode_names": sorted(bytecode_names), "violations": []})


def audit_committed_authority_sources(authorities: AuthorityRepository) -> str:
    enumeration = authorities.load("governed_enumeration").value
    results = []
    for path in enumeration["authority_code_paths"]:
        observed = authorities._read(path)
        results.append({"path": path, "audit": audit_authority_source_resolved(observed.data, path)})
    return semantic_identity(results)


# ---------- isolated-process receipts ----------

def _sanitized_environment() -> dict[str, str]:
    environment = {
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"):
        if key in os.environ:
            environment[key] = os.environ[key]
    return environment


def run_isolated_worker(
    authorities: AuthorityRepository,
    mode: str,
    payload: dict[str, Any],
    *,
    worker_role: str = "isolated_worker_code",
    source_role: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    require_plain_data(payload)
    worker = authorities.load(worker_role)
    source = authorities.load(source_role) if source_role else None
    envelope = {
        "schema_version": "7.0.0-DRAFT",
        "mode": mode,
        "payload": payload,
        "source_bytes_hex": source.raw.hex() if source else "",
        "source_raw_sha256": source.sha256 if source else "0" * 64,
        "source_git_blob": source.git_blob if source else "0" * 40,
    }
    input_bytes = canonical_json_bytes(envelope)
    with tempfile.TemporaryDirectory(prefix="r5-isolated-") as temporary:
        worker_path = Path(temporary) / "isolated_worker_R5_DRAFT.py"
        write_disposable_binary(worker_path, worker.raw, exclusive=True)
        command = [sys.executable, "-I", "-S", os.fspath(worker_path)]
        completed = subprocess.run(
            command,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_sanitized_environment(),
            cwd=temporary,
            check=False,
        )
    stdout_sha = sha256(completed.stdout)
    stderr_sha = sha256(completed.stderr)
    receipt = {
        "schema_version": "7.0.0-DRAFT",
        "mode": mode,
        "worker_git_blob": worker.git_blob,
        "worker_raw_sha256": worker.sha256,
        "source_git_blob": source.git_blob if source else "0" * 40,
        "source_raw_sha256": source.sha256 if source else "0" * 64,
        "python_implementation": sys.implementation.name,
        "python_version": ".".join(str(item) for item in sys.version_info[:3]),
        "interpreter_flags": ["-I", "-S"],
        "environment_policy": "RANDLE-R5-SANITIZED-PYTHON-1",
        "module_search_policy": "ISOLATED_WORKER_DIRECTORY_ONLY",
        "input_sha256": sha256(input_bytes),
        "stdout_sha256": stdout_sha,
        "stderr_sha256": stderr_sha,
        "returncode": completed.returncode,
        "invocation": "PYTHON -I -S ISOLATED_WORKER",
    }
    receipt["execution_receipt_sha256"] = semantic_identity(receipt)
    require(completed.returncode == 0, "ISOLATED_EXECUTION_FAILED", f"{mode}:{completed.returncode}:{completed.stderr.decode('utf-8', 'replace')}")
    result = strict_json_loads(completed.stdout)
    require(type(result) is dict, "ISOLATED_RESULT_TYPE", mode)
    return result, receipt


def verify_parser_execution(authorities: AuthorityRepository, log_path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    require(type(builtins.compile) is types.BuiltinFunctionType, "PARSER_PARENT_COMPILE_PATCHED")
    require(type(builtins.exec) is types.BuiltinFunctionType, "PARSER_PARENT_EXEC_PATCHED")
    require(type(builtins.__import__) is types.BuiltinFunctionType, "PARSER_PARENT_IMPORT_PATCHED")
    parser_authority = authorities.load("historical_parser_authority").value
    executable = read_binary(sys.executable, allow_reparse=False)
    require(executable.sha256 == parser_authority["python_executable_identity"], "PARSER_INTERPRETER_IDENTITY")
    evidence_authority = authorities.load("historical_evidence_authority").value
    require(log_path == evidence_authority["physical_path"], "HISTORICAL_AUTHORITY_PATH")
    observed = read_binary(log_path, allow_reparse=False)
    require(observed.sha256.upper() == evidence_authority["sha256"], "HISTORICAL_LOG_HASH")
    require(len(observed.data) == evidence_authority["size"], "HISTORICAL_LOG_SIZE")
    payload = {
        "logical_path": evidence_authority["logical_evidence_id"],
        "log_bytes_hex": observed.data.hex(),
        "parser_symbol": parser_authority["parser_symbol"],
        "parser_interface_version": parser_authority["parser_interface_version"],
        "expected_log_sha256": evidence_authority["sha256"],
    }
    result, receipt = run_isolated_worker(authorities, "historical_parser", payload, source_role="historical_parser_code")
    validate_json_schema(authorities.load("historical_parser_result_schema").value, result, "historical_parser_result")
    validate_json_schema(authorities.load("parser_execution_receipt_schema").value, receipt, "parser_execution_receipt")
    require(result.get("outcome_count_by_status") == {"ERROR": 0, "FAILED": 156, "PASSED": 571, "SKIPPED": 3, "SUBFAILED": 23, "XFAIL": 0, "XPASS": 0}, "HISTORICAL_TOTALS")
    require(result.get("source_total") == 753 and result.get("failed_outcome_count") == 179, "HISTORICAL_TOTALS")
    require(receipt["source_git_blob"] == parser_authority["parser_git_blob"], "PARSER_EXECUTION_BLOB")
    require(receipt["source_raw_sha256"] == parser_authority["parser_raw_sha256"], "PARSER_EXECUTION_HASH")
    return result, receipt


def verify_comparator_execution(
    authorities: AuthorityRepository,
    expectations: dict[str, Any],
    observations: list[dict[str, Any]],
    context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    require(type(builtins.compile) is types.BuiltinFunctionType, "COMPARATOR_PARENT_COMPILE_PATCHED")
    require(type(builtins.exec) is types.BuiltinFunctionType, "COMPARATOR_PARENT_EXEC_PATCHED")
    require(type(builtins.__import__) is types.BuiltinFunctionType, "COMPARATOR_PARENT_IMPORT_PATCHED")
    comparator = authorities.load("comparison_authority").value
    executable = read_binary(sys.executable, allow_reparse=False)
    require(executable.sha256 == comparator["python_executable_identity"], "COMPARATOR_INTERPRETER_IDENTITY")
    payload = {"expectations": expectations, "observations": observations, "context": context}
    result, execution = run_isolated_worker(authorities, "comparator", payload, source_role="comparison_engine_code")
    validate_json_schema(authorities.load("comparator_execution_receipt_schema").value, execution, "comparator_execution_receipt")
    require(execution["source_git_blob"] == comparator["comparator_git_blob"], "COMPARATOR_EXECUTION_BLOB")
    require(execution["source_raw_sha256"] == comparator["comparator_raw_sha256"], "COMPARATOR_EXECUTION_HASH")
    require(result.get("interface_version") == comparator["interface_version"], "COMPARATOR_INTERFACE")
    result["comparator_execution_receipt_identity"] = execution["execution_receipt_sha256"]
    result["comparison_receipt_sha256"] = semantic_identity(result)
    return result, execution


def validate_comparison_receipt(
    receipt: Any,
    execution: Any,
    authorities: AuthorityRepository,
    expectations: dict[str, Any],
    observations: list[dict[str, Any]],
    context: dict[str, Any],
) -> None:
    require_plain_data(receipt)
    require_plain_data(execution)
    comparison = authorities.load("comparison_authority").value
    issuance = authorities.load("comparison_issuance_authority").value
    fields = {
        "comparator_authority_id": comparison["authority_id"],
        "comparator_code_blob": comparison["comparator_git_blob"],
        "comparator_raw_sha256": comparison["comparator_raw_sha256"],
        "interface_version": comparison["interface_version"],
        "comparison_policy_identity": authorities.load("comparison_policy").semantic_sha256,
        "case_definition_identity": context["case_definition_identity"],
        "case_set_identity": context["case_set_identity"],
        "expected_case_count": len(expectations["cases"]),
        "observed_case_count": len(observations),
        "completed": True,
        "expectation_identity": semantic_identity(expectations),
        "observation_identity": semantic_identity(observations),
        "enforcing_code_identity": context["enforcing_code_identity"],
        "schema_set_identity": context["schema_set_identity"],
        "authority_set_identity": context["authority_set_identity"],
        "discrepancy_count": 0,
        "terminal_status": "MATCHED",
        "cleanup_result": "PASS",
        "issuance_authority": issuance["issuance_authority"],
        "issued_timestamp": issuance["issued_timestamp"],
        "prior_committed_result_identity": issuance["prior_committed_result_identity"],
        "comparator_execution_receipt_identity": execution["execution_receipt_sha256"],
    }
    for key, expected in fields.items():
        require(receipt.get(key) == expected, "COMPARISON_RECEIPT_FIELD", key)
    require(comparison["expectation_identity"] == semantic_identity(expectations), "COMPARATOR_EXPECTATION_AUTHORITY")
    require(comparison["observation_identity"] == semantic_identity(observations), "COMPARATOR_OBSERVATION_AUTHORITY")
    claimed = dict(receipt)
    identity = claimed.pop("comparison_receipt_sha256", None)
    require(identity == semantic_identity(claimed), "COMPARISON_RECEIPT_HASH")
    validate_json_schema(authorities.load("terminal_comparison_receipt_schema").value, receipt, "terminal_comparison_receipt")


# ---------- event and provenance authority ----------

def event_hash(event: dict[str, Any]) -> str:
    copy = dict(event)
    copy.pop("event_hash", None)
    return semantic_identity(copy)


def validate_event_source(events: Any, authorities: AuthorityRepository, context: dict[str, Any]) -> str:
    require_plain_data(events)
    require(type(events) is list and len(events) == context["case_count"], "EVENT_COUNT")
    source = authorities.load("enforcement_event_source_authority").value
    require(source["authorized_run_identity"] == context["run_identity"], "EVENT_AUTHORIZED_RUN")
    prior = source["initial_root"]
    seen: set[str] = set()
    for sequence, event in enumerate(events, 1):
        require(type(event) is dict, "EVENT_TYPE")
        require(event.get("sequence_number") == sequence, "EVENT_SEQUENCE")
        require(event.get("prior_event_hash") == prior, "EVENT_PRIOR_HASH")
        require(event.get("event_hash") == event_hash(event), "EVENT_HASH")
        require(event.get("source_id") == source["source_id"], "EVENT_SOURCE_ID")
        require(event.get("attempt_id") == source["attempt_id"], "EVENT_ATTEMPT")
        require(event.get("run_id") == context["run_identity"], "EVENT_RUN")
        require(event.get("event_recorder_identity") == source["event_recorder_identity"], "EVENT_RECORDER")
        require(event.get("event_reader_identity") == source["event_reader_identity"], "EVENT_READER")
        case_id = event.get("case_id")
        require(type(case_id) is str and case_id not in seen, "EVENT_CASE_DUPLICATE", str(case_id))
        seen.add(case_id)
        prior = event["event_hash"]
    require(prior == source["expected_append_only_root"], "EVENT_APPEND_ONLY_ROOT")
    if not context.get("bootstrap", False):
        committed = authorities.load("enforcement_event_source")
        fresh_bytes = b"".join(canonical_json_bytes(item) for item in events)
        require(committed.raw == fresh_bytes, "EVENT_SOURCE_BYTES")
        require(committed.sha256 == source["source_raw_sha256"], "EVENT_SOURCE_RAW_SHA256")
        require(committed.git_blob == source["source_git_blob"], "EVENT_SOURCE_GIT_BLOB")
    return prior


def validate_observation_submission(
    submitted: Any,
    events: Any,
    authorities: AuthorityRepository,
    context: dict[str, Any],
) -> None:
    """A submitted observation has no authority unless event reconstruction equals it."""
    require_plain_data(submitted)
    derived = derive_observations_from_events(events, authorities, context)
    require(submitted == derived, "OBSERVATION_NOT_EVENT_DERIVED")


def validate_expectation_artifact(candidate: Any, authorities: AuthorityRepository) -> None:
    require_plain_data(candidate)
    committed = authorities.load("independent_expectations").value
    require(candidate == committed, "EXPECTATION_NOT_COMMITTED_AUTHORITY")


def validate_trace_locator(locator: Any, authorities: AuthorityRepository) -> None:
    require_plain_data(locator)
    require(
        locator == {
            "authority_ref": authorities.authority_ref,
            "path": authorities.load("semantic_traceability").path,
            "git_blob": authorities.load("semantic_traceability").git_blob,
        },
        "TRACE_LOCATOR_NOT_AUTHORIZED",
    )


def validate_trace_candidate_bytes(candidate: bytes, authorities: AuthorityRepository) -> None:
    require(type(candidate) is bytes, "TRACE_BYTES_TYPE")
    require(candidate == authorities.load("semantic_traceability").raw, "TRACE_MATRIX_BYTES_MISMATCH")


def validate_current_run_claim(run_id: Any, context: dict[str, Any]) -> None:
    require(type(run_id) is str and run_id == context["run_identity"], "TRACE_PRIOR_RUN_EVENT")


def derive_observations_from_events(
    events: Any,
    authorities: AuthorityRepository,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    root = validate_event_source(events, authorities, context)
    observations: list[dict[str, Any]] = []
    for event in events:
        observations.append(
            {
                "case_id": event["case_id"],
                "run_id": event["run_id"],
                "actual_input_identity": event["actual_input_identity"],
                "actual_status": event["actual_result_status"],
                "observed_code": event["actual_result_code"],
                "observed_enforcing_function": event["enforcing_function"],
                "observed_code_blob": event["source_code_blob"],
                "observed_authority_source": event["actual_authority_identity"],
                "observed_evidence_result": event["actual_evidence_identity"],
                "event_identity": event["event_hash"],
                "event_sequence": event["sequence_number"],
                "event_source_root": root,
                "execution_receipt": event["execution_receipt_identity"],
                "provenance": {
                    "source_kind": "APPEND_ONLY_ENFORCEMENT_EVENT",
                    "expectation_dependency": "NONE",
                    "producer_authority": event["event_source_issuance_authority"],
                },
            }
        )
    return observations


def validate_fixture_provenance(expectations: Any, observations: Any, events: Any, authorities: AuthorityRepository, context: dict[str, Any]) -> None:
    require_plain_data(expectations)
    require_plain_data(observations)
    derived = derive_observations_from_events(events, authorities, context)
    require(observations == derived, "OBSERVATION_NOT_EVENT_DERIVED")
    expectation_authority = authorities.load("expectation_authority").value
    observation_authority = authorities.load("observation_authority").value
    require(expectation_authority["source_kind"] == "COMMITTED_INDEPENDENT_EXPECTATION", "EXPECTATION_PROVENANCE")
    require(observation_authority["source_kind"] == "CURRENT_RUN_ENFORCEMENT_EVENTS", "OBSERVATION_PROVENANCE")
    require(expectation_authority["provenance_root"] != observation_authority["provenance_root"], "PROVENANCE_ROOT_COLLISION")
    require(expectation_authority["observation_dependency"] == "NONE", "EXPECTATION_OBSERVATION_DEPENDENCY")
    require(observation_authority["expectation_dependency"] == "NONE", "OBSERVATION_EXPECTATION_DEPENDENCY")
    require(expectation_authority["issued_timestamp"] < observation_authority["valid_from"], "EXPECTATION_AFTER_OBSERVATION")


# ---------- immutable trace authority ----------

def _extract_clauses(specification: bytes) -> dict[str, str]:
    text = specification.decode("utf-8", errors="strict")
    clauses: dict[str, str] = {}
    for match in re.finditer(r"^### \[(CPB-R5-\d{2})\] (.+)$", text, re.MULTILINE):
        clauses[match.group(1)] = match.group(2).strip()
    return clauses


def validate_traceability_internal(authorities: AuthorityRepository, events: Any, observations: Any, expectations: Any, context: dict[str, Any]) -> str:
    matrix_doc = authorities.load("semantic_traceability")
    matrix = matrix_doc.value
    require_plain_data(matrix)
    clauses = _extract_clauses(authorities.load("specification").raw)
    event_by_case = {item["case_id"]: item for item in events}
    observation_by_case = {item["case_id"]: item for item in observations}
    expectation_by_case = {item["case_id"]: item for item in expectations["cases"]}
    reverse: dict[str, set[str]] = {}
    for row in matrix["rows"]:
        clause_id = row["clause_id"]
        require(clause_id in clauses, "TRACE_CLAUSE_MISSING", clause_id)
        require(sha256(clauses[clause_id].encode("utf-8")) == row["clause_text_sha256"], "TRACE_CLAUSE_HASH", clause_id)
        for case_id in [row["positive_case"], *row["mutation_cases"]]:
            require(case_id in expectation_by_case, "TRACE_EXPECTATION_MISSING", case_id)
            require(case_id in event_by_case, "TRACE_FRESH_EVENT_MISSING", case_id)
            require(case_id in observation_by_case, "TRACE_OBSERVATION_MISSING", case_id)
            event = event_by_case[case_id]
            observation = observation_by_case[case_id]
            expectation = expectation_by_case[case_id]
            require(event["run_id"] == context["run_identity"], "TRACE_PRIOR_RUN_EVENT", case_id)
            require(observation["run_id"] == context["run_identity"], "TRACE_PRIOR_RUN_OBSERVATION", case_id)
            require(expectation["expected_enforcing_function"] == observation["observed_enforcing_function"], "TRACE_FUNCTION", case_id)
            require(expectation["expected_code"] == observation["observed_code"], "TRACE_CODE", case_id)
            reverse.setdefault(case_id, set()).add(clause_id)
    require(set(reverse) == set(expectation_by_case), "TRACE_REVERSE_MAPPING")
    require(matrix["case_set_identity"] == context["case_set_identity"], "TRACE_CASE_SET")
    require(matrix["expectation_identity"] == semantic_identity(expectations), "TRACE_EXPECTATION_IDENTITY")
    require(matrix["issuing_authority"] == authorities.load("trace_issuance_authority").value["authority_id"], "TRACE_ISSUER")
    return matrix_doc.semantic_sha256


# ---------- reviewer and compatibility trust ----------

def validate_future_authorities(review_receipt: Any, compatibility: Any, manifest: Any, authorities: AuthorityRepository) -> None:
    require_plain_data(review_receipt)
    require_plain_data(compatibility)
    require_plain_data(manifest)
    review_issuance = authorities.load("review_issuance_authority").value
    reviewer_trust = authorities.load("reviewer_trust_root").value
    compatibility_issuance = authorities.load("compatibility_verification").value
    compatibility_trust = authorities.load("compatibility_trust_root").value
    require(review_receipt == review_issuance["authorized_receipt"], "REVIEW_RECEIPT_NOT_ISSUED")
    require(review_receipt["reviewer_identity"] == reviewer_trust["reviewer_identity"], "REVIEWER_IDENTITY")
    require(review_receipt["reviewer_persona"] == reviewer_trust["reviewer_persona"], "REVIEWER_PERSONA")
    require("INDEPENDENT_REVIEW" in reviewer_trust["reviewer_capabilities"], "REVIEWER_CAPABILITY")
    issued = parse_timestamp(review_receipt["issued_timestamp"], "review issued")
    require(parse_timestamp(reviewer_trust["valid_from"], "review valid_from") <= issued <= parse_timestamp(reviewer_trust["valid_until"], "review valid_until"), "REVIEW_ISSUE_WINDOW")
    require(review_receipt["reviewer_identity"] != manifest["package_author_identity"], "REVIEW_SELF_REVIEW")
    require(review_receipt["decision"] == "ACCEPT", "REVIEW_DECISION")
    require(review_receipt["manifest_identity"] == semantic_identity(manifest), "REVIEW_MANIFEST")
    require(review_receipt["package_identity"] == manifest["package_identity"], "REVIEW_PACKAGE")
    require(review_receipt["script_identity"] == manifest["script_identity"], "REVIEW_SCRIPT")
    require(review_receipt["accepted_specification_identity"] == manifest["accepted_specification_identity"], "REVIEW_SPECIFICATION")
    require(review_receipt["trust_root_identity"] == authorities.load("reviewer_trust_root").semantic_sha256, "REVIEW_TRUST_ROOT")
    require(compatibility == compatibility_issuance, "COMPATIBILITY_NOT_ISSUED")
    require(compatibility["issuer"] == compatibility_trust["issuer_identity"], "COMPATIBILITY_ISSUER")
    require("ISSUE_COMPATIBILITY" in compatibility_trust["issuer_capabilities"], "COMPATIBILITY_CAPABILITY")
    compatibility_time = parse_timestamp(compatibility["issued_timestamp"], "compatibility issued")
    require(parse_timestamp(compatibility_trust["valid_from"], "compatibility valid_from") <= compatibility_time <= parse_timestamp(compatibility_trust["valid_until"], "compatibility valid_until"), "COMPATIBILITY_WINDOW")
    require(compatibility["final_state"] == "COMPATIBLE_WITH_ACCEPTED_SPECIFICATION", "COMPATIBILITY_STATE")
    require(compatibility["manifest_identity"] == semantic_identity(manifest), "COMPATIBILITY_MANIFEST")
    require(compatibility["verification_evidence"]["status"] == "PASS", "COMPATIBILITY_EVIDENCE")
    require(compatibility["verification_evidence"]["verifier_code_identity"] == compatibility_trust["verifier_code_identity"], "COMPATIBILITY_VERIFIER")
    require(review_receipt["compatibility_identity"] == semantic_identity(compatibility), "REVIEW_COMPATIBILITY")


# ---------- documentation claim authority ----------

CLAIM_WORDS = re.compile(r"\b(demonstrated|enforced|proven|verified)\b", re.IGNORECASE)
CLAIM_TAG = re.compile(r"\[CLAIM:(R5-[A-Z0-9-]+)\]")


def validate_document_text(role: str, text: Any, supported: dict[str, Any], current_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    require(type(text) is str, "DOCUMENT_TEXT_TYPE", role)
    require_plain_data(supported)
    require_plain_data(current_evidence)
    results = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not CLAIM_WORDS.search(line):
            continue
        tag = CLAIM_TAG.search(line)
        require(tag is not None, "DOCUMENT_CLAIM_UNBOUND", f"{role}:{line_number}")
        claim = supported.get(tag.group(1))
        require(claim is not None and claim["status"] == "PASS", "DOCUMENT_CLAIM_UNSUPPORTED", tag.group(1))
        require(current_evidence.get(tag.group(1)) == claim["evidence_identity"], "DOCUMENT_CLAIM_EVIDENCE", tag.group(1))
        results.append({"role": role, "line": line_number, "claim": tag.group(1), "evidence": claim["evidence_identity"]})
    lowered = text.lower()
    for forbidden in ("baseline capture is authorized", "deployment is authorized", "canonical incorporation is complete", "live-money trading is authorized"):
        require(forbidden not in lowered, "DOCUMENT_AUTHORIZATION_LEAKAGE", f"{role}:{forbidden}")
    return results


def validate_document_claims(authorities: AuthorityRepository, current_evidence: dict[str, Any]) -> str:
    require_plain_data(current_evidence)
    policy = authorities.load("document_claim_evidence").value
    supported = {item["claim_id"]: item for item in policy["claims"]}
    require(current_evidence == {key: item["evidence_identity"] for key, item in supported.items()}, "DOCUMENT_EVIDENCE_STALE")
    results = []
    for role in ("architecture_impact", "canonical_delta"):
        raw = authorities.load(role).raw
        text = raw.decode("utf-8", errors="strict")
        results.extend(validate_document_text(role, text, supported, current_evidence))
    return semantic_identity(results)


def validate_reconciliation(value: Any) -> None:
    require_plain_data(value)
    require(value.get("reconciliation") == "MATCHED", "RECONCILIATION_NOT_MATCHED")
    for key in ("all_cases_completed", "comparison_completed", "committed_result_exists", "terminal_receipt_valid", "comparison_authority_valid"):
        require(value.get(key) is True, "RECONCILIATION_FLAG", key)
    require(value.get("cleanup") == "PASS", "RECONCILIATION_CLEANUP")
