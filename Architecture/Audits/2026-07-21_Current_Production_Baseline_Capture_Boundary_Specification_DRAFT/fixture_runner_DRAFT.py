#!/usr/bin/env python3
"""R2 independent-expectation and raw-observation verification runner.

This draft utility operates only on disposable fixture roots.  A mutation case
passes only when its real enforcing function produces the immutable expected
rejection code and surface.  No helper converts an expected exception to PASS.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from governed_file_access_DRAFT import enumerate_directory as governed_enumerate_directory
from governed_file_access_DRAFT import enumerate_regular_files as governed_enumerate_regular_files
from governed_file_access_DRAFT import canonical_absolute_path as governed_canonical_absolute_path

from boundary_verifier_DRAFT import (
    BoundaryError,
    FREEZE_V4_FIELDS,
    QUESTIONED_TESTS,
    STABILITY_FIELDS,
    attempt_entry_hash_v4,
    canonical_json_bytes,
    chained_ledger_root_v4,
    derive_accepted_specification_authority,
    derive_committed_package_authority,
    derive_selection_from_accepted_specification,
    evidence_registry_root,
    find_authorization_leakage,
    observe_controlled_repository_state,
    reconstruct_freeze_authority_v4,
    semantic_identity,
    sha256_bytes,
    stored_json_bytes,
    strict_json_loads,
    validate_attempt_capture_authority_v4,
    validate_attempt_ledger_v4,
    validate_authorization_state,
    validate_boundary_configuration,
    validate_evidence_bindings_v4,
    validate_freeze_v4,
    validate_git_command_argv,
    validate_governance_package,
    validate_multi_pass,
    validate_operational_package_authority,
    validate_package_checkout,
    validate_registries,
    validate_required_evidence_policy,
    validate_rule_registry,
    validate_terminal_against_authority,
    validate_terminal_result,
    validate_test_classification,
    validate_traceability_v4,
    verify_stored_canonical_json,
    verify_freeze_claim_v4,
)
from historical_log_parser_DRAFT import HistoricalLogError, validate_historical_record
from inventory_generator_DRAFT import (
    InventoryError,
    alternate_data_streams,
    enumerate_inventory,
    extended_length_path,
    stable_read,
)
from schema_validation_DRAFT import (
    SchemaValidationError,
    strict_canonical_json_loads,
    validate_governed_artifact,
    validate_schema_and_instance,
    validator_identity,
)
from selection_engine_DRAFT import derive_repository_selection
from governed_file_access_DRAFT import read_binary as governed_read_binary


PACKAGE = Path(__file__).resolve().parent
FIXTURE_PREFIX = "randle_boundary_r2_v4_"
EXTERNAL_LOG = Path(
    r"C:\Users\Trader\OneDrive\RandleRuntimeData\provenance"
    r"\current_production_baseline_capture_20260720_retry1"
    r"\command_results\18_broad_captured_entry_agent_pytest.log"
)
EXTERNAL_LOG_LOGICAL_PATH = (
    "provenance/current_production_baseline_capture_20260720_retry1/"
    "command_results/18_broad_captured_entry_agent_pytest.log"
)
HARNESS_VERSION = "4.0.0-DRAFT"
CaseOperation = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]


class FixtureInfrastructureError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


def read_bytes(path: Path) -> bytes:
    return governed_read_binary(path).data


def load_json(name: str) -> Any:
    return strict_canonical_json_loads(read_bytes(PACKAGE / name))


def write_fixture(path: Path, data: bytes | str) -> None:
    os.makedirs(extended_length_path(path.parent), exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    with open(extended_length_path(path), "wb") as handle:
        handle.write(payload)


def git(repository: Path, *args: str, input_bytes: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    command = ["git", "-c", "core.longpaths=true", "-c", f"safe.directory={repository.as_posix()}", "-C", os.fspath(repository), *args]
    validate_git_command_argv(command)
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
            "TZ": "UTC",
        }
    )
    result = subprocess.run(
        command,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=environment,
    )
    if check and result.returncode:
        raise FixtureInfrastructureError("FIXTURE_GIT", result.stderr.decode("utf-8", "replace"))
    return result


def make_repository(files: Mapping[str, bytes | str], *, attributes: str | None = None) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX)
    root = Path(temporary.name)
    write_fixture(root / ".boundary_fixture_root", b"RANDLE-BOUNDARY-FIXTURE\n")
    git(root, "init", "-q")
    material = dict(files)
    if attributes is not None:
        material[".gitattributes"] = attributes
    for relative, data in material.items():
        write_fixture(root / relative, data)
    if material:
        git(root, "add", "--", *sorted(material))
        git(root, "-c", "user.name=Randle Fixture", "-c", "user.email=fixture@invalid", "commit", "-q", "-m", "fixture")
    return temporary, root


def success(surface: str, *evidence: str, identities: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    return {
        "code": "OK",
        "surface": surface,
        "evidence": list(evidence) or ["REAL_ENFORCING_SURFACE"],
        "authority_result": "SATISFIED",
        "identities": dict(identities or {}),
    }


def exception_code(exc: BaseException) -> str:
    if hasattr(exc, "code"):
        return str(getattr(exc, "code"))
    text = str(exc)
    return text.split(":", 1)[0] if text else type(exc).__name__


def exception_surface(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)
    ignored = {"require", "_require_fields"}
    for frame in reversed(frames):
        name = Path(frame.filename).name
        if name in {
            "boundary_verifier_DRAFT.py",
            "inventory_generator_DRAFT.py",
            "selection_engine_DRAFT.py",
            "schema_validation_DRAFT.py",
            "historical_log_parser_DRAFT.py",
            "fixture_runner_DRAFT.py",
        } and frame.name not in ignored:
            return f"{name[:-3]}.{frame.name}"
    return f"{type(exc).__module__}.{type(exc).__name__}"


def execute_raw(case_definition: Mapping[str, Any], operation: CaseOperation) -> dict[str, Any]:
    case_id = case_definition["case_id"]
    try:
        result = operation(case_definition) or {}
        if not isinstance(result, Mapping) or not {"code", "surface", "evidence", "authority_result", "identities"} <= set(result):
            raise FixtureInfrastructureError("INVALID_SUCCESS_OBSERVATION", case_id)
        return {
            "case_id": case_id,
            "observed_status": "ACCEPTED",
            "observed_disposition": "CONTINUE",
            "observed_code": result["code"],
            "observed_enforcing_surface": result["surface"],
            "observed_evidence": result["evidence"],
            "observed_authority_result": result["authority_result"],
            "observed_identities": {"authoritative_input_identity": case_definition["authoritative_input_identity"], **result["identities"]},
        }
    except BaseException as exc:
        return {
            "case_id": case_id,
            "observed_status": "REJECTED",
            "observed_disposition": "TERMINATE",
            "observed_code": exception_code(exc),
            "observed_enforcing_surface": exception_surface(exc),
            "observed_evidence": ["ERROR_CODE", "TRACEBACK_SURFACE"],
            "observed_authority_result": "REJECTED",
            "observed_identities": {"authoritative_input_identity": case_definition["authoritative_input_identity"]},
        }


def compare_observations(expectations: Mapping[str, Any], observations: list[Mapping[str, Any]]) -> dict[str, Any]:
    expected = {item["case_id"]: item for item in expectations["cases"]}
    if len(expected) != len(expectations["cases"]):
        raise FixtureInfrastructureError("DUPLICATE_EXPECTATION")
    observed = {item["case_id"]: item for item in observations}
    if set(expected) != set(observed):
        raise FixtureInfrastructureError("EXPECTATION_OBSERVATION_SET", repr(sorted(set(expected) ^ set(observed))))
    fields = (
        ("expected_status", "observed_status"),
        ("expected_disposition", "observed_disposition"),
        ("expected_code", "observed_code"),
        ("expected_enforcing_surface", "observed_enforcing_surface"),
        ("expected_evidence_obligations", "observed_evidence"),
        ("expected_authority_result", "observed_authority_result"),
    )
    discrepancies: list[dict[str, Any]] = []
    for case_id in sorted(expected):
        for expected_field, observed_field in fields:
            if expected[case_id][expected_field] != observed[case_id][observed_field]:
                discrepancies.append(
                    {
                        "case_id": case_id,
                        "field": observed_field,
                        "expected": expected[case_id][expected_field],
                        "observed": observed[case_id][observed_field],
                    }
                )
    receipt = {
        "comparison_completed": True,
        "expectation_count": len(expected),
        "observation_count": len(observed),
        "discrepancies": discrepancies,
        "discrepancy_count": len(discrepancies),
    }
    receipt["comparison_receipt_sha256"] = semantic_identity(receipt)
    return receipt


def require_comparison_receipt(receipt: Mapping[str, Any] | None) -> None:
    if not isinstance(receipt, Mapping) or receipt.get("comparison_completed") is not True:
        raise FixtureInfrastructureError("COMPARISON_NOT_COMPLETED")
    semantic = {key: value for key, value in receipt.items() if key != "comparison_receipt_sha256"}
    if receipt.get("comparison_receipt_sha256") != semantic_identity(semantic):
        raise FixtureInfrastructureError("COMPARISON_RECEIPT_IDENTITY")
    if receipt.get("discrepancy_count") != len(receipt.get("discrepancies", [])):
        raise FixtureInfrastructureError("COMPARISON_RECEIPT_COUNT")


def generic_include(path: str, index: int) -> dict[str, Any]:
    return {
        "entry_id": f"INC-R2-{index:03d}",
        "path": path,
        "path_kind": "repository-relative",
        "class": "production-runtime-source",
        "selection_rule_id": "GOVERNED_INCLUDE_SEED",
        "evidence_references": ["SPEC:4.1", "R2:REAL-PARSER"],
        "authority_status": "DRAFT_REQUIRED_PENDING_INDEPENDENT_REVIEW",
        "required_capture_form": "RAW_AND_GIT_OBJECT",
        "expected_existence_state": "MUST_EXIST_AT_FREEZE",
        "rationale": "Disposable governed fixture source used to exercise the actual parser-backed selection interface.",
    }


def selection_documents(files: Mapping[str, bytes | str]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    base_include = load_json("include_registry_DRAFT.json")
    mandatory = [copy.deepcopy(item) for item in base_include["entries"] if item["path"] in QUESTIONED_TESTS]
    known = {item["path"] for item in mandatory}
    entries = mandatory + [generic_include(path, index) for index, path in enumerate(sorted(files), 1) if path not in known]
    include = {"schema_version": "4.0.0-DRAFT", "canonical_serialization": "RANDLE-CAPTURE-CJSON-1", "entries": entries}
    exclusion = {"schema_version": "4.0.0-DRAFT", "canonical_serialization": "RANDLE-CAPTURE-CJSON-1", "validation_mode": "DRAFT_SPECIFICATION", "entries": []}
    return include, exclusion, load_json("selection_rule_registry_DRAFT.json"), load_json("boundary_config_DRAFT.json")


def registry_bindings(documents: tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]) -> dict[str, str]:
    names = ("include_registry_blob", "exclusion_registry_blob", "selection_rule_registry_blob", "boundary_configuration_blob")
    return {
        name: hashlib.sha1(b"blob " + str(len(stored_json_bytes(document))).encode("ascii") + b"\0" + stored_json_bytes(document)).hexdigest()
        for name, document in zip(names, documents)
    }


def selection_case(files: Mapping[str, bytes | str]) -> Mapping[str, Any]:
    complete = dict(files)
    for name in QUESTIONED_TESTS:
        complete.setdefault(name, "def test_mandatory_boundary():\n    assert True\n")
    temporary, root = make_repository(complete)
    try:
        documents = selection_documents(complete)
        result = derive_repository_selection(root, *documents, authority_universe=load_json("governed_authority_universe_DRAFT.json"), registry_bindings=registry_bindings(documents))
        return success(
            "selection_engine_DRAFT.derive_repository_selection",
            "PARSER_EDGE_RECORDS",
            "TERMINAL_DISPOSITIONS",
            identities={"selection": result["disposition_set_sha256"]},
        )
    finally:
        temporary.cleanup()


def op_dependency(case: Mapping[str, Any]) -> Mapping[str, Any]:
    vector = case["vector"]
    files: dict[str, str]
    if vector == "positive_python":
        files = {
            "app.py": (
                "import importlib\nimport subprocess\nimport unittest\nfrom pathlib import Path\nfrom pkg import module\n"
                "RESOURCE='resource'+'_data'\nopen(RESOURCE).read()\nPath('asset').read_text()\n"
                "importlib.import_module('plugin')\n__import__('plugin')\n"
                "register_handler('handler.module')\nregister_factory('factory.module')\nregister_plugin('plugin')\n"
                "app.add_url_rule('/x','x','handler.module')\nrender_template('template.html')\n"
                "load_replay('replay.json')\nregister_scenario('scenario.json')\n"
                "subprocess.run(['python','worker.py'])\n"
                "@pytest.fixture\ndef sample_fixture(): return 1\n"
                "def test_fixture_relation(sample_fixture): assert sample_fixture\n"
                "class TestUnit(unittest.TestCase): pass\n"
            ),
            "plugin.py": "VALUE=1\n",
            "pkg/__init__.py": "VALUE=1\n",
            "pkg/module.py": "from . import helper\n",
            "pkg/helper.py": "VALUE=1\n",
            "handler/module.py": "VALUE=1\n",
            "factory/module.py": "VALUE=1\n",
            "worker.py": "VALUE=1\n",
            "resource_data": "x",
            "asset": "y",
            "template.html": "template",
            "replay.json": "{}\n",
            "scenario.json": "{}\n",
        }
    elif vector == "positive_configs":
        files = {
            "app.py": "VALUE=1\n",
            "target": "x",
            "config.json": '{"target":"target"}\n',
            "config.yaml": "target: target\n",
            "config.toml": 'target = "target"\n',
            "config.ini": "[main]\ntarget=target\n",
        }
    elif vector == "positive_launchers":
        files = {
            "app.py": "VALUE=1\n",
            "helper.ps1": "# helper\n",
            "module.psm1": "# module\n",
            "config.json": "{}\n",
            "output.txt": "output\n",
            "launch.ps1": (
                "& '.\\app.py'\n. '.\\helper.ps1'\n"
                "Start-Process -FilePath '.\\app.py'\nImport-Module '.\\module.psm1'\n"
                "Get-Content -LiteralPath '.\\config.json'\nSet-Content -LiteralPath '.\\output.txt' -Value 'x'\n"
                "Test-Path -LiteralPath '.\\config.json'\n"
            ),
            "launch.sh": "python app.py\n",
            "launch.cmd": "python app.py\n",
        }
    else:
        vectors = {
            "extensionless_open": {"app.py": 'open("missing_resource").read()\n'},
            "missing_route": {"app.py": 'app.add_url_rule("/x", "x", missing_handler)\n'},
            "missing_handler": {"app.py": 'register_handler("missing.handler")\n'},
            "missing_factory": {"app.py": 'register_factory("missing.factory")\n'},
            "missing_plugin": {"app.py": 'register_plugin("missing.plugin")\n'},
            "missing_launcher": {"launch.sh": "python missing_launcher\n"},
            "missing_config": {"config.json": '{"target":"missing_config"}\n'},
            "missing_static": {"app.py": 'render_template("missing_asset")\n'},
            "missing_subprocess": {"app.py": 'import subprocess\nsubprocess.run(["python","missing_process"])\n'},
            "missing_file_open": {"app.py": 'open(file="missing_file").read()\n'},
            "malformed_json": {"config.json": '{"target":]\n'},
            "malformed_yaml": {"config.yaml": "target: [unterminated\n"},
            "malformed_toml": {"config.toml": 'target = "unterminated\n'},
            "malformed_ini": {"config.ini": "[broken\ntarget=x\n"},
            "unsupported_powershell": {"launch.ps1": "$x='missing'; & $x\n"},
            "unsupported_shell": {"launch.sh": "if true; then python app.py; fi\n", "app.py": "VALUE=1\n"},
            "unresolved_dynamic_import": {"app.py": "import importlib\nname=input()\nimportlib.import_module(name)\n"},
            "pathlib_extensionless": {"app.py": "from pathlib import Path\nPath('missing_path').read_text()\n"},
            "constant_concat": {"app.py": "RESOURCE='missing_'+'resource'\nopen(RESOURCE).read()\n"},
        }
        files = vectors[vector]
    return selection_case(files)


def valid_terminal() -> tuple[dict[str, Any], list[str], dict[str, str]]:
    rule_blob = "a" * 40
    bindings = {
        "include_registry_blob": "b" * 40,
        "exclusion_registry_blob": "c" * 40,
        "selection_rule_registry_blob": rule_blob,
        "boundary_configuration_blob": "d" * 40,
    }
    universe = ["a.py", "cache.pyc", "runtime.log"]
    records: list[dict[str, Any]] = []
    specs = [
        ("a.py", "INCLUDE", "RAW_AND_GIT_OBJECT", [], None, None),
        ("cache.pyc", "EXCLUDE", "NO_CONTENT_EXCLUSION", [], semantic_identity("review"), None),
        ("runtime.log", "SEPARATE_AND_BIND", "SEPARATE_CONTENT_BINDING", ["BIND-1"], None, semantic_identity("separate")),
    ]
    for path, disposition, capture, obligation_ids, review, separate in specs:
        evidence = [f"EVIDENCE:{path}"]
        authority = f"AUTHORITY:{path}"
        records.append(
            {
                "artifact_key": path,
                "canonical_path": path,
                "path_kind": "repository-relative",
                "artifact_class": "fixture",
                "terminal_disposition": disposition,
                "governing_rule": "GOVERNED_INCLUDE_SEED",
                "rule_registry_blob": rule_blob,
                "authority": authority,
                "authority_identity": semantic_identity(authority),
                "rationale": "Complete disposable terminal disposition authority record for independent mutation verification.",
                "evidence": evidence,
                "evidence_identities": [semantic_identity(item) for item in evidence],
                "source_identity": semantic_identity({"path": path}),
                "capture_form": capture,
                "existence_state": "MAY_EXIST_CLASSIFIED",
                "external_root_id": None,
                "binding_obligation_ids": obligation_ids,
                "exclusion_review_identity": review,
                "separate_evidence_registry_identity": separate,
            }
        )
    obligation = {
        "obligation_id": "BIND-1",
        "artifact_key": "runtime.log",
        "canonical_path": "runtime.log",
        "role": "runtime-log",
        "authority": "AUTHORITY:runtime.log",
        "required_fields": ["canonical_path", "role", "byte_size", "sha256", "git_blob", "authority_status", "immutability_status", "required_for_recovery"],
        "evidence": ["EVIDENCE:runtime.log"],
    }
    result = {
        "enumeration_universe": list(universe),
        "terminal_dispositions": records,
        "binding_obligations": [obligation],
        "included_paths": ["a.py"],
        "excluded_paths": ["cache.pyc"],
        "separately_bound_paths": ["runtime.log"],
        "included_set_sha256": semantic_identity(["a.py"]),
        "excluded_set_sha256": semantic_identity(["cache.pyc"]),
        "separately_bound_set_sha256": semantic_identity(["runtime.log"]),
        "disposition_set_sha256": semantic_identity(records),
        "enumeration_universe_sha256": semantic_identity(universe),
        "binding_obligation_set_sha256": semantic_identity([obligation]),
        **bindings,
    }
    return result, universe, bindings


def rebuild_terminal(result: dict[str, Any]) -> None:
    result["included_paths"] = sorted(item["artifact_key"] for item in result["terminal_dispositions"] if item["terminal_disposition"] == "INCLUDE")
    result["excluded_paths"] = sorted(item["artifact_key"] for item in result["terminal_dispositions"] if item["terminal_disposition"] == "EXCLUDE")
    result["separately_bound_paths"] = sorted(item["artifact_key"] for item in result["terminal_dispositions"] if item["terminal_disposition"] == "SEPARATE_AND_BIND")
    result["included_set_sha256"] = semantic_identity(result["included_paths"])
    result["excluded_set_sha256"] = semantic_identity(result["excluded_paths"])
    result["separately_bound_set_sha256"] = semantic_identity(result["separately_bound_paths"])
    result["disposition_set_sha256"] = semantic_identity(result["terminal_dispositions"])
    result["enumeration_universe_sha256"] = semantic_identity(result["enumeration_universe"])
    result["binding_obligation_set_sha256"] = semantic_identity(result["binding_obligations"])


def op_terminal(case: Mapping[str, Any]) -> Mapping[str, Any]:
    result, universe, bindings = valid_terminal()
    vector = case["vector"]
    if vector == "positive":
        validate_terminal_against_authority(result, universe, bindings)
        return success("boundary_verifier_DRAFT.validate_terminal_against_authority", "COMPLETE_DISPOSITION_ROOT", "REGISTRY_BLOBS")
    if vector == "missing":
        result["terminal_dispositions"].pop()
    elif vector == "duplicate":
        result["terminal_dispositions"].append(copy.deepcopy(result["terminal_dispositions"][0]))
    elif vector == "conflict":
        duplicate = copy.deepcopy(result["terminal_dispositions"][0]); duplicate["terminal_disposition"] = "EXCLUDE"; result["terminal_dispositions"].append(duplicate)
    elif vector == "include_rogue_binding":
        result["terminal_dispositions"][0]["binding_obligation_ids"] = ["ROGUE"]
    elif vector == "exclude_include_metadata":
        result["terminal_dispositions"][1]["capture_form"] = "RAW_AND_GIT_OBJECT"
    elif vector == "separate_no_evidence":
        result["terminal_dispositions"][2]["evidence"] = []
    elif vector == "alter_authority":
        result["terminal_dispositions"][0]["authority_identity"] = semantic_identity("forged")
    elif vector == "alter_evidence":
        result["terminal_dispositions"][0]["evidence"][0] += "-forged"
    elif vector == "alter_rule_blob":
        result["selection_rule_registry_blob"] = "e" * 40
    elif vector == "self_root_omission":
        result["enumeration_universe"].pop(); result["terminal_dispositions"].pop(); result["binding_obligations"].clear()
    elif vector == "unenumerated_add":
        rogue = copy.deepcopy(result["terminal_dispositions"][0]); rogue["artifact_key"] = rogue["canonical_path"] = "rogue.py"; rogue["source_identity"] = semantic_identity({"path":"rogue.py"}); result["terminal_dispositions"].append(rogue); result["enumeration_universe"].append("rogue.py")
    rebuild_terminal(result)
    validate_terminal_against_authority(result, universe, bindings)
    return success("boundary_verifier_DRAFT.validate_terminal_against_authority")


def schema_by_name(name: str) -> Mapping[str, Any]:
    return load_json(name)


def op_schema(case: Mapping[str, Any]) -> Mapping[str, Any]:
    vector = case["vector"]
    if vector == "governed_pipeline":
        raw = read_bytes(PACKAGE / "authorization_state_DRAFT.json")
        schema = schema_by_name("authorization_state_schema_DRAFT.json")
        expected = load_json("authorization_state_DRAFT.json")
        validate_governed_artifact(
            raw,
            schema,
            validate_authorization_state,
            lambda value: (_ for _ in ()).throw(FixtureInfrastructureError("PIPELINE_CROSS_ARTIFACT"))
            if set(value["protected_domains"]) != set(expected["protected_domains"])
            else None,
            lambda value: (_ for _ in ()).throw(FixtureInfrastructureError("PIPELINE_IMMUTABLE_AUTHORITY"))
            if semantic_identity(value) != semantic_identity(expected)
            else None,
            "authorization_state",
        )
        return success(
            "schema_validation_DRAFT.validate_governed_artifact",
            "STRICT_SCHEMA_SEMANTIC_CROSS_AUTHORITY_PIPELINE",
        )
    if vector == "all_metaschemas":
        names = sorted(path.name for path in _governed_schema_paths())
        for name in names:
            validate_schema_and_instance(schema_by_name(name), _minimal_valid_instance(name), f"active:{name}")
        return success("schema_validation_DRAFT.validate_schema_and_instance", "DRAFT_2020_12", "ACTIVE_INSTANCES", identities={"schemas": semantic_identity(names)})
    config = copy.deepcopy(load_json("boundary_config_DRAFT.json"))
    semantic = None
    schema_name = "capture_boundary_schema_DRAFT.json"
    if vector in {"empty_discovery", "removed_long_path", "removed_ads", "removed_stability", "invalid_external_root"}:
        if vector == "empty_discovery":
            config["discovery_policy"]["supported_parsers"] = []
        elif vector == "removed_long_path":
            config.pop("long_path_policy")
        elif vector == "removed_ads":
            config.pop("ads_policy")
        elif vector == "removed_stability":
            config.pop("stability_policy")
        else:
            config["external_roots"][0].pop("root_id")
        instance = config
    elif vector == "pending_exclusion":
        instance = copy.deepcopy(load_json("exclusion_registry_DRAFT.json"))
        instance["validation_mode"] = "CAPTURE"
        schema_name = "exclusion_registry_schema_DRAFT.json"
    elif vector == "unknown_rule":
        instance = copy.deepcopy(load_json("include_registry_DRAFT.json"))
        instance["entries"][0]["selection_rule_id"] = "UNKNOWN_RULE"
        schema_name = "include_registry_schema_DRAFT.json"
    elif vector == "missing_disposition_field":
        instance = valid_terminal()[0]
        instance["terminal_dispositions"][0].pop("authority")
        schema_name = "terminal_disposition_schema_DRAFT.json"
    elif vector == "incomplete_freeze":
        instance = _minimal_valid_instance("freeze_receipt_schema_DRAFT.json")
        instance.pop("schema_set_identity")
        schema_name = "freeze_receipt_schema_DRAFT.json"
    elif vector == "incomplete_attempt":
        instance = ledger_fixture()[0]
        instance.pop("current_ledger_root")
        schema_name = "attempt_ledger_schema_DRAFT.json"
    elif vector == "incomplete_evidence":
        instance = evidence_fixture()[0]
        instance.pop("policy_blob")
        schema_name = "durable_evidence_binding_registry_schema_DRAFT.json"
    elif vector == "authorization_positive":
        instance = copy.deepcopy(load_json("authorization_state_DRAFT.json"))
        instance["protected_domains"]["deployment"] = "AUTHORIZED"
        schema_name = "authorization_state_schema_DRAFT.json"
    elif vector == "invalid_git_length":
        instance = _minimal_valid_instance("freeze_receipt_schema_DRAFT.json")
        instance["repository_head"] = "a" * 41
        schema_name = "freeze_receipt_schema_DRAFT.json"
    elif vector == "empty_classification":
        instance = copy.deepcopy(load_json("historical_classification_DRAFT.json"))
        instance["outcomes"][0]["classification_rationale"] = ""
        schema_name = "test_classification_schema_DRAFT.json"
    else:
        raise FixtureInfrastructureError("UNKNOWN_SCHEMA_VECTOR", vector)
    validate_schema_and_instance(schema_by_name(schema_name), instance, vector)
    return success("schema_validation_DRAFT.validate_schema_and_instance")


def op_semantic(case: Mapping[str, Any]) -> Mapping[str, Any]:
    vector = case["vector"]
    if vector in {"empty_discovery", "removed_long_path", "removed_ads", "removed_stability", "invalid_external_root"}:
        instance = copy.deepcopy(load_json("boundary_config_DRAFT.json"))
        if vector == "empty_discovery": instance["discovery_policy"]["supported_parsers"] = []
        elif vector == "removed_long_path": instance.pop("long_path_policy")
        elif vector == "removed_ads": instance.pop("ads_policy")
        elif vector == "removed_stability": instance.pop("stability_policy")
        else: instance["external_roots"][0].pop("root_id")
        validate_boundary_configuration(instance, load_json("governed_authority_universe_DRAFT.json"))
        return success("boundary_verifier_DRAFT.validate_boundary_configuration")
    if vector in {"pending_exclusion", "unknown_rule"}:
        include = copy.deepcopy(load_json("include_registry_DRAFT.json"))
        exclusion = copy.deepcopy(load_json("exclusion_registry_DRAFT.json"))
        if vector == "pending_exclusion": exclusion["validation_mode"] = "CAPTURE"
        else: include["entries"][0]["selection_rule_id"] = "UNKNOWN_RULE"
        rules = validate_rule_registry(load_json("selection_rule_registry_DRAFT.json"))
        validate_registries(include, exclusion, rules, authority_universe=load_json("governed_authority_universe_DRAFT.json"), capture_mode=vector=="pending_exclusion")
        return success("boundary_verifier_DRAFT.validate_registries")
    if vector == "invalid_git_length":
        receipt = _minimal_valid_instance("freeze_receipt_schema_DRAFT.json")
        receipt["repository_head"] = "a" * 41
        receipt["freeze_receipt_sha256"] = semantic_identity({key:value for key,value in receipt.items() if key!="freeze_receipt_sha256"})
        reconstructed = {field:receipt[field] for field in FREEZE_V4_FIELDS}
        validate_freeze_v4(receipt, reconstructed)
        return success("boundary_verifier_DRAFT.validate_freeze_v4")
    if vector == "missing_disposition_field":
        instance, universe, bindings = valid_terminal(); instance["terminal_dispositions"][0].pop("authority")
        validate_terminal_against_authority(instance, universe, bindings)
        return success("boundary_verifier_DRAFT.validate_terminal_against_authority")
    if vector == "incomplete_freeze":
        receipt = _minimal_valid_instance("freeze_receipt_schema_DRAFT.json"); receipt.pop("schema_set_identity")
        validate_freeze_v4(receipt, {field:receipt.get(field) for field in FREEZE_V4_FIELDS})
        return success("boundary_verifier_DRAFT.validate_freeze_v4")
    if vector == "incomplete_attempt":
        ledger, prefix, binding = ledger_fixture(); ledger.pop("current_ledger_root")
        validate_attempt_ledger_v4(ledger, prefix, binding)
        return success("boundary_verifier_DRAFT.validate_attempt_ledger_v4")
    if vector == "incomplete_evidence":
        registry, policy, binding, ledger, payloads = evidence_fixture(); registry.pop("policy_blob")
        validate_evidence_bindings_v4(registry, policy, binding, attempt_ledger=ledger, artifact_bytes=payloads)
        return success("boundary_verifier_DRAFT.validate_evidence_bindings_v4")
    if vector == "empty_classification":
        instance = copy.deepcopy(load_json("historical_classification_DRAFT.json")); instance["outcomes"][0]["classification_rationale"] = ""
        validate_test_classification(instance, read_bytes(EXTERNAL_LOG))
        return success("boundary_verifier_DRAFT.validate_test_classification")
    raise FixtureInfrastructureError("UNKNOWN_SEMANTIC_VECTOR", vector)


def _minimal_valid_instance(name: str) -> Any:
    if name == "authorization_state_schema_DRAFT.json":
        return load_json("authorization_state_DRAFT.json")
    if name == "case_definition_schema_DRAFT.json":
        return load_json("case_definitions_DRAFT.json")
    if name == "independent_expectations_schema_DRAFT.json":
        return load_json("independent_expectations_DRAFT.json")
    if name == "semantic_traceability_schema_DRAFT.json":
        return load_json("semantic_traceability_DRAFT.json")
    if name == "required_evidence_policy_schema_DRAFT.json":
        return load_json("required_evidence_policy_DRAFT.json")
    if name == "attempt_prefix_authority_schema_DRAFT.json":
        return load_json("attempt_prefix_authority_DRAFT.json")
    if name == "operational_package_interface_schema_DRAFT.json":
        return load_json("operational_package_interface_DRAFT.json")
    if name == "test_classification_schema_DRAFT.json":
        return load_json("historical_classification_DRAFT.json")
    if name == "capture_boundary_schema_DRAFT.json":
        return load_json("boundary_config_DRAFT.json")
    if name == "include_registry_schema_DRAFT.json":
        return load_json("include_registry_DRAFT.json")
    if name == "exclusion_registry_schema_DRAFT.json":
        return load_json("exclusion_registry_DRAFT.json")
    if name == "selection_rule_registry_schema_DRAFT.json":
        return load_json("selection_rule_registry_DRAFT.json")
    if name == "terminal_disposition_schema_DRAFT.json":
        return valid_terminal()[0]
    if name == "attempt_ledger_schema_DRAFT.json":
        return ledger_fixture()[0]
    if name == "durable_evidence_binding_registry_schema_DRAFT.json":
        return evidence_fixture()[0]
    if name == "freeze_receipt_schema_DRAFT.json":
        state = {field: semantic_identity(field) for field in FREEZE_V4_FIELDS}
        git_fields = {
            "specification_commit","specification_parent","specification_tree","specification_document_blob",
            "include_registry_blob","exclusion_registry_blob","selection_rule_registry_blob","boundary_configuration_blob",
            "selection_engine_blob","inventory_generator_blob","boundary_verifier_blob","authorization_state_blob",
            "evidence_policy_blob","attempt_prefix_authority_blob","repository_head","repository_parent",
        }
        for field in git_fields:
            state[field] = "a" * 40
        state.update({
            "schema_version": "4.0.0-DRAFT", "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
            "artifact_count": 1, "total_bytes": 1, "repository_branch_or_detached": "fixture",
            "repository_object_format": "sha1", "operational_capture_script_blob": "b" * 40,
            "attempt_id": "attempt-1", "timestamp_authority": "2026-07-21T00:00:00Z",
            "freeze_receipt_sha256": "F" * 64,
        })
        return state
    if name == "durable_manifest_schema_DRAFT.json":
        return {
            "schema_version": "3.0.0-DRAFT",
            "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
            "enumeration": {},
            "artifacts": [],
            "total_artifact_count": 0,
            "total_bytes": 0,
            "artifact_path_set_sha256": "A" * 64,
            "artifact_set_semantic_sha256": "B" * 64,
            "manifest_semantic_sha256": "C" * 64,
        }
    raise FixtureInfrastructureError("NO_ACTIVE_INSTANCE", name)


def ads_root() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX)
    root = Path(temporary.name)
    write_fixture(root / ".boundary_fixture_root", b"RANDLE-BOUNDARY-FIXTURE\n")
    write_fixture(root / "file.txt", b"ordinary")
    return temporary, root


def op_ads(case: Mapping[str, Any]) -> Mapping[str, Any]:
    vector = case["vector"]
    temporary, root = ads_root()
    path = root / "file.txt"
    try:
        if vector == "colon_content":
            write_fixture(path, "ordinary:colon:text")
            enumerate_inventory(root)
            return success("inventory_generator_DRAFT.enumerate_inventory", "REAL_NTFS_SCAN")
        if vector in {"named", "zero", "multiple", "disappear", "content_change"}:
            with open(str(path) + ":one", "wb") as handle:
                handle.write(b"" if vector == "zero" else b"one")
        if vector == "multiple":
            with open(str(path) + ":two", "wb") as handle:
                handle.write(b"two")
        if vector == "appear":
            hook = lambda _: write_fixture(Path(str(path) + ":late"), b"late")
            stable_read(path, hook)
        elif vector == "disappear":
            def remove(_: Path) -> None:
                os.remove(str(path) + ":one")
            stable_read(path, remove)
        elif vector == "content_change":
            def alter(_: Path) -> None:
                write_fixture(Path(str(path) + ":one"), b"two")
            stable_read(path, alter)
        elif vector == "access_failure":
            sid_result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=False)
            fields = [item.strip().strip('"') for item in sid_result.stdout.strip().split(",")]
            if sid_result.returncode or len(fields) < 2 or not fields[-1].startswith("S-1-"):
                raise InventoryError("ADS_ACCESS_FAILURE_UNSUPPORTED", "SID")
            sid = fields[-1]
            deny = subprocess.run(["icacls", str(path), "/deny", f"*{sid}:(R,REA,RA)"], capture_output=True, text=True, check=False)
            if deny.returncode:
                raise InventoryError("ADS_ACCESS_FAILURE_UNSUPPORTED", deny.stderr)
            try:
                alternate_data_streams(path)
            finally:
                subprocess.run(["icacls", str(path), "/remove:d", f"*{sid}"], capture_output=True, text=True, check=False)
        else:
            enumerate_inventory(root)
        return success("inventory_generator_DRAFT.enumerate_inventory")
    finally:
        temporary.cleanup()


def op_stability(case: Mapping[str, Any]) -> Mapping[str, Any]:
    temporary, root = ads_root()
    path = root / "file.txt"
    try:
        before = os.stat(path)
        def swap(_: Path) -> None:
            if case["vector"] == "content_between_reads":
                write_fixture(path, b"content changed between governed reads")
                return
            write_fixture(path, b"swapped!")
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            os.chmod(path, stat.S_IMODE(before.st_mode))
        stable_read(path, swap)
        return success("inventory_generator_DRAFT.stable_read")
    finally:
        temporary.cleanup()


def op_git_identity(case: Mapping[str, Any]) -> Mapping[str, Any]:
    temporary, root = make_repository({"text.txt": b"line1\r\nline2\r\n"}, attributes="*.txt text eol=lf\n")
    try:
        first = enumerate_inventory(root)
        record = next(item for item in first["artifacts"] if item["canonical_path"] == "text.txt")
        vector = case["vector"]
        if vector == "positive_clean":
            if record["raw_sha256"] == record["working_tree_git_cleaned_sha256"]:
                raise FixtureInfrastructureError("RAW_CLEAN_IDENTITY_COLLAPSED")
            return success("inventory_generator_DRAFT.enumerate_inventory", "RAW_IDENTITY", "GIT_CLEAN_FILTER_IDENTITY")
        if vector == "mode":
            git(root, "update-index", "--chmod=+x", "--", "text.txt")
        elif vector == "attributes":
            write_fixture(root / ".gitattributes", "*.txt -text\n")
        elif vector == "clean_filter_config":
            current = git(root, "config", "--get", "core.autocrlf", check=False).stdout.decode().strip().casefold()
            git(root, "config", "core.autocrlf", "false" if current == "true" else "true")
        elif vector == "path":
            os.replace(root / "text.txt", root / "renamed.txt")
        elif vector == "index":
            write_fixture(root / "text.txt", b"index-mutated\n"); git(root, "add", "--", "text.txt")
        elif vector == "parent":
            write_fixture(root / "text.txt", b"parent-mutated\n"); git(root, "add", "--", "text.txt"); git(root, "-c", "user.name=Randle Fixture", "-c", "user.email=fixture@invalid", "commit", "-q", "-m", "parent mutation")
        elif vector == "bom":
            write_fixture(root / "text.txt", b"\xef\xbb\xbfline1\nline2\n")
        elif vector == "encoding":
            write_fixture(root / "text.txt", "line1\nline2\n".encode("utf-16"))
        else:
            write_fixture(root / "text.txt", b"line1\nline2\n")
        second = enumerate_inventory(root)
        from boundary_verifier_DRAFT import verify_inventory
        verify_inventory(first["artifacts"], second["artifacts"])
        return success("boundary_verifier_DRAFT.verify_inventory")
    finally:
        temporary.cleanup()


def ledger_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    prefix = load_json("attempt_prefix_authority_DRAFT.json")
    preserved_record = {
        "attempt_id": "attempt-1",
        "sequence_number": 1,
        "predecessor_attempt_id": None,
        "prior_entry_hash": prefix["genesis_entry_hash_sha256"],
        "prior_ledger_root": prefix["preserved_ledger_root_sha256"],
        "current_entry_hash": "",
        "current_ledger_root": "",
        "start_time": "2026-07-21T00:00:00Z",
        "end_time": "2026-07-21T00:01:00Z",
        "worktree": "fixture",
        "branch": "fixture",
        "evidence_directory": "evidence",
        "pass_a_status": "FAILED",
        "pass_b_status": "NOT_STARTED",
        "staging_state": "ABORTED",
        "commits": [],
        "manifest": {"canonical_path":"manifest.json","byte_size":1,"sha256":"A"*64},
        "terminal_disposition": "UNSTABLE",
        "relationship_to_prior_attempts": [],
        "runtime_access": False,
        "production_modification": False,
        "deployment_attempted": False,
        "service_restart_attempted": False,
    }
    preserved_record["current_entry_hash"] = attempt_entry_hash_v4(preserved_record)
    preserved_record["current_ledger_root"] = chained_ledger_root_v4(preserved_record["prior_ledger_root"], preserved_record["current_entry_hash"])
    prefix["preserved_attempt_ids"] = ["attempt-1"]
    prefix["preserved_entry_count"] = 1
    prefix["preserved_ledger_root_sha256"] = preserved_record["current_ledger_root"]
    binding = {"git_blob": "a" * 40, "raw_sha256": sha256_bytes(stored_json_bytes(prefix))}
    current_record = copy.deepcopy(preserved_record)
    current_record.update({
        "attempt_id": "attempt-2",
        "sequence_number": 2,
        "predecessor_attempt_id": "attempt-1",
        "prior_entry_hash": preserved_record["current_entry_hash"],
        "prior_ledger_root": preserved_record["current_ledger_root"],
        "current_entry_hash": "",
        "current_ledger_root": "",
        "start_time": "2026-07-21T00:02:00Z",
        "end_time": "2026-07-21T00:03:00Z",
        "relationship_to_prior_attempts": ["attempt-1"],
    })
    current_record["current_entry_hash"] = attempt_entry_hash_v4(current_record)
    current_record["current_ledger_root"] = chained_ledger_root_v4(current_record["prior_ledger_root"], current_record["current_entry_hash"])
    ledger = {
        "schema_version": "4.0.0-DRAFT",
        "prefix_authority_blob": binding["git_blob"],
        "prefix_authority_raw_sha256": binding["raw_sha256"],
        "preserved_prefix_count": 1,
        "full_current_count": 2,
        "attempts": [preserved_record, current_record],
        "current_ledger_root": current_record["current_ledger_root"],
    }
    return ledger, prefix, binding


def rebuild_ledger(ledger: dict[str, Any], prefix: Mapping[str, Any]) -> None:
    previous_id = None
    previous_hash = prefix["genesis_entry_hash_sha256"]
    previous_root = prefix["genesis_entry_hash_sha256"]
    for sequence, record in enumerate(ledger["attempts"], 1):
        record["sequence_number"] = sequence
        record["predecessor_attempt_id"] = previous_id
        record["prior_entry_hash"] = previous_hash
        record["prior_ledger_root"] = previous_root
        record["current_entry_hash"] = attempt_entry_hash_v4(record)
        record["current_ledger_root"] = chained_ledger_root_v4(previous_root, record["current_entry_hash"])
        previous_id = record["attempt_id"]; previous_hash = record["current_entry_hash"]; previous_root = record["current_ledger_root"]
    ledger["full_current_count"] = len(ledger["attempts"])
    ledger["current_ledger_root"] = previous_root


def op_ledger(case: Mapping[str, Any]) -> Mapping[str, Any]:
    ledger, prefix, binding = ledger_fixture()
    vector = case["vector"]
    if vector == "positive":
        validate_attempt_capture_authority_v4(ledger, prefix, binding)
        return success("boundary_verifier_DRAFT.validate_attempt_capture_authority_v4", "IMMUTABLE_PREFIX", "CHAINED_ROOT")
    if vector == "unrelated_root":
        ledger["attempts"][0]["prior_ledger_root"] = "F" * 64
    elif vector == "removed_attempt":
        ledger["attempts"] = []; rebuild_ledger(ledger, prefix)
    elif vector == "duplicate":
        ledger["attempts"].append(copy.deepcopy(ledger["attempts"][0])); rebuild_ledger(ledger, prefix)
    elif vector == "predecessor":
        ledger["attempts"][0]["predecessor_attempt_id"] = "missing"
    elif vector == "prefix_count":
        ledger["preserved_prefix_count"] = 0
    elif vector == "entry_hash":
        ledger["attempts"][0]["current_entry_hash"] = "E" * 64
    elif vector == "root":
        ledger["current_ledger_root"] = "D" * 64
    elif vector == "chronology":
        ledger["attempts"][1]["end_time"] = "2026-07-20T00:00:00Z"; rebuild_ledger(ledger, prefix)
    elif vector == "relationship":
        ledger["attempts"][1]["relationship_to_prior_attempts"] = ["missing"]; rebuild_ledger(ledger, prefix)
    elif vector == "cycle":
        ledger["attempts"][0]["predecessor_attempt_id"] = "attempt-2"
    elif vector == "collapse":
        ledger["attempts"][1]["terminal_disposition"] = "NO_ARTIFACT"; rebuild_ledger(ledger, prefix)
    elif vector == "runtime_incident":
        ledger["attempts"][1]["runtime_access"] = True; rebuild_ledger(ledger, prefix)
    elif vector == "production_incident":
        ledger["attempts"][1]["production_modification"] = True; rebuild_ledger(ledger, prefix)
    elif vector == "deployment_incident":
        ledger["attempts"][1]["deployment_attempted"] = True; rebuild_ledger(ledger, prefix)
    elif vector == "restart_incident":
        ledger["attempts"][1]["service_restart_attempted"] = True; rebuild_ledger(ledger, prefix)
    validate_attempt_capture_authority_v4(ledger, prefix, binding)
    return success("boundary_verifier_DRAFT.validate_attempt_capture_authority_v4")


def evidence_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, str], dict[str, Any], dict[str, bytes]]:
    policy = load_json("required_evidence_policy_DRAFT.json")
    binding = {"git_blob": "b" * 40, "raw_sha256": sha256_bytes(stored_json_bytes(policy))}
    ledger, _, _ = ledger_fixture()
    role_class = {
        "attempt-ledger":"attempt-provenance",
        "boundary-inventory":"inventory",
        "command-log":"command-result",
        "complete-test-log":"test-evidence",
        "durable-manifest":"durable-manifest",
        "failure-classification":"failure-classification",
        "freeze-receipt":"freeze-receipt",
        "status-artifact":"status",
    }
    payloads: dict[str, bytes] = {}
    entries = []
    for index, (role, artifact_class) in enumerate(role_class.items(), 1):
        path = f"evidence/{index:02d}-{role}.json"
        payloads[path] = f"{role}\n".encode()
        entries.append({
            "canonical_path":path,"role":role,"artifact_class":artifact_class,"authority_status":"DRAFT_BOUND",
            "byte_size":len(payloads[path]),"sha256":sha256_bytes(payloads[path]),"git_blob":None,
            "immutability_status":"CONTENT_ADDRESSED_EXTERNAL","required_for_recovery":True,
            "source_attempt":"attempt-1","capture_pass":"HISTORICAL" if role=="complete-test-log" else "PRE_PASS_A",
            "semantic_purpose":policy["required_roles"][role]["semantic_purpose"],
        })
    paths = sorted(payloads)
    registry = {
        "entries":entries,
        "policy_blob":binding["git_blob"],
        "policy_raw_sha256":binding["raw_sha256"],
        "expected_entry_count":len(entries),
        "expected_path_set_sha256":semantic_identity(paths),
        "expected_role_set":sorted(policy["required_roles"]),
        "expected_artifact_class_set":sorted(policy["required_classes"]),
        "total_bytes":sum(len(item) for item in payloads.values()),
        "semantic_root_sha256":evidence_registry_root(entries),
    }
    registry["registry_identity_sha256"] = semantic_identity(registry)
    return registry, policy, binding, ledger, payloads


def rebuild_evidence(registry: dict[str, Any]) -> None:
    registry["expected_entry_count"] = len(registry["entries"])
    registry["expected_path_set_sha256"] = semantic_identity(sorted(item["canonical_path"] for item in registry["entries"]))
    registry["total_bytes"] = sum(item["byte_size"] for item in registry["entries"])
    registry["semantic_root_sha256"] = evidence_registry_root(registry["entries"])
    registry["registry_identity_sha256"] = semantic_identity({key:value for key,value in registry.items() if key!="registry_identity_sha256"})


def op_evidence(case: Mapping[str, Any]) -> Mapping[str, Any]:
    registry, policy, binding, ledger, payloads = evidence_fixture()
    vector = case["vector"]
    if vector == "positive":
        validate_evidence_bindings_v4(registry, policy, binding, attempt_ledger=ledger, artifact_bytes=payloads)
        return success("boundary_verifier_DRAFT.validate_evidence_bindings_v4", "PREEXISTING_POLICY", "SOURCE_ATTEMPT")
    if vector == "recovery_rebuild":
        registry["entries"][0]["required_for_recovery"] = False
    elif vector == "remove_class":
        victim = registry["entries"].pop()
        payloads.pop(victim["canonical_path"])
    elif vector == "remove_dependency":
        victim = registry["entries"].pop(0)
        payloads.pop(victim["canonical_path"])
    elif vector == "source_attempt":
        registry["entries"][0]["source_attempt"] = "missing"
    elif vector == "role":
        registry["entries"][0]["role"] = "forged-role"
    elif vector == "authority":
        registry["entries"][0]["authority_status"] = ""
    elif vector == "immutability":
        registry["entries"][0]["immutability_status"] = "MUTABLE_SOURCE_SNAPSHOT"
    elif vector == "purpose":
        registry["entries"][0]["semantic_purpose"] = "forged"
    elif vector == "policy_blob":
        registry["policy_blob"] = "c" * 40
    rebuild_evidence(registry)
    validate_evidence_bindings_v4(registry, policy, binding, attempt_ledger=ledger, artifact_bytes=payloads)
    return success("boundary_verifier_DRAFT.validate_evidence_bindings_v4")


def op_historical(case: Mapping[str, Any]) -> Mapping[str, Any]:
    record = copy.deepcopy(load_json("historical_classification_DRAFT.json"))
    data = read_bytes(EXTERNAL_LOG)
    vector = case["vector"]
    if vector == "positive":
        validate_test_classification(record, data)
        return success("boundary_verifier_DRAFT.validate_test_classification", "ACTUAL_LOG_BYTES", "753_OUTCOMES", identities={"log": sha256_bytes(data)})
    if vector == "log_byte":
        data = data[:-1] + bytes([data[-1] ^ 1])
    elif vector == "log_hash":
        record["full_log_sha256"] = "A" * 64
    elif vector == "source_location":
        record["outcomes"][0]["source_log_location"]["byte_start"] += 1
    elif vector == "wrong_outcome_location":
        record["outcomes"][0]["source_log_location"] = copy.deepcopy(record["outcomes"][-1]["source_log_location"])
    elif vector == "remove_subfailed":
        record["outcomes"].pop()
    elif vector == "duplicate":
        record["outcomes"].append(copy.deepcopy(record["outcomes"][0]))
    elif vector == "parent":
        next(item for item in record["outcomes"] if item["outcome"]=="SUBFAILED")["parent_identity"] = "wrong"
    elif vector == "classification":
        next(item for item in record["outcomes"] if item["outcome"]=="FAILED")["classification_category"] = "wrong"
    elif vector == "parser_version":
        record["parser_version"] = "wrong"
    elif vector == "classification_rule":
        next(item for item in record["outcomes"] if item["outcome"]=="FAILED")["classification_rule"] = "wrong"
    validate_test_classification(record, data)
    return success("boundary_verifier_DRAFT.validate_test_classification")


def observer_repository() -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
    roles = {
        "include_registry":"roles/include","exclusion_registry":"roles/exclude","selection_rule_registry":"roles/rules",
        "boundary_configuration":"roles/config","selection_engine":"roles/select","inventory_generator":"roles/inventory",
        "boundary_verifier":"roles/verifier","operational_capture_script":"roles/script","include_set":"roles/included",
        "exclude_set":"roles/excluded","separate_set":"roles/separate","external_evidence":"roles/external",
        "required_evidence":"roles/evidence","attempt_ledger":"roles/ledger","freeze_receipt":"roles/freeze","schema_set":"roles/schema",
    }
    files = {"specification.md":"draft\n", **{path:f"{role}\n" for role,path in roles.items()}}
    temporary, root = make_repository(files, attributes="* text eol=lf\n")
    config = {
        "dependency_versions": {"jsonschema":"4.25.1"},
        "observer_genesis_root": "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",
        "parser_versions": {"observer":"4.0.0-DRAFT"},
        "roles": roles,
        "specification_path": "specification.md",
    }
    write_fixture(root / ".randle_observer_config.json", stored_json_bytes(config))
    git(root, "add", "--", ".randle_observer_config.json")
    git(root, "-c", "user.name=Randle Fixture", "-c", "user.email=fixture@invalid", "commit", "-q", "-m", "observer config")
    event_path = Path(temporary.name).parent / f"{FIXTURE_PREFIX}events_{Path(temporary.name).name}.jsonl"
    write_fixture(event_path, b"")
    return temporary, root, event_path


def append_event(path: Path, event_type: str) -> None:
    raw = read_bytes(path)
    previous = "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855"
    sequence = 1
    if raw:
        last = strict_json_loads(raw.splitlines()[-1])
        previous = last["current_root"]; sequence = last["sequence"] + 1
    event = {"sequence":sequence,"event_type":event_type,"timestamp":f"2026-07-21T00:00:{sequence:02d}Z","previous_root":previous}
    event["current_root"] = semantic_identity(event)
    with open(path, "ab") as handle:
        handle.write(stored_json_bytes(event))


def op_multipass(case: Mapping[str, Any]) -> Mapping[str, Any]:
    temporary, root, events = observer_repository()
    try:
        a = observe_controlled_repository_state(root, events)
        vector = case["vector"]
        if vector == "positive":
            b = observe_controlled_repository_state(root, events); c = observe_controlled_repository_state(root, events)
            validate_multi_pass(a,b,c)
            return success("boundary_verifier_DRAFT.validate_multi_pass", "ACTUAL_GIT_OBSERVER", "APPEND_ONLY_EVENT_SOURCE")
        if vector == "equal_invalid_head":
            for state in (a,):
                state["repository_head"] = "z"*40
            b=copy.deepcopy(a);c=copy.deepcopy(a)
        else:
            if vector == "branch":
                git(root, "checkout", "-q", "-b", "moved")
            elif vector == "head":
                write_fixture(root/"head.txt","head\n");git(root,"add","--","head.txt");git(root,"-c","user.name=Randle Fixture","-c","user.email=fixture@invalid","commit","-q","-m","move head")
            elif vector == "index":
                write_fixture(root/"roles/include","index\n");git(root,"add","--","roles/include")
            elif vector == "status":
                write_fixture(root/"roles/include","status\n")
            elif vector == "file":
                write_fixture(root/"roles/verifier","file\n")
            elif vector == "registry":
                write_fixture(root/"roles/rules","rules replacement\n")
            elif vector == "config":
                write_fixture(root/"roles/config","config replacement\n")
            elif vector == "count":
                write_fixture(root/"extra.txt","extra\n")
            elif vector == "bytes":
                write_fixture(root/"roles/external","larger external evidence\n")
            elif vector == "evidence":
                write_fixture(root/"roles/evidence","changed evidence\n")
            elif vector == "writer":
                append_event(events,"WRITER")
            elif vector == "runtime":
                append_event(events,"RUNTIME_OPERATION")
            elif vector == "deployment":
                append_event(events,"DEPLOYMENT_ATTEMPT")
            elif vector == "restart":
                append_event(events,"SERVICE_RESTART_ATTEMPT")
            b = observe_controlled_repository_state(root, events); c = observe_controlled_repository_state(root, events)
        validate_multi_pass(a,b,c)
        return success("boundary_verifier_DRAFT.validate_multi_pass")
    finally:
        try:
            events.unlink(missing_ok=True)
        finally:
            temporary.cleanup()


def op_authorization(case: Mapping[str, Any]) -> Mapping[str, Any]:
    state = copy.deepcopy(load_json("authorization_state_DRAFT.json"))
    vector = case["vector"]
    if vector == "package_scan":
        role_map = load_json("package_role_authority_DRAFT.json")
        repository_root = PACKAGE.parents[2]
        paths = [entry["path"] for entry in role_map["roles"]]
        paths.extend(
            [
                "Architecture/Audits/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT/fixture_results_DRAFT.json",
                "Architecture/Audits/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT/REMEDIATION_REPORT_DRAFT.md",
            ]
        )
        contents = {
            path: read_bytes(repository_root.joinpath(*PurePosixPath(path).parts))
            for path in paths
        }
        validate_governance_package(paths, contents, authorization_state=state)
        return success(
            "boundary_verifier_DRAFT.validate_governance_package",
            "STRUCTURED_WITHHOLDING_STATE",
            "FAIL_CLOSED_TEXT_SCAN",
        )
    allowed = {
        "allowed_deploy_not": ["Deployment", " is not ", "authorized."],
        "allowed_deploy_withheld": ["Deployment", " remains ", "withheld."],
        "allowed_live_not": ["Live-money trading", " is not ", "authorized."],
        "allowed_capture_pending": ["The baseline capture", " is pending independent review."],
    }
    positive = {
        "deploy_authorized": ["Deployment", " is ", "authorized."],
        "deploy_permitted": ["Deployment", " is ", "permitted."],
        "may_deploy": ["May now ", "deploy."],
        "live_authorized": ["Live-money trading", " is ", "authorized."],
        "paper_approved": ["Paper trading ", "approved."],
        "capture_begin": ["The baseline capture", " may ", "begin."],
        "bucket_complete": ["Bucket 0", " is ", "complete."],
        "phase_proceed": ["Phase 3C2", " may ", "proceed."],
        "nq_proceed": ["Proceed with ", "NQ cutover."],
        "implementation_approved": ["Production implementation", " is ", "approved."],
        "conditional_capture": ["Capture can ", "start ", "once this passes."],
        "contradictory": ["Deployment is not authorized. ", "Deployment", " is ", "authorized."],
        "mixed_case": ["dEpLoYmEnT", " Is ", "AuThOrIzEd."],
        "punctuation": ["Deployment: ", "is ", "authorized!"],
        "heading": ["# Deployment", " is ", "authorized."],
        "nested_list": ["  - > Deployment", " is ", "authorized."],
        "blockquote": ["> Deployment", " is ", "authorized."],
    }
    if vector == "structured_positive":
        state["protected_domains"]["deployment"] = "AUTHORIZED"
        validate_authorization_state(state)
    phrase = "".join(allowed.get(vector, positive.get(vector, [])))
    if not phrase and vector not in {"json_positive", "approval_status", "markdown_table"}:
        raise FixtureInfrastructureError("UNKNOWN_AUTH_VECTOR", vector)
    if vector == "json_positive":
        payload = canonical_json_bytes({"deployment_authorized": True})
        path = "Architecture/probe.json"
    elif vector == "approval_status":
        payload = canonical_json_bytes({"approval_status": "APPROVED"})
        path = "Architecture/probe.json"
    elif vector == "markdown_table":
        payload = ("| domain | state |\n|---|---|\n| " + "Deployment" + " | is " + "authorized |\n").encode()
        path = "Architecture/probe.md"
    else:
        payload = phrase.encode()
        path = "Architecture/probe.md"
    validate_governance_package([path], {path:payload}, authorization_state=state)
    return success("boundary_verifier_DRAFT.validate_governance_package", "STRUCTURED_WITHHOLDING_STATE", "FAIL_CLOSED_TEXT_SCAN")


def op_operational(case: Mapping[str, Any]) -> Mapping[str, Any]:
    temporary, root = make_repository({"spec.txt":"spec\n"})
    try:
        spec_commit = git(root,"rev-parse","HEAD").stdout.decode().strip()
        accepted = {"commit":spec_commit,"interface_version":"RANDLE-BASELINE-BOUNDARY-4"}
        accepted["accepted_specification_identity"] = semantic_identity(accepted)
        write_fixture(root/"capture.py","print('fixture only')\n")
        git(root,"add","--","capture.py")
        git(root,"-c","user.name=Randle Fixture","-c","user.email=fixture@invalid","commit","-q","-m","later reviewed package")
        commit = git(root,"rev-parse","HEAD").stdout.decode().strip()
        parent = git(root,"rev-parse","HEAD^").stdout.decode().strip()
        tree = git(root,"rev-parse","HEAD^{tree}").stdout.decode().strip()
        blob = git(root,"rev-parse","HEAD:capture.py").stdout.decode().strip()
        raw = git(root,"show","HEAD:capture.py").stdout
        claim = {
            "identity_kind":"GIT_COMMIT","accepted_specification_commit":spec_commit,
            "accepted_specification_interface_version":"RANDLE-BASELINE-BOUNDARY-4",
            "independent_review_decision":"ACCEPT","package_review_receipt_sha256":"A"*64,
            "package_manifest_sha256":"B"*64,"operational_script_raw_sha256":sha256_bytes(raw),
            "supporting_module_identities":[],"package_commit":commit,"package_parent":parent,"package_tree":tree,
            "operational_script_path":"capture.py","operational_script_git_blob":blob,"freeze_package_identity":"",
        }
        derived_core={"identity_kind":"GIT_COMMIT","commit":commit,"parent":parent,"tree":tree,"script_blob":blob,"script_raw_sha256":sha256_bytes(raw)}
        package_identity=semantic_identity({**derived_core,"manifest":claim["package_manifest_sha256"],"review":claim["package_review_receipt_sha256"],"supporting":[]})
        claim["freeze_package_identity"]=package_identity
        freeze={"accepted_specification_identity":accepted["accepted_specification_identity"],"operational_package_identity":package_identity}
        vector=case["vector"]
        if vector=="wrong_spec": claim["accepted_specification_commit"]="0"*40
        elif vector=="modified_spec": accepted["accepted_specification_identity"]="F"*64
        elif vector=="unreviewed": claim["independent_review_decision"]="PENDING"
        elif vector=="wrong_blob": claim["operational_script_git_blob"]="1"*40
        elif vector=="wrong_tree": claim["package_tree"]="2"*40
        elif vector=="interface": claim["accepted_specification_interface_version"]="old"
        elif vector=="self_reference": claim["package_commit"]=spec_commit
        elif vector=="external_unbound":
            claim={"identity_kind":"EXTERNAL_CONTENT_ADDRESS","accepted_specification_commit":spec_commit,"accepted_specification_interface_version":"RANDLE-BASELINE-BOUNDARY-4","independent_review_decision":"ACCEPT","package_review_receipt_sha256":"A"*64,"package_manifest_sha256":"B"*64,"operational_script_raw_sha256":"C"*64,"supporting_module_identities":[],"freeze_package_identity":"D"*64,"package_content_address":"SHA256:"+"E"*64,"operational_script_content_address":"SHA256:"+"F"*64}
        result=validate_operational_package_authority(root,accepted,claim,freeze)
        return success("boundary_verifier_DRAFT.validate_operational_package_authority","DISTINCT_ACCEPTED_SPEC","LATER_PACKAGE",identities=result)
    finally:
        temporary.cleanup()


def package_snapshot_repository(*, governed_fixture: bool = False) -> tuple[tempfile.TemporaryDirectory[str], Path, str]:
    temporary = tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX)
    repository = Path(temporary.name) / "source"
    repository.mkdir()
    write_fixture(repository / ".boundary_fixture_root", b"RANDLE-BOUNDARY-FIXTURE\n")
    git(repository, "init", "-q")
    write_fixture(repository / ".git" / "info" / "exclude", b".boundary_fixture_root\n")
    git(repository, "-c", "user.name=Randle Fixture", "-c", "user.email=fixture@invalid", "commit", "--allow-empty", "-q", "-m", "genesis")
    role_map = load_json("package_role_authority_DRAFT.json")
    worktree_root = PACKAGE.parents[2]
    for entry in role_map["roles"]:
        source = worktree_root.joinpath(*entry["path"].split("/"))
        write_fixture(repository.joinpath(*entry["path"].split("/")), read_bytes(source))
    if governed_fixture:
        for entry in load_json("include_registry_DRAFT.json")["entries"]:
            if entry["path_kind"] != "repository-relative":
                continue
            path = entry["path"]
            destination = repository.joinpath(*path.split("/"))
            if destination.is_file():
                continue
            suffix = destination.suffix.casefold()
            if path in QUESTIONED_TESTS:
                payload = "def test_mandatory_boundary():\n    assert True\n"
            elif suffix == ".py":
                payload = "VALUE = 1\n"
            elif suffix == ".json":
                payload = "{}\n"
            elif suffix in {".yaml", ".yml"}:
                payload = "{}\n"
            elif suffix == ".toml":
                payload = "# governed fixture\n"
            elif suffix in {".ini", ".cfg"}:
                payload = "[main]\n"
            else:
                payload = "governed fixture\n"
            write_fixture(destination, payload)
    git(repository, "add", "--all")
    git(repository, "-c", "user.name=Randle Fixture", "-c", "user.email=fixture@invalid", "commit", "-q", "-m", "exact R2 package snapshot")
    return temporary, repository, git(repository, "rev-parse", "HEAD").stdout.decode().strip()


def clone_snapshot(source: Path, destination: Path, autocrlf: bool) -> None:
    destination.mkdir(parents=True)
    shutil.copytree(source / ".git", destination / ".git")
    git(destination, "-c", f"core.autocrlf={'true' if autocrlf else 'false'}", "checkout-index", "-a", "-f")


def op_checkout(case: Mapping[str, Any]) -> Mapping[str, Any]:
    vector = case["vector"]
    if vector == "missing_longpath":
        validate_git_command_argv(["git", "status"])
    if vector == "long_path":
        temporary = tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX)
        try:
            source = Path(temporary.name) / "source"
            checkout = Path(temporary.name) / ("checkout-" + "l" * 90)
            source.mkdir()
            git(source, "init", "-q")
            long_relative = "long/" + "/".join(["segment-" + str(index) + "-" + "x" * 48 for index in range(4)]) + "/artifact.json"
            blob = git(source, "hash-object", "-w", "--stdin", input_bytes=b'{"long_path":true}\n').stdout.decode().strip()
            git(source, "update-index", "--add", "--cacheinfo", f"100644,{blob},{long_relative}")
            git(source, "-c", "user.name=Randle Fixture", "-c", "user.email=fixture@invalid", "commit", "-q", "-m", "long path")
            clone_snapshot(source, checkout, False)
            blob = git(checkout, "show", f"HEAD:{long_relative}").stdout
            disk = governed_read_binary(checkout.joinpath(*long_relative.split("/"))).data
            if blob != disk:
                raise FixtureInfrastructureError("LONG_PATH_CHECKOUT_BYTES")
            return success("fixture_runner_DRAFT.op_checkout", "LONG_PATH_GIT_OBJECT", "LONG_PATH_WORKTREE")
        finally:
            shutil.rmtree(extended_length_path(Path(temporary.name)), ignore_errors=True)
            temporary.cleanup()
    temporary, source, _ = package_snapshot_repository()
    try:
        checkout = Path(temporary.name) / "checkout"
        clone_snapshot(source, checkout, vector in {"autocrlf_true", "crlf", "attributes", "blob_changed", "worktree_changed"})
        commit = git(checkout, "rev-parse", "HEAD").stdout.decode().strip()
        role_map = load_json("package_role_authority_DRAFT.json")
        authorization_path = next(item["path"] for item in role_map["roles"] if item["role"] == "authorization_state")
        target = checkout.joinpath(*authorization_path.split("/"))
        if vector == "crlf":
            write_fixture(target, read_bytes(target).rstrip(b"\n") + b"\r\n")
        elif vector == "attributes":
            attribute_path = checkout.joinpath(*next(item["path"] for item in role_map["roles"] if item["role"] == "package_line_ending_authority").split("/"))
            write_fixture(attribute_path, b"*.json text eol=crlf\n*.py text eol=lf\n*.md text eol=lf\n.gitattributes text eol=lf\n")
        elif vector == "worktree_changed":
            write_fixture(target, read_bytes(target).replace(b"PENDING_INDEPENDENT_REVIEW", b"PENDING_INDEPENDENT_REVIE0", 1))
        elif vector == "blob_changed":
            original = read_bytes(target)
            write_fixture(target, original.replace(b"PENDING_INDEPENDENT_REVIEW", b"PENDING_INDEPENDENT_REVIE0", 1))
            git(checkout, "add", "--", authorization_path)
            git(checkout, "-c", "user.name=Randle Fixture", "-c", "user.email=fixture@invalid", "commit", "-q", "-m", "changed authoritative blob")
            commit = git(checkout, "rev-parse", "HEAD").stdout.decode().strip()
            write_fixture(target, original)
        authority = derive_committed_package_authority(checkout, commit)
        validate_package_checkout(authority)
        return success(
            "boundary_verifier_DRAFT.validate_package_checkout",
            "COMMITTED_GIT_BLOB_BYTES", "WORKTREE_CLEAN_FILTER_IDENTITY",
            identities={"tree": authority["tree"], "authority": authority["authority_sha256"]},
        )
    finally:
        temporary.cleanup()


def commit_fixture_change(repository: Path, path: str, payload: bytes, subject: str) -> str:
    write_fixture(repository.joinpath(*path.split("/")), payload)
    git(repository, "add", "--", path)
    git(repository, "-c", "user.name=Randle Fixture", "-c", "user.email=fixture@invalid", "commit", "-q", "-m", subject)
    return git(repository, "rev-parse", "HEAD").stdout.decode().strip()


def op_mandatory(case: Mapping[str, Any]) -> Mapping[str, Any]:
    temporary, repository, accepted_commit = package_snapshot_repository(governed_fixture=True)
    selection_temporary: tempfile.TemporaryDirectory[str] | None = None
    selection_root: Path | None = None
    try:
        accepted_authority = derive_accepted_specification_authority(repository, accepted_commit)
        vector = case["vector"]
        role_map = load_json("package_role_authority_DRAFT.json")
        role_paths = {item["role"]: item["path"] for item in role_map["roles"]}
        if vector in {"separate_authority_root", "separate_unmarked_root"}:
            selection_temporary, selection_root, _ = package_snapshot_repository(governed_fixture=True)
            if vector == "separate_unmarked_root":
                (selection_root / ".boundary_fixture_root").unlink()
        elif vector in {"governed_read_only", "governed_dirty", "governed_wrong_head"}:
            (repository / ".boundary_fixture_root").unlink()
            if vector == "governed_dirty":
                write_fixture(repository / "untracked-governed-mutation.txt", "dirty\n")
            elif vector == "governed_wrong_head":
                commit_fixture_change(repository, "governed-head-mutation.txt", b"head moved\n", vector)
        elif vector in {"forged_authority", "forged_evidence", "replace_include"}:
            document = copy.deepcopy(load_json("include_registry_DRAFT.json"))
            mandatory = next(item for item in document["entries"] if item["path"] == QUESTIONED_TESTS[0])
            if vector == "forged_authority":
                mandatory["authority_status"] = "DRAFT_FORGED"
            elif vector == "forged_evidence":
                mandatory["evidence_references"] = ["FORGED:EVIDENCE"]
            else:
                document["entries"] = [item for item in document["entries"] if item["path"] != QUESTIONED_TESTS[0]]
            accepted_commit = commit_fixture_change(repository, role_paths["include_registry"], stored_json_bytes(document), vector)
        elif vector in {"pending_exclusion", "approved_unbound_exclusion", "replace_exclusion"}:
            document = copy.deepcopy(load_json("exclusion_registry_DRAFT.json"))
            candidate = copy.deepcopy(document["entries"][0])
            candidate["entry_id"] = "EXC-R2-FORGED-MANDATORY"
            candidate["match_type"] = "exact"
            candidate["path_or_pattern"] = QUESTIONED_TESTS[0]
            candidate["authority"] = "PENDING_REVIEW" if vector == "pending_exclusion" else "APPROVED"
            candidate["accepted_review_identity"] = None
            document["entries"].append(candidate)
            if vector in {"pending_exclusion", "approved_unbound_exclusion"}:
                document["validation_mode"] = "CAPTURE"
            accepted_commit = commit_fixture_change(repository, role_paths["exclusion_registry"], stored_json_bytes(document), vector)
        elif vector == "replace_rules":
            document = copy.deepcopy(load_json("selection_rule_registry_DRAFT.json"))
            document["rules"] = [item for item in document["rules"] if item["rule_id"] != "PRODUCTION_TEST_CLOSURE"]
            accepted_commit = commit_fixture_change(repository, role_paths["selection_rule_registry"], stored_json_bytes(document), vector)
        elif vector == "changed_rule_blob":
            document = copy.deepcopy(load_json("selection_rule_registry_DRAFT.json"))
            document["rules"][0]["predicate"] += " governed mutation"
            accepted_commit = commit_fixture_change(repository, role_paths["selection_rule_registry"], stored_json_bytes(document), vector)
        elif vector == "changed_configuration":
            document = copy.deepcopy(load_json("boundary_config_DRAFT.json"))
            document.pop("long_path_policy")
            accepted_commit = commit_fixture_change(repository, role_paths["boundary_configuration"], stored_json_bytes(document), vector)
        elif vector in {"changed_selection_engine", "changed_inventory_generator", "changed_verifier"}:
            role = {"changed_selection_engine":"selection_engine", "changed_inventory_generator":"inventory_generator", "changed_verifier":"boundary_verifier"}[vector]
            original = read_bytes(repository.joinpath(*role_paths[role].split("/")))
            accepted_commit = commit_fixture_change(repository, role_paths[role], original + b"# governed mutation\n", vector)
        elif vector in {"rename", "case_change", "missing_physical", "remove_relevance"}:
            source = repository / QUESTIONED_TESTS[0]
            if vector == "rename":
                os.replace(source, repository / "renamed_mandatory_test.py")
            elif vector == "case_change":
                intermediate = repository / "case-intermediate.py"
                os.replace(source, intermediate)
                os.replace(intermediate, repository / QUESTIONED_TESTS[0].upper())
            elif vector == "missing_physical":
                source.unlink()
            else:
                write_fixture(source, "VALUE = 1\n")
        elif vector == "changed_committed_blob":
            original = read_bytes(repository.joinpath(*role_paths["boundary_verifier"].split("/")))
            commit_fixture_change(repository, role_paths["boundary_verifier"], original + b"# changed after accepted authority\n", vector)
        result = derive_selection_from_accepted_specification(
            repository,
            accepted_authority,
            capture_mode=vector in {"pending_exclusion", "approved_unbound_exclusion"},
            selection_root=selection_root,
        )
        return success(
            "boundary_verifier_DRAFT.derive_selection_from_accepted_specification",
            "COMMITTED_REGISTRY_BLOBS", "MANDATORY_TEST_CONTENT_IDENTITIES",
            identities={"disposition": result["disposition_set_sha256"]},
        )
    finally:
        if selection_temporary is not None:
            shutil.rmtree(extended_length_path(Path(selection_temporary.name)), ignore_errors=True)
            selection_temporary.cleanup()
        shutil.rmtree(extended_length_path(Path(temporary.name)), ignore_errors=True)
        temporary.cleanup()


def operational_claim_fixture(repository: Path, accepted_specification_commit: str) -> dict[str, Any]:
    write_fixture(repository / "capture.py", "raise SystemExit('draft fixture only')\n")
    git(repository, "add", "--", "capture.py")
    git(repository, "-c", "user.name=Randle Fixture", "-c", "user.email=fixture@invalid", "commit", "-q", "-m", "later independently reviewed operational package")
    commit = git(repository, "rev-parse", "HEAD").stdout.decode().strip()
    parent = git(repository, "rev-parse", "HEAD^").stdout.decode().strip()
    tree = git(repository, "rev-parse", "HEAD^{tree}").stdout.decode().strip()
    blob = git(repository, "rev-parse", "HEAD:capture.py").stdout.decode().strip()
    raw = git(repository, "show", "HEAD:capture.py").stdout
    claim = {
        "identity_kind": "GIT_COMMIT",
        "accepted_specification_commit": accepted_specification_commit,
        "accepted_specification_interface_version": "RANDLE-BASELINE-BOUNDARY-4",
        "independent_review_decision": "ACCEPT",
        "package_review_receipt_sha256": "A" * 64,
        "package_manifest_sha256": "B" * 64,
        "operational_script_raw_sha256": sha256_bytes(raw),
        "supporting_module_identities": [],
        "package_commit": commit,
        "package_parent": parent,
        "package_tree": tree,
        "operational_script_path": "capture.py",
        "operational_script_git_blob": blob,
    }
    core = {"identity_kind":"GIT_COMMIT", "commit":commit, "parent":parent, "tree":tree, "script_blob":blob, "script_raw_sha256":sha256_bytes(raw)}
    claim["freeze_package_identity"] = semantic_identity({**core, "manifest":claim["package_manifest_sha256"], "review":claim["package_review_receipt_sha256"], "supporting":[]})
    return claim


def freeze_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path, dict[str, Any], Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    temporary, repository, accepted_commit = package_snapshot_repository(governed_fixture=True)
    accepted_authority = derive_accepted_specification_authority(repository, accepted_commit)
    operational_repository = Path(temporary.name) / "operational"
    clone_snapshot(repository, operational_repository, False)
    claim = operational_claim_fixture(operational_repository, accepted_commit)
    reconstructed = reconstruct_freeze_authority_v4(
        repository, accepted_authority, operational_repository, claim,
        attempt_id="attempt-r2-freeze-1", timestamp_authority="2026-07-21T00:00:00Z",
    )
    receipt = dict(reconstructed)
    receipt["freeze_receipt_sha256"] = semantic_identity(receipt)
    return temporary, repository, accepted_authority, operational_repository, claim, reconstructed, receipt


def rebuild_freeze_receipt(receipt: dict[str, Any]) -> None:
    receipt["freeze_receipt_sha256"] = semantic_identity({key:value for key,value in receipt.items() if key!="freeze_receipt_sha256"})


def op_freeze(case: Mapping[str, Any]) -> Mapping[str, Any]:
    temporary, repository, accepted_authority, operational_repository, claim, reconstructed, receipt = freeze_fixture()
    try:
        vector = case["vector"]
        if vector == "matching_invalid_commit":
            accepted_authority["commit"] = "0" * 40
            accepted_authority["accepted_specification_identity"] = semantic_identity(
                {key: value for key, value in accepted_authority.items() if key != "accepted_specification_identity"}
            )
            receipt["specification_commit"] = accepted_authority["commit"]
        elif vector == "matching_invalid_schema":
            receipt["schema_set_identity"] = "Z" * 64
        elif vector == "forged_inventory":
            receipt["generated_inventory_sha256"] = "A" * 64
        elif vector == "forged_disposition":
            receipt["generated_disposition_sha256"] = "B" * 64
        elif vector == "forged_evidence":
            receipt["evidence_policy_identity"] = "C" * 64
        elif vector == "forged_attempt_universe":
            receipt["attempt_prefix_authority_identity"] = "D" * 64
        elif vector == "changed_environment":
            receipt["environment_identity"] = "E" * 64
        elif vector in {"changed_package_blob", "changed_registry", "changed_configuration"}:
            role = {"changed_package_blob":"boundary_verifier", "changed_registry":"include_registry", "changed_configuration":"boundary_configuration"}[vector]
            role_path = next(item["path"] for item in load_json("package_role_authority_DRAFT.json")["roles"] if item["role"] == role)
            target = repository.joinpath(*role_path.split("/"))
            write_fixture(target, read_bytes(target) + (b"# mutation\n" if not target.suffix.casefold()==".json" else b"\n"))
        elif vector == "incomplete":
            receipt.pop("schema_set_identity")
        rebuild_freeze_receipt(receipt)
        if vector in {"positive", "matching_invalid_commit", "changed_package_blob", "changed_registry", "changed_configuration"}:
            verify_freeze_claim_v4(receipt, repository, accepted_authority, operational_repository, claim)
            surface = "boundary_verifier_DRAFT.verify_freeze_claim_v4"
        else:
            validate_freeze_v4(receipt, reconstructed)
            surface = "boundary_verifier_DRAFT.validate_freeze_v4"
        return success(surface, "INDEPENDENT_RECONSTRUCTION", "COMPLETE_SCHEMA_SET")
    finally:
        shutil.rmtree(extended_length_path(Path(temporary.name)), ignore_errors=True)
        temporary.cleanup()


def op_trace(case: Mapping[str, Any]) -> Mapping[str, Any]:
    matrix = copy.deepcopy(load_json("semantic_traceability_DRAFT.json"))
    expectations = copy.deepcopy(load_json("independent_expectations_DRAFT.json"))
    vector = case["vector"]
    if vector == "remove_field_mapping":
        matrix["schema_field_mappings"].pop()
    elif vector == "nonexistent_function":
        matrix["rows"][0]["symbol"] = "function_that_does_not_exist"
    elif vector == "wrong_function":
        matrix["rows"][0]["symbol"] = "strict_json_loads"
    elif vector == "unused_function":
        matrix["function_mappings"][0]["invoked_case_ids"] = []
    elif vector == "remove_rule_mapping":
        matrix["rule_mappings"].pop()
    elif vector == "identifier_only":
        matrix["schema_field_mappings"] = []
    elif vector == "alter_expected_surface":
        target = matrix["rows"][0]["mutation_case"]
        next(item for item in expectations["cases"] if item["case_id"] == target)["expected_enforcing_surface"] = "boundary_verifier_DRAFT.strict_json_loads"
    validate_traceability_v4(matrix, PACKAGE, expectations, load_json("selection_rule_registry_DRAFT.json"))
    return success("boundary_verifier_DRAFT.validate_traceability_v4", "FIELD_LEVEL_MAPPING", "FUNCTION_INVOCATION_MAPPING")


def op_json(case: Mapping[str, Any]) -> Mapping[str, Any]:
    raw=read_bytes(PACKAGE/"authorization_state_DRAFT.json")
    vector=case["vector"]
    if vector=="positive":
        verify_stored_canonical_json(raw);return success("boundary_verifier_DRAFT.verify_stored_canonical_json","AUTHORITATIVE_BYTES")
    mutations={
        "whitespace":raw.replace(b"{",b"{ ",1),"key_order":b'{"z":0,'+raw[1:],
        "bom":b"\xef\xbb\xbf"+raw,"utf16":raw.decode().encode("utf-16"),
        "duplicate":raw.replace(b'{"authority":',b'{"authority":"x","authority":',1),
        "missing_lf":raw.rstrip(b"\n"),"extra_lf":raw+b"\n",
        "unicode_nfd":b'{"a":"e\xcc\x81"}\n',"crlf":raw.replace(b"\n",b"\r\n"),
    }
    verify_stored_canonical_json(mutations[vector]);return success("boundary_verifier_DRAFT.verify_stored_canonical_json")


def op_meta(case: Mapping[str, Any]) -> Mapping[str, Any]:
    vector=case["vector"]
    expectations={"authority":"STATIC","cases":[{"case_id":"negative","expected_status":"REJECTED","expected_disposition":"TERMINATE","expected_code":"DENIED","expected_enforcing_surface":"surface.reject","expected_evidence_obligations":["ERROR_CODE","TRACEBACK_SURFACE"],"expected_authority_result":"REJECTED"}]}
    rejected={"case_id":"negative","observed_status":"REJECTED","observed_disposition":"TERMINATE","observed_code":"DENIED","observed_enforcing_surface":"surface.reject","observed_evidence":["ERROR_CODE","TRACEBACK_SURFACE"],"observed_authority_result":"REJECTED","observed_identities":{}}
    accepted={**rejected,"observed_status":"ACCEPTED","observed_disposition":"CONTINUE","observed_code":"OK","observed_authority_result":"SATISFIED","observed_evidence":["REAL_ENFORCING_SURFACE"]}
    if vector=="no_op_helper":
        source = read_bytes(Path(__file__))
        helper_name = ("expect_" + "failure").encode("ascii")
        if helper_name in source:
            raise FixtureInfrastructureError("NEGATIVE_HELPER_PRESENT")
        receipt=compare_observations(expectations,[accepted])
        if receipt["discrepancy_count"]==0: raise FixtureInfrastructureError("FORCED_SUCCESS_NOT_DETECTED")
        return success("fixture_runner_DRAFT.compare_observations","FORCED_SUCCESS_MISMATCH")
    if vector in {"all_success","one_success"}:
        definitions = load_json("case_definitions_DRAFT.json")["cases"]
        complete_expectations = load_json("independent_expectations_DRAFT.json")["cases"]
        selected = [item for item in definitions if item["kind"] == "mutation"]
        if vector == "one_success":
            selected = selected[:1]
        selected_ids = {item["case_id"] for item in selected}
        expected_subset = {
            "authority": "STATIC_INDEPENDENT_EXPECTATIONS_PENDING_INDEPENDENT_REVIEW",
            "cases": [item for item in complete_expectations if item["case_id"] in selected_ids],
        }
        forced = [
            execute_raw(item, lambda _case: success("mutated_enforcement.force_success"))
            for item in selected
        ]
        receipt=compare_observations(expected_subset,forced)
        if receipt["discrepancy_count"]==0: raise FixtureInfrastructureError("FORCED_SUCCESS_NOT_DETECTED")
        return success(
            "fixture_runner_DRAFT.compare_observations",
            "OBSERVATION_CHANGED",
            identities={"forced_observation_semantic_sha256": semantic_identity(forced)},
        )
    if vector=="disable_comparison":
        require_comparison_receipt(None)
    if vector=="replace_observation":
        replacement={"case_id":"negative","observed_status":"REJECTED","observed_disposition":"TERMINATE","observed_code":"DENIED","observed_enforcing_surface":"surface.reject","observed_evidence":["ERROR_CODE","TRACEBACK_SURFACE"],"observed_authority_result":"REJECTED"}
        if "observed_identities" not in replacement: raise FixtureInfrastructureError("OBSERVATION_PROVENANCE_MISSING")
    if vector=="generate_expectations":
        generated={
            "schema_version":"4.0.0-DRAFT",
            "canonical_serialization":"RANDLE-CAPTURE-CJSON-1",
            "authority":"IMPLEMENTATION_GENERATED_FROM_OBSERVATIONS",
            "cases":[],
        }
        validate_schema_and_instance(
            schema_by_name("independent_expectations_schema_DRAFT.json"),
            generated,
            "implementation-generated-expectations",
        )
    if vector=="expectation_mutation":
        mutant=copy.deepcopy(expectations);mutant["cases"][0]["expected_code"]="OTHER";receipt=compare_observations(mutant,[rejected])
        if receipt["discrepancy_count"]==0: raise FixtureInfrastructureError("EXPECTATION_MUTATION_NOT_DETECTED")
        return success("fixture_runner_DRAFT.compare_observations","EXPECTATION_MISMATCH")
    if vector=="observation_mutation":
        mutant={**rejected,"observed_code":"OTHER"};receipt=compare_observations(expectations,[mutant])
        if receipt["discrepancy_count"]==0: raise FixtureInfrastructureError("OBSERVATION_MUTATION_NOT_DETECTED")
        return success("fixture_runner_DRAFT.compare_observations","OBSERVATION_MISMATCH")
    if vector=="code_mutation":
        original=read_bytes(PACKAGE/"boundary_verifier_DRAFT.py")
        mutant=original.replace(
            b"    if not condition:\n        raise BoundaryError(code, detail)\n",
            b"    return None\n",
            1,
        )
        if sha256_bytes(original)==sha256_bytes(mutant):raise FixtureInfrastructureError("CODE_MUTATION_NOT_DETECTED")
        temporary = tempfile.TemporaryDirectory(prefix=FIXTURE_PREFIX)
        try:
            mutant_path = Path(temporary.name) / "boundary_verifier_mutated.py"
            write_fixture(mutant_path, mutant)
            spec = importlib.util.spec_from_file_location("boundary_verifier_mutated", mutant_path)
            if spec is None or spec.loader is None:
                raise FixtureInfrastructureError("MUTATED_CODE_LOAD")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.validate_git_command_argv(["git", "status"])
            mutated_observation = {**accepted, "observed_enforcing_surface":"boundary_verifier_mutated.validate_git_command_argv"}
            receipt = compare_observations(expectations, [mutated_observation])
            if receipt["discrepancy_count"] == 0:
                raise FixtureInfrastructureError("CODE_MUTATION_NOT_DETECTED")
            return success("fixture_runner_DRAFT.op_meta","ENFORCING_CODE_IDENTITY_CHANGED")
        finally:
            temporary.cleanup()
    if vector=="descriptive_label":
        mutated=copy.deepcopy(expectations);mutated["cases"][0]["description"]="changed label"
        receipt=compare_observations(mutated,[rejected]);require_comparison_receipt(receipt)
        if receipt["discrepancy_count"]:raise FixtureInfrastructureError("LABEL_REDEFINED_TRUTH")
        return success("fixture_runner_DRAFT.compare_observations","LABEL_IGNORED_FOR_TRUTH")
    raise FixtureInfrastructureError("UNKNOWN_META_VECTOR",vector)


OPERATIONS: dict[str, CaseOperation] = {
    "dependency": op_dependency,
    "terminal": op_terminal,
    "schema": op_schema,
    "semantic": op_semantic,
    "ads": op_ads,
    "stability": op_stability,
    "git_identity": op_git_identity,
    "ledger": op_ledger,
    "evidence": op_evidence,
    "historical": op_historical,
    "multipass": op_multipass,
    "authorization": op_authorization,
    "operational": op_operational,
    "checkout": op_checkout,
    "mandatory": op_mandatory,
    "freeze": op_freeze,
    "trace": op_trace,
    "json": op_json,
    "meta": op_meta,
}


def enforcing_code_identity() -> str:
    names=("boundary_verifier_DRAFT.py","selection_engine_DRAFT.py","inventory_generator_DRAFT.py","historical_log_parser_DRAFT.py","schema_validation_DRAFT.py","fixture_runner_DRAFT.py")
    return semantic_identity([{"path":name,"sha256":sha256_bytes(read_bytes(PACKAGE/name))} for name in names])


def _governed_schema_paths() -> list[Path]:
    package_identity = Path(governed_canonical_absolute_path(PACKAGE))
    return sorted(
        Path(identity.canonical_path)
        for identity in governed_enumerate_regular_files(PACKAGE)
        if Path(identity.canonical_path).parent == package_identity and Path(identity.canonical_path).name.endswith("_schema_DRAFT.json")
    )


def schema_set_identity() -> str:
    return semantic_identity([{"path":path.name,"sha256":sha256_bytes(read_bytes(path))} for path in _governed_schema_paths()])


def run() -> dict[str, Any]:
    definitions=load_json("case_definitions_DRAFT.json")
    expectations=load_json("independent_expectations_DRAFT.json")
    validate_schema_and_instance(load_json("case_definition_schema_DRAFT.json"), definitions, "case-definitions")
    validate_schema_and_instance(load_json("independent_expectations_schema_DRAFT.json"), expectations, "independent-expectations")
    if expectations.get("authority") != "STATIC_INDEPENDENT_EXPECTATIONS_PENDING_INDEPENDENT_REVIEW":
        raise FixtureInfrastructureError("EXPECTATION_AUTHORITY")
    cases=definitions["cases"]
    if {item["case_id"] for item in cases}!={item["case_id"] for item in expectations["cases"]}:
        raise FixtureInfrastructureError("CASE_EXPECTATION_SET")
    if len(cases)!=len({item["case_id"] for item in cases}):
        raise FixtureInfrastructureError("DUPLICATE_CASE")
    expected_by_id={item["case_id"]:item for item in expectations["cases"]}
    for case in cases:
        identity=semantic_identity({key:value for key,value in case.items() if key!="authoritative_input_identity"})
        if case["authoritative_input_identity"]!=identity:
            raise FixtureInfrastructureError("CASE_INPUT_IDENTITY",case["case_id"])
        if expected_by_id[case["case_id"]]["authoritative_input_identity"]!=identity:
            raise FixtureInfrastructureError("EXPECTATION_INPUT_IDENTITY",case["case_id"])
    started=time.perf_counter()
    observations=[]
    before={Path(path).name for path in governed_enumerate_directory(tempfile.gettempdir(),allow_reparse_entries=True) if Path(path).name.startswith(FIXTURE_PREFIX)}
    for case in cases:
        operation=OPERATIONS.get(case["operation"])
        if operation is None:
            raise FixtureInfrastructureError("UNKNOWN_OPERATION",case["operation"])
        observations.append(execute_raw(case,operation))
    after={Path(path).name for path in governed_enumerate_directory(tempfile.gettempdir(),allow_reparse_entries=True) if Path(path).name.startswith(FIXTURE_PREFIX)}
    cleanup="PASS"
    if after!=before:
        cleanup="FAIL"
        for name in after-before:
            target=Path(tempfile.gettempdir())/name
            if target.is_dir():shutil.rmtree(target,ignore_errors=True)
            else:target.unlink(missing_ok=True)
    receipt=compare_observations(expectations,observations)
    require_comparison_receipt(receipt)
    kinds=Counter(item["kind"] for item in cases)
    result={
        "schema_version":"4.0.0-DRAFT","canonical_serialization":"RANDLE-CAPTURE-CJSON-1",
        "authority":"DRAFT_FIXTURE_EVIDENCE_PENDING_INDEPENDENT_REVIEW",
        "harness_version":HARNESS_VERSION,"validator":validator_identity(),
        "python_version":platform.python_version(),"git_version":subprocess.run(["git","--version"],capture_output=True,text=True,check=True).stdout.strip(),
        "operating_system_identity":platform.platform(),"filesystem_identity":"NTFS" if os.name=="nt" else platform.system(),
        "total_cases":len(cases),"positive_cases":kinds["positive"],"mutation_cases":kinds["mutation"],
        "real_surface_cases":sum(bool(item["real_surface"]) for item in cases),"meta_verification_cases":sum(bool(item["meta_verification"]) for item in cases),
        "passed":len(cases)-receipt["discrepancy_count"],"failed":receipt["discrepancy_count"],"discrepancies":receipt["discrepancy_count"],
        "cleanup_result":cleanup,"wall_time_seconds":f"{time.perf_counter()-started:.3f}",
        "case_definition_sha256":sha256_bytes(read_bytes(PACKAGE/"case_definitions_DRAFT.json")),
        "case_set_sha256":semantic_identity(sorted(item["case_id"] for item in cases)),
        "independent_expectation_sha256":sha256_bytes(read_bytes(PACKAGE/"independent_expectations_DRAFT.json")),
        "observation_semantic_sha256":semantic_identity(observations),
        "enforcing_code_identity":enforcing_code_identity(),"schema_set_identity":schema_set_identity(),
        "external_historical_evidence_identity":sha256_bytes(read_bytes(EXTERNAL_LOG)),
        "comparison_receipt_sha256":receipt["comparison_receipt_sha256"],
        "observations":observations,
    }
    committed=load_json("fixture_results_DRAFT.json")
    fields=("total_cases","positive_cases","mutation_cases","real_surface_cases","meta_verification_cases","passed","failed","discrepancies","cleanup_result","case_definition_sha256","case_set_sha256","independent_expectation_sha256","observation_semantic_sha256","enforcing_code_identity","schema_set_identity","external_historical_evidence_identity")
    if committed.get("schema_version") != "4.0.0-DRAFT":
        result["committed_result_match"] = "INVALID_COMMITTED_RESULT"
    elif all(committed.get(field) == result[field] for field in fields):
        result["committed_result_match"] = "MATCHED"
    else:
        result["committed_result_match"] = "MISMATCH"
    return result


def main() -> int:
    result=run()
    print(json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=False))
    return 0 if result["failed"] == 0 and result["cleanup_result"] == "PASS" and result["committed_result_match"] == "MATCHED" else 1


if __name__=="__main__":
    raise SystemExit(main())
