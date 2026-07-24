#!/usr/bin/env python3
"""Fail-closed pre/post-commit verifier for the corrected R7 package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any


BASE = "bb04ac54fb328516d0c785f4e6551e6a20d73759"
R6 = "87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94"
PROHIBITED = ("06c6805ed52a0d539a73088c097c60dec335462a", "8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6")
CASE_BLOB = "dae357d801cabdde7ca8a314c83380984161e687"
CASE_SHA256 = "58d6c043b857b6950d375724ef1f05b695028a3778ee47067284148c477b9214"
EXPECTATION_BLOB = "c21ea8f5ab4b54fc0d0638e9bb20df83c8a88f1d"
EXPECTATION_SHA256 = "7563a8b8af74f15ad226d61015d0946867fa1d18495143e8206600f1c3c81005"
POLICY_SHA256 = "76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b"
PACKAGE_REL = Path("Architecture/Audits/2026-07-23_Current_Production_Baseline_Boundary_R7_Terminal_Authority_Implementation_DRAFT")
AIA_REL = Path("Architecture/Impact_Assessments/2026-07-23_R7_Terminal_Authority_Implementation_Architecture_Impact_Assessment_DRAFT.md")


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def run_git(root: Path, *args: str, allowed: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[bytes]:
    command = ["git", "-c", f"safe.directory={root.as_posix()}", *args]
    result = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(result.returncode in allowed, f"GIT_EXIT:{args[0]}:{result.returncode}:{result.stderr.decode('utf-8', 'replace')}")
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_bytes(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    require(not data.startswith(b"\xef\xbb\xbf"), f"UTF8_BOM:{path}")
    text = data.decode("utf-8", errors="strict")
    require("\r" not in text, f"NON_LF_TEXT:{path}")
    require(unicodedata.normalize("NFC", text) == text, f"NON_NFC_TEXT:{path}")
    value = json.loads(text, object_pairs_hook=no_duplicate_pairs)
    require(isinstance(value, dict), f"JSON_ROOT:{path}")
    return value


def no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"DUPLICATE_JSON_KEY:{key}")
        result[key] = value
    return result


def resolve_ref(root_schema: dict[str, Any], reference: str) -> dict[str, Any]:
    require(reference.startswith("#/"), f"EXTERNAL_SCHEMA_REF:{reference}")
    value: Any = root_schema
    for token in reference[2:].split("/"):
        value = value[token.replace("~1", "/").replace("~0", "~")]
    require(isinstance(value, dict), f"SCHEMA_REF_OBJECT:{reference}")
    return value


def type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise RuntimeError(f"UNSUPPORTED_SCHEMA_TYPE:{expected}")


def validate_schema(value: Any, schema: Any, root_schema: dict[str, Any], path: str = "$") -> None:
    if schema is True:
        return
    if schema is False:
        raise RuntimeError(f"SCHEMA_FALSE:{path}")
    require(isinstance(schema, dict), f"SCHEMA_NODE:{path}")
    if "$ref" in schema:
        validate_schema(value, resolve_ref(root_schema, schema["$ref"]), root_schema, path)
        return
    if "oneOf" in schema:
        successes = 0
        for candidate in schema["oneOf"]:
            try:
                validate_schema(value, candidate, root_schema, path)
                successes += 1
            except RuntimeError:
                pass
        require(successes == 1, f"SCHEMA_ONE_OF:{path}:{successes}")
        return
    if "const" in schema:
        require(value == schema["const"] and type(value) is type(schema["const"]), f"SCHEMA_CONST:{path}")
    if "enum" in schema:
        require(any(value == item and type(value) is type(item) for item in schema["enum"]), f"SCHEMA_ENUM:{path}")
    expected_type = schema.get("type")
    if expected_type is not None:
        if isinstance(expected_type, list):
            require(any(type_matches(value, item) for item in expected_type), f"SCHEMA_TYPE:{path}")
        else:
            require(type_matches(value, expected_type), f"SCHEMA_TYPE:{path}:{expected_type}")
    if isinstance(value, str):
        if "minLength" in schema:
            require(len(value) >= schema["minLength"], f"SCHEMA_MIN_LENGTH:{path}")
        if "pattern" in schema:
            require(re.search(schema["pattern"], value) is not None, f"SCHEMA_PATTERN:{path}")
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema:
            require(value >= schema["minimum"], f"SCHEMA_MINIMUM:{path}")
    if isinstance(value, list):
        if "minItems" in schema:
            require(len(value) >= schema["minItems"], f"SCHEMA_MIN_ITEMS:{path}")
        if "maxItems" in schema:
            require(len(value) <= schema["maxItems"], f"SCHEMA_MAX_ITEMS:{path}")
        if schema.get("uniqueItems"):
            serialized = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            require(len(serialized) == len(set(serialized)), f"SCHEMA_UNIQUE_ITEMS:{path}")
        prefixes = schema.get("prefixItems", [])
        for index, item_schema in enumerate(prefixes):
            if index < len(value):
                validate_schema(value[index], item_schema, root_schema, f"{path}[{index}]")
        item_schema = schema.get("items")
        if item_schema is False:
            require(len(value) <= len(prefixes), f"SCHEMA_EXTRA_ARRAY_ITEM:{path}")
        elif item_schema is not None:
            start = len(prefixes) if prefixes else 0
            for index in range(start, len(value)):
                validate_schema(value[index], item_schema, root_schema, f"{path}[{index}]")
    if isinstance(value, dict):
        if "minProperties" in schema:
            require(len(value) >= schema["minProperties"], f"SCHEMA_MIN_PROPERTIES:{path}")
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            require(key in value, f"SCHEMA_REQUIRED:{path}.{key}")
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                validate_schema(item, properties[key], root_schema, f"{path}.{key}")
            elif additional is False:
                raise RuntimeError(f"SCHEMA_ADDITIONAL:{path}.{key}")
            elif isinstance(additional, dict):
                validate_schema(item, additional, root_schema, f"{path}.{key}")


def validate_instance(package: Path, instance_name: str, schema_name: str) -> None:
    instance = read_json(package / instance_name)
    schema = read_json(package / schema_name)
    require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"SCHEMA_DIALECT:{schema_name}")
    validate_schema(instance, schema, schema)


def changed_paths(root: Path) -> set[str]:
    head = run_git(root, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    committed: list[str] = []
    if head != BASE:
        committed = run_git(root, "diff", "--name-only", "--diff-filter=ACMR", BASE, head).stdout.decode("utf-8").splitlines()
    tracked = run_git(root, "diff", "--name-only", "--diff-filter=ACMR").stdout.decode("utf-8").splitlines()
    staged = run_git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR").stdout.decode("utf-8").splitlines()
    untracked = run_git(root, "ls-files", "--others", "--exclude-standard").stdout.decode("utf-8").splitlines()
    return {value.replace("\\", "/") for value in committed + tracked + staged + untracked if value}


def secret_scan(paths: list[Path]) -> dict[str, Any]:
    forbidden_suffixes = {".pfx", ".p12", ".pkcs12", ".key", ".jks"}
    patterns = {
        "private_pem": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "credential_assignment": re.compile(r"(?i)\b(?:password|api[_-]?key|access[_-]?token|client[_-]?secret)\b\s*[:=]\s*[\"'][^\"']{6,}[\"']"),
        "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    }
    findings: list[str] = []
    for path in paths:
        if path.suffix.lower() in forbidden_suffixes:
            findings.append(f"forbidden_suffix:{path}")
            continue
        data = path.read_bytes()
        require(b"\x00" not in data, f"BINARY_STAGED_FILE:{path}")
        text = data.decode("utf-8", errors="strict")
        for label, pattern in patterns.items():
            if pattern.search(text):
                findings.append(f"{label}:{path}")
    require(not findings, "SECRET_SCAN:" + "|".join(findings))
    return {"finding_count": 0, "pattern_count": len(patterns), "scanned_file_count": len(paths), "status": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", default=str(Path(__file__).resolve().parents[3]))
    args = parser.parse_args()
    root = Path(args.repository_root).resolve()
    package = root / PACKAGE_REL
    require(package.is_dir(), "PACKAGE_MISSING")

    head = run_git(root, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    base_ancestry = run_git(root, "merge-base", "--is-ancestor", BASE, "HEAD", allowed=(0, 1))
    require(base_ancestry.returncode == 0, "BASE_ANCESTRY")
    linear_commits = run_git(root, "rev-list", "--reverse", "--first-parent", f"{BASE}..HEAD").stdout.decode("ascii").split()
    prior = BASE
    for commit in linear_commits:
        parents = run_git(root, "show", "-s", "--format=%P", commit).stdout.decode("ascii").strip().split()
        require(len(parents) == 1 and parents[0] == prior, f"LINEAR_PARENT_AUTHORITY:{commit}")
        prior = commit
    require(prior == head, "LINEAR_HEAD_AUTHORITY")
    require(run_git(root, "rev-parse", f"{R6}^{{commit}}").stdout.decode("ascii").strip() == R6, "R6_RESOLUTION")
    require(run_git(root, "show", "-s", "--format=%T", R6).stdout.decode("ascii").strip() == "f9891562ea09d011d4d9803d9cf64b88ff1f2dbf", "R6_TREE")
    require(run_git(root, "show", "-s", "--format=%P", R6).stdout.decode("ascii").strip() == "c211870a8183e8f3e9ea9bf17fa34288b2c3000e", "R6_PARENT")
    require(run_git(root, "show", "-s", "--format=%T", BASE).stdout.decode("ascii").strip() == "b25b41d9cfb5a0dbfdb271e4519734f60a11ad80", "BASE_TREE")
    require(run_git(root, "show", "-s", "--format=%P", BASE).stdout.decode("ascii").strip() == R6, "BASE_PARENT")
    for commit in PROHIBITED:
        ancestry = run_git(root, "merge-base", "--is-ancestor", commit, "HEAD", allowed=(0, 1))
        require(ancestry.returncode == 1, f"PROHIBITED_ANCESTRY:{commit}")

    manifest = read_json(package / "implementation_manifest_R7_DRAFT.json")
    described_paths = {row["path"] for row in manifest["paths"]}
    manifest_path = manifest["manifest_path"]
    expected_paths = described_paths | {manifest_path}
    require(manifest["manifest_self_identity_model"] == "STAGED_OR_COMMITTED_GIT_OBJECT_VERIFIED_EXTERNALLY_TO_AVOID_RECURSION", "MANIFEST_SELF_MODEL")
    require(len(described_paths) == len(manifest["paths"]), "MANIFEST_PATH_DUPLICATE")
    require(len(expected_paths) == manifest["expected_changed_path_count"] == len(manifest["paths"]) + 1, "MANIFEST_PATH_COUNT")
    actual_paths = changed_paths(root)
    require(actual_paths == expected_paths, f"DELTA_PATH_SET:missing={sorted(expected_paths-actual_paths)}:extra={sorted(actual_paths-expected_paths)}")

    rows_by_path = {row["path"]: row for row in manifest["paths"]}
    for path_string in sorted(expected_paths):
        path = root / path_string
        require(path.is_file(), f"MANIFEST_FILE_MISSING:{path_string}")
        data = path.read_bytes()
        require(not data.startswith(b"\xef\xbb\xbf"), f"UTF8_BOM:{path_string}")
        text = data.decode("utf-8", errors="strict")
        require("\r" not in text, f"NON_LF_TEXT:{path_string}")
        require(unicodedata.normalize("NFC", text) == text, f"NON_NFC_TEXT:{path_string}")
        if path_string in rows_by_path:
            row = rows_by_path[path_string]
            require(row["mode"] == "100644", f"MANIFEST_MODE:{path_string}")
            require(row["size"] == len(data), f"MANIFEST_SIZE:{path_string}")
            require(row["raw_sha256"] == hashlib.sha256(data).hexdigest(), f"MANIFEST_SHA256:{path_string}")
            require(row["git_blob"] == git_blob_bytes(data), f"MANIFEST_GIT_BLOB:{path_string}")

    validate_instance(package, "r7_real_case_definitions_DRAFT.json", "r7_real_case_definitions_schema_DRAFT.json")
    validate_instance(package, "r7_independent_expectations_DRAFT.json", "r7_independent_expectations_schema_DRAFT.json")
    validate_instance(package, "r7i_b01_adversarial_probes_DRAFT.json", "r7i_b01_adversarial_probes_schema_DRAFT.json")
    validate_instance(package, "r7_terminal_authority_policy_DRAFT.json", "r7_terminal_authority_policy_schema_DRAFT.json")
    validate_instance(package, "r7_terminal_public_interface_coverage_DRAFT.json", "r7_terminal_public_interface_coverage_schema_DRAFT.json")

    cases_path = package / "r7_real_case_definitions_DRAFT.json"
    expectations_path = package / "r7_independent_expectations_DRAFT.json"
    policy_path = package / "r7_terminal_authority_policy_DRAFT.json"
    require(sha256(cases_path) == CASE_SHA256 and git_blob_bytes(cases_path.read_bytes()) == CASE_BLOB and cases_path.stat().st_size == 995804, "CASE_IDENTITY")
    require(sha256(expectations_path) == EXPECTATION_SHA256 and git_blob_bytes(expectations_path.read_bytes()) == EXPECTATION_BLOB and expectations_path.stat().st_size == 285399, "EXPECTATION_IDENTITY")
    require(sha256(policy_path) == POLICY_SHA256, "POLICY_IDENTITY")
    cases = read_json(cases_path)
    expectations = read_json(expectations_path)
    case_ids = [row["case_id"] for row in cases["cases"]]
    expectation_ids = [row["case_id"] for row in expectations["expectations"]]
    require(len(case_ids) == len(set(case_ids)) == 178 and case_ids == expectation_ids, "CASE_EXPECTATION_BIJECTION")
    require(sum(row["expected_acceptance"] == "ACCEPTED" for row in cases["cases"]) == 20, "POSITIVE_CASE_DERIVATION")
    require(sum(row["expected_acceptance"] == "REJECTED" for row in cases["cases"]) == 158, "NEGATIVE_CASE_DERIVATION")

    matrix = read_json(package / "r7_terminal_precommit_matrix_result_DRAFT.json")
    require(matrix["status"] == "PASS" and matrix["execution_count"] == 8 and matrix["reconciliation_count"] == 4, "MATRIX_STATUS")
    require(len(matrix["rows"]) == 4 and matrix["final_ledger"]["ledger_sequence"] > matrix["initial_ledger"]["ledger_sequence"], "MATRIX_LEDGER")
    uniqueness_fields = ["run_id", "run_nonce", "subject_run_id", "event_root", "event_source_locator", "observation_locator", "comparator_result_locator", "process_index_locator", "traceability_locator"]
    collected = {key: [] for key in uniqueness_fields}
    process_locators: list[str] = []
    process_nonces: list[str] = []
    terminals: list[str] = []
    reconciliations: list[str] = []
    for row in matrix["rows"]:
        require(row["checkout"]["head"] == BASE, "MATRIX_CHECKOUT_HEAD")
        require((row["checkout"]["path_length"] < 100) == (row["checkout"]["path_class"] == "SHORT"), "MATRIX_PATH_CLASS")
        require(row["checkout"]["status_before_stdout_sha256"] == row["checkout"]["status_after_stdout_sha256"] == hashlib.sha256(b"").hexdigest(), "MATRIX_CHECKOUT_CLEAN")
        for phase in ("CANDIDATE", "FRESH"):
            value = row["phases"][phase]
            require(value["public_verification"]["status"] == "VERIFIED", "MATRIX_PUBLIC_TERMINAL")
            terminals.append(value["receipt_locator"])
            process_locators.extend(value["process_receipt_locators"])
            process_nonces.extend(value["process_receipt_nonces"])
            for key in uniqueness_fields:
                collected[key].append(value[key])
        require(row["reconciliation"]["public_verification"]["status"] == "VERIFIED", "MATRIX_PUBLIC_RECONCILIATION")
        require(row["reconciliation"]["result"] == "SEMANTICALLY_EQUIVALENT_REAL_EXECUTIONS", "MATRIX_RECONCILIATION_SEMANTICS")
        reconciliations.append(row["reconciliation"]["locator"])
    for key, values in collected.items():
        require(len(values) == len(set(values)) == 8, f"MATRIX_UNIQUENESS:{key}")
    require(len(terminals) == len(set(terminals)) == 8, "MATRIX_TERMINAL_UNIQUENESS")
    require(len(reconciliations) == len(set(reconciliations)) == 4, "MATRIX_RECONCILIATION_UNIQUENESS")
    require(len(process_locators) == len(set(process_locators)) == 24, "MATRIX_PROCESS_LOCATOR_UNIQUENESS")
    require(len(process_nonces) == len(set(process_nonces)) == 24, "MATRIX_PROCESS_NONCE_UNIQUENESS")

    attacks = read_json(package / "r7i_b01_precommit_adversarial_result_DRAFT.json")
    require(attacks["status"] == "PASS" and attacks["probe_count"] == len(attacks["probe_results"]) == 25, "ATTACK_COUNT")
    require(attacks["outer_ledger_unchanged"] and attacks["initial_ledger"] == attacks["final_ledger"], "ATTACK_LEDGER")
    require(attacks["cleanup_complete"] and all(row["rejected"] and row["ledger_unchanged"] for row in attacks["probe_results"]), "ATTACK_REJECTION")
    require(not attacks["control"]["rejected"] and not attacks["control"]["discrepancy_codes"], "ATTACK_CONTROL")

    structural = read_json(package / "r7_structural_boundary_regression_result_DRAFT.json")
    require(structural["status"] == "PASS", "STRUCTURAL_STATUS")
    require(structural["principal_isolation"]["repository_write_access"] is False, "STRUCTURAL_REPOSITORY_DENIAL")
    require(structural["key_isolation"]["caller_key_open_denied"] and structural["key_isolation"]["caller_private_export_denied"], "STRUCTURAL_KEY")
    require(structural["durable_response_failure"]["success_response_absent"] and structural["durable_response_failure"]["ledger_delta"] == 1, "STRUCTURAL_DURABLE_RESPONSE")
    require(structural["service_stopped_and_restart"]["stopped_client_exit_code"] != 0, "STRUCTURAL_STOPPED_FAIL_CLOSED")
    require(all(structural["service_stopped_and_restart"][key] == 0 for key in ("offline_candidate_exit_code", "offline_fresh_exit_code", "offline_ledger_exit_code", "offline_reconciliation_exit_code")), "STRUCTURAL_OFFLINE_PUBLIC")
    require(structural["substitution_controls"]["copied_service_ledger_unchanged"] and structural["substitution_controls"]["governed_trust_unchanged"], "STRUCTURAL_SUBSTITUTION")

    build = read_json(package / "source_to_binary_build_receipt_R7_DRAFT.json")
    require(build["status"] == "BUILT_INSTALLED_SEMANTICALLY_REBUILT_NOT_ACCEPTED" and len(build["outputs"]) == 7, "BUILD_STATUS")
    for source in build["sources"]:
        path = root / source["path"]
        require(path.is_file(), f"BUILD_SOURCE_PATH:{source['path']}")
        if source["path"].startswith(PACKAGE_REL.as_posix() + "/"):
            source_bytes = path.read_bytes()
        else:
            committed_blob = run_git(root, "rev-parse", f"HEAD:{source['path']}").stdout.decode("ascii").strip()
            require(committed_blob == source["git_blob"], f"BUILD_INHERITED_SOURCE_BLOB:{source['path']}")
            source_bytes = run_git(root, "cat-file", "blob", committed_blob).stdout
        require(hashlib.sha256(source_bytes).hexdigest() == source["raw_sha256"] and git_blob_bytes(source_bytes) == source["git_blob"] and len(source_bytes) == source["size"], f"BUILD_SOURCE:{source['path']}")
    for output in build["outputs"]:
        require(output["semantic_equality"] is True and output["normalized_il_sha256"], f"BUILD_SEMANTICS:{output['name']}")
        if output["installed_path"] is not None:
            require(output["installed_sha256"] == output["reference_sha256"], f"BUILD_INSTALLED:{output['name']}")

    source_text = "\n".join((package / name).read_text(encoding="utf-8") for name in ("TerminalAuthorityR7Service_DRAFT.cs", "TerminalAuthorityR7Worker_DRAFT.cs"))
    for prohibited in ("RecordEvents", "ExecuteEnforcement"):
        require(prohibited not in source_text, f"SYNTHETIC_SOURCE_SURVIVED:{prohibited}")
    package_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in package.iterdir()
        if path.is_file() and path.name != Path(__file__).name
    )
    stale_identities = (
        "7e940c0a" + "eacf4569bf9b3a1dd3b061e1ef759d458e162df79df0c803a8717050",
        "9ca4657a" + "abe60a85ce80a13662fae9218899109141fcc403c06493979d09ca80",
        "ecca1ffc" + "062775e1cadd9b169cf50960b1c18612cbb0a5d5aab82d143621f8a4",
    )
    for stale in stale_identities:
        require(stale not in package_text, f"STALE_SYNTHETIC_IDENTITY:{stale}")
    require(re.search(r"(?im)^(?:status|disposition)\s*:\s*(?:APPROVED|ACCEPTED|PRODUCTION READY|DEPLOYED)\s*$", package_text) is None, "FORBIDDEN_AUTHORIZATION_CLAIM")

    scanned_paths = [root / value for value in sorted(expected_paths)]
    secret_result = secret_scan(scanned_paths)
    result = {
        "artifact_type": "R7_PACKAGE_VERIFICATION_RESULT",
        "case_count": 178,
        "changed_path_count": len(actual_paths),
        "head": head,
        "matrix_execution_count": 8,
        "matrix_reconciliation_count": 4,
        "prohibited_ancestry_absent": True,
        "r7i_b01_probe_count": 25,
        "schema_version": "7.1.0-DRAFT",
        "secret_scan": secret_result,
        "status": "PASS_NOT_ACCEPTANCE",
    }
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write(type(exc).__name__ + ": " + str(exc) + "\n")
        raise SystemExit(1)
