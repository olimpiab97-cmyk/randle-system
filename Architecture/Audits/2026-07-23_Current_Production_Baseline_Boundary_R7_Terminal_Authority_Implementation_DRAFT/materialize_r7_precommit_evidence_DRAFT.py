#!/usr/bin/env python3
"""Materialize reviewable public summaries from immutable pre-commit evidence."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
from typing import Any


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON_OBJECT:{path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def source_descriptor(path: Path, root: Path) -> dict[str, Any]:
    return {
        "git_blob": git_blob(path),
        "path": path.relative_to(root).as_posix(),
        "raw_sha256": sha256(path),
        "size": path.stat().st_size,
    }


def write_json(path: Path, value: Any) -> None:
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))


def capture_descriptor(path: Path) -> dict[str, Any]:
    return {"diagnostic_path": str(path), "raw_sha256": sha256(path), "size": path.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--adversarial", required=True)
    parser.add_argument("--structural", required=True)
    parser.add_argument("--semantic", required=True)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--package-root", required=True)
    args = parser.parse_args()

    repository_root = Path(args.repository_root).resolve()
    package_root = Path(args.package_root).resolve()
    matrix_path = Path(args.matrix).resolve()
    adversarial_path = Path(args.adversarial).resolve()
    structural_path = Path(args.structural).resolve()
    semantic_path = Path(args.semantic).resolve()
    require(package_root.is_relative_to(repository_root), "PACKAGE_OUTSIDE_REPOSITORY")

    matrix = read_json(matrix_path)
    adversarial = read_json(adversarial_path)
    structural = read_json(structural_path)
    semantic = read_json(semantic_path)
    cases = read_json(package_root / "r7_real_case_definitions_DRAFT.json")
    expectations = read_json(package_root / "r7_independent_expectations_DRAFT.json")
    probe_definitions = read_json(package_root / "r7i_b01_adversarial_probes_DRAFT.json")
    policy = read_json(package_root / "r7_terminal_authority_policy_DRAFT.json")

    require(matrix.get("status") == "PASS" and matrix.get("execution_count") == len(policy["allowed_configurations"]) * 2, "MATRIX_INPUT")
    require(matrix.get("reconciliation_count") == len(policy["allowed_configurations"]), "MATRIX_RECONCILIATIONS")
    require(adversarial.get("status") == "PASS" and len(adversarial["probe_results"]) == probe_definitions["probe_count"] == 25, "ADVERSARIAL_INPUT")
    require(structural.get("status") == "PASS", "STRUCTURAL_INPUT")
    require(semantic.get("status") == "PASS" and len(semantic["outputs"]) == 7, "SEMANTIC_INPUT")
    require(cases["case_count"] == expectations["case_count"] == 178, "AUTHORITY_COUNT")

    matrix_rows: list[dict[str, Any]] = []
    for row in matrix["rows"]:
        phase_summaries: dict[str, Any] = {}
        for phase in ("CANDIDATE", "FRESH"):
            source = row["phases"][phase]
            phase_summaries[phase] = {
                "event_root": source["terminal_summary"]["event_root"],
                "event_source_locator": source["terminal_summary"]["event_source_locator"],
                "observation_locator": source["terminal_summary"]["observation_locator"],
                "comparator_result_locator": source["terminal_summary"]["comparator_result_locator"],
                "process_index_locator": source["terminal_summary"]["process_index_locator"],
                "process_receipt_locators": source["process_receipt_locators"],
                "process_receipt_nonces": source["process_receipt_nonces"],
                "public_verification": source["public_verification"],
                "receipt_identity": source["receipt_identity"],
                "receipt_locator": source["receipt_locator"],
                "run_id": source["terminal_summary"]["run_id"],
                "run_nonce": source["terminal_summary"]["run_nonce"],
                "subject_process_id": source["terminal_summary"]["subject_process_id"],
                "subject_run_id": source["terminal_summary"]["subject_run_id"],
                "traceability_locator": source["terminal_summary"]["traceability_locator"],
            }
        matrix_rows.append({
            "attempt_id": row["attempt_id"],
            "checkout": {
                "autocrlf": row["checkout"]["autocrlf"],
                "eol_stdout_sha256": row["checkout"]["eol_capture"]["stdout_sha256"],
                "head": row["checkout"]["head"],
                "path": row["checkout"]["path"],
                "path_class": row["checkout"]["path_class"],
                "path_length": row["checkout"]["path_length"],
                "status_after_stdout_sha256": row["checkout"]["status_after_capture"]["stdout_sha256"],
                "status_before_stdout_sha256": row["checkout"]["status_before_capture"]["stdout_sha256"],
            },
            "configuration": row["configuration"],
            "phases": phase_summaries,
            "reconciliation": {
                "identity": row["reconciliation"]["identity"],
                "locator": row["reconciliation"]["locator"],
                "process_nonce": row["reconciliation"]["process_nonce"],
                "process_receipt_locator": row["reconciliation"]["process_receipt_locator"],
                "public_verification": row["reconciliation"]["public_verification"],
                "result": row["reconciliation"]["result"],
            },
        })

    matrix_summary = {
        "artifact_type": "R7_REAL_EXECUTION_PRECOMMIT_MATRIX_RESULT",
        "authority_status": "IMPLEMENTATION_EVIDENCE_NOT_ACCEPTANCE",
        "case_definition": policy["case_authority"],
        "checkout_commit": matrix["checkout_commit"],
        "checkout_count": matrix["checkout_count"],
        "execution_count": matrix["execution_count"],
        "expectation": policy["expectation_authority"],
        "final_ledger": matrix["final_ledger"],
        "initial_ledger": matrix["initial_ledger"],
        "policy_sha256": sha256(package_root / "r7_terminal_authority_policy_DRAFT.json"),
        "reconciliation_count": matrix["reconciliation_count"],
        "rows": matrix_rows,
        "schema_version": "7.1.0-DRAFT",
        "source_evidence": capture_descriptor(matrix_path),
        "status": "PASS",
        "uniqueness": matrix["uniqueness"],
    }
    write_json(package_root / "r7_terminal_precommit_matrix_result_DRAFT.json", matrix_summary)

    attack_by_id = {row["probe_id"]: row for row in probe_definitions["probes"]}
    attack_rows = []
    for result in adversarial["probe_results"]:
        definition = attack_by_id[result["probe_id"]]
        attack_rows.append({
            "attack": definition["attack"],
            "discrepancy_codes": result["discrepancy_codes"],
            "ledger_unchanged": result["ledger_unchanged"],
            "method": result["method"],
            "probe_id": result["probe_id"],
            "rejected": result["rejected"],
            "status": result["status"],
            "stderr_sha256": result["stderr_sha256"],
            "stdout_sha256": result["stdout_sha256"],
        })
    adversarial_summary = {
        "artifact_type": "R7I_B01_PRECOMMIT_ADVERSARIAL_RESULT",
        "authority_status": "IMPLEMENTATION_EVIDENCE_NOT_ACCEPTANCE",
        "case_authority_sha256": adversarial["case_authority_sha256"],
        "cleanup_count": len(adversarial["cleanup"]),
        "cleanup_complete": all(row["removed"] for row in adversarial["cleanup"]),
        "control": adversarial["control"],
        "expectation_authority_sha256": adversarial["expectation_authority_sha256"],
        "final_ledger": adversarial["final_ledger"],
        "initial_ledger": adversarial["initial_ledger"],
        "outer_ledger_unchanged": adversarial["outer_ledger_unchanged"],
        "probe_count": len(attack_rows),
        "probe_results": attack_rows,
        "schema_version": "7.1.0-DRAFT",
        "source_evidence": capture_descriptor(adversarial_path),
        "status": "PASS",
    }
    write_json(package_root / "r7i_b01_precommit_adversarial_result_DRAFT.json", adversarial_summary)

    sresults = structural["results"]
    structural_summary = {
        "artifact_type": "R7_STRUCTURAL_BOUNDARY_PRECOMMIT_RESULT",
        "append_before_response": sresults["append_before_response"],
        "candidate_fresh_replay": sresults["candidate_fresh_replay"],
        "durable_response_failure": {
            "ledger_delta": sresults["durable_response_failure"]["ledger_delta"],
            "success_response_absent": sresults["durable_response_failure"]["success_response_absent"],
            "task_created_blocker_removed": sresults["durable_response_failure"]["task_created_blocker_removed"],
        },
        "final_identity": sresults["final_identity"],
        "ipc_integrity": {
            "disconnected_partial_exit_code": sresults["ipc_integrity"]["disconnected_partial"]["exit_code"],
            "negative_probe_count": len(sresults["ipc_integrity"]["negative_probes"]),
            "negative_probes": sresults["ipc_integrity"]["negative_probes"],
            "partial_request_exit_code": sresults["ipc_integrity"]["partial_request"]["exit_code"],
            "pipe_acl_exit_code": sresults["ipc_integrity"]["pipe_acl_probe"]["exit_code"],
            "request_limit": sresults["ipc_integrity"]["request_limit"],
        },
        "key_isolation": sresults["key_isolation"],
        "ledger_integrity": sresults["ledger_integrity"],
        "principal_isolation": {
            "qsidtype": sresults["principal_isolation"]["qsidtype"],
            "qprivs": sresults["principal_isolation"]["qprivs"],
            "repository_write_access": sresults["principal_isolation"]["repository_write_access"],
            "service_sid": sresults["principal_isolation"]["service_sid"],
        },
        "replay_retry_idempotency": sresults["replay_retry_idempotency"],
        "schema_version": "7.1.0-DRAFT",
        "service_stopped_and_restart": {
            "offline_candidate_exit_code": sresults["service_stopped_and_restart"]["offline_candidate"]["exit_code"],
            "offline_fresh_exit_code": sresults["service_stopped_and_restart"]["offline_fresh"]["exit_code"],
            "offline_ledger_exit_code": sresults["service_stopped_and_restart"]["offline_ledger"]["exit_code"],
            "offline_reconciliation_exit_code": sresults["service_stopped_and_restart"]["offline_reconciliation"]["exit_code"],
            "post_restart_checkpoint": sresults["service_stopped_and_restart"]["post_restart_checkpoint"],
            "pre_stop_checkpoint": sresults["service_stopped_and_restart"]["pre_stop_checkpoint"],
            "stopped_client_exit_code": sresults["service_stopped_and_restart"]["stopped_client"]["exit_code"],
        },
        "source_evidence": capture_descriptor(structural_path),
        "status": "PASS",
        "substitution_controls": {
            "altered_trust_exit_code": sresults["substitution_controls"]["altered_trust"]["exit_code"],
            "copied_service_ledger_unchanged": sresults["substitution_controls"]["copied_service_ledger_unchanged"],
            "copied_service_removed": sresults["substitution_controls"]["copied_service_removed"],
            "governed_trust_unchanged": sresults["substitution_controls"]["governed_trust_unchanged"],
        },
    }
    write_json(package_root / "r7_structural_boundary_regression_result_DRAFT.json", structural_summary)

    roles = {
        "RandleTerminalAuthority.exe": ("RESTRICTED_EXTERNAL_TERMINAL_AUTHORITY", "anycpu"),
        "RandleTerminalAuthorityR7Worker.exe": ("MEASURED_OBSERVER_COMPARATOR_RECONCILER", "anycpu"),
        "RandleTerminalAuthorityR7Client.exe": ("NONAUTHORITATIVE_PUBLIC_CLIENT", "anycpu"),
        "RandleTerminalAuthorityR7PublicVerifier.exe": ("PUBLIC_ONLY_GRAPH_AND_LEDGER_VERIFIER", "anycpu"),
        "RandleTerminalAuthorityR7AdversarialProbe.exe": ("NONAUTHORITATIVE_STRUCTURAL_PROBE", "anycpu"),
        "RandleTerminalAuthorityR7FixtureHost.exe": ("CLOSED_MEASURED_JUNCTION_FIXTURE", "x64"),
        "RandleTerminalAuthorityR7SubjectLauncher.exe": ("MEASURED_SUBJECT_LAUNCHER", "x64"),
    }
    binary_rows = []
    for row in semantic["outputs"]:
        role, platform = roles[row["name"]]
        binary_rows.append(row | {"platform": platform, "role": role})
    source_paths = [
        repository_root / "Architecture" / "Audits" / "2026-07-23_Terminal_Authority_Infrastructure_Provisioning_DRAFT" / "TerminalAuthorityCommon_DRAFT.cs",
        package_root / "TerminalAuthorityR7Common_DRAFT.cs",
        package_root / "TerminalAuthorityR7Service_DRAFT.cs",
        package_root / "TerminalAuthorityR7Worker_DRAFT.cs",
        package_root / "TerminalAuthorityR7Client_DRAFT.cs",
        package_root / "TerminalAuthorityR7PublicVerifier_DRAFT.cs",
        package_root / "TerminalAuthorityR7AdversarialProbe_DRAFT.cs",
        package_root / "TerminalAuthorityR7FixtureHost_DRAFT.cs",
        package_root / "TerminalAuthorityR7SubjectLauncher_DRAFT.cs",
    ]
    build_receipt = {
        "artifact_type": "R7_TERMINAL_AUTHORITY_SOURCE_TO_BINARY_BUILD_RECEIPT",
        "build_driver": source_descriptor(package_root / "build_r7_binaries_DRAFT.ps1", repository_root),
        "compiler_options": ["/nologo", "/target:exe", "/optimize+", "/platform:anycpu-or-x64-per-output"],
        "compiler_path": semantic["compiler_path"],
        "compiler_sha256": semantic["compiler_sha256"],
        "nondeterminism_control": {
            "excluded_fields": ["MVID", "runtime load image base"],
            "method": semantic["normalization"],
            "note": "Legacy compiler lacks /deterministic; exact installation bytes equal captured reference bytes and normalized token/byte IL equals a fresh rebuild.",
        },
        "outputs": binary_rows,
        "schema_version": "7.1.0-DRAFT",
        "semantic_verification_source": capture_descriptor(semantic_path),
        "sources": [source_descriptor(path, repository_root) for path in source_paths],
        "status": "BUILT_INSTALLED_SEMANTICALLY_REBUILT_NOT_ACCEPTED",
    }
    write_json(package_root / "source_to_binary_build_receipt_R7_DRAFT.json", build_receipt)

    case_counts = collections.Counter(row["governing_requirement_id"] for row in cases["cases"])
    interface_counts = collections.Counter(row["public_interface"] for row in cases["cases"])
    coverage = {
        "artifact_type": "R7_REAL_PUBLIC_INTERFACE_COVERAGE",
        "authority_status": "IMPLEMENTATION_EVIDENCE_NOT_ACCEPTANCE",
        "case_definition_git_blob": policy["case_authority"]["git_blob"],
        "case_definition_sha256": policy["case_authority"]["raw_sha256"],
        "case_count": cases["case_count"],
        "case_execution_count": matrix["execution_count"] * cases["case_count"],
        "expected_acceptance_counts": dict(sorted(collections.Counter(row["expected_acceptance"] for row in cases["cases"]).items())),
        "expectation_git_blob": policy["expectation_authority"]["git_blob"],
        "expectation_sha256": policy["expectation_authority"]["raw_sha256"],
        "interface_counts": dict(sorted(interface_counts.items())),
        "matrix_execution_count": matrix["execution_count"],
        "reconciliation_count": matrix["reconciliation_count"],
        "requirement_counts": dict(sorted(case_counts.items())),
        "r7i_b01_attack_count": len(adversarial["probe_results"]),
        "schema_version": "7.1.0-DRAFT",
        "status": "PASS",
    }
    write_json(package_root / "r7_terminal_public_interface_coverage_DRAFT.json", coverage)

    host_identity = {
        "artifact_type": "R7_TERMINAL_AUTHORITY_HOST_IDENTITY_RECEIPT",
        "authority_status": "IMPLEMENTATION_EVIDENCE_NOT_ACCEPTANCE",
        "certificate_thumbprint": sresults["key_isolation"]["certificate_thumbprint"],
        "final_ledger_root": matrix["final_ledger"]["ledger_root"],
        "final_ledger_sequence": matrix["final_ledger"]["ledger_sequence"],
        "interface_version": policy["interface_version"],
        "key_caller_open_denied": sresults["key_isolation"]["caller_key_open_denied"],
        "key_caller_private_export_denied": sresults["key_isolation"]["caller_private_export_denied"],
        "ledger_id": policy["ledger_id"],
        "policy_sha256": sha256(package_root / "r7_terminal_authority_policy_DRAFT.json"),
        "provisioned_original_service_sha256": "632afaeeaf15c26ac057b34692ac672e03bc02f60fbb35177c378736b5e316ba",
        "public_trust_sha256": sresults["final_identity"]["public_trust_sha256"],
        "repository_write_access": sresults["principal_isolation"]["repository_write_access"],
        "restricted_service_sid": sresults["principal_isolation"]["service_sid"],
        "schema_version": "7.1.0-DRAFT",
        "service_sha256": sresults["final_identity"]["service_sha256"],
        "service_state": sresults["final_identity"]["service_state"],
        "status": "VERIFIED_NOT_ACCEPTED",
        "worker_sha256": sresults["final_identity"]["worker_sha256"],
    }
    write_json(package_root / "r7_terminal_host_identity_receipt_DRAFT.json", host_identity)

    verification = {
        "artifact_type": "R7_TERMINAL_AUTHORITY_PRECOMMIT_VERIFICATION_RESULTS",
        "adversarial": {"probe_count": len(adversarial["probe_results"]), "source": capture_descriptor(adversarial_path), "status": adversarial["status"]},
        "authority_status": "IMPLEMENTATION_EVIDENCE_NOT_ACCEPTANCE",
        "case_count": cases["case_count"],
        "matrix": {"execution_count": matrix["execution_count"], "reconciliation_count": matrix["reconciliation_count"], "source": capture_descriptor(matrix_path), "status": matrix["status"]},
        "schema_version": "7.1.0-DRAFT",
        "source_to_binary": {"binary_count": len(semantic["outputs"]), "source": capture_descriptor(semantic_path), "status": semantic["status"]},
        "status": "PASS_PRECOMMIT_NOT_ACCEPTANCE",
        "structural": {"negative_ipc_probe_count": len(sresults["ipc_integrity"]["negative_probes"]), "source": capture_descriptor(structural_path), "status": structural["status"]},
    }
    write_json(package_root / "r7_terminal_verification_results_DRAFT.json", verification)

    role_overrides = {
        "R7_TERMINAL_AUTHORITY_IMPLEMENTATION_REPORT_DRAFT.md": "IMPLEMENTATION_EVIDENCE_REPORT",
        "CANONICAL_DELTA_DRAFT.md": "PROPOSAL_ONLY_CANONICAL_DELTA",
        "R7_TERMINAL_AUTHORITY_WORKFLOW_SPECIFICATION_DRAFT.md": "DRAFT_GOVERNED_WORKFLOW",
        "R7_TERMINAL_REQUIREMENT_MATRIX_DRAFT.md": "BIDIRECTIONAL_TRACEABILITY",
        "r7_real_case_definitions_DRAFT.json": "IMMUTABLE_CASE_DEFINITIONS",
        "r7_independent_expectations_DRAFT.json": "IMMUTABLE_INDEPENDENT_EXPECTATIONS",
        "r7i_b01_adversarial_probes_DRAFT.json": "IMMUTABLE_ATTACK_DEFINITIONS",
        "r7_terminal_precommit_matrix_result_DRAFT.json": "PRECOMMIT_REAL_EXECUTION_MATRIX",
        "r7i_b01_precommit_adversarial_result_DRAFT.json": "PRECOMMIT_SYNTHETIC_ATTACK_RESULTS",
        "r7_structural_boundary_regression_result_DRAFT.json": "PRECOMMIT_STRUCTURAL_RESULTS",
        "source_to_binary_build_receipt_R7_DRAFT.json": "SOURCE_TO_BINARY_EVIDENCE",
    }
    package_paths = []
    for path in sorted(package_root.iterdir(), key=lambda item: item.name.lower()):
        require(path.is_file(), f"UNEXPECTED_PACKAGE_DIRECTORY:{path.name}")
        if path.name == "implementation_manifest_R7_DRAFT.json":
            continue
        role = role_overrides.get(path.name)
        if role is None:
            role = "SOURCE" if path.suffix.lower() in (".cs", ".py", ".ps1") else "SCHEMA_OR_POLICY" if "schema" in path.name.lower() or "policy" in path.name.lower() else "PUBLIC_IMPLEMENTATION_ARTIFACT"
        row = source_descriptor(path, repository_root)
        row.update({"mode": "100644", "role": role})
        package_paths.append(row)
    aia = repository_root / "Architecture" / "Impact_Assessments" / "2026-07-23_R7_Terminal_Authority_Implementation_Architecture_Impact_Assessment_DRAFT.md"
    attributes = repository_root / ".gitattributes"
    attributes_row = source_descriptor(attributes, repository_root)
    attributes_row.update({"mode": "100644", "role": "LINE_ENDING_PIN"})
    aia_row = source_descriptor(aia, repository_root)
    aia_row.update({"mode": "100644", "role": "PROPOSAL_ONLY_ARCHITECTURE_IMPACT_ASSESSMENT"})
    manifest_paths = [attributes_row, aia_row] + package_paths
    manifest_path = (package_root / "implementation_manifest_R7_DRAFT.json").relative_to(repository_root).as_posix()
    manifest = {
        "artifact_type": "R7_TERMINAL_AUTHORITY_IMPLEMENTATION_MANIFEST",
        "authorized_ancestry": {
            "direct_parent": "bb04ac54fb328516d0c785f4e6551e6a20d73759",
            "prohibited_ancestors": ["06c6805ed52a0d539a73088c097c60dec335462a", "8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6"],
            "provisioning_parent": "87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94",
        },
        "expected_changed_path_count": len(manifest_paths) + 1,
        "manifest_path": manifest_path,
        "manifest_self_identity_model": "STAGED_OR_COMMITTED_GIT_OBJECT_VERIFIED_EXTERNALLY_TO_AVOID_RECURSION",
        "paths": manifest_paths,
        "schema_version": "7.1.0-DRAFT",
        "status": "IMPLEMENTED_NOT_ACCEPTED",
    }
    write_json(package_root / "implementation_manifest_R7_DRAFT.json", manifest)
    print(json.dumps({"generated": 8, "manifest_path_count": len(manifest_paths) + 1, "status": "MATERIALIZED"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
