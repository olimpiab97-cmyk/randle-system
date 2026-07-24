from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "Architecture/Audits/2026-07-23_Current_Production_Baseline_Boundary_R7_Terminal_Authority_Implementation_DRAFT"
CASE_PATH = PACKAGE / "r7_real_case_definitions_DRAFT.json"
EXPECTATION_PATH = PACKAGE / "r7_independent_expectations_DRAFT.json"
F0 = "f0cfbce97e913a133530dd66a70326b1e03a0fb6"
OLD_ROOT = "Architecture/Audits/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def load_no_duplicates(data: bytes):
    def hook(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate key: {key}")
            value[key] = item
        return value

    return json.loads(data.decode("utf-8"), object_pairs_hook=hook)


def git_show(commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def main() -> int:
    case_bytes = CASE_PATH.read_bytes()
    expectation_bytes = EXPECTATION_PATH.read_bytes()
    cases_doc = load_no_duplicates(case_bytes)
    expectations_doc = load_no_duplicates(expectation_bytes)

    old_case_bytes = git_show(F0, f"{OLD_ROOT}/case_definitions_R7_DRAFT.json")
    old_expectation_bytes = git_show(F0, f"{OLD_ROOT}/independent_expectations_R7_DRAFT.json")
    old_cases = {row["case_id"]: row for row in load_no_duplicates(old_case_bytes)["cases"]}
    old_expectations = {row["case_id"]: row for row in load_no_duplicates(old_expectation_bytes)["cases"]}
    cases = cases_doc["cases"]
    expectations = expectations_doc["expectations"]
    expectation_by_id = {row["case_id"]: row for row in expectations}

    copied_source_cases = sum(row["source_case"] == old_cases[row["case_id"]] for row in cases)
    copied_expectation_rows = 0
    case_expectation_equal = 0
    for case in cases:
        case_id = case["case_id"]
        old = old_expectations[case_id]
        current = expectation_by_id[case_id]
        copied = (
            current["expected_outcome"] == old["expected_status"]
            and current["expected_response_classification"] == old["expected_code"]
            and current["expected_enforcing_function"] == old["expected_enforcing_function"]
            and current["expected_authority_source"] == old["expected_authority"]
            and current["expected_evidence_obligation"] == old["expected_evidence_obligation"]
        )
        copied_expectation_rows += copied
        case_expectation_equal += (
            case["expected_response_semantics"]["outcome"] == current["expected_outcome"]
            and case["expected_response_semantics"]["classification"] == current["expected_response_classification"]
            and case["source_case"]["expected_authority_source"] == current["expected_authority_source"]
            and case["source_case"]["expected_evidence_obligation"] == current["expected_evidence_obligation"]
        )

    r6_spec_path = "Architecture/15_Randle_AI_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT.md"
    r6_spec = git_show("87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94", r6_spec_path).decode("utf-8")
    outer_operations = {
        "ISSUE_R7_ATTEMPT",
        "EXECUTE_R7_RUN",
        "GET_R7_RECEIPT",
        "RECONCILE_R7_TERMINAL_RECEIPTS",
        "GET_R7_RECONCILIATION",
    }
    runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.cs"))
    obligation_fields = [
        "expected_evidence_obligation",
        "expected_ledger_delta",
        "forbidden_outcomes",
        "forbidden_side_effects",
        "required_evidence",
        "required_side_effects",
    ]

    result = {
        "artifact_type": "R7_INDEPENDENT_CASE_EXPECTATION_AUDIT_RESULT",
        "schema_version": "1.0.0",
        "status": "FAIL",
        "candidate_commit": "35add65e8900ce9a48c3a7175e5e61e5e0868a84",
        "case_artifact": {
            "path": CASE_PATH.relative_to(ROOT).as_posix(),
            "size": len(case_bytes),
            "sha256": sha256(case_bytes),
            "git_blob": git_blob(case_bytes),
            "count": len(cases),
        },
        "expectation_artifact": {
            "path": EXPECTATION_PATH.relative_to(ROOT).as_posix(),
            "size": len(expectation_bytes),
            "sha256": sha256(expectation_bytes),
            "git_blob": git_blob(expectation_bytes),
            "count": len(expectations),
        },
        "discarded_source": {
            "commit": F0,
            "case_blob": git_blob(old_case_bytes),
            "expectation_blob": git_blob(old_expectation_bytes),
            "source_cases_copied_exactly": copied_source_cases,
            "expectation_semantics_copied": copied_expectation_rows,
        },
        "independence": {
            "case_expectation_semantics_equal": case_expectation_equal,
            "unique_expected_authority_sources": len({row["expected_authority_source"] for row in expectations}),
            "expected_authority_values": sorted({row["expected_authority_source"] for row in expectations}),
        },
        "authority_mapping": {
            "r6_spec_blob": git_blob(r6_spec.encode("utf-8")),
            "r6_cpb_r6_clause_count": r6_spec.count("CPB-R6-"),
            "r6_cpb_r7_clause_count": r6_spec.count("CPB-R7-"),
            "cases_claiming_r7_requirement": sum(str(row["governing_requirement_id"]).startswith("R7-") for row in cases),
        },
        "coverage": {
            "operation_counts": dict(sorted(Counter(row["operation"] for row in cases).items())),
            "caller_class_counts": dict(sorted(Counter(row["caller_class"] for row in cases).items())),
            "meta_verification_count": sum(bool(row["source_case"]["meta_verification"]) for row in cases),
            "outer_terminal_operation_case_count": sum(row["operation"] in outer_operations for row in cases),
            "expected_acceptance_counts": dict(sorted(Counter(row["expected_acceptance"] for row in cases).items())),
        },
        "runtime_obligation_field_reference_counts": {
            field: runtime_text.count(f'"{field}"') for field in obligation_fields
        },
        "blocking_findings": [
            "All source cases and expectation semantics are imported from discarded sibling commit f0cfbce.",
            "The R6 blob cited for R7-01 through R7-15 contains no CPB-R7 clauses.",
            "The separate expectation file is not substantively independent from case construction or discarded implementation output.",
            "All cases use execute_case under a restricted service child; no case exercises the outer terminal/reconciliation protocol.",
            "Declared evidence, side-effect, durability, replay, and reconciliation obligations are not consumed by runtime verifier code.",
        ],
    }
    output = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if len(sys.argv) == 2:
        pathlib.Path(sys.argv[1]).write_text(output, encoding="utf-8", newline="\n")
    sys.stdout.write(output)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
