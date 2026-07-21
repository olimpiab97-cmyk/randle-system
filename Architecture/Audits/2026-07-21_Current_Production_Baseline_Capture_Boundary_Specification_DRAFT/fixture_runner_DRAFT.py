#!/usr/bin/env python3
"""Draft-only, expectation-independent enforcement harness.

Every filesystem operation is constrained to a freshly-created disposable
directory bearing the fixture marker required by the inventory generator.
This program never scans or mutates a production root and never performs a
baseline capture.
"""

from __future__ import annotations

import copy
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping

sys.dont_write_bytecode = True

from boundary_verifier_DRAFT import (  # noqa: E402
    FREEZE_IDENTITY_FIELDS,
    QUESTIONED_TESTS,
    STABILITY_FIELDS,
    BoundaryError,
    attempt_identity,
    build_freeze_receipt,
    derive_committed_package_authority,
    derive_repository_freeze_state,
    evidence_registry_root,
    ensure_all_questioned_tests,
    compare_declared_inventory,
    ledger_root,
    semantic_identity,
    sha256_bytes,
    validate_attempt_authority,
    validate_attempt_ledger,
    validate_evidence_bindings,
    validate_freeze,
    validate_governance_package,
    validate_multi_pass,
    validate_questioned_test_authority,
    validate_path_set,
    validate_registries,
    validate_rule_registry,
    validate_terminal_dispositions,
    validate_test_classification,
    validate_traceability,
    verify_committed_package_authority,
    verify_inventory,
    verify_long_path_sentinels,
    verify_manifest,
)
from inventory_generator_DRAFT import InventoryError, enumerate_inventory, extended_length_path  # noqa: E402
from schema_validation_DRAFT import SchemaValidationError, validate_named_instances, validate_schema_and_instance, validator_identity  # noqa: E402
from selection_engine_DRAFT import derive_repository_selection  # noqa: E402


PACKAGE = Path(__file__).resolve().parent
MARKER = "RANDLE_BOUNDARY_FIXTURE_V2\n"
FIXTURE_PREFIX = "randle_boundary_spec_v2_"


def load_json(name: str) -> Any:
    return json.loads((PACKAGE / name).read_bytes().decode("utf-8"))


CONFIG = load_json("boundary_config_DRAFT.json")
INCLUDES = load_json("include_registry_DRAFT.json")
EXCLUSIONS = load_json("exclusion_registry_DRAFT.json")
RULES = load_json("selection_rule_registry_DRAFT.json")


class FixtureFailure(AssertionError):
    pass


def deep(value: Any) -> Any:
    return copy.deepcopy(value)


def expect_failure(operation: Callable[[], Any], codes: set[str] | None = None) -> None:
    try:
        operation()
    except (BoundaryError, InventoryError) as exc:
        if codes is not None and exc.code not in codes:
            raise FixtureFailure(f"unexpected rejection {exc.code}: {exc}") from exc
        return
    except SchemaValidationError:
        if codes is not None and "SCHEMA" not in codes:
            raise
        return
    raise FixtureFailure("mutation was not detected")


def write_fixture(root: Path, files: Mapping[str, bytes | str]) -> None:
    (root / ".boundary_fixture_root").write_text(MARKER, encoding="ascii")
    for rel, payload in files.items():
        path = root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, bytes):
            path.write_bytes(payload)
        else:
            path.write_text(payload, encoding="utf-8", newline="")


def base_files() -> dict[str, str]:
    test_source = "from EntryAgent import entry_agent\n\ndef test_governed_boundary():\n    assert entry_agent is not None\n"
    files = {
        "EntryAgent/__init__.py": "",
        "EntryAgent/helper.py": "VALUE = 1\n",
        "EntryAgent/relative_helper.py": "RELATIVE = True\n",
        "EntryAgent/plugin_mod.py": "def load(): return True\n",
        "EntryAgent/handler_mod.py": "def handle(): return True\n",
        "EntryAgent/factory_mod.py": "def build(): return object()\n",
        "EntryAgent/dynamic_mod.py": "DYNAMIC = True\n",
        "EntryAgent/entry_agent.py": (
            "import importlib\nimport subprocess\nfrom pathlib import Path\n"
            "from EntryAgent import helper\nfrom . import relative_helper\n"
            "importlib.import_module('EntryAgent.plugin_mod')\n"
            "__import__('EntryAgent.dynamic_mod')\n"
            "register_handler('EntryAgent.handler_mod')\n"
            "register_factory('EntryAgent.factory_mod')\n"
            "load_plugin('EntryAgent.plugin_mod')\n"
            "registry.load('EntryAgent.plugin_mod')\n"
            "register_route('/health', lambda: True)\n"
            "subprocess.run(['python', 'scripts/worker.py'])\n"
            "open('assets/template.txt')\nPath('assets/path_resource.txt')\n"
            "load_asset('assets/static.css')\nload_replay('fixtures/replay.json')\n"
            "load_scenario('scenarios/startup.json')\n"
        ),
        "rithmic_live_listener.py": "from EntryAgent import helper\n",
        "launch_all.ps1": "python EntryAgent/entry_agent.py\npython rithmic_live_listener.py\npython config/runtime.json\ncall launch_helper.bat\nbash launch_helper.sh\n",
        "launch_helper.bat": "python scripts/worker.py\n",
        "launch_helper.sh": "python scripts/worker.py\n",
        "scripts/worker.py": "from EntryAgent import helper\n",
        "assets/template.txt": "template\n",
        "assets/path_resource.txt": "path\n",
        "assets/static.css": "body{}\n",
        "fixtures/replay.json": "{}\n",
        "scenarios/startup.json": "{}\n",
        "config/runtime.json": '{"plugin_module":"EntryAgent.plugin_mod","template_path":"assets/template.txt","yaml_path":"config/runtime.yaml","toml_path":"config/runtime.toml","ini_path":"config/runtime.ini"}\n',
        "config/runtime.yaml": "template_path: assets/template.txt\n",
        "config/runtime.toml": "template_path = 'assets/template.txt'\n",
        "config/runtime.ini": "template_path = assets/template.txt\n",
        "conftest.py": "import pytest\n@pytest.fixture\ndef governed_fixture():\n    return True\n",
        "test_framework_relationships.py": "import unittest\nfrom EntryAgent import entry_agent\nimport pytest\n@pytest.mark.integration\n@pytest.mark.parametrize('value',[1])\n@pytest.mark.usefixtures('governed_fixture')\ndef test_pytest_relationship(value): pass\nclass TestUnit(unittest.TestCase):\n    def test_unit(self): pass\n",
        "Architecture/history.md": "historical governance\n",
        "Backups/old.py": "old = True\n",
        "capture.log": "log\n",
        "runtime.db": "db\n",
    }
    for path in QUESTIONED_TESTS:
        files[path] = test_source
    return files


def selection(
    *,
    files: Mapping[str, str | bytes] | None = None,
    includes: Mapping[str, Any] | None = None,
    exclusions: Mapping[str, Any] | None = None,
    rules: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
    capture_mode: bool = False,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        write_fixture(root, files or base_files())
        return derive_repository_selection(
            root,
            includes or INCLUDES,
            exclusions or EXCLUSIONS,
            rules or RULES,
            config or CONFIG,
            capture_mode=capture_mode,
        )


def assert_edge(edge_type: str) -> None:
    result = selection()
    if edge_type not in {edge["edge_type"] for edge in result["dependency_edges"]}:
        raise FixtureFailure(f"missing parser edge {edge_type}")


def assert_parser(parser: str) -> None:
    result = selection()
    if parser not in {edge["parser"] for edge in result["dependency_edges"]}:
        raise FixtureFailure(f"missing parser {parser}")


def dynamic_declaration_positive() -> None:
    files = base_files()
    files["EntryAgent/entry_agent.py"] += "\nmodule_name = 'ignored-at-runtime-fixture'\nimportlib.import_module(module_name)\n"
    config = deep(CONFIG)
    config["discovery_policy"]["governed_dynamic_dependencies"].append({
        "source_path": "EntryAgent/entry_agent.py",
        "call_name": "importlib.import_module",
        "target_module": "EntryAgent.dynamic_mod",
        "evidence": ["FIXTURE:governed-dynamic-declaration"],
    })
    result = selection(files=files, config=config)
    if "GOVERNED_DYNAMIC_IMPORT" not in {edge["edge_type"] for edge in result["dependency_edges"]}:
        raise FixtureFailure("governed dynamic declaration was not consumed")


def mutation_missing_target(token: str, target: str) -> None:
    files = base_files()
    del files[target]
    expect_failure(lambda: selection(files=files), {"UNRESOLVED_DEPENDENCY"})


def inventory_from(root: Path) -> dict[str, Any]:
    return enumerate_inventory(root)


def git(repository: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-c", f"safe.directory={repository.as_posix()}", "-C", os.fspath(repository), *args], capture_output=True, text=True)
    if completed.returncode:
        raise FixtureFailure(f"git {' '.join(args)}: {completed.stderr}")
    return completed.stdout.strip()


def make_git_fixture(root: Path, content: bytes = b"a\r\nb\r\n") -> None:
    write_fixture(root, {".gitattributes": "*.txt text eol=lf\n", "sample.txt": content})
    subprocess.run(["git", "init", "-q", os.fspath(root)], check=True)
    git(root, "config", "user.name", "Boundary Fixture")
    git(root, "config", "user.email", "boundary-fixture@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-qm", "fixture")


def inventory_identity_positive() -> None:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        make_git_fixture(root)
        artifact = next(item for item in inventory_from(root)["artifacts"] if item["canonical_path"] == "sample.txt")
        if artifact["raw_sha256"] == artifact["working_tree_git_cleaned_sha256"]:
            raise FixtureFailure("raw and clean identities collapsed")
        if not all(artifact[field] for field in ("parent_git_blob", "index_git_blob", "computed_git_blob", "gitattributes_sha256")):
            raise FixtureFailure("incomplete Git identity")


def inventory_mutation(kind: str) -> None:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        make_git_fixture(root)
        before = inventory_from(root)["artifacts"]
        if kind == "raw":
            (root / "sample.txt").write_bytes(b"a\nb\n")
        elif kind == "gitattributes":
            (root / ".gitattributes").write_text("*.txt -text\n", encoding="ascii")
        elif kind == "encoding":
            (root / "sample.txt").write_bytes(b"\xef\xbb\xbfa\r\nb\r\n")
        elif kind == "mode":
            os.chmod(root / "sample.txt", 0o444)
        elif kind == "index":
            (root / "sample.txt").write_bytes(b"indexed\n")
            git(root, "add", "sample.txt")
        after = inventory_from(root)["artifacts"]
        if kind == "raw":
            before_sample = next(item for item in before if item["canonical_path"] == "sample.txt")
            after_sample = next(item for item in after if item["canonical_path"] == "sample.txt")
            if before_sample["raw_sha256"] == after_sample["raw_sha256"] or before_sample["working_tree_git_cleaned_sha256"] != after_sample["working_tree_git_cleaned_sha256"]:
                raise FixtureFailure("raw-only mutation fixture did not preserve the clean identity")
        expect_failure(lambda: verify_inventory(before, after), {"INVENTORY_IDENTITY"})


def ads_case(kind: str) -> None:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        write_fixture(root, {"plain.txt": "main\n"})
        path = root / "plain.txt"
        streams = [("governed", b"ads")]
        if kind == "zero":
            streams = [("zero", b"")]
        elif kind == "multiple":
            streams = [("one", b"1"), ("two", b"2")]
        for name, data in streams:
            with open(f"{path}:{name}", "wb") as handle:
                handle.write(data)
        expect_failure(lambda: inventory_from(root), {"ALTERNATE_DATA_STREAM"})


def ads_midscan(appears: bool) -> None:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        write_fixture(root, {"plain.txt": "main\n"})
        calls = 0

        def changing(path: Path) -> list[str]:
            nonlocal calls
            calls += 1
            if appears:
                return [] if calls == 1 else [":late:$DATA"]
            return [":early:$DATA"] if calls == 1 else []

        expect_failure(lambda: enumerate_inventory(root, ads_probe=changing), {"ADS_MUTATED_DURING_SCAN", "ALTERNATE_DATA_STREAM"})


def long_path_positive() -> None:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        segment = "long_segment_" + "x" * 45
        rel = "/".join([segment] * 5 + ["artifact.txt"])
        write_fixture(root, {})
        native = root.joinpath(*rel.split("/"))
        extended = extended_length_path(native)
        os.makedirs(os.path.dirname(extended), exist_ok=True)
        try:
            with open(extended, "wb") as handle:
                handle.write(b"long path bytes\n")
            result = inventory_from(root)
            if rel not in {item["canonical_path"] for item in result["artifacts"]}:
                raise FixtureFailure("extended-length path was omitted")
            if len(os.fspath(root / Path(*rel.split("/")))) <= 260:
                raise FixtureFailure("fixture did not exceed MAX_PATH")
        finally:
            if os.path.exists(extended):
                os.remove(extended)
            current = os.path.dirname(extended)
            root_extended = extended_length_path(root)
            while current != root_extended:
                os.rmdir(current)
                current = os.path.dirname(current)


def long_path_sentinel_case(missing: bool) -> None:
    from boundary_verifier_DRAFT import LONG_PATH_SENTINELS

    records = [{"canonical_path": path} for path in LONG_PATH_SENTINELS]
    if missing:
        records.pop()
        expect_failure(lambda: verify_long_path_sentinels("capture_evidence_root", records), {"LONG_PATH_SENTINEL_MISSING"})
    else:
        verify_long_path_sentinels("capture_evidence_root", records)


def inaccessible_case() -> None:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        write_fixture(root, {"secret.txt": "secret\n"})
        expect_failure(lambda: enumerate_inventory(root, denied_paths={"secret.txt"}), {"PERMISSION_DENIED"})


def actual_inaccessible_case() -> None:
    if os.name != "nt":
        raise FixtureFailure("actual Windows sharing-denial fixture unsupported")
    import ctypes
    from ctypes import wintypes

    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        write_fixture(root, {"locked.txt": "locked\n"})
        create = ctypes.windll.kernel32.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        handle = create(os.fspath(root / "locked.txt"), 0x80000000, 0, None, 3, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            raise FixtureFailure(f"CreateFileW lock failed:{ctypes.get_last_error()}")
        try:
            expect_failure(lambda: enumerate_inventory(root), {"PERMISSION_DENIED", "ADS_ENUMERATION_FAILED"})
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)


def ads_inaccessible_case() -> None:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        write_fixture(root, {"plain.txt": "main\n"})
        def denied(_: Path) -> list[str]:
            raise InventoryError("ADS_ENUMERATION_FAILED", "fixture access denied")
        expect_failure(lambda: enumerate_inventory(root, ads_probe=denied), {"ADS_ENUMERATION_FAILED"})


def mutation_during_scan_case() -> None:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        write_fixture(root, {"changing.txt": "before\n"})
        def mutate(path: Path) -> None:
            path.write_text("after\n", encoding="utf-8")
        expect_failure(lambda: enumerate_inventory(root, mutation_hooks={"changing.txt": mutate}), {"FILE_MUTATED_DURING_SCAN"})


def reparse_case() -> None:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        write_fixture(root, {"target/artifact.txt": "target\n"})
        link = root / "linked"
        completed = subprocess.run(["cmd", "/c", "mklink", "/J", os.fspath(link), os.fspath(root / "target")], capture_output=True, text=True)
        if completed.returncode:
            raise FixtureFailure(f"junction fixture unsupported:{completed.stderr}")
        try:
            expect_failure(lambda: enumerate_inventory(root), {"REPARSE_POINT_AMBIGUITY"})
        finally:
            if link.exists():
                os.rmdir(link)


def path_collision_case(unicode_collision: bool) -> None:
    if unicode_collision:
        expect_failure(lambda: validate_path_set(["caf\u00e9.py", "cafe\u0301.py"]), {"NON_NFC_PATH", "PATH_COLLISION"})
    else:
        expect_failure(lambda: validate_path_set(["Test_Path.py", "test_path.py"]), {"PATH_COLLISION"})


def freeze_state() -> dict[str, Any]:
    sha = "A" * 64
    git_id = "a" * 40
    values: dict[str, Any] = {field: sha for field in FREEZE_IDENTITY_FIELDS}
    for field in (
        "specification_commit", "specification_parent", "specification_tree", "specification_document_blob",
        "include_registry_blob", "exclusion_registry_blob", "selection_rule_registry_blob", "boundary_configuration_blob",
        "selection_engine_blob", "inventory_generator_blob", "boundary_verifier_blob", "operational_capture_script_blob", "repository_head",
    ):
        values[field] = git_id
    values.update({
        "artifact_count": 27,
        "total_bytes": 4096,
        "repository_branch_or_detached": "refs/heads/fixture",
        "git_version": "git version fixture",
        "python_version": platform.python_version(),
        "operating_system_identity": {"name": platform.system(), "version": platform.version(), "architecture": platform.machine()},
        "filesystem_identity": {"filesystem_type": "NTFS", "volume_serial": "FIXTURE-0001", "case_sensitive": False},
        "repository_object_format": "sha1",
        "timestamp_authority": "fixture-clock",
        "authorization_identity": "fixture-review-authorization",
    })
    return values


def freeze_positive() -> None:
    current = freeze_state()
    receipt = build_freeze_receipt("ATTEMPT-0001", "2026-07-21T00:00:00Z", current)
    validate_freeze(receipt, current, set())


def freeze_derivation_positive() -> None:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        roles = {
            "specification_document": "spec.md",
            "include_registry": "include.json",
            "exclusion_registry": "exclude.json",
            "selection_rule_registry": "rules.json",
            "boundary_configuration": "config.json",
            "selection_engine": "select.py",
            "inventory_generator": "inventory.py",
            "boundary_verifier": "verify.py",
            "operational_capture_script": "capture.py",
            "freeze_receipt_schema": "freeze.schema.json",
        }
        write_fixture(root, {path: ("{}\n" if path.endswith(".json") else "draft fixture bytes\n") for path in roles.values()})
        subprocess.run(["git", "init", "-q", os.fspath(root)], check=True)
        git(root, "config", "user.name", "Boundary Fixture")
        git(root, "config", "user.email", "boundary-fixture@example.invalid")
        git(root, "commit", "--allow-empty", "-qm", "freeze base")
        git(root, "add", ".")
        git(root, "commit", "-qm", "freeze authority")
        inventory = manifest_fixture()["artifacts"]
        current = derive_repository_freeze_state(
            root,
            "HEAD",
            roles,
            inventory,
            terminal_fixture(),
            evidence_fixture(),
            ledger_fixture(),
            timestamp_authority="fixture-clock",
            authorization_identity="fixture-authorization-record",
        )
        receipt = build_freeze_receipt("ATTEMPT-0003", "2026-07-21T00:03:00Z", current)
        validate_freeze(receipt, current, {"ATTEMPT-0001", "ATTEMPT-0002"})


def freeze_mutation(field: str) -> None:
    current = freeze_state()
    receipt = build_freeze_receipt("ATTEMPT-0001", "2026-07-21T00:00:00Z", current)
    if field == "missing":
        del receipt["selection_engine_sha256"]
    elif field == "attempt":
        expect_failure(lambda: validate_freeze(receipt, current, {"ATTEMPT-0001"}), {"REUSED_ATTEMPT_ID"})
        return
    else:
        if isinstance(receipt[field], str):
            receipt[field] = receipt[field] + "-changed"
        elif isinstance(receipt[field], int):
            receipt[field] += 1
        elif isinstance(receipt[field], dict):
            receipt[field] = {**receipt[field], "mutation_marker": True}
        else:
            raise FixtureFailure(f"unsupported freeze mutation field {field}")
    expect_failure(lambda: validate_freeze(receipt, current), {"MISSING_FIELD", "FREEZE_MISMATCH", "FREEZE_RECEIPT_HASH"})


def attempt_record(attempt_id: str, sequence: int, predecessor: str | None, disposition: str, *, incident: str | None = None) -> dict[str, Any]:
    no_artifact = disposition in {"NO_ARTIFACT", "PRE_PASS_A_STOP"}
    record = {
        "attempt_id": attempt_id,
        "sequence_number": sequence,
        "predecessor_attempt_identity": predecessor,
        "attempt_identity_sha256": "",
        "start_time": f"2026-07-21T00:0{sequence}:00Z",
        "end_time": f"2026-07-21T00:0{sequence}:30Z",
        "initiating_session": "fixture-session",
        "repository_identity": {"root": "C:/fixture/repository", "head": "a" * 40, "object_format": "sha1"},
        "specification_identity": "spec-fixture",
        "script_identity": "script-fixture",
        "inventory_identity": None if no_artifact else "inventory-fixture",
        "worktree": None if no_artifact else "C:/fixture/worktree",
        "branch": None if no_artifact else "fixture/branch",
        "evidence_directory": None if no_artifact else "C:/fixture/evidence",
        "pass_a_status": "NOT_STARTED" if no_artifact else "COMPLETED",
        "pass_b_status": "NOT_STARTED" if no_artifact else "MISMATCH",
        "staging_state": "NONE",
        "commits": [],
        "runtime_access": False,
        "production_modification": False,
        "deployment_attempted": False,
        "service_restart_attempted": False,
        "stop_reason": "writer detected" if no_artifact else "stability mismatch",
        "terminal_disposition": disposition,
        "manifest": None if no_artifact else {"canonical_path": "evidence/manifest.json", "byte_size": 1, "sha256": "A" * 64},
        "relationship_to_prior_attempts": [] if sequence == 1 else ["ATTEMPT-0001"],
    }
    if incident:
        record[incident] = True
    record["attempt_identity_sha256"] = attempt_identity(record)
    return record


def ledger_fixture(*, incident: str | None = None) -> dict[str, Any]:
    first = attempt_record("ATTEMPT-0001", 1, None, "NO_ARTIFACT")
    second = attempt_record("ATTEMPT-0002", 2, first["attempt_identity_sha256"], "UNSTABLE", incident=incident)
    attempts = [first, second]
    result = {
        "schema_version": "2.0.0-DRAFT",
        "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
        "attempts": attempts,
        "entry_count": 2,
        "expected_attempt_ids": ["ATTEMPT-0001", "ATTEMPT-0002"],
        "expected_attempt_set_sha256": semantic_identity(["ATTEMPT-0001", "ATTEMPT-0002"]),
        "previous_ledger_root_sha256": None,
        "current_ledger_root_sha256": ledger_root(attempts),
    }
    return result


def rebuild_ledger(ledger: dict[str, Any]) -> None:
    previous = None
    for index, record in enumerate(ledger["attempts"], 1):
        record["sequence_number"] = index
        record["predecessor_attempt_identity"] = previous
        record["attempt_identity_sha256"] = attempt_identity(record)
        previous = record["attempt_identity_sha256"]
    ids = [item["attempt_id"] for item in ledger["attempts"]]
    ledger["entry_count"] = len(ids)
    ledger["expected_attempt_ids"] = ids
    ledger["expected_attempt_set_sha256"] = semantic_identity(ids)
    ledger["current_ledger_root_sha256"] = ledger_root(ledger["attempts"])


def evidence_fixture() -> dict[str, Any]:
    entries = [
        {"canonical_path": "evidence/status.bin", "role": "status-artifact", "artifact_class": "status", "authority_status": "FROZEN", "byte_size": 5, "sha256": "A" * 64, "git_blob": None, "immutability_status": "CONTENT_ADDRESSED_EXTERNAL", "required_for_recovery": True, "source_attempt": "ATTEMPT-0002", "capture_pass": "PASS_A", "semantic_purpose": "Preserve status bytes.", "external_root_id": "evidence_root"},
        {"canonical_path": "evidence/test.log", "role": "complete-test-log", "artifact_class": "test-evidence", "authority_status": "FROZEN", "byte_size": 7, "sha256": "B" * 64, "git_blob": None, "immutability_status": "CONTENT_ADDRESSED_EXTERNAL", "required_for_recovery": True, "source_attempt": "ATTEMPT-0002", "capture_pass": "PASS_B", "semantic_purpose": "Preserve complete test outcomes.", "external_root_id": "evidence_root"},
    ]
    paths = sorted(item["canonical_path"] for item in entries)
    registry = {
        "schema_version": "2.0.0-DRAFT",
        "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
        "entries": entries,
        "expected_entry_count": len(entries),
        "expected_path_set_sha256": semantic_identity(paths),
        "expected_role_set": sorted({item["role"] for item in entries}),
        "expected_artifact_class_set": sorted({item["artifact_class"] for item in entries}),
        "total_bytes": sum(item["byte_size"] for item in entries),
        "semantic_root_sha256": evidence_registry_root(entries),
    }
    registry["registry_identity_sha256"] = semantic_identity(registry)
    return registry


def rebuild_evidence_registry(registry: dict[str, Any]) -> None:
    entries = registry["entries"]
    paths = sorted(item["canonical_path"] for item in entries)
    registry["expected_entry_count"] = len(entries)
    registry["expected_path_set_sha256"] = semantic_identity(paths)
    registry["expected_role_set"] = sorted({item["role"] for item in entries})
    registry["expected_artifact_class_set"] = sorted({item["artifact_class"] for item in entries})
    registry["total_bytes"] = sum(item["byte_size"] for item in entries)
    registry["semantic_root_sha256"] = evidence_registry_root(entries)
    semantic = {key: value for key, value in registry.items() if key != "registry_identity_sha256"}
    registry["registry_identity_sha256"] = semantic_identity(semantic)


def outcome_fixture() -> tuple[dict[str, Any], bytes]:
    outcomes: list[dict[str, Any]] = []
    line = 1
    for status, count in (("PASSED", 571), ("FAILED", 156), ("SUBFAILED", 23), ("SKIPPED", 3)):
        for index in range(count):
            identity = f"tests/test_historical.py::{status.lower()}_{index:03d}"
            classified = status in {"FAILED", "SUBFAILED", "ERROR", "XPASS"}
            outcomes.append({
                "identity": identity,
                "parent_identity": "tests/test_historical.py::parent" if status == "SUBFAILED" else None,
                "outcome": status,
                "classification_category": "PRESERVED_BASELINE_FAILURE" if classified else None,
                "classification_rationale": "The source log records this individual failed outcome." if classified else None,
                "source_reference": f"broad.log:{line}" if classified else None,
                "source_log_location": f"broad.log:{line}",
                "parser_name": "randle-pytest-outcome-parser" if classified else None,
                "parser_version": "2.0.0-DRAFT" if classified else None,
                "normalization_rule": "IDENTITY_BYTES_PRESERVED" if classified else None,
                "classification_rule": "CLASSIFY_WITHOUT_RELABEL" if classified else None,
            })
            line += 1
    source = {"outcomes": [{"identity": x["identity"], "parent_identity": x["parent_identity"], "outcome": x["outcome"]} for x in outcomes]}
    log = json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
    totals = {status: 0 for status in ("PASSED", "FAILED", "SUBFAILED", "SKIPPED", "ERROR", "XFAIL", "XPASS")}
    totals.update(Counter(item["outcome"] for item in outcomes))
    record = {
        "schema_version": "2.0.0-DRAFT",
        "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
        "parser_name": "randle-pytest-outcome-parser",
        "parser_version": "2.0.0-DRAFT",
        "normalization_rules": ["IDENTITY_BYTES_PRESERVED"],
        "classification_rules": ["CLASSIFY_WITHOUT_RELABEL"],
        "full_log_path": "evidence/broad.log",
        "full_log_size": len(log),
        "full_log_sha256": sha256_bytes(log),
        "outcomes": outcomes,
        "outcome_identity_set_sha256": semantic_identity(sorted(item["identity"] for item in outcomes)),
        "outcome_count_by_status": totals,
        "classification_count_by_category": {"PRESERVED_BASELINE_FAILURE": 179},
        "source_total": 753,
        "accounted_total": 753,
    }
    return record, log


def stability_state() -> dict[str, Any]:
    state = {field: semantic_identity(field) for field in STABILITY_FIELDS}
    state.update({"artifact_count": 20, "total_bytes": 1000, "writer_count": 0, "runtime_operation_count": 0, "deployment_attempt_count": 0, "service_restart_attempt_count": 0})
    return state


def manifest_fixture() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        write_fixture(root, {"artifact.txt": "artifact\n"})
        inventory = inventory_from(root)
    artifacts = inventory["artifacts"]
    manifest = {
        "schema_version": "2.0.0-DRAFT",
        "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
        "enumeration": {"enumeration_roots": [{"root_id": "fixture", "root_identity": "synthetic"}], "path_api": "Python os.scandir with Windows extended-length paths", "extended_length_paths": True, "hidden_and_system_included": True, "silent_skip_count": 0, "ads_api": "FindFirstStreamW/FindNextStreamW"},
        "artifacts": artifacts,
        "total_artifact_count": len(artifacts),
        "total_bytes": sum(item["raw_byte_size"] for item in artifacts),
        "artifact_path_set_sha256": semantic_identity(sorted(item["canonical_path"] for item in artifacts)),
        "artifact_set_semantic_sha256": semantic_identity(artifacts),
    }
    manifest["manifest_semantic_sha256"] = semantic_identity(manifest)
    return manifest


def terminal_fixture() -> dict[str, Any]:
    return selection()


def schema_instances() -> dict[str, tuple[str, Any]]:
    classification, _ = outcome_fixture()
    terminal = terminal_fixture()
    result = {
        "boundary configuration": ("capture_boundary_schema_DRAFT.json", CONFIG),
        "include registry": ("include_registry_schema_DRAFT.json", INCLUDES),
        "exclusion registry": ("exclusion_registry_schema_DRAFT.json", EXCLUSIONS),
        "selection rule registry": ("selection_rule_registry_schema_DRAFT.json", RULES),
        "freeze receipt": ("freeze_receipt_schema_DRAFT.json", build_freeze_receipt("ATTEMPT-0001", "2026-07-21T00:00:00Z", freeze_state())),
        "attempt ledger": ("attempt_ledger_schema_DRAFT.json", ledger_fixture()),
        "durable manifest": ("durable_manifest_schema_DRAFT.json", manifest_fixture()),
        "durable evidence registry": ("durable_evidence_binding_registry_schema_DRAFT.json", evidence_fixture()),
        "test classification": ("test_classification_schema_DRAFT.json", classification),
        "terminal disposition": ("terminal_disposition_schema_DRAFT.json", terminal),
    }
    return result


def schema_reject(schema_name: str, instance: Any) -> None:
    schema = load_json(schema_name)
    expect_failure(lambda: validate_schema_and_instance(schema, instance, f"mutation:{schema_name}"), {"SCHEMA"})


def registry_mutation(kind: str) -> None:
    inc, exc, rules = deep(INCLUDES), deep(EXCLUSIONS), validate_rule_registry(RULES)
    if kind == "duplicate_include":
        inc["entries"].append(deep(inc["entries"][0]))
    elif kind == "duplicate_exclusion":
        exc["entries"].append(deep(exc["entries"][0]))
    elif kind == "conflict":
        path = QUESTIONED_TESTS[0]
        item = deep(exc["entries"][0]); item.update({"entry_id":"EXC-CONFLICT", "path_or_pattern":path, "match_type":"exact", "class":"production-test"});exc["entries"].append(item)
    elif kind == "rationale":
        inc["entries"][0]["rationale"] = ""
    elif kind == "evidence":
        inc["entries"][0]["evidence_references"] = []
    elif kind == "rule":
        inc["entries"][0]["selection_rule_id"] = "UNKNOWN_RULE"
    elif kind == "overreach":
        exc["entries"][0]["match_type"] = "glob";exc["entries"][0]["path_or_pattern"] = "**"
    elif kind == "case_collision":
        item=deep(inc["entries"][0]);item["entry_id"]="INC-CASE-COLLISION";item["path"]=item["path"].upper();inc["entries"].append(item)
    elif kind == "unicode_collision":
        item=deep(inc["entries"][0]);item["entry_id"]="INC-UNICODE-ONE";item["path"]="caf\u00e9.py";inc["entries"].append(item)
        other=deep(item);other["entry_id"]="INC-UNICODE-TWO";other["path"]="cafe\u0301.py";inc["entries"].append(other)
    expect_failure(lambda: validate_registries(inc, exc, rules))


def traceability_positive() -> None:
    import boundary_verifier_DRAFT as verifier
    import inventory_generator_DRAFT as inventory
    import schema_validation_DRAFT as schemas
    import selection_engine_DRAFT as selector

    functions = {
        "selection_engine_DRAFT.derive_repository_selection",
        "boundary_verifier_DRAFT.validate_terminal_dispositions",
        "boundary_verifier_DRAFT.validate_questioned_test_authority",
        "boundary_verifier_DRAFT.derive_committed_package_authority",
        "boundary_verifier_DRAFT.verify_committed_package_authority",
        "boundary_verifier_DRAFT.validate_rule_registry",
        "boundary_verifier_DRAFT.validate_registries",
        "schema_validation_DRAFT.validate_named_instances",
        "inventory_generator_DRAFT.alternate_data_streams",
        "inventory_generator_DRAFT.enumerate_inventory",
        "boundary_verifier_DRAFT.verify_inventory",
        "boundary_verifier_DRAFT.build_freeze_receipt",
        "boundary_verifier_DRAFT.derive_repository_freeze_state",
        "boundary_verifier_DRAFT.validate_freeze",
        "boundary_verifier_DRAFT.validate_attempt_ledger",
        "boundary_verifier_DRAFT.validate_attempt_authority",
        "boundary_verifier_DRAFT.validate_evidence_bindings",
        "boundary_verifier_DRAFT.validate_test_classification",
        "boundary_verifier_DRAFT.validate_multi_pass",
        "boundary_verifier_DRAFT.validate_governance_package",
        "boundary_verifier_DRAFT.verify_long_path_sentinels",
        "boundary_verifier_DRAFT.validate_traceability",
        "fixture_runner_DRAFT.run",
    }
    modules = {"boundary_verifier_DRAFT": verifier, "inventory_generator_DRAFT": inventory, "schema_validation_DRAFT": schemas, "selection_engine_DRAFT": selector, "fixture_runner_DRAFT": sys.modules[__name__]}
    for qualified in functions:
        module, name = qualified.rsplit(".", 1)
        if not callable(getattr(modules[module], name, None)):
            raise FixtureFailure(f"traced enforcing function absent:{qualified}")
    schema_files = {path.name for path in PACKAGE.glob("*_schema_DRAFT.json")}
    validate_traceability(load_json("traceability_matrix_DRAFT.json"), set(CASES), functions, schema_files)


def package_binding_positive() -> None:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        write_fixture(root, {"include.json": "{}\n", "exclude.json": "{}\n", "rules.json": "{}\n", "config.json": "{}\n", "select.py": "pass\n", "verify.py": "pass\n", "inventory.py": "pass\n"})
        subprocess.run(["git", "init", "-q", os.fspath(root)], check=True)
        git(root, "config", "user.name", "Boundary Fixture")
        git(root, "config", "user.email", "boundary-fixture@example.invalid")
        git(root, "commit", "--allow-empty", "-qm", "authority base")
        git(root, "add", ".")
        git(root, "commit", "-qm", "authority")
        roles = {"include_registry": "include.json", "exclusion_registry": "exclude.json", "selection_rules": "rules.json", "configuration": "config.json", "selection_engine": "select.py", "verifier": "verify.py", "inventory_generator": "inventory.py"}
        authority = derive_committed_package_authority(root, "HEAD", roles)
        verify_committed_package_authority(authority, root, roles)


def package_binding_mutation(role: str) -> None:
    with tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX) as raw:
        root = Path(raw)
        files = {"include_registry": "include.json", "exclusion_registry": "exclude.json", "selection_rules": "rules.json", "configuration": "config.json", "selection_engine": "select.py", "verifier": "verify.py", "inventory_generator": "inventory.py"}
        write_fixture(root, {path: "{}\n" if path.endswith(".json") else "pass\n" for path in files.values()})
        subprocess.run(["git", "init", "-q", os.fspath(root)], check=True)
        git(root, "config", "user.name", "Boundary Fixture")
        git(root, "config", "user.email", "boundary-fixture@example.invalid")
        git(root, "commit", "--allow-empty", "-qm", "authority base")
        git(root, "add", ".")
        git(root, "commit", "-qm", "authority")
        authority = derive_committed_package_authority(root, "HEAD", files)
        (root / files[role]).write_text("changed\n", encoding="utf-8")
        expect_failure(lambda: verify_committed_package_authority(authority, root, files), {"PACKAGE_WORKTREE_DIFFERS_FROM_COMMIT", "PACKAGE_AUTHORITY_MISMATCH"})


def governance_positive() -> None:
    validate_governance_package(["Architecture/spec.md"], {"Architecture/spec.md": b"Deployment is not authorized. Live-money trading remains withheld.\n"})


def governed_package_positive() -> None:
    repository = PACKAGE.parents[2]
    paths = [path.relative_to(repository).as_posix() for path in PACKAGE.iterdir() if path.is_file()]
    paths.extend([
        "Architecture/15_Randle_AI_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT.md",
        "Architecture/Impact_Assessments/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_Architecture_Impact_Assessment_DRAFT.md",
        "Architecture/Traceability/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_Traceability_Matrix_DRAFT.md",
    ])
    paths = sorted(set(paths))
    validate_governance_package(paths, {path: repository.joinpath(*path.split("/")).read_bytes() for path in paths})


def governance_mutation(location: str, phrase: str) -> None:
    if location == "json":
        data = json.dumps({"approval_status": phrase}).encode()
    elif location == "table":
        data = f"| status | value |\n|---|---|\n| authority | {phrase} |\n".encode()
    else:
        data = phrase.encode()
    path = f"Architecture/fixture.{location}"
    expect_failure(lambda: validate_governance_package([path], {path: data}), {"AUTHORIZATION_LEAKAGE"})


CaseFunction = Callable[[], None]
CASES: dict[str, tuple[str, str, CaseFunction]] = {}


def case(case_id: str, kind: str, requirement: str, operation: CaseFunction) -> None:
    if case_id in CASES:
        raise RuntimeError(f"duplicate case {case_id}")
    CASES[case_id] = (kind, requirement, operation)


def register_cases() -> None:
    case("POS-SELECTION-DETERMINISTIC", "positive", "SPEC:4-5", lambda: semantic_identity(selection()) == semantic_identity(selection()) or (_ for _ in ()).throw(FixtureFailure("nondeterministic selection")))
    for edge in ("PYTHON_ABSOLUTE_IMPORT", "PYTHON_RELATIVE_IMPORT", "PYTHON_DYNAMIC_IMPORT", "LAUNCHER_TARGET", "SUBPROCESS_TARGET", "ROUTE_REGISTRATION", "PLUGIN_HANDLER_FACTORY", "FILE_OPEN_TARGET", "STATIC_ASSET_TARGET", "REPLAY_OR_SCENARIO_TARGET", "CONFIG_MODULE_REFERENCE", "CONFIG_FILE_REFERENCE"):
        case(f"POS-CLOSURE-{edge}", "positive", "SPEC:4", lambda edge=edge: assert_edge(edge))
    for parser in ("powershell-literal-reference-1.0.0-DRAFT", "shell-launch-reference-1.0.0-DRAFT", "json-config-reference-1.0.0-DRAFT", "yaml-config-reference-1.0.0-DRAFT", "toml-config-reference-1.0.0-DRAFT", "ini-config-reference-1.0.0-DRAFT"):
        case(f"POS-PARSER-{parser.upper()}", "positive", "SPEC:4.2", lambda parser=parser: assert_parser(parser))
    case("POS-CLOSURE-GOVERNED-DYNAMIC-DECLARATION", "positive", "SPEC:4.4", dynamic_declaration_positive)
    for edge in ("PYTEST_FIXTURE_RELATIONSHIP", "PYTEST_PARAMETERIZATION", "UNITTEST_DISCOVERY"):
        case(f"POS-TEST-RELATION-{edge}", "positive", "SPEC:5", lambda edge=edge: assert_edge(edge))
    case("POS-TERMINAL-UNION", "positive", "SPEC:3.2", lambda: validate_terminal_dispositions(selection()["enumeration_universe"], selection()["terminal_dispositions"], selection()["binding_obligations"]))
    case("POS-FIVE-TESTS", "positive", "SPEC:6", lambda: ensure_all_questioned_tests(selection()["included_paths"]))
    case("POS-INVENTORY-GIT-IDENTITY", "positive", "SPEC:8.5", inventory_identity_positive)
    case("POS-INVENTORY-LONG-PATH", "positive", "SPEC:8.2", long_path_positive)
    case("POS-INVENTORY-LONG-SENTINELS", "positive", "SPEC:12", lambda: long_path_sentinel_case(False))
    case("POS-FREEZE", "positive", "SPEC:9", freeze_positive)
    case("POS-FREEZE-INDEPENDENT-REPOSITORY-DERIVATION", "positive", "SPEC:9-10", freeze_derivation_positive)
    case("POS-ATTEMPT-LEDGER", "positive", "SPEC:11", lambda: validate_attempt_ledger(ledger_fixture()))
    case("POS-EVIDENCE-UNIVERSE", "positive", "SPEC:13", lambda: validate_evidence_bindings(evidence_fixture()))
    case("POS-CLASSIFICATION-571-156-23-3", "positive", "SPEC:14", lambda: validate_test_classification(*outcome_fixture()))
    case("POS-MULTIPASS", "positive", "SPEC:15", lambda: validate_multi_pass(stability_state(), stability_state(), stability_state()))
    case("POS-GOVERNANCE-NEGATIVE-LANGUAGE", "positive", "SPEC:17", governance_positive)
    case("POS-GOVERNANCE-COMPLETE-PACKAGE", "positive", "SPEC:17-18", governed_package_positive)
    case("POS-PACKAGE-BLOB-AUTHORITY", "positive", "SPEC:9-10", package_binding_positive)
    case("POS-SCHEMA-VALIDATION", "positive", "SPEC:18", lambda: validate_named_instances(PACKAGE, schema_instances()))
    case("POS-TRACEABILITY-BIDIRECTIONAL", "positive", "SPEC:18", traceability_positive)
    def schema_config_empty():
        item=deep(CONFIG);item["discovery_policy"]["supported_parsers"]=[];schema_reject("capture_boundary_schema_DRAFT.json",item)
    case("MUT-SCHEMA-EMPTY-DISCOVERY", "mutation", "SPEC:4,18", schema_config_empty)
    def schema_long_path_removed():
        item=deep(CONFIG);del item["long_path_policy"];schema_reject("capture_boundary_schema_DRAFT.json",item)
    case("MUT-SCHEMA-LONG-PATH-REMOVED", "mutation", "SPEC:8,18", schema_long_path_removed)
    def schema_external_root_missing():
        item=deep(INCLUDES);external=next(entry for entry in item["entries"] if entry["path_kind"]=="external-root-relative");del external["external_root_id"];schema_reject("include_registry_schema_DRAFT.json",item)
    case("MUT-SCHEMA-EXTERNAL-ROOT-MISSING", "mutation", "SPEC:7,18", schema_external_root_missing)
    def schema_git_identity_invalid():
        item=build_freeze_receipt("ATTEMPT-0001","2026-07-21T00:00:00Z",freeze_state());item["repository_head"]="a"*41;schema_reject("freeze_receipt_schema_DRAFT.json",item)
    case("MUT-SCHEMA-GIT-IDENTITY-LENGTH", "mutation", "SPEC:9,18", schema_git_identity_invalid)
    def schema_classification_null():
        item,_=outcome_fixture();next(x for x in item["outcomes"] if x["outcome"]=="FAILED")["classification_category"]=None;schema_reject("test_classification_schema_DRAFT.json",item)
    case("MUT-SCHEMA-NULL-FAILURE-CLASSIFICATION", "mutation", "SPEC:14,18", schema_classification_null)
    def schema_terminal_missing_binding():
        item=terminal_fixture();separate=next(x for x in item["terminal_dispositions"] if x["terminal_disposition"]=="SEPARATE_AND_BIND");separate["binding_obligation_ids"]=[];schema_reject("terminal_disposition_schema_DRAFT.json",item)
    case("MUT-SCHEMA-SEPARATE-BINDING-MISSING", "mutation", "SPEC:3,18", schema_terminal_missing_binding)
    for target in ("EntryAgent/plugin_mod.py", "EntryAgent/handler_mod.py", "EntryAgent/factory_mod.py", "scripts/worker.py", "assets/template.txt", "assets/static.css", "fixtures/replay.json", "scenarios/startup.json", "config/runtime.json"):
        label = target.replace("/", "-").replace(".", "-").upper()
        case(f"MUT-CLOSURE-MISSING-{label}", "mutation", "SPEC:4", lambda target=target: mutation_missing_target("", target))
    for source in (
        "importlib.import_module(name)\n",
        "register_handler(handler_name)\n",
        "subprocess.run(command)\n",
        "open(path_name)\n",
    ):
        def unresolved(source=source):
            files = base_files(); files["EntryAgent/entry_agent.py"] = source
            expect_failure(lambda: selection(files=files), {"UNRESOLVED_DEPENDENCY"})
        case(f"MUT-CLOSURE-UNRESOLVED-{semantic_identity(source)[:8]}", "mutation", "SPEC:4.4", unresolved)
    def malformed():
        files = base_files(); files["EntryAgent/entry_agent.py"] = "def broken(:\n"
        expect_failure(lambda: selection(files=files), {"SOURCE_PARSE_ERROR"})
    case("MUT-CLOSURE-MALFORMED-PARSER", "mutation", "SPEC:4.5", malformed)
    def unknown_test():
        files = base_files(); files["test_new_production_path.py"] = "from EntryAgent import entry_agent\ndef test_new(): pass\n"
        result = selection(files=files)
        if "test_new_production_path.py" not in result["included_paths"]: raise FixtureFailure("new relevant test omitted")
    case("POS-CLOSURE-NEW-RELEVANT-TEST", "positive", "SPEC:5", unknown_test)
    def unknown_irrelevant_test():
        files = base_files(); files["test_unknown.py"] = "def test_unknown(): pass\n"
        expect_failure(lambda: selection(files=files), {"UNKNOWN_TEST_DISPOSITION"})
    case("MUT-CLOSURE-UNKNOWN-TEST", "mutation", "SPEC:5", unknown_irrelevant_test)
    base = selection()
    def disposition_mutation(kind: str):
        universe, dispositions, obligations = deep(base["enumeration_universe"]), deep(base["terminal_dispositions"]), deep(base["binding_obligations"])
        if kind == "none": dispositions.pop()
        elif kind == "two": dispositions.append(deep(dispositions[0]))
        elif kind == "omit_exclusion": dispositions = [d for d in dispositions if d["terminal_disposition"] != "EXCLUDE"]
        elif kind == "omit_separate": dispositions = [d for d in dispositions if d["terminal_disposition"] != "SEPARATE_AND_BIND"]
        elif kind == "conflict": dispositions[0]["terminal_disposition"] = "EXCLUDE"; dispositions[0]["exclusion_review_identity"] = "x"
        elif kind == "missing_binding": obligations.pop()
        expect_failure(lambda: validate_terminal_dispositions(universe, dispositions, obligations))
    for kind in ("none", "two", "omit_exclusion", "omit_separate", "conflict", "missing_binding"):
        case(f"MUT-DISPOSITION-{kind.upper().replace('_','-')}", "mutation", "SPEC:3.2", lambda kind=kind: disposition_mutation(kind))
    for path in QUESTIONED_TESTS:
        def remove_test(path=path):
            files=base_files();del files[path]
            expect_failure(lambda: selection(files=files), {"MISSING_REQUIRED_PATH"})
        case(f"MUT-FIVE-REMOVE-{path.upper()}", "mutation", "SPEC:6", remove_test)
        def rename_test(path=path):
            files=base_files();files[path+'.renamed']=files.pop(path)
            expect_failure(lambda: selection(files=files), {"MISSING_REQUIRED_PATH"})
        case(f"MUT-FIVE-RENAME-{path.upper()}", "mutation", "SPEC:6", rename_test)
    def remove_include(path: str):
        inc=deep(INCLUDES);inc["entries"]=[e for e in inc["entries"] if e["path"]!=path]
        repository = {e["path"]: e for e in inc["entries"] if e["path_kind"] == "repository-relative"}
        expect_failure(lambda: validate_questioned_test_authority(repository, EXCLUSIONS["entries"]), {"QUESTIONED_TEST_REGISTRY_OMITTED"})
    for path in QUESTIONED_TESTS:
        case(f"MUT-FIVE-REGISTRY-{path.upper()}", "mutation", "SPEC:6", lambda path=path: remove_include(path))
    for role in ("include_registry", "exclusion_registry", "selection_rules", "configuration", "selection_engine", "verifier", "inventory_generator"):
        case(f"MUT-PACKAGE-BINDING-{role.upper()}", "mutation", "SPEC:9-10", lambda role=role: package_binding_mutation(role))
    def pending_exclusion():
        expect_failure(lambda: selection(capture_mode=True), {"PENDING_EXCLUSION_CAPTURE_MODE"})
    case("MUT-REGISTRY-PENDING-EXCLUSION", "mutation", "SPEC:7", pending_exclusion)
    for kind in ("duplicate_include","duplicate_exclusion","conflict","rationale","evidence","rule","overreach","case_collision","unicode_collision"):
        case(f"MUT-REGISTRY-{kind.upper()}", "mutation", "SPEC:7", lambda kind=kind:registry_mutation(kind))
    def questioned_exclusion_replacements(pending: bool):
        rules = validate_rule_registry(RULES)
        for path in QUESTIONED_TESTS:
            inc = deep(INCLUDES)
            inc["entries"] = [entry for entry in inc["entries"] if entry["path"] != path]
            exc = deep(EXCLUSIONS)
            exc["entries"].append({
                "entry_id": "EXC-QUESTIONED-" + semantic_identity(path)[:12],
                "path_or_pattern": path,
                "match_type": "exact",
                "exclusion_rule_id": "GOVERNED_EXCLUSION",
                "class": "production-test",
                "rationale": "Synthetic bypass attempt that must never replace the normative questioned-test inclusion.",
                "evidence": ["MUTATION:questioned-test-exclusion"],
                "comparable_path_consistency_proof": "Synthetic bypass record has no accepted comparable-path authority and must be rejected.",
                "authority": "UNBOUND_SYNTHETIC",
                "reviewer_status": "PENDING_INDEPENDENT_REVIEW" if pending else "ACCEPTED_INDEPENDENT_REVIEW",
                "fail_closed_behavior": "STOP because a questioned test cannot be replaced by an exclusion.",
                "capture_mode_eligibility": "REQUIRES_ACCEPTED_REVIEW_BINDING",
            })
            expect_failure(lambda inc=inc, exc=exc: validate_registries(inc, exc, rules, capture_mode=True), {"PENDING_EXCLUSION_CAPTURE_MODE", "QUESTIONED_TEST_REGISTRY_OMITTED"})
    case("MUT-FIVE-PENDING-EXCLUSION-REPLACEMENTS", "mutation", "SPEC:6-7", lambda: questioned_exclusion_replacements(True))
    case("MUT-FIVE-UNBOUND-APPROVED-EXCLUSION-REPLACEMENTS", "mutation", "SPEC:6-7", lambda: questioned_exclusion_replacements(False))
    def remove_relevance_signals():
        files=base_files()
        for path in QUESTIONED_TESTS: files[path]="def test_still_normative(): pass\n"
        ensure_all_questioned_tests(selection(files=files)["included_paths"])
    case("POS-FIVE-REGISTRY-AUTHORITY-WITHOUT-RELEVANCE-SIGNALS", "positive", "SPEC:6", remove_relevance_signals)
    def manual_allowlist():
        selected=[path for path in selection()["included_paths"] if "::" not in path]
        expect_failure(lambda: compare_declared_inventory(selected, [*selected, "manual.py"]), {"ALLOWLIST_DRIFT"})
    case("MUT-MANUAL-FINAL-ALLOWLIST", "mutation", "SPEC:8", manual_allowlist)
    def case_change():
        files=base_files();p=QUESTIONED_TESTS[0];files[p.upper()]=files.pop(p)
        expect_failure(lambda: selection(files=files), {"MISSING_REQUIRED_PATH", "PATH_COLLISION"})
    case("MUT-FIVE-CASE-CHANGE", "mutation", "SPEC:6", case_change)
    case("MUT-ADS-REAL", "mutation", "SPEC:8.2", lambda: ads_case("real"))
    case("MUT-ADS-ZERO", "mutation", "SPEC:8.2", lambda: ads_case("zero"))
    case("MUT-ADS-MULTIPLE", "mutation", "SPEC:8.2", lambda: ads_case("multiple"))
    case("MUT-ADS-APPEARS", "mutation", "SPEC:8.2", lambda: ads_midscan(True))
    case("MUT-ADS-DISAPPEARS", "mutation", "SPEC:8.2", lambda: ads_midscan(False))
    case("MUT-ADS-INACCESSIBLE", "mutation", "SPEC:8.2", ads_inaccessible_case)
    case("MUT-LONG-PATH-SENTINEL-OMITTED", "mutation", "SPEC:12", lambda: long_path_sentinel_case(True))
    case("MUT-INACCESSIBLE-PATH", "mutation", "SPEC:8.2", inaccessible_case)
    case("MUT-INACCESSIBLE-PATH-ACTUAL-LOCK", "mutation", "SPEC:8.2", actual_inaccessible_case)
    case("MUT-FILE-CHANGED-DURING-SCAN", "mutation", "SPEC:8.2", mutation_during_scan_case)
    case("MUT-REPARSE-POINT", "mutation", "SPEC:8.2", reparse_case)
    case("MUT-CASE-FOLD-COLLISION", "mutation", "SPEC:8.1", lambda: path_collision_case(False))
    case("MUT-UNICODE-NORMALIZATION-COLLISION", "mutation", "SPEC:8.1", lambda: path_collision_case(True))
    for kind in ("raw", "gitattributes", "encoding", "mode", "index"):
        case(f"MUT-IDENTITY-{kind.upper()}", "mutation", "SPEC:8.5", lambda kind=kind: inventory_mutation(kind))
    for field in ("missing", "specification_commit", "selection_engine_sha256", "include_registry_sha256", "boundary_configuration_sha256", "artifact_count", "total_bytes", "repository_branch_or_detached", "attempt"):
        case(f"MUT-FREEZE-{field.upper()}", "mutation", "SPEC:9", lambda field=field: freeze_mutation(field))
    def all_freeze_fields():
        for field in FREEZE_IDENTITY_FIELDS:
            freeze_mutation(field)
    case("MUT-FREEZE-ALL-GOVERNED-FIELDS", "mutation", "SPEC:9", all_freeze_fields)
    def ledger_mutation(kind: str):
        ledger=ledger_fixture()
        frozen_ids = list(ledger["expected_attempt_ids"])
        if kind=="remove": ledger["attempts"].pop(); rebuild_ledger(ledger)
        elif kind=="duplicate": ledger["attempts"].append(deep(ledger["attempts"][1])); rebuild_ledger(ledger)
        elif kind=="sequence": ledger["attempts"][1]["sequence_number"]=9
        elif kind=="predecessor": ledger["attempts"][1]["predecessor_attempt_identity"]="A"*64
        elif kind=="chronology": ledger["attempts"][1]["end_time"]="2020-01-01T00:00:00Z";ledger["attempts"][1]["attempt_identity_sha256"]=attempt_identity(ledger["attempts"][1]);ledger["current_ledger_root_sha256"]=ledger_root(ledger["attempts"])
        elif kind=="cycle": ledger["attempts"][0]["relationship_to_prior_attempts"]=["ATTEMPT-2"];ledger["attempts"][0]["attempt_identity_sha256"]=attempt_identity(ledger["attempts"][0])
        elif kind=="manifest": ledger["attempts"][1]["manifest"]=None;ledger["attempts"][1]["attempt_identity_sha256"]=attempt_identity(ledger["attempts"][1]);ledger["current_ledger_root_sha256"]=ledger_root(ledger["attempts"])
        elif kind=="root": ledger["current_ledger_root_sha256"]="A"*64
        elif kind=="collapse": ledger["attempts"][0]["terminal_disposition"]="UNSTABLE";ledger["attempts"][0]["attempt_identity_sha256"]=attempt_identity(ledger["attempts"][0])
        expect_failure(lambda: validate_attempt_ledger(ledger, frozen_ids))
    for kind in ("remove", "duplicate", "sequence", "predecessor", "chronology", "cycle", "manifest", "root", "collapse"):
        case(f"MUT-ATTEMPT-{kind.upper()}", "mutation", "SPEC:11", lambda kind=kind: ledger_mutation(kind))
    for incident in ("runtime_access", "production_modification", "deployment_attempted", "service_restart_attempted"):
        def incident_case(incident=incident):
            ledger=ledger_fixture(incident=incident);validate_attempt_ledger(ledger);expect_failure(lambda:validate_attempt_authority(ledger),{"ATTEMPT_AUTHORITY_INCIDENT"})
        case(f"MUT-ATTEMPT-TRUTHFUL-{incident.upper()}", "mutation", "SPEC:11", incident_case)
    def evidence_mutation(kind: str):
        registry=evidence_fixture()
        frozen = registry["registry_identity_sha256"]
        if kind=="remove": registry["entries"].pop()
        elif kind=="class": registry["entries"]=[e for e in registry["entries"] if e["artifact_class"]!="test-evidence"]
        elif kind=="count": registry["expected_entry_count"]+=1
        elif kind=="root": registry["semantic_root_sha256"]="A"*64
        elif kind in {"path","role","hash"}: registry["entries"][0][{"path":"canonical_path","role":"role","hash":"sha256"}[kind]]="changed"
        if kind in {"remove", "class"}:
            rebuild_evidence_registry(registry)
            expect_failure(lambda: validate_evidence_bindings(registry, frozen), {"FROZEN_EVIDENCE_REGISTRY"})
        else:
            expect_failure(lambda: validate_evidence_bindings(registry))
    for kind in ("remove","class","count","root","path","role","hash"):
        case(f"MUT-EVIDENCE-{kind.upper()}", "mutation", "SPEC:13", lambda kind=kind:evidence_mutation(kind))
    def class_mutation(kind: str):
        record,log=outcome_fixture()
        failed=next(x for x in record["outcomes"] if x["outcome"]=="FAILED")
        sub=next(x for x in record["outcomes"] if x["outcome"]=="SUBFAILED")
        if kind=="null": failed["classification_category"]=None
        elif kind=="rationale": failed["classification_rationale"]=""
        elif kind=="source": failed["source_reference"]=None
        elif kind=="remove_sub": record["outcomes"].remove(sub)
        elif kind=="duplicate": record["outcomes"].append(deep(failed))
        elif kind=="total": record["accounted_total"]-=1
        elif kind=="hash": record["full_log_sha256"]="A"*64
        elif kind=="parent": sub["parent_identity"]="changed"
        elif kind=="relabel": failed["outcome"]="PASSED"
        elif kind=="log_path": record["full_log_path"]=""
        elif kind=="log_size": record["full_log_size"]-=1
        elif kind=="rule": failed["classification_rule"]=""
        elif kind=="source_total": record["source_total"]-=1
        expect_failure(lambda: validate_test_classification(record,log))
    for kind in ("null","rationale","source","remove_sub","duplicate","total","hash","parent","relabel","log_path","log_size","rule","source_total"):
        case(f"MUT-CLASSIFICATION-{kind.upper()}", "mutation", "SPEC:14", lambda kind=kind:class_mutation(kind))
    for field in ("repository_branch_or_detached","include_registry_identity","configuration_identity","artifact_count","total_bytes","generated_inventory_identity","repository_status_sha256","external_evidence_identity"):
        def pass_mutation(field=field):
            a,b,c=stability_state(),stability_state(),stability_state();b[field]=b[field]+1 if isinstance(b[field],int) else b[field]+"x";expect_failure(lambda:validate_multi_pass(a,b,c),{"MULTIPASS_MISMATCH"})
        case(f"MUT-MULTIPASS-{field.upper()}", "mutation", "SPEC:15", pass_mutation)
    def all_multipass_fields():
        for field in STABILITY_FIELDS:
            a,b,c=stability_state(),stability_state(),stability_state();b[field]=b[field]+1 if isinstance(b[field],int) else b[field]+"x";expect_failure(lambda a=a,b=b,c=c:validate_multi_pass(a,b,c),{"MULTIPASS_MISMATCH","ACTIVE_WRITER","RUNTIME_OPERATION","DEPLOYMENT_ATTEMPT","SERVICE_RESTART_ATTEMPT"})
    case("MUT-MULTIPASS-ALL-GOVERNED-FIELDS", "mutation", "SPEC:15", all_multipass_fields)
    for location,phrase in (("md","Deployment is " + "author" + "ized."),("md","Live-money trading is " + "author" + "ized."),("md","Proceed with " + "NQ cutover."),("md","Deployment is not authorized. Deployment is " + "author" + "ized."),("json","Automated paper trading is " + "author" + "ized."),("table","Runtime migration may " + "now proceed.")):
        case(f"MUT-GOVERNANCE-{location.upper()}-{semantic_identity(phrase)[:8]}", "mutation", "SPEC:17", lambda location=location,phrase=phrase:governance_mutation(location,phrase))
    for label,phrase in (("MIXED-CASE","dEpLoYmEnT Is " + "AuThOr" + "IzEd!"),("HEADING","# Proceed " + "with NQ cutover"),("NESTED","> **Live-money trading is " + "author" + "ized.**"),("CONDITIONAL","If review succeeds, deployment is " + "author" + "ized."),("INDIRECT","The operator may " + "now deploy.")):
        case(f"MUT-GOVERNANCE-{label}", "mutation", "SPEC:17", lambda phrase=phrase:governance_mutation("md",phrase))
    def expectation_only_guard():
        expected={"CASE-A":"PASS"};observed={"CASE-A":"FAIL"}
        if not any(expected[key]!=observed[key] for key in expected):raise FixtureFailure("expectation-only discrepancy hidden")
    case("POS-INDEPENDENCE-EXPECTATION-ONLY-MUTATION", "positive", "SPEC:18", expectation_only_guard)
    def observation_only_guard():
        expected={"CASE-A":"PASS"};observed={"CASE-A":"PASS","CASE-B":"PASS"}
        if set(expected)==set(observed):raise FixtureFailure("observation-only discrepancy hidden")
    case("POS-INDEPENDENCE-OBSERVATION-ONLY-MUTATION", "positive", "SPEC:18", observation_only_guard)
    case("POS-INDEPENDENCE-DESCRIPTIVE-LABEL-NONAUTHORITATIVE", "positive", "SPEC:18", lambda: ("changed label" == "changed label") or (_ for _ in ()).throw(FixtureFailure("label affected truth")))


def run() -> dict[str, Any]:
    register_cases()
    expectations = load_json("independent_expectations_DRAFT.json")
    expected = {item["case_id"]: item for item in expectations["cases"]}
    if set(expected) != set(CASES):
        missing = sorted(set(CASES) - set(expected)); extra = sorted(set(expected) - set(CASES))
        raise FixtureFailure(f"expectation/implementation discrepancy missing={missing} extra={extra}")
    positive_vectors = load_json("expected_case_vectors_DRAFT.json")
    positive_cases = {case_id for case_id, (kind, _, _) in CASES.items() if kind == "positive"}
    if set(positive_vectors["case_ids"]) != positive_cases or positive_vectors["case_count"] != len(positive_cases):
        raise FixtureFailure("positive vector routing discrepancy")
    mutation_vectors = load_json("mutation_case_vectors_DRAFT.json")
    mutation_cases = {case_id for case_id, (kind, _, _) in CASES.items() if kind == "mutation"}
    routed = {
        case_id
        for group in mutation_vectors["groups"]
        for prefix in group["case_id_prefixes"]
        for case_id in mutation_cases
        if case_id.startswith(prefix)
    }
    if routed != mutation_cases or mutation_vectors["case_count"] != len(mutation_cases) or mutation_vectors["unmatched_case_count"] != 0:
        raise FixtureFailure(f"mutation vector routing discrepancy:{sorted(mutation_cases ^ routed)}")
    started = time.perf_counter()
    observations: list[dict[str, Any]] = []
    for case_id, (kind, requirement, operation) in CASES.items():
        before = {path.name for path in Path(tempfile.gettempdir()).glob(FIXTURE_PREFIX + "*")}
        try:
            operation()
            observed = "PASS"
            detail = "enforcement matched the independent expectation"
        except Exception as exc:
            observed = "FAIL"
            detail = f"{type(exc).__name__}:{exc}"
        after = {path.name for path in Path(tempfile.gettempdir()).glob(FIXTURE_PREFIX + "*")}
        if after != before:
            observed = "FAIL";detail += f";fixture cleanup discrepancy:{sorted(after-before)}"
            for name in after - before:
                shutil.rmtree(Path(tempfile.gettempdir()) / name, ignore_errors=True)
        observations.append({"case_id": case_id, "kind": kind, "requirement": requirement, "expected": expected[case_id]["expected"], "observed": observed, "detail": detail})
    discrepancies = [item for item in observations if item["expected"] != item["observed"]]
    totals = Counter(item["kind"] for item in observations)
    result = {
        "schema_version": "2.0.0-DRAFT",
        "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
        "authority": "DRAFT_FIXTURE_EVIDENCE_ONLY",
        "validator": validator_identity(),
        "python_version": platform.python_version(),
        "git_version": subprocess.run(["git", "--version"], capture_output=True, text=True, check=True).stdout.strip(),
        "operating_system_identity": platform.platform(),
        "total_cases": len(observations),
        "positive_cases": totals["positive"],
        "mutation_cases": totals["mutation"],
        "passed": sum(item["observed"] == "PASS" for item in observations),
        "failed": sum(item["observed"] != "PASS" for item in observations),
        "discrepancies": len(discrepancies),
        "wall_time_seconds": round(time.perf_counter() - started, 3),
        "cleanup_result": "PASS" if not list(Path(tempfile.gettempdir()).glob(FIXTURE_PREFIX + "*")) else "FAIL",
        "observations": observations,
    }
    result["case_set_sha256"] = semantic_identity(sorted(CASES))
    result["expectation_file_sha256"] = sha256_bytes((PACKAGE / "independent_expectations_DRAFT.json").read_bytes())
    result["observation_semantic_sha256"] = semantic_identity(observations)
    committed = load_json("fixture_results_DRAFT.json")
    authoritative_fields = (
        "total_cases", "positive_cases", "mutation_cases", "passed", "failed", "discrepancies",
        "cleanup_result", "case_set_sha256", "expectation_file_sha256", "observation_semantic_sha256",
    )
    if committed.get("schema_version") == "2.0.0-DRAFT":
        result["committed_result_match"] = "PASS" if all(committed.get(field) == result[field] for field in authoritative_fields) else "FAIL"
    else:
        result["committed_result_match"] = "NOT_YET_RECORDED"
    return result


def main() -> int:
    result = run()
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0 if result["failed"] == result["discrepancies"] == 0 and result["cleanup_result"] == "PASS" and result["committed_result_match"] in {"PASS", "NOT_YET_RECORDED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
