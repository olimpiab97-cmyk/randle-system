#!/usr/bin/env python3
"""Run the governed R7 candidate/fresh matrix from real isolated checkouts.

This host driver is not an authority component.  It records raw subprocess
bytes and independently resolves the service's immutable public receipts.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


AUTHORITY_ROOT = Path(r"C:\ProgramData\RandleAI\TerminalAuthority")
INSTALL_ROOT = Path(r"C:\Program Files\RandleAI\TerminalAuthority")
POLICY_PATH = AUTHORITY_ROOT / "Config" / "r7_terminal_authority_policy.json"
CLIENT_PATH = INSTALL_ROOT / "RandleTerminalAuthorityR7Client.exe"
VERIFIER_PATH = INSTALL_ROOT / "RandleTerminalAuthorityR7PublicVerifier.exe"
EXPECTED_POLICY_SHA256 = "76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b"
EXPECTED_CASE_BLOB = "dae357d801cabdde7ca8a314c83380984161e687"
EXPECTED_CASE_SHA256 = "58d6c043b857b6950d375724ef1f05b695028a3778ee47067284148c477b9214"
EXPECTED_EXPECTATION_BLOB = "c21ea8f5ab4b54fc0d0638e9bb20df83c8a88f1d"
EXPECTED_EXPECTATION_SHA256 = "7563a8b8af74f15ad226d61015d0946867fa1d18495143e8206600f1c3c81005"
EXPECTED_SERVICE_SHA256 = "9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526"
EXPECTED_WORKER_SHA256 = "b2971b85de73d999bfa801d047b22c2ec6fc3d6bc5cb5923ea4a9ab240ed4401"


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def progress(stage: str, configuration: str = "") -> None:
    print(json.dumps({"configuration": configuration, "matrix_progress": stage}, sort_keys=True), file=sys.stderr, flush=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def parse_json_bytes(data: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8", errors="strict"))
    except Exception as exc:
        raise RuntimeError(code) from exc
    require(isinstance(value, dict), code)
    return value


class CaptureRunner:
    def __init__(self, raw_root: Path) -> None:
        self.raw_root = raw_root

    def run(
        self,
        name: str,
        argv: list[str],
        cwd: Path | None = None,
        timeout: int = 900,
        allowed: tuple[int, ...] = (0,),
    ) -> dict[str, Any]:
        completed = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        stdout_path = self.raw_root / f"{name}.stdout.bin"
        stderr_path = self.raw_root / f"{name}.stderr.bin"
        stdout_path.write_bytes(completed.stdout)
        stderr_path.write_bytes(completed.stderr)
        result = {
            "argv": argv,
            "cwd": str(cwd) if cwd else None,
            "exit_code": completed.returncode,
            "stderr_length": len(completed.stderr),
            "stderr_sha256": sha256_bytes(completed.stderr),
            "stdout_length": len(completed.stdout),
            "stdout_sha256": sha256_bytes(completed.stdout),
        }
        require(completed.returncode in allowed, f"PROCESS_EXIT:{name}:{completed.returncode}")
        return result | {"stdout": completed.stdout, "stderr": completed.stderr}


def public_call(
    runner: CaptureRunner,
    name: str,
    argv: list[str],
    cwd: Path,
    expected_status: str,
    expected_result: str,
    timeout: int = 900,
) -> tuple[dict[str, Any], dict[str, Any]]:
    capture = runner.run(name, argv, cwd=cwd, timeout=timeout)
    response = parse_json_bytes(capture["stdout"], f"PUBLIC_JSON:{name}")
    require(response.get("status") == expected_status, f"PUBLIC_STATUS:{name}")
    require(response.get("result_code") == expected_result, f"PUBLIC_RESULT:{name}")
    capture.pop("stdout")
    capture.pop("stderr")
    return capture, response


def resolve_content(directory: Path, identity: str) -> tuple[Path, bytes, dict[str, Any]]:
    require(len(identity) == 64 and all(char in "0123456789abcdef" for char in identity), "CONTENT_IDENTITY_FORMAT")
    matches = [Path(value) for value in glob.glob(str(directory / f"{identity}.*")) if Path(value).is_file()]
    require(len(matches) == 1, f"CONTENT_RESOLUTION:{identity}:{len(matches)}")
    data = matches[0].read_bytes()
    require(sha256_bytes(data) == identity, f"CONTENT_ADDRESS:{identity}")
    return matches[0], data, parse_json_bytes(data, f"CONTENT_JSON:{identity}")


def locator_identity(locator: str, kind: str) -> str:
    prefix = f"randle-{kind}://sha256/"
    require(locator.startswith(prefix), f"LOCATOR_KIND:{kind}")
    identity = locator[len(prefix) :]
    require(len(identity) == 64 and all(char in "0123456789abcdef" for char in identity), f"LOCATOR_FORMAT:{kind}")
    return identity


def receipt_payload(locator: str) -> tuple[str, dict[str, Any]]:
    identity = locator_identity(locator, "terminal")
    _, _, envelope = resolve_content(AUTHORITY_ROOT / "Receipts", identity)
    payload = envelope.get("payload")
    require(isinstance(payload, dict), "TERMINAL_ENVELOPE_PAYLOAD")
    return identity, payload


def reconciliation_payload(locator: str) -> tuple[str, dict[str, Any]]:
    identity = locator_identity(locator, "reconciliation")
    _, _, envelope = resolve_content(AUTHORITY_ROOT / "Reconciliations", identity)
    payload = envelope.get("payload")
    require(isinstance(payload, dict), "RECONCILIATION_ENVELOPE_PAYLOAD")
    return identity, payload


def evidence_object(locator: str) -> tuple[str, dict[str, Any]]:
    identity = locator_identity(locator, "evidence")
    _, _, value = resolve_content(AUTHORITY_ROOT / "Evidence", identity)
    return identity, value


def process_receipt_set(payload: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    _, process_index = evidence_object(str(payload["process_index_locator"]))
    require(process_index.get("run_id") == payload["run_id"], "PROCESS_INDEX_RUN")
    keys = (
        "suite_process_receipt_locator",
        "observation_process_receipt_locator",
        "comparator_process_receipt_locator",
    )
    locators: set[str] = set()
    nonces: set[str] = set()
    process_identities: set[str] = set()
    for key in keys:
        locator = str(process_index[key])
        identity, envelope = evidence_object(locator)
        process_payload = envelope.get("payload")
        require(isinstance(process_payload, dict), f"PROCESS_RECEIPT_PAYLOAD:{key}")
        require(process_payload.get("run_id") == payload["run_id"], f"PROCESS_RECEIPT_RUN:{key}")
        require(process_payload.get("worker_sha256", EXPECTED_WORKER_SHA256) == EXPECTED_WORKER_SHA256, f"PROCESS_WORKER:{key}")
        if process_payload.get("artifact_type") == "R7_REAL_SUITE_PROCESS_RECEIPT":
            token_evidence = process_payload.get("subject_token_evidence")
            require(isinstance(token_evidence, dict), "SUITE_PROCESS_TOKEN_EVIDENCE")
            nonce = str(process_payload["subject_run_id"])
            process_id = str(process_payload["subject_process_id"])
            start_time = str(token_evidence["launch_time"])
        else:
            nonce = str(process_payload["process_nonce"])
            process_id = str(process_payload["process_id"])
            start_time = str(process_payload["start_time"])
        process_identity = "|".join(
            (
                process_id,
                start_time,
                nonce,
                identity,
            )
        )
        locators.add(locator)
        nonces.add(nonce)
        process_identities.add(process_identity)
    require(len(locators) == 3 and len(nonces) == 3 and len(process_identities) == 3, "PROCESS_RECEIPT_LOCAL_UNIQUENESS")
    return locators, nonces, process_identities


def fixed_terminal_checks(payload: dict[str, Any], configuration: str, phase: str) -> None:
    require(payload.get("artifact_type") == "R7_SIGNED_TERMINAL_RECEIPT", "TERMINAL_TYPE")
    require(payload.get("configuration") == configuration, "TERMINAL_CONFIGURATION")
    require(payload.get("phase") == phase, "TERMINAL_PHASE")
    require(payload.get("case_count") == 178, "TERMINAL_CASE_COUNT")
    require(payload.get("case_definition_git_blob") == EXPECTED_CASE_BLOB, "TERMINAL_CASE_BLOB")
    require(payload.get("case_definition_sha256") == EXPECTED_CASE_SHA256, "TERMINAL_CASE_SHA256")
    require(payload.get("expectation_git_blob") == EXPECTED_EXPECTATION_BLOB, "TERMINAL_EXPECTATION_BLOB")
    require(payload.get("expectation_sha256") == EXPECTED_EXPECTATION_SHA256, "TERMINAL_EXPECTATION_SHA256")
    require(payload.get("service_binary_sha256") == EXPECTED_SERVICE_SHA256, "TERMINAL_SERVICE_BINARY")
    require(payload.get("worker_sha256") == EXPECTED_WORKER_SHA256, "TERMINAL_WORKER_BINARY")
    require(payload.get("terminal_verifier_result") == "SEMANTICALLY_VERIFIED", "TERMINAL_SEMANTIC_RESULT")


def unique_count(values: list[str], expected: int, code: str) -> None:
    require(len(values) == expected, f"{code}_COUNT")
    require(len(set(values)) == expected, f"{code}_DUPLICATE")


def clean_capture(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in ("stdout", "stderr")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--checkout-commit", required=True)
    parser.add_argument("--phase-label", choices=("PRECOMMIT", "POSTCOMMIT"), required=True)
    parser.add_argument("--short-root", required=True)
    parser.add_argument("--long-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source_repository = Path(args.source_repository).resolve()
    checkout_commit = args.checkout_commit.lower()
    output_path = Path(args.output).resolve()
    raw_root = output_path.with_suffix("").parent / (output_path.with_suffix("").name + "_raw")
    short_root = Path(args.short_root).resolve()
    long_root = Path(args.long_root).resolve()
    temp_root = Path(os.environ["TEMP"]).resolve()
    for root in (short_root, long_root, output_path.parent, raw_root):
        require(os.path.commonpath((str(temp_root), str(root))) == str(temp_root), "PATH_OUTSIDE_TEMP")
    require(source_repository.is_dir(), "SOURCE_REPOSITORY_MISSING")
    require(len(checkout_commit) == 40 and all(char in "0123456789abcdef" for char in checkout_commit), "CHECKOUT_COMMIT_FORMAT")
    require(not output_path.exists() and not raw_root.exists(), "OUTPUT_ALREADY_EXISTS")
    raw_root.mkdir(parents=True, exist_ok=False)
    runner = CaptureRunner(raw_root)

    git = shutil.which("git.exe") or shutil.which("git")
    require(git is not None, "GIT_NOT_FOUND")
    git_path = Path(git).resolve()
    require(CLIENT_PATH.is_file() and VERIFIER_PATH.is_file() and POLICY_PATH.is_file(), "AUTHORITY_INSTALLATION_MISSING")
    require(sha256_file(POLICY_PATH) == EXPECTED_POLICY_SHA256, "POLICY_IDENTITY")
    require(sha256_file(CLIENT_PATH) == "8d5a5e803c9b7c17f06a488ef815b138d9de1dcd666ab1d4c333414801d4b6e9", "CLIENT_IDENTITY")
    require(sha256_file(VERIFIER_PATH) == "88c4e631035af0c7ec366256c78f4d1f21994554a30201b30b4d6bf775314a3d", "VERIFIER_IDENTITY")
    policy = parse_json_bytes(POLICY_PATH.read_bytes(), "POLICY_JSON")
    configurations = policy.get("allowed_configurations")
    require(isinstance(configurations, list) and all(isinstance(value, str) for value in configurations), "POLICY_CONFIGURATIONS")
    require(set(configurations) == {
        "SHORT_AUTOCRLF_TRUE",
        "SHORT_AUTOCRLF_FALSE",
        "LONG_AUTOCRLF_TRUE",
        "LONG_AUTOCRLF_FALSE",
    }, "POLICY_CONFIGURATION_SET")

    checkout_rows: list[dict[str, Any]] = []
    terminal_payloads: list[dict[str, Any]] = []
    terminal_locators: list[str] = []
    reconciliation_locators: list[str] = []
    all_process_locators: list[str] = []
    all_process_nonces: list[str] = []
    all_process_identities: list[str] = []
    reconciliation_process_locators: list[str] = []
    reconciliation_process_nonces: list[str] = []
    initial_ledger = public_call(
        runner,
        "initial_ledger_verification",
        [str(VERIFIER_PATH), "verify-ledger"],
        source_repository,
        "VERIFIED",
        "R7_PUBLIC_LEDGER_VERIFIED",
    )

    for position, configuration in enumerate(configurations, start=1):
        progress("CHECKOUT_START", configuration)
        path_class = "SHORT" if configuration.startswith("SHORT_") else "LONG"
        autocrlf = configuration.endswith("_TRUE")
        destination = (short_root if path_class == "SHORT" else long_root) / configuration.lower()
        require(not destination.exists(), f"CHECKOUT_EXISTS:{configuration}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        prefix = f"{position:02d}_{configuration.lower()}"
        clone = runner.run(
            prefix + "_git_clone",
            [git, "-c", "core.longpaths=true", "clone", "--no-checkout", "--no-hardlinks", str(source_repository), str(destination)],
            timeout=300,
        )
        runner.run(prefix + "_git_longpaths", [git, "-C", str(destination), "config", "core.longpaths", "true"])
        runner.run(prefix + "_git_autocrlf_set", [git, "-C", str(destination), "config", "core.autocrlf", str(autocrlf).lower()])
        checkout = runner.run(
            prefix + "_git_checkout",
            [git, "-C", str(destination), "-c", "advice.detachedHead=false", "checkout", "--detach", checkout_commit],
            timeout=300,
        )
        head_capture = runner.run(prefix + "_git_head", [git, "-C", str(destination), "rev-parse", "HEAD"])
        status_before = runner.run(prefix + "_git_status_before", [git, "-C", str(destination), "status", "--porcelain=v2", "--untracked-files=all"])
        unmerged = runner.run(prefix + "_git_unmerged", [git, "-C", str(destination), "ls-files", "-u"])
        autocrlf_capture = runner.run(prefix + "_git_autocrlf_get", [git, "-C", str(destination), "config", "--get", "core.autocrlf"])
        eol_capture = runner.run(prefix + "_git_eol", [git, "-C", str(destination), "ls-files", "--eol"])
        head = head_capture["stdout"].decode("ascii", errors="strict").strip()
        actual_autocrlf = autocrlf_capture["stdout"].decode("ascii", errors="strict").strip()
        eol_text = eol_capture["stdout"].decode("utf-8", errors="strict")
        require(head == checkout_commit, f"CHECKOUT_HEAD:{configuration}")
        require(status_before["stdout"] == b"" and unmerged["stdout"] == b"", f"CHECKOUT_NOT_CLEAN:{configuration}")
        require(actual_autocrlf == str(autocrlf).lower(), f"CHECKOUT_AUTOCRLF:{configuration}")
        require(("w/crlf" in eol_text) if autocrlf else ("w/lf" in eol_text), f"CHECKOUT_EOL_EVIDENCE:{configuration}")
        require((len(str(destination)) < 100) if path_class == "SHORT" else (len(str(destination)) >= 180), f"CHECKOUT_PATH_CLASS:{configuration}")
        progress("CHECKOUT_VERIFIED", configuration)

        issue_nonce = str(uuid.uuid4())
        issue_capture, issue = public_call(
            runner,
            prefix + "_issue_attempt",
            [str(CLIENT_PATH), "issue-attempt", configuration, issue_nonce],
            destination,
            "COMPLETE",
            "R7_ATTEMPT_ISSUED",
        )
        attempt_id = str(issue["attempt_id"])

        phase_results: dict[str, dict[str, Any]] = {}
        pair_process_locators: dict[str, set[str]] = {}
        pair_process_nonces: dict[str, set[str]] = {}
        for phase in ("CANDIDATE", "FRESH"):
            execute_nonce = str(uuid.uuid4())
            execution_capture, execution = public_call(
                runner,
                prefix + "_" + phase.lower() + "_execute",
                [str(CLIENT_PATH), "execute-run", attempt_id, phase, execute_nonce],
                destination,
                "COMPLETE",
                "R7_TERMINAL_RECEIPT_ISSUED",
                timeout=1200,
            )
            locator = str(execution["receipt_locator"])
            verify_capture, verification = public_call(
                runner,
                prefix + "_" + phase.lower() + "_public_verify",
                [str(VERIFIER_PATH), "verify-terminal", locator],
                destination,
                "VERIFIED",
                "R7_PUBLIC_TERMINAL_VERIFIED",
                timeout=600,
            )
            receipt_identity, payload = receipt_payload(locator)
            fixed_terminal_checks(payload, configuration, phase)
            require(payload["attempt_id"] == attempt_id and payload["run_id"] == execution["run_id"], f"TERMINAL_RESPONSE_BINDING:{phase}")
            process_locators, process_nonces, process_identities = process_receipt_set(payload)
            pair_process_locators[phase] = process_locators
            pair_process_nonces[phase] = process_nonces
            all_process_locators.extend(sorted(process_locators))
            all_process_nonces.extend(sorted(process_nonces))
            all_process_identities.extend(sorted(process_identities))
            terminal_payloads.append(payload)
            terminal_locators.append(locator)
            progress(phase + "_TERMINAL_PUBLICLY_VERIFIED", configuration)
            phase_results[phase] = {
                "execute_nonce": execute_nonce,
                "execution": execution,
                "execution_capture": execution_capture,
                "process_receipt_locators": sorted(process_locators),
                "process_receipt_nonces": sorted(process_nonces),
                "public_verification": verification,
                "public_verification_capture": verify_capture,
                "receipt_identity": receipt_identity,
                "receipt_locator": locator,
                "terminal_summary": {
                    "comparator_result_locator": payload["comparator_result_locator"],
                    "event_root": payload["event_root"],
                    "event_source_locator": payload["event_source_locator"],
                    "observation_locator": payload["observation_locator"],
                    "process_index_locator": payload["process_index_locator"],
                    "run_id": payload["run_id"],
                    "run_nonce": payload["run_nonce"],
                    "subject_process_id": payload["subject_process_id"],
                    "subject_run_id": payload["subject_run_id"],
                    "traceability_locator": payload["traceability_locator"],
                },
            }

        candidate = terminal_payloads[-2]
        fresh = terminal_payloads[-1]
        for key in (
            "run_id", "run_nonce", "subject_run_id", "event_root", "event_source_locator",
            "observation_locator", "comparator_result_locator", "process_index_locator",
            "suite_process_receipt_locator", "traceability_locator",
        ):
            require(candidate[key] != fresh[key], f"PAIR_PROVENANCE_REUSE:{configuration}:{key}")
        require(candidate["subject_process_id"] != fresh["subject_process_id"], f"PAIR_SUBJECT_PROCESS_REUSE:{configuration}")
        require(pair_process_locators["CANDIDATE"].isdisjoint(pair_process_locators["FRESH"]), f"PAIR_PROCESS_RECEIPT_REUSE:{configuration}")
        require(pair_process_nonces["CANDIDATE"].isdisjoint(pair_process_nonces["FRESH"]), f"PAIR_PROCESS_NONCE_REUSE:{configuration}")

        reconcile_nonce = str(uuid.uuid4())
        reconcile_capture, reconcile = public_call(
            runner,
            prefix + "_reconcile",
            [str(CLIENT_PATH), "reconcile", attempt_id, phase_results["CANDIDATE"]["receipt_locator"], phase_results["FRESH"]["receipt_locator"], reconcile_nonce],
            destination,
            "COMPLETE",
            "R7_RECONCILIATION_RECEIPT_ISSUED",
            timeout=900,
        )
        reconciliation_locator = str(reconcile["reconciliation_locator"])
        reconciliation_verify_capture, reconciliation_verification = public_call(
            runner,
            prefix + "_reconciliation_public_verify",
            [str(VERIFIER_PATH), "verify-reconciliation", reconciliation_locator],
            destination,
            "VERIFIED",
            "R7_PUBLIC_RECONCILIATION_VERIFIED",
            timeout=900,
        )
        reconciliation_identity, reconciliation = reconciliation_payload(reconciliation_locator)
        require(reconciliation.get("attempt_id") == attempt_id, "RECONCILIATION_ATTEMPT")
        require(reconciliation.get("configuration") == configuration, "RECONCILIATION_CONFIGURATION")
        require(reconciliation.get("candidate_run_id") == candidate["run_id"] and reconciliation.get("fresh_run_id") == fresh["run_id"], "RECONCILIATION_RUN_BINDING")
        require(reconciliation.get("candidate_event_root") == candidate["event_root"] and reconciliation.get("fresh_event_root") == fresh["event_root"], "RECONCILIATION_EVENT_BINDING")
        require(reconciliation.get("provenance_disjoint") is True and reconciliation.get("synthetic_result_class_absent") is True, "RECONCILIATION_SEMANTICS")
        require(reconciliation.get("reconciliation_result") == "SEMANTICALLY_EQUIVALENT_REAL_EXECUTIONS", "RECONCILIATION_RESULT")
        reconciliation_locators.append(reconciliation_locator)
        reconciliation_process_locators.append(str(reconciliation["reconciliation_process_receipt_locator"]))
        reconciliation_process_nonces.append(str(reconciliation["reconciliation_process_nonce"]))
        progress("RECONCILIATION_PUBLICLY_VERIFIED", configuration)

        status_after = runner.run(prefix + "_git_status_after", [git, "-C", str(destination), "status", "--porcelain=v2", "--untracked-files=all"])
        require(status_after["stdout"] == b"", f"CHECKOUT_DIRTY_AFTER:{configuration}")
        checkout_rows.append({
            "attempt_id": attempt_id,
            "checkout": {
                "autocrlf": actual_autocrlf,
                "checkout_capture": clean_capture(checkout),
                "clone_capture": clean_capture(clone),
                "eol_capture": clean_capture(eol_capture),
                "head": head,
                "path": str(destination),
                "path_class": path_class,
                "path_length": len(str(destination)),
                "status_after_capture": clean_capture(status_after),
                "status_before_capture": clean_capture(status_before),
            },
            "configuration": configuration,
            "issue_capture": issue_capture,
            "issue_nonce": issue_nonce,
            "phases": phase_results,
            "reconciliation": {
                "identity": reconciliation_identity,
                "locator": reconciliation_locator,
                "process_nonce": reconciliation["reconciliation_process_nonce"],
                "process_receipt_locator": reconciliation["reconciliation_process_receipt_locator"],
                "public_verification": reconciliation_verification,
                "public_verification_capture": reconciliation_verify_capture,
                "reconcile_capture": reconcile_capture,
                "reconcile_nonce": reconcile_nonce,
                "result": reconciliation["reconciliation_result"],
            },
        })

    expected_runs = len(configurations) * 2
    expected_reconciliations = len(configurations)
    uniqueness_fields = (
        "run_id", "run_nonce", "subject_run_id", "event_root", "event_source_locator",
        "observation_locator", "comparator_result_locator", "process_index_locator",
        "suite_process_receipt_locator", "traceability_locator",
    )
    uniqueness: dict[str, int] = {}
    for key in uniqueness_fields:
        values = [str(payload[key]) for payload in terminal_payloads]
        unique_count(values, expected_runs, "GLOBAL_" + key.upper())
        uniqueness[key] = len(set(values))
    unique_count(terminal_locators, expected_runs, "GLOBAL_TERMINAL_LOCATORS")
    unique_count(reconciliation_locators, expected_reconciliations, "GLOBAL_RECONCILIATION_LOCATORS")
    unique_count(all_process_locators, expected_runs * 3, "GLOBAL_PROCESS_RECEIPT_LOCATORS")
    unique_count(all_process_nonces, expected_runs * 3, "GLOBAL_PROCESS_NONCES")
    unique_count(all_process_identities, expected_runs * 3, "GLOBAL_PROCESS_IDENTITIES")
    unique_count(reconciliation_process_locators, expected_reconciliations, "GLOBAL_RECONCILIATION_PROCESS_LOCATORS")
    unique_count(reconciliation_process_nonces, expected_reconciliations, "GLOBAL_RECONCILIATION_PROCESS_NONCES")

    final_ledger_capture, final_ledger = public_call(
        runner,
        "final_ledger_verification",
        [str(VERIFIER_PATH), "verify-ledger"],
        source_repository,
        "VERIFIED",
        "R7_PUBLIC_LEDGER_VERIFIED",
    )
    output = {
        "artifact_type": "R7_REAL_EXECUTION_CHECKOUT_MATRIX_RESULT",
        "authority_status": "IMPLEMENTATION_EVIDENCE_PENDING_INDEPENDENT_REVIEW",
        "case_definition_git_blob": EXPECTED_CASE_BLOB,
        "case_definition_sha256": EXPECTED_CASE_SHA256,
        "checkout_commit": checkout_commit,
        "checkout_count": len(checkout_rows),
        "execution_count": expected_runs,
        "expectation_git_blob": EXPECTED_EXPECTATION_BLOB,
        "expectation_sha256": EXPECTED_EXPECTATION_SHA256,
        "final_ledger": final_ledger,
        "final_ledger_capture": final_ledger_capture,
        "git_binary": {"path": str(git_path), "sha256": sha256_file(git_path)},
        "initial_ledger": initial_ledger[1],
        "initial_ledger_capture": initial_ledger[0],
        "phase_label": args.phase_label,
        "policy_sha256": EXPECTED_POLICY_SHA256,
        "reconciliation_count": expected_reconciliations,
        "rows": checkout_rows,
        "schema_version": "7.1.0-DRAFT",
        "service_binary_sha256": EXPECTED_SERVICE_SHA256,
        "source_repository": str(source_repository),
        "status": "PASS",
        "uniqueness": uniqueness | {
            "process_receipt_locators": len(set(all_process_locators)),
            "process_receipt_nonces": len(set(all_process_nonces)),
            "reconciliation_process_receipts": len(set(reconciliation_process_locators)),
            "reconciliations": len(set(reconciliation_locators)),
            "terminal_receipts": len(set(terminal_locators)),
        },
        "worker_binary_sha256": EXPECTED_WORKER_SHA256,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(json_bytes(output))
    progress("MATRIX_COMPLETE", args.phase_label)
    summary = {
        "execution_count": expected_runs,
        "output": str(output_path),
        "reconciliation_count": expected_reconciliations,
        "sha256": sha256_file(output_path),
        "status": "PASS",
    }
    sys.stdout.buffer.write(json_bytes(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
