#!/usr/bin/env python3
"""Synthetic, draft-only verification harness for the boundary specification."""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

sys.dont_write_bytecode = True

from boundary_verifier_DRAFT import (  # noqa: E402
    ALLOWED_OUTCOMES,
    LONG_PATH_ARTIFACTS,
    QUESTIONED_TESTS,
    BoundaryError,
    compare_declared_inventory,
    derive_selection,
    ensure_all_questioned_tests,
    semantic_identity,
    sha256_bytes,
    validate_attempt_ledger,
    validate_evidence_bindings,
    validate_freeze,
    validate_governance_package,
    validate_inventory_security,
    validate_multi_pass,
    validate_registries,
    validate_rule_registry,
    validate_test_classification,
    verify_inventory,
    verify_long_path_artifacts,
    verify_manifest,
)
from inventory_generator_DRAFT import (  # noqa: E402
    InventoryError,
    enumerate_inventory,
    extended_length_path,
)
from selection_engine_DRAFT import derive_repository_selection  # noqa: E402


PACKAGE = Path(__file__).resolve().parent
SCHEMA_FILES = (
    "capture_boundary_schema_DRAFT.json",
    "include_registry_schema_DRAFT.json",
    "exclusion_registry_schema_DRAFT.json",
    "freeze_receipt_schema_DRAFT.json",
    "attempt_ledger_schema_DRAFT.json",
    "durable_manifest_schema_DRAFT.json",
    "durable_evidence_binding_registry_schema_DRAFT.json",
    "test_classification_schema_DRAFT.json",
)


def load_json(name: str) -> Any:
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


RULES = load_json("selection_rule_registry_DRAFT.json")
INCLUDES = load_json("include_registry_DRAFT.json")
EXCLUSIONS = load_json("exclusion_registry_DRAFT.json")


def expect_reject(codes: str | set[str], operation: Callable[[], Any]) -> None:
    accepted = {codes} if isinstance(codes, str) else codes
    try:
        operation()
    except BoundaryError as exc:
        if exc.code not in accepted:
            raise AssertionError(f"expected {sorted(accepted)}, received {exc.code}: {exc.detail}") from exc
        return
    raise AssertionError(f"expected rejection {sorted(accepted)}")


def repository_include_entries() -> list[dict[str, Any]]:
    return [entry for entry in INCLUDES["entries"] if entry["path_kind"] == "repository-relative"]


def base_files() -> list[dict[str, Any]]:
    files = []
    for entry in repository_include_entries():
        signals = ["governed_production_recovery"]
        if entry["class"] == "production-test":
            signals = ["imports_captured_runtime"]
        files.append({"path": entry["path"], "class": entry["class"], "signals": signals})
    files.extend(
        [
            {"path": "Architecture/history.md", "class": "governance-only", "signals": []},
            {"path": "Backups/old_entry_agent.py", "class": "backup", "signals": []},
            {"path": ".pytest_cache/v/cache/nodeids", "class": "cache", "signals": []},
        ]
    )
    return files


def base_selection() -> list[str]:
    return derive_selection(base_files(), INCLUDES, EXCLUSIONS, RULES)


def clone_registry(registry: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(registry)


def make_include(path: str, entry_id: str = "INC-FIXTURE") -> dict[str, Any]:
    return {
        "authority_status": "DRAFT_FIXTURE",
        "class": "production-test",
        "entry_id": entry_id,
        "evidence_references": ["FIXTURE:evidence"],
        "expected_existence_state": "MUST_EXIST_AT_FREEZE",
        "path": path,
        "path_kind": "repository-relative",
        "rationale": "Synthetic governed fixture inclusion with deterministic evidence and recovery relevance.",
        "required_capture_form": "RAW_AND_GIT_OBJECT",
        "selection_rule_id": "PRODUCTION_TEST_CLOSURE",
    }


def make_exclusion(target: str, match_type: str = "exact", entry_id: str = "EXC-FIXTURE") -> dict[str, Any]:
    return {
        "authority": "DRAFT_FIXTURE",
        "class": "temporary-cache-build-editor",
        "comparable_path_consistency_proof": "Synthetic comparable paths all receive the identical narrow fixture predicate.",
        "entry_id": entry_id,
        "evidence": ["FIXTURE:evidence"],
        "exclusion_rule_id": "GOVERNED_EXCLUSION",
        "fail_closed_behavior": "STOP when a conflicting production relationship is present.",
        "match_type": match_type,
        "path_or_pattern": target,
        "rationale": "Synthetic exclusion used only to prove deterministic registry validation behavior.",
        "reviewer_status": "PENDING_INDEPENDENT_REVIEW",
    }


def selection_identity(paths: list[str]) -> str:
    return semantic_identity({"paths": paths})


def repository_fixture_selection(*, new_test: str | None = None, unresolved_dynamic: bool = False) -> dict[str, Any]:
    with FixtureRoot() as fixture:
        for entry in repository_include_entries():
            path = entry["path"]
            if path == "EntryAgent/entry_agent.py":
                data = b"from EntryAgent import helper\n"
            elif path == "rithmic_live_listener.py":
                data = b"from EntryAgent import helper\n"
            elif path.endswith(".py"):
                data = b"from EntryAgent import entry_agent\n"
            else:
                data = b"# synthetic governed launcher\n"
            fixture.write(path, data)
        fixture.write("EntryAgent/helper.py", b"VALUE = 1\n")
        fixture.write("Backups/old_module.py", b"OLD = True\n")
        if new_test:
            fixture.write(new_test, b"from EntryAgent import entry_agent\n")
        if unresolved_dynamic:
            fixture.write("EntryAgent/dynamic_helper.py", b"import importlib\nname = 'EntryAgent.helper'\nimportlib.import_module(name)\n")
            fixture.write("EntryAgent/entry_agent.py", b"from EntryAgent import dynamic_helper\n")
        return derive_repository_selection(fixture.root, INCLUDES, EXCLUSIONS, RULES)


def _write_long(path: Path, data: bytes) -> None:
    os.makedirs(extended_length_path(path.parent), exist_ok=True)
    with open(extended_length_path(path), "wb") as handle:
        handle.write(data)


class FixtureRoot:
    def __enter__(self) -> "FixtureRoot":
        self._temporary = tempfile.TemporaryDirectory(prefix="randle_boundary_spec_")
        self.root = Path(self._temporary.name)
        (self.root / ".boundary_fixture_root").write_bytes(b"draft synthetic fixture\n")
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._temporary.cleanup()

    def write(self, relative: str, data: bytes) -> Path:
        path = self.root.joinpath(*relative.split("/"))
        _write_long(path, data)
        return path


def inventory_records(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"path": item["canonical_path"], "size": item["size"], "sha256": item["sha256"]}
        for item in inventory["artifacts"]
    ]


def manifest_from_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifacts": [
            {"canonical_path": item["canonical_path"], "size": item["size"], "sha256": item["sha256"]}
            for item in inventory["artifacts"]
        ],
        "total_artifact_count": inventory["total_artifact_count"],
        "total_bytes": inventory["total_bytes"],
    }


def build_long_inventory(include_both: bool = True) -> dict[str, Any]:
    fixture = FixtureRoot()
    fixture.__enter__()
    try:
        fixture.write(LONG_PATH_ARTIFACTS[0], b"pine-one\n")
        if include_both:
            fixture.write(LONG_PATH_ARTIFACTS[1], b"pine-two\n")
        fixture.write("ordinary/status.txt", b"stable\n")
        return enumerate_inventory(fixture.root)
    finally:
        fixture.__exit__(None, None, None)


def freeze_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    h = "A" * 64
    g = "1" * 40
    receipt = {
        "attempt_id": "capture-20260721-fixture-001",
        "specification_commit": g,
        "specification_tree": "2" * 40,
        "specification_document_blob": "3" * 40,
        "include_registry_blob": "4" * 40,
        "exclusion_registry_blob": "5" * 40,
        "selection_script_blob": "6" * 40,
        "verification_script_blob": "7" * 40,
        "canonical_configuration_blob": "8" * 40,
        "inventory_sha256": h,
        "repository_status_sha256": "B" * 64,
        "repository_head": "9" * 40,
        "index_sha256": "C" * 64,
    }
    receipt["freeze_receipt_sha256"] = semantic_identity(receipt)
    current = {key: value for key, value in receipt.items() if key != "freeze_receipt_sha256"}
    return receipt, current


def source_log_and_classification() -> tuple[bytes, dict[str, Any]]:
    source_outcomes = [
        {"identity": "t.py::test_pass", "parent_identity": None, "outcome": "PASSED"},
        {"identity": "t.py::test_fail", "parent_identity": None, "outcome": "FAILED"},
        {"identity": "t.py::test_parent::subcase", "parent_identity": "t.py::test_parent", "outcome": "SUBFAILED"},
        {"identity": "t.py::test_skip", "parent_identity": None, "outcome": "SKIPPED"},
        {"identity": "t.py::test_error", "parent_identity": None, "outcome": "ERROR"},
        {"identity": "t.py::test_xfail", "parent_identity": None, "outcome": "XFAIL"},
        {"identity": "t.py::test_xpass", "parent_identity": None, "outcome": "XPASS"},
    ]
    log = json.dumps({"outcomes": source_outcomes}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    classified = []
    for item in source_outcomes:
        result = dict(item)
        if item["outcome"] in {"FAILED", "SUBFAILED", "ERROR", "XPASS"}:
            result.update(
                {
                    "classification_category": "PRESERVED_BASELINE_FAILURE",
                    "classification_rationale": "Synthetic failure remains a failure and is traceable to the source outcome.",
                    "source_reference": f"fixture-log:{item['identity']}",
                }
            )
        else:
            result.update({"classification_category": None, "classification_rationale": None, "source_reference": None})
        classified.append(result)
    totals = {outcome: 0 for outcome in ALLOWED_OUTCOMES}
    for item in classified:
        totals[item["outcome"]] += 1
    return log, {
        "parser_name": "randle-pytest-outcome-parser",
        "parser_version": "1.0.0-DRAFT",
        "normalization_rules": ["NFC identities", "forward slashes", "no outcome relabeling"],
        "broad_log_sha256": sha256_bytes(log),
        "outcomes": classified,
        "totals": totals,
    }


def attempt_record(attempt_id: str, disposition: str) -> dict[str, Any]:
    no_artifact = disposition in {"NO_ARTIFACT", "PRE_PASS_A_STOP"}
    manifest = None if no_artifact else {"canonical_path": "evidence/manifest.json", "size": 10, "sha256": "D" * 64}
    return {
        "attempt_id": attempt_id,
        "start_time": "2026-07-21T10:00:00-07:00",
        "end_time": "2026-07-21T10:01:00-07:00",
        "initiating_session": "synthetic-fixture",
        "repository_identity": {"root": "synthetic"},
        "specification_identity": None if no_artifact else "spec",
        "script_identity": None if no_artifact else "script",
        "inventory_identity": None if no_artifact else "inventory",
        "worktree": None if no_artifact else "synthetic-worktree",
        "branch": None if no_artifact else "synthetic-branch",
        "evidence_directory": None if no_artifact else "synthetic-evidence",
        "pass_a_status": "NOT_STARTED" if no_artifact else "COMPLETED",
        "pass_b_status": "NOT_STARTED" if no_artifact else "MISMATCH",
        "staging_state": "NONE",
        "commits": [],
        "runtime_access": False,
        "production_modification": False,
        "stop_reason": "Synthetic governed stop reason.",
        "terminal_disposition": disposition,
        "manifest": manifest,
        "relationship_to_prior_attempts": [],
    }


def evidence_registry() -> dict[str, Any]:
    return {
        "entries": [
            {
                "canonical_path": "external/evidence/status.bin",
                "role": "status-artifact",
                "byte_size": 12,
                "sha256": "E" * 64,
                "git_blob": None,
                "authority_status": "CAPTURE_EVIDENCE",
                "immutability_status": "CONTENT_ADDRESSED_EXTERNAL",
                "required_for_recovery": True,
            }
        ]
    }


def stable_state() -> dict[str, Any]:
    state = {field: f"stable-{field}" for field in (
        "specification_identity",
        "script_identity",
        "inventory_identity",
        "raw_byte_identity",
        "git_cleaned_identity",
        "status_identity",
        "external_evidence_identity",
        "head_identity",
        "index_identity",
    )}
    state.update({"path_count": 12, "writer_count": 0, "runtime_operations": 0})
    return state


def case_selection_deterministic() -> None:
    first = repository_fixture_selection()
    second = repository_fixture_selection()
    assert semantic_identity(first) == semantic_identity(second)


def case_selection_ordered() -> None:
    selected = repository_fixture_selection()["selected_paths"]
    assert selected == sorted(selected, key=lambda item: item.encode("utf-8"))


def case_allowlist_drift() -> None:
    selected = base_selection()
    expect_reject("ALLOWLIST_DRIFT", lambda: compare_declared_inventory(selected, selected[:-1]))


def case_undocumented_exclusion() -> None:
    includes = clone_registry(INCLUDES)
    includes["entries"] = [entry for entry in includes["entries"] if entry["path"] != "test_new_watchdog.py"]
    exclusions = clone_registry(EXCLUSIONS)
    exclusions["entries"].append(make_exclusion("test_new_watchdog.py"))
    files = base_files() + [{"path": "test_new_watchdog.py", "class": "production-test", "signals": ["listener_feed_health"]}]
    expect_reject("RELEVANT_TEST_EXCLUDED", lambda: derive_selection(files, includes, exclusions, RULES))


def case_unknown_test() -> None:
    with FixtureRoot() as fixture:
        for entry in repository_include_entries():
            fixture.write(entry["path"], b"# governed fixture\n")
        fixture.write("test_unknown_future.py", b"def test_unknown():\n    assert True\n")
        expect_reject("UNKNOWN_TEST_DISPOSITION", lambda: derive_repository_selection(fixture.root, INCLUDES, EXCLUSIONS, RULES))


def case_new_relevant_test() -> None:
    path = "test_new_pipeline.py"
    assert path in repository_fixture_selection(new_test=path)["selected_paths"]


def case_unresolved_dynamic() -> None:
    expect_reject("UNRESOLVED_DYNAMIC_DEPENDENCY", lambda: repository_fixture_selection(unresolved_dynamic=True))


def case_five_included() -> None:
    ensure_all_questioned_tests(base_selection())


def case_five_removed() -> None:
    selected = base_selection()
    for path in QUESTIONED_TESTS:
        expect_reject("QUESTIONED_TEST_OMITTED", lambda path=path: ensure_all_questioned_tests([item for item in selected if item != path]))


def case_add_required_identity() -> None:
    selected = base_selection()
    assert selection_identity(selected) != selection_identity(sorted([*selected, "future_required.py"]))


def case_remove_required_identity() -> None:
    selected = base_selection()
    assert selection_identity(selected) != selection_identity(selected[:-1])


def case_duplicate_include() -> None:
    includes = clone_registry(INCLUDES)
    includes["entries"].append(copy.deepcopy(includes["entries"][0]))
    expect_reject("DUPLICATE_INCLUDE", lambda: validate_registries(includes, EXCLUSIONS, validate_rule_registry(RULES)))


def case_duplicate_exclusion() -> None:
    exclusions = clone_registry(EXCLUSIONS)
    exclusions["entries"].append(copy.deepcopy(exclusions["entries"][0]))
    expect_reject("DUPLICATE_EXCLUSION", lambda: validate_registries(INCLUDES, exclusions, validate_rule_registry(RULES)))


def case_include_exclude_conflict() -> None:
    exclusions = clone_registry(EXCLUSIONS)
    exclusions["entries"].append(make_exclusion(QUESTIONED_TESTS[0]))
    expect_reject("INCLUDE_EXCLUDE_CONFLICT", lambda: validate_registries(INCLUDES, exclusions, validate_rule_registry(RULES)))


def case_missing_rationale() -> None:
    includes = clone_registry(INCLUDES)
    includes["entries"][0]["rationale"] = ""
    expect_reject("MISSING_RATIONALE", lambda: validate_registries(includes, EXCLUSIONS, validate_rule_registry(RULES)))


def case_missing_evidence() -> None:
    exclusions = clone_registry(EXCLUSIONS)
    exclusions["entries"][0]["evidence"] = []
    expect_reject("MISSING_EVIDENCE", lambda: validate_registries(INCLUDES, exclusions, validate_rule_registry(RULES)))


def case_invalid_rule() -> None:
    includes = clone_registry(INCLUDES)
    includes["entries"][0]["selection_rule_id"] = "MISSING_RULE"
    expect_reject("INVALID_RULE_ID", lambda: validate_registries(includes, EXCLUSIONS, validate_rule_registry(RULES)))


def case_pattern_overreach() -> None:
    exclusions = clone_registry(EXCLUSIONS)
    exclusions["entries"].append(make_exclusion("**", "glob"))
    expect_reject("PATTERN_OVERREACH", lambda: validate_registries(INCLUDES, exclusions, validate_rule_registry(RULES)))


def case_casefold_collision() -> None:
    includes = clone_registry(INCLUDES)
    includes["entries"].append(make_include("entryagent/ENTRY_AGENT.py", "INC-CASE-COLLISION"))
    expect_reject("PATH_COLLISION", lambda: validate_registries(includes, EXCLUSIONS, validate_rule_registry(RULES)))


def case_unicode_collision() -> None:
    includes = clone_registry(INCLUDES)
    includes["entries"].append(make_include("fixtures/café.py", "INC-NFC"))
    includes["entries"].append(make_include("fixtures/cafe\u0301.py", "INC-NFD"))
    expect_reject({"PATH_UNICODE", "PATH_COLLISION"}, lambda: validate_registries(includes, EXCLUSIONS, validate_rule_registry(RULES)))


def case_long_enumeration() -> None:
    inventory = build_long_inventory()
    assert LONG_PATH_ARTIFACTS[0] in {item["canonical_path"] for item in inventory["artifacts"]}
    assert len(LONG_PATH_ARTIFACTS[0]) > 150


def case_two_long_artifacts() -> None:
    manifest = manifest_from_inventory(build_long_inventory())
    verify_manifest(manifest)
    verify_long_path_artifacts(manifest)


def case_missing_long() -> None:
    manifest = manifest_from_inventory(build_long_inventory(False))
    expect_reject("LONG_PATH_OMISSION", lambda: verify_long_path_artifacts(manifest))


def case_inventory_extra() -> None:
    inventory = build_long_inventory()
    expected = inventory_records(inventory)
    actual = copy.deepcopy(expected) + [{"path": "extra.bin", "size": 1, "sha256": "A" * 64}]
    expect_reject("INVENTORY_PATH_SET", lambda: verify_inventory(expected, actual))


def case_inventory_size() -> None:
    expected = inventory_records(build_long_inventory())
    actual = copy.deepcopy(expected)
    actual[0]["size"] += 1
    expect_reject("INVENTORY_IDENTITY", lambda: verify_inventory(expected, actual))


def case_inventory_hash() -> None:
    expected = inventory_records(build_long_inventory())
    actual = copy.deepcopy(expected)
    actual[0]["sha256"] = "F" * 64
    expect_reject("INVENTORY_IDENTITY", lambda: verify_inventory(expected, actual))


def case_inventory_substitute() -> None:
    expected = inventory_records(build_long_inventory())
    actual = copy.deepcopy(expected)
    actual[-1]["sha256"] = sha256_bytes(b"substitution")
    expect_reject("INVENTORY_IDENTITY", lambda: verify_inventory(expected, actual))


def case_reparse() -> None:
    expect_reject("REPARSE_POINT_AMBIGUITY", lambda: validate_inventory_security([{"path": "link", "reparse_point": True}]))


def case_mutation_during_scan() -> None:
    with FixtureRoot() as fixture:
        fixture.write("mutable.bin", b"before")

        def mutate(path: Path) -> None:
            with open(extended_length_path(path), "wb") as handle:
                handle.write(b"after-and-longer")

        expect_reject("FILE_MUTATED_DURING_SCAN", lambda: enumerate_inventory(fixture.root, mutation_hooks={"mutable.bin": mutate}))


def case_permission_denied() -> None:
    with FixtureRoot() as fixture:
        fixture.write("denied.bin", b"denied")
        expect_reject("PERMISSION_DENIED", lambda: enumerate_inventory(fixture.root, denied_paths={"denied.bin"}))


def case_inventory_duplicate() -> None:
    expected = inventory_records(build_long_inventory())
    actual = copy.deepcopy(expected) + [copy.deepcopy(expected[0])]
    expect_reject("DUPLICATE_PATH", lambda: verify_inventory(expected, actual))


def case_ads() -> None:
    with FixtureRoot() as fixture:
        fixture.write("streamed.bin", b"primary")
        expect_reject("ALTERNATE_DATA_STREAM", lambda: enumerate_inventory(fixture.root, ads_paths={"streamed.bin"}))


def changed_freeze(field: str) -> None:
    receipt, current = freeze_pair()
    current[field] = "0" * len(str(current[field]))
    expect_reject("FREEZE_MISMATCH", lambda: validate_freeze(receipt, current))


def case_freeze_positive() -> None:
    receipt, current = freeze_pair()
    validate_freeze(receipt, current)


def case_freeze_reuse() -> None:
    receipt, current = freeze_pair()
    expect_reject("REUSED_ATTEMPT_ID", lambda: validate_freeze(receipt, current, {receipt["attempt_id"]}))


def case_freeze_missing() -> None:
    expect_reject("MISSING_FIELD", lambda: validate_freeze({}, {}))


def case_test_positive() -> None:
    log, record = source_log_and_classification()
    validate_test_classification(record, log)


def case_ordinary_failure() -> None:
    log, record = source_log_and_classification()
    validate_test_classification(record, log)
    assert sum(item["outcome"] == "FAILED" for item in record["outcomes"]) == 1


def case_subfailed() -> None:
    log, record = source_log_and_classification()
    validate_test_classification(record, log)
    assert sum(item["outcome"] == "SUBFAILED" for item in record["outcomes"]) == 1


def case_removed_subfailed() -> None:
    log, record = source_log_and_classification()
    record["outcomes"] = [item for item in record["outcomes"] if item["outcome"] != "SUBFAILED"]
    record["totals"]["SUBFAILED"] = 0
    expect_reject("UNSUPPORTED_RECLASSIFICATION", lambda: validate_test_classification(record, log))


def case_duplicate_failure() -> None:
    log, record = source_log_and_classification()
    failure = next(item for item in record["outcomes"] if item["outcome"] == "FAILED")
    record["outcomes"].append(copy.deepcopy(failure))
    record["totals"]["FAILED"] += 1
    expect_reject("DUPLICATE_OUTCOME", lambda: validate_test_classification(record, log))


def case_reclassification() -> None:
    log, record = source_log_and_classification()
    failure = next(item for item in record["outcomes"] if item["outcome"] == "FAILED")
    failure["outcome"] = "PASSED"
    record["totals"]["FAILED"] -= 1
    record["totals"]["PASSED"] += 1
    expect_reject("UNSUPPORTED_RECLASSIFICATION", lambda: validate_test_classification(record, log))


def case_total_mismatch() -> None:
    log, record = source_log_and_classification()
    record["totals"]["FAILED"] += 1
    expect_reject("TEST_TOTAL_MISMATCH", lambda: validate_test_classification(record, log))


def case_log_hash() -> None:
    log, record = source_log_and_classification()
    expect_reject("BROAD_LOG_HASH", lambda: validate_test_classification(record, log + b"mutation"))


def case_all_outcomes() -> None:
    log, record = source_log_and_classification()
    validate_test_classification(record, log)
    assert set(record["totals"]) == ALLOWED_OUTCOMES


def case_historical_156_23_regression() -> None:
    source = []
    source.extend({"identity": f"historical.py::pass_{index:03d}", "parent_identity": None, "outcome": "PASSED"} for index in range(571))
    source.extend({"identity": f"historical.py::failed_{index:03d}", "parent_identity": None, "outcome": "FAILED"} for index in range(156))
    source.extend({"identity": f"historical.py::parent_{index:03d}::subfailed", "parent_identity": f"historical.py::parent_{index:03d}", "outcome": "SUBFAILED"} for index in range(23))
    source.extend({"identity": f"historical.py::skipped_{index:03d}", "parent_identity": None, "outcome": "SKIPPED"} for index in range(3))
    log = json.dumps({"outcomes": source}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    outcomes = []
    for item in source:
        classified = dict(item)
        if item["outcome"] in {"FAILED", "SUBFAILED"}:
            classified.update({"classification_category": "HISTORICAL_PRESERVED_FAILURE", "classification_rationale": "Regression fixture retains the prior failed outcome without relabeling.", "source_reference": f"historical-log:{item['identity']}"})
        else:
            classified.update({"classification_category": None, "classification_rationale": None, "source_reference": None})
        outcomes.append(classified)
    record = {
        "parser_name": "randle-pytest-outcome-parser",
        "parser_version": "1.0.0-DRAFT",
        "normalization_rules": ["NFC identities", "no outcome relabeling"],
        "broad_log_sha256": sha256_bytes(log),
        "outcomes": outcomes,
        "totals": {"PASSED": 571, "FAILED": 156, "SUBFAILED": 23, "SKIPPED": 3, "ERROR": 0, "XFAIL": 0, "XPASS": 0},
    }
    validate_test_classification(record, log)
    assert len(outcomes) == 753


def case_attempt_distinct() -> None:
    records = [attempt_record("attempt-no-artifact-001", "NO_ARTIFACT"), attempt_record("attempt-unstable-002", "UNSTABLE")]
    validate_attempt_ledger(records)
    assert records[0]["attempt_id"] != records[1]["attempt_id"]


def case_attempt_conflict() -> None:
    record = attempt_record("attempt-no-artifact-001", "NO_ARTIFACT")
    record["worktree"] = "contradictory-worktree"
    expect_reject("CONFLICTING_ATTEMPT_CLAIM", lambda: validate_attempt_ledger([record]))


def case_attempt_manifest() -> None:
    record = attempt_record("attempt-unstable-002", "UNSTABLE")
    record["manifest"] = None
    expect_reject("MISSING_MANIFEST_REFERENCE", lambda: validate_attempt_ledger([record]))


def case_attempt_duplicate() -> None:
    record = attempt_record("attempt-unstable-002", "UNSTABLE")
    expect_reject("DUPLICATE_ATTEMPT_ID", lambda: validate_attempt_ledger([record, copy.deepcopy(record)]))


def case_attempt_terminal() -> None:
    record = attempt_record("attempt-unstable-002", "UNSTABLE")
    record["terminal_disposition"] = None
    expect_reject("MISSING_TERMINAL_DISPOSITION", lambda: validate_attempt_ledger([record]))


def case_evidence_positive() -> None:
    validate_evidence_bindings(evidence_registry())


def case_evidence_mutation() -> None:
    registry = evidence_registry()
    registry["entries"][0]["sha256"] = "bad"
    expect_reject("EVIDENCE_HASH", lambda: validate_evidence_bindings(registry))


def case_manifest_totals() -> None:
    manifest = manifest_from_inventory(build_long_inventory())
    manifest["total_bytes"] += 1
    expect_reject("MANIFEST_BYTES", lambda: verify_manifest(manifest))


def case_stability_positive() -> None:
    state = stable_state()
    validate_multi_pass(state, copy.deepcopy(state), copy.deepcopy(state))


def case_stability_raw() -> None:
    a = stable_state()
    b = copy.deepcopy(a)
    b["raw_byte_identity"] = "changed"
    expect_reject("MULTIPASS_MISMATCH", lambda: validate_multi_pass(a, b, a))


def case_stability_path() -> None:
    a = stable_state()
    b = copy.deepcopy(a)
    b["path_count"] += 1
    expect_reject("MULTIPASS_MISMATCH", lambda: validate_multi_pass(a, b, a))


def case_stability_branch_index() -> None:
    a = stable_state()
    b = copy.deepcopy(a)
    b["index_identity"] = "changed"
    expect_reject("MULTIPASS_MISMATCH", lambda: validate_multi_pass(a, b, a))


def package_paths() -> list[str]:
    root = PACKAGE.parents[1]
    return sorted(
        "Architecture/" + path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def case_governance_positive() -> None:
    validate_governance_package(package_paths(), [], [])


def forbidden_event(event: str) -> None:
    expect_reject("FORBIDDEN_EVENT", lambda: validate_governance_package(["Architecture/spec_DRAFT.md"], [event], []))


def case_governance_auth() -> None:
    expect_reject("AUTHORIZATION_EMITTED", lambda: validate_governance_package(["Architecture/spec_DRAFT.md"], [], ["live-money trading"]))


def case_vector_coverage() -> None:
    vector_ids = {item["case_id"] for name in ("expected_case_vectors_DRAFT.json", "mutation_case_vectors_DRAFT.json") for item in load_json(name)["cases"]}
    assert vector_ids == set(CASES)


def case_schema_parse() -> None:
    for name in SCHEMA_FILES:
        schema = load_json(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"


def case_independent_expectations() -> None:
    expectations = load_json("independent_expectations_DRAFT.json")
    assert set(expectations["expected_case_ids"]) == set(CASES)
    assert expectations["default_expected_runner_status"] == "PASS"


def case_traceability_coverage() -> None:
    matrix = load_json("traceability_matrix_DRAFT.json")
    assert {item["finding_id"] for item in matrix["findings"]} == {"B1", "B2", "B3", "B4", "B5"}
    requirements = matrix["requirements"]
    assert {item["clause"] for item in requirements} == {str(number) for number in range(1, 18)}
    traced_rules = {rule for item in requirements for rule in item["rule_ids"]}
    assert traced_rules == validate_rule_registry(RULES)
    traced_cases = {case for item in requirements for case in item["verification_case_ids"]}
    assert traced_cases == set(CASES)
    obligation_ids = {item["obligation_id"] for item in matrix["future_obligations"]}
    assert obligation_ids
    assert all(set(item["future_obligation_ids"]) <= obligation_ids for item in requirements)


def case_recorded_results() -> None:
    recorded = load_json("fixture_results_DRAFT.json")
    assert set(recorded["case_results"]["PASS"]) == set(CASES)
    assert recorded["case_results"]["FAIL"] == []
    assert recorded["totals"]["total"] == len(CASES)
    assert recorded["totals"]["passed"] == len(CASES)
    assert recorded["totals"]["failed"] == 0


CASES: dict[str, Callable[[], None]] = {
    "SEL-001": case_selection_deterministic,
    "SEL-002": case_selection_ordered,
    "SEL-003": case_allowlist_drift,
    "SEL-004": case_undocumented_exclusion,
    "SEL-005": case_unknown_test,
    "SEL-006": case_new_relevant_test,
    "SEL-007": case_five_included,
    "SEL-008": case_five_removed,
    "SEL-009": case_add_required_identity,
    "SEL-010": case_remove_required_identity,
    "SEL-011": case_unresolved_dynamic,
    "REG-001": case_duplicate_include,
    "REG-002": case_duplicate_exclusion,
    "REG-003": case_include_exclude_conflict,
    "REG-004": case_missing_rationale,
    "REG-005": case_missing_evidence,
    "REG-006": case_invalid_rule,
    "REG-007": case_pattern_overreach,
    "REG-008": case_casefold_collision,
    "REG-009": case_unicode_collision,
    "INV-001": case_long_enumeration,
    "INV-002": case_two_long_artifacts,
    "INV-003": case_missing_long,
    "INV-004": case_inventory_extra,
    "INV-005": case_inventory_size,
    "INV-006": case_inventory_hash,
    "INV-007": case_inventory_substitute,
    "INV-008": case_reparse,
    "INV-009": case_mutation_during_scan,
    "INV-010": case_permission_denied,
    "INV-011": case_inventory_duplicate,
    "INV-012": case_ads,
    "FRZ-000": case_freeze_positive,
    "FRZ-001": lambda: changed_freeze("specification_commit"),
    "FRZ-002": lambda: changed_freeze("selection_script_blob"),
    "FRZ-003": lambda: changed_freeze("include_registry_blob"),
    "FRZ-004": lambda: changed_freeze("inventory_sha256"),
    "FRZ-005": lambda: changed_freeze("repository_status_sha256"),
    "FRZ-006": lambda: changed_freeze("repository_head"),
    "FRZ-007": lambda: changed_freeze("index_sha256"),
    "FRZ-008": case_freeze_reuse,
    "FRZ-009": case_freeze_missing,
    "FRZ-010": lambda: changed_freeze("verification_script_blob"),
    "FRZ-011": lambda: changed_freeze("exclusion_registry_blob"),
    "FRZ-012": lambda: changed_freeze("canonical_configuration_blob"),
    "TST-000": case_test_positive,
    "TST-001": case_ordinary_failure,
    "TST-002": case_subfailed,
    "TST-003": case_removed_subfailed,
    "TST-004": case_duplicate_failure,
    "TST-005": case_reclassification,
    "TST-006": case_total_mismatch,
    "TST-007": case_log_hash,
    "TST-008": case_all_outcomes,
    "TST-009": case_historical_156_23_regression,
    "ATT-001": case_attempt_distinct,
    "ATT-002": case_attempt_conflict,
    "ATT-003": case_attempt_manifest,
    "ATT-004": case_attempt_duplicate,
    "ATT-005": case_attempt_terminal,
    "EVD-001": case_evidence_positive,
    "EVD-002": case_evidence_mutation,
    "EVD-003": case_manifest_totals,
    "STB-001": case_stability_positive,
    "STB-002": case_stability_raw,
    "STB-003": case_stability_path,
    "STB-004": case_stability_branch_index,
    "GOV-001": case_governance_positive,
    "GOV-002": lambda: forbidden_event("runtime_access"),
    "GOV-003": lambda: forbidden_event("deployment"),
    "GOV-004": lambda: forbidden_event("baseline_capture"),
    "GOV-005": case_governance_auth,
    "PKG-001": case_vector_coverage,
    "PKG-002": case_schema_parse,
    "PKG-003": case_independent_expectations,
    "PKG-004": case_traceability_coverage,
    "PKG-005": case_recorded_results,
}


def run() -> dict[str, Any]:
    expected_vectors = {
        item["case_id"]: item
        for name in ("expected_case_vectors_DRAFT.json", "mutation_case_vectors_DRAFT.json")
        for item in load_json(name)["cases"]
    }
    results = []
    for case_id, operation in CASES.items():
        expected = expected_vectors.get(case_id, {}).get("expected_runner_status", "MISSING")
        try:
            operation()
            status = "PASS"
            detail = "Expected behavior observed."
        except Exception as exc:  # harness must preserve the exact failing case
            status = "FAIL"
            detail = f"{type(exc).__name__}: {exc}"
        results.append(
            {
                "case_id": case_id,
                "detail": detail,
                "expected_runner_status": expected,
                "status": status,
            }
        )
    passed = sum(item["status"] == "PASS" and item["expected_runner_status"] == "PASS" for item in results)
    failed = len(results) - passed
    return {
        "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
        "fixture_scope": "Synthetic temporary roots only; no production repository, runtime, deployment, capture, or trading operation.",
        "harness": "fixture_runner_DRAFT.py",
        "harness_version": "1.0.0-DRAFT",
        "results": results,
        "schema_version": "1.0.0-DRAFT",
        "totals": {"failed": failed, "passed": passed, "total": len(results)},
    }


def main() -> int:
    results = run()
    print(json.dumps(results, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if results["totals"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
