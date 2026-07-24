#!/usr/bin/env python3
"""Execute the 25 R7I-B01 attacks against measured installed components."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
from typing import Any


AUTHORITY_ROOT = Path(r"C:\ProgramData\RandleAI\TerminalAuthority")
EVIDENCE_ROOT = AUTHORITY_ROOT / "Evidence"
RECEIPT_ROOT = AUTHORITY_ROOT / "Receipts"
SESSION_ROOT = AUTHORITY_ROOT / "Sessions"
CHECKPOINT_PATH = AUTHORITY_ROOT / "Ledger" / "checkpoint.json"
INSTALL_ROOT = Path(r"C:\Program Files\RandleAI\TerminalAuthority")
WORKER_PATH = INSTALL_ROOT / "RandleTerminalAuthorityR7Worker.exe"
PUBLIC_VERIFIER_PATH = INSTALL_ROOT / "RandleTerminalAuthorityR7PublicVerifier.exe"
POLICY_PATH = AUTHORITY_ROOT / "Config" / "r7_terminal_authority_policy.json"
CASE_PATH = AUTHORITY_ROOT / "Config" / "R7Authorities" / "r7_real_case_definitions.json"
EXPECTATION_PATH = AUTHORITY_ROOT / "Config" / "R7Authorities" / "r7_independent_expectations.json"
HISTORICAL_SYNTHETIC_RECEIPT = "75eb453346d232b9a67f6a88cf7f2796bf75daf4ac577cebdad321ee2cf597cc"
ZERO_HASH = "0" * 64


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if canonical(value) != raw.rstrip(b"\n"):
        raise RuntimeError(f"noncanonical JSON: {path}")
    return value


def parse_locator(locator: str, kind: str) -> str:
    prefix = f"randle-{kind}://sha256/"
    if not locator.startswith(prefix):
        raise RuntimeError(f"wrong locator kind: {locator}")
    identity = locator[len(prefix) :]
    if len(identity) != 64 or identity != identity.lower() or any(character not in "0123456789abcdef" for character in identity):
        raise RuntimeError(f"noncanonical locator: {locator}")
    return identity


def read_locator(locator: str, kind: str) -> dict[str, Any]:
    identity = parse_locator(locator, kind)
    root = RECEIPT_ROOT if kind == "terminal" else EVIDENCE_ROOT
    matches = [path for path in (root / f"{identity}.json", root / f"{identity}.bin") if path.is_file()]
    if len(matches) != 1:
        raise RuntimeError(f"unresolved or ambiguous locator: {locator}")
    raw = matches[0].read_bytes()
    if sha256_bytes(raw) != identity:
        raise RuntimeError(f"content address mismatch: {locator}")
    return json.loads(raw.decode("utf-8"))


def checkpoint() -> dict[str, Any]:
    envelope = read_json(CHECKPOINT_PATH)
    payload = envelope["payload"]
    return {
        "identity": sha256_file(CHECKPOINT_PATH),
        "root_hash": payload["root_hash"],
        "sequence": payload["sequence"],
    }


def receipt_payload(locator: str) -> dict[str, Any]:
    envelope = read_locator(locator, "terminal")
    if set(envelope) != {"payload", "public_key_identity", "signature", "signature_algorithm"}:
        raise RuntimeError("terminal envelope shape rejected")
    return envelope["payload"]


def index_by_case(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["case_id"]: row for row in rows}


def rehash_events(event_source: dict[str, Any], observations: dict[str, Any] | None, traces: dict[str, Any] | None) -> None:
    observed = index_by_case(observations["observations"]) if observations is not None else {}
    traced = index_by_case(traces["rows"]) if traces is not None else {}
    prior = ZERO_HASH
    for event in event_source["events"]:
        event["prior_event_hash"] = prior
        event.pop("event_hash", None)
        identity = sha256_bytes(canonical(event))
        event["event_hash"] = identity
        if event["case_id"] in observed:
            observed[event["case_id"]]["event_hash"] = identity
        if event["case_id"] in traced:
            traced[event["case_id"]]["event_hash"] = identity
        prior = identity
    event_source["event_count"] = len(event_source["events"])
    event_source["event_root"] = prior


class Harness:
    def __init__(self, output_root: Path, candidate_locator: str, fresh_locator: str, attempt_id: str) -> None:
        self.output_root = output_root
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.candidate_locator = candidate_locator
        self.fresh_locator = fresh_locator
        self.attempt_id = attempt_id
        self.candidate_payload = receipt_payload(candidate_locator)
        self.fresh_payload = receipt_payload(fresh_locator)
        self.candidate_event = read_locator(self.candidate_payload["event_source_locator"], "evidence")
        self.candidate_observation = read_locator(self.candidate_payload["observation_locator"], "evidence")
        self.candidate_trace = read_locator(self.candidate_payload["traceability_locator"], "evidence")
        self.fresh_event = read_locator(self.fresh_payload["event_source_locator"], "evidence")
        self.fresh_observation = read_locator(self.fresh_payload["observation_locator"], "evidence")
        self.fresh_trace = read_locator(self.fresh_payload["traceability_locator"], "evidence")
        self.expectations = read_json(EXPECTATION_PATH)
        self.cases = read_json(CASE_PATH)
        self.created_evidence: list[Path] = []
        self.cleanup_records: list[dict[str, Any]] = []

    def store_evidence(self, value: dict[str, Any]) -> str:
        raw = canonical(value)
        identity = sha256_bytes(raw)
        path = EVIDENCE_ROOT / f"{identity}.json"
        binary_path = EVIDENCE_ROOT / f"{identity}.bin"
        if binary_path.exists():
            raise RuntimeError(f"attack evidence identity is ambiguous: {identity}")
        if path.exists():
            if path.read_bytes() != raw:
                raise RuntimeError(f"attack evidence collision: {identity}")
        else:
            path.write_bytes(raw)
            self.created_evidence.append(path)
        return f"randle-evidence://sha256/{identity}"

    def invoke_worker(self, probe_id: str, mode: str, run_id: str, subject: dict[str, Any]) -> dict[str, Any]:
        process_nonce = secrets.token_hex(32)
        session = SESSION_ROOT / f"r7i-b01-{probe_id.lower()}-{secrets.token_hex(8)}"
        session.mkdir(parents=False, exist_ok=False)
        input_path = session / "input.json"
        input_value = {"mode": mode, "process_nonce": process_nonce, "run_id": run_id, "subject": subject}
        input_bytes = canonical(input_value)
        input_path.write_bytes(input_bytes)
        try:
            process = subprocess.run(
                [str(WORKER_PATH), mode, run_id, process_nonce, str(input_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=180,
                check=False,
            )
        finally:
            shutil.rmtree(session)
            self.cleanup_records.append({"path": str(session), "recovery": "not applicable; task-created worker input", "removed": True})
        record: dict[str, Any] = {
            "exit_code": process.returncode,
            "input_sha256": sha256_bytes(input_bytes),
            "process_nonce": process_nonce,
            "stderr_length": len(process.stderr),
            "stderr_sha256": sha256_bytes(process.stderr),
            "stderr_excerpt": process.stderr.decode("utf-8", errors="replace")[:512],
            "stdout_length": len(process.stdout),
            "stdout_sha256": sha256_bytes(process.stdout),
            "worker_sha256": sha256_file(WORKER_PATH),
        }
        if process.returncode == 0:
            wrapper = json.loads(process.stdout.decode("utf-8"))
            result = wrapper["result"]
            record["result"] = result
        return record

    def compare(self, probe_id: str, event: dict[str, Any], observation: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
        event_locator = self.store_evidence(event)
        observation_locator = self.store_evidence(observation)
        trace_locator = self.store_evidence(trace)
        record = self.invoke_worker(
            probe_id,
            "compare",
            event["run_id"],
            {
                "event_source_locator": event_locator,
                "observation_locator": observation_locator,
                "traceability_locator": trace_locator,
            },
        )
        if record["exit_code"] == 0:
            result = record["result"]
            record["discrepancy_codes"] = sorted({row.get("code", "") for row in result.get("discrepancies", [])})
            record["rejected"] = result.get("conformity") == "NONCONFORMANT" and result.get("discrepancy_count", 0) > 0
            del record["result"]
        else:
            record["discrepancy_codes"] = ["STRUCTURAL_EXCEPTION"]
            record["rejected"] = True
        return record

    def structural_compare(self, probe_id: str, subject: dict[str, Any]) -> dict[str, Any]:
        record = self.invoke_worker(probe_id, "compare", self.candidate_payload["run_id"], subject)
        record["discrepancy_codes"] = ["STRICT_INPUT_REJECTION"] if record["exit_code"] != 0 else []
        record["rejected"] = record["exit_code"] != 0
        record.pop("result", None)
        return record

    def reconcile(self, probe_id: str, candidate: str, fresh: str, attempt_id: str | None = None) -> dict[str, Any]:
        record = self.invoke_worker(
            probe_id,
            "reconcile",
            secrets.token_hex(32),
            {"attempt_id": attempt_id or self.attempt_id, "candidate_locator": candidate, "fresh_locator": fresh},
        )
        if record["exit_code"] == 0:
            result = record["result"]
            record["discrepancy_codes"] = sorted({row.get("code", "") for row in result.get("discrepancies", [])})
            record["rejected"] = result.get("reconciliation_result") == "REJECTED" and result.get("discrepancy_count", 0) > 0
            del record["result"]
        else:
            record["discrepancy_codes"] = ["STRUCTURAL_EXCEPTION"]
            record["rejected"] = True
        return record

    def public_verify_rejection(self, probe_id: str, locator: str) -> dict[str, Any]:
        process = subprocess.run(
            [str(PUBLIC_VERIFIER_PATH), "verify-terminal", locator],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
        return {
            "discrepancy_codes": ["PUBLIC_VERIFIER_REJECTION"],
            "exit_code": process.returncode,
            "public_verifier_sha256": sha256_file(PUBLIC_VERIFIER_PATH),
            "rejected": process.returncode != 0,
            "stderr_excerpt": process.stderr.decode("utf-8", errors="replace")[:512],
            "stderr_length": len(process.stderr),
            "stderr_sha256": sha256_bytes(process.stderr),
            "stdout_length": len(process.stdout),
            "stdout_sha256": sha256_bytes(process.stdout),
        }

    def cloned(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        return copy.deepcopy(self.candidate_event), copy.deepcopy(self.candidate_observation), copy.deepcopy(self.candidate_trace)

    def run(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        def record(probe_id: str, method: str, action: Any) -> None:
            before = checkpoint()
            detail = action()
            after = checkpoint()
            detail["ledger_after"] = after
            detail["ledger_before"] = before
            detail["ledger_unchanged"] = before["sequence"] == after["sequence"] and before["root_hash"] == after["root_hash"]
            detail["method"] = method
            detail["probe_id"] = probe_id
            detail["status"] = "REJECTED_AS_REQUIRED" if detail.get("rejected") and detail["ledger_unchanged"] else "FAILED"
            results.append(detail)

        event, observation, trace = self.cloned()
        for row in event["events"]:
            row["actual_outcome"] = "PASS"
            row["interface_invoked"] = False
            row["response_classification"] = "OK"
        for row in observation["observations"]:
            row["actual_outcome"] = "PASS"
            row["interface_invoked"] = False
            row["response_classification"] = "OK"
        rehash_events(event, observation, trace)
        record("R7I-B01-A01", "measured comparator / synthetic event mutation", lambda: self.compare("R7I-B01-A01", event, observation, trace))

        event, observation, trace = self.cloned()
        event["events"][0]["actual_authority_identity"] = sha256_file(POLICY_PATH)
        event["events"][0]["enforcing_function"] = "POLICY_IDENTITY_ECHO"
        rehash_events(event, observation, trace)
        record("R7I-B01-A02", "measured comparator / policy echo mutation", lambda: self.compare("R7I-B01-A02", event, observation, trace))

        event, _, trace = self.cloned()
        copied = {
            "artifact_type": "R7_DERIVED_CURRENT_OBSERVATIONS",
            "event_source_locator": "randle-evidence://sha256/" + ZERO_HASH,
            "observation_count": len(self.expectations["expectations"]),
            "observations": copy.deepcopy(self.expectations["expectations"]),
            "observer_binary_sha256": sha256_file(WORKER_PATH),
            "observer_process_id": os.getpid(),
            "observer_process_nonce": secrets.token_hex(32),
            "run_id": event["run_id"],
            "schema_version": "7.1.0-DRAFT",
        }
        record("R7I-B01-A03", "measured comparator / expectation-to-observation copy", lambda: self.compare("R7I-B01-A03", event, copied, trace))

        event, observation, trace = self.cloned()
        event["events"][0]["actual_outcome"] = "OK"
        event["events"][0]["response_classification"] = "OK"
        observation["observations"][0]["actual_outcome"] = "OK"
        observation["observations"][0]["response_classification"] = "OK"
        rehash_events(event, observation, trace)
        record("R7I-B01-A04", "measured comparator / constructed matching text", lambda: self.compare("R7I-B01-A04", event, observation, trace))

        record("R7I-B01-A05", "measured comparator / caller-authored zero discrepancies", lambda: self.structural_compare("R7I-B01-A05", {"conformity": "CONFORMANT", "discrepancies": [], "discrepancy_count": 0}))

        event, observation, trace = self.cloned()
        event["case_definition_git_blob"] = "f" * 40
        record("R7I-B01-A06", "measured comparator / unresolved case identity", lambda: self.compare("R7I-B01-A06", event, observation, trace))

        altered_cases = copy.deepcopy(self.cases)
        altered_cases["cases"][0]["case_id"] = altered_cases["cases"][0]["case_id"] + "-ALTERED"
        altered_case_path = self.output_root / "altered_case_definitions.json"
        altered_case_path.write_bytes(canonical(altered_cases))
        base_subject = {
            "event_source_locator": self.candidate_payload["event_source_locator"],
            "observation_locator": self.candidate_payload["observation_locator"],
            "traceability_locator": self.candidate_payload["traceability_locator"],
        }
        subject = dict(base_subject); subject["case_definition_path"] = str(altered_case_path)
        record("R7I-B01-A07", "measured comparator / post-identity changed case bytes", lambda: self.structural_compare("R7I-B01-A07", subject))
        subject = dict(base_subject); subject["case_definition_path"] = str(altered_case_path)
        record("R7I-B01-A08", "measured comparator / caller-selected case path", lambda: self.structural_compare("R7I-B01-A08", subject))

        altered_expectations = copy.deepcopy(self.expectations)
        altered_expectations["expectations"][0]["expected_outcome"] = "OK"
        altered_expectation_path = self.output_root / "altered_expectations.json"
        altered_expectation_path.write_bytes(canonical(altered_expectations))
        subject = dict(base_subject); subject["expectation_path"] = str(altered_expectation_path)
        record("R7I-B01-A09", "measured comparator / caller-selected expectation path", lambda: self.structural_compare("R7I-B01-A09", subject))

        event, observation, trace = self.cloned()
        removed_case = event["events"].pop()["case_id"]
        observation["observations"] = [row for row in observation["observations"] if row["case_id"] != removed_case]
        trace["rows"] = [row for row in trace["rows"] if row["case_id"] != removed_case]
        rehash_events(event, observation, trace)
        record("R7I-B01-A10", "measured comparator / omitted required case", lambda: self.compare("R7I-B01-A10", event, observation, trace))

        event, observation, trace = self.cloned()
        event["events"].append(copy.deepcopy(event["events"][0]))
        rehash_events(event, observation, trace)
        record("R7I-B01-A11", "measured comparator / duplicate case", lambda: self.compare("R7I-B01-A11", event, observation, trace))

        event, observation, trace = self.cloned()
        unknown = copy.deepcopy(event["events"][0]); unknown["case_id"] = "R7I-B01-UNKNOWN-EXTRA"
        event["events"].append(unknown)
        rehash_events(event, observation, trace)
        record("R7I-B01-A12", "measured comparator / unknown extra case", lambda: self.compare("R7I-B01-A12", event, observation, trace))

        event = copy.deepcopy(self.fresh_event); observation = copy.deepcopy(self.fresh_observation); trace = copy.deepcopy(self.fresh_trace)
        event["events"][0] = copy.deepcopy(self.candidate_event["events"][0])
        rehash_events(event, observation, trace)
        record("R7I-B01-A13", "measured comparator / prior-run event substitution", lambda: self.compare("R7I-B01-A13", event, observation, trace))

        event = copy.deepcopy(self.fresh_event); observation = copy.deepcopy(self.fresh_observation); trace = copy.deepcopy(self.fresh_trace)
        prior_suite = self.candidate_payload["suite_process_receipt_locator"]
        event["events"][0]["suite_process_receipt_locator"] = prior_suite
        event["events"][0]["invoking_process_receipt_identity"] = parse_locator(prior_suite, "evidence")
        rehash_events(event, observation, trace)
        record("R7I-B01-A14", "measured comparator / prior-run signed process receipt", lambda: self.compare("R7I-B01-A14", event, observation, trace))

        event, observation, trace = self.cloned()
        event["events"][0]["public_request_locator"] = "randle-evidence://sha256/" + "e" * 64
        event["events"][0]["request_sha256"] = "e" * 64
        rehash_events(event, observation, trace)
        record("R7I-B01-A15", "measured comparator / fabricated request locator", lambda: self.compare("R7I-B01-A15", event, observation, trace))

        event, observation, trace = self.cloned()
        event["events"][0]["interface_invoked"] = False
        observation["observations"][0]["interface_invoked"] = False
        rehash_events(event, observation, trace)
        record("R7I-B01-A16", "measured comparator / process receipt without invocation", lambda: self.compare("R7I-B01-A16", event, observation, trace))

        event, observation, trace = self.cloned()
        event["events"][0]["target_process_binary_sha256"] = "f" * 64
        rehash_events(event, observation, trace)
        record("R7I-B01-A17", "measured comparator / wrong target binary", lambda: self.compare("R7I-B01-A17", event, observation, trace))

        expected = index_by_case(self.expectations["expectations"])
        event, observation, trace = self.cloned()
        negative = next(row for row in event["events"] if expected[row["case_id"]]["expected_outcome"] == "REJECTED")
        negative["outer_post_ledger_sequence"] = negative["outer_pre_ledger_sequence"] + 1
        negative["outer_post_ledger_root"] = "f" * 64
        negative["forbidden_side_effect_absent"] = False
        observed_negative = index_by_case(observation["observations"])[negative["case_id"]]
        observed_negative["outer_ledger_delta"] = 1
        observed_negative["forbidden_side_effect_absent"] = False
        rehash_events(event, observation, trace)
        record("R7I-B01-A18", "measured comparator / rejected case with authority delta", lambda: self.compare("R7I-B01-A18", event, observation, trace))

        event, observation, trace = self.cloned()
        positive = next(row for row in event["events"] if expected[row["case_id"]]["expected_outcome"] != "REJECTED")
        positive["subject_event_ledger_delta"] = 0
        index_by_case(observation["observations"])[positive["case_id"]]["subject_event_ledger_delta"] = 0
        rehash_events(event, observation, trace)
        record("R7I-B01-A19", "measured comparator / success without durable subject append", lambda: self.compare("R7I-B01-A19", event, observation, trace))

        record("R7I-B01-A20", "measured reconciler / candidate-fresh evidence reuse", lambda: self.reconcile("R7I-B01-A20", self.candidate_locator, self.candidate_locator))
        fake_candidate = "randle-terminal://sha256/" + "a" * 64
        fake_fresh = "randle-terminal://sha256/" + "b" * 64
        record("R7I-B01-A21", "measured reconciler / two synthetic receipt locators", lambda: self.reconcile("R7I-B01-A21", fake_candidate, fake_fresh))

        event, observation, trace = self.cloned()
        trace["rows"][0]["event_hash"] = "f" * 64
        record("R7I-B01-A22", "measured comparator / false trace row", lambda: self.compare("R7I-B01-A22", event, observation, trace))

        historical_locator = f"randle-terminal://sha256/{HISTORICAL_SYNTHETIC_RECEIPT}"
        record("R7I-B01-A23", "public verifier / valid signature with semantically unresolved synthetic children", lambda: self.public_verify_rejection("R7I-B01-A23", historical_locator))

        suite_identity = parse_locator(self.candidate_payload["suite_process_receipt_locator"], "evidence")
        detached_locator = f"randle-terminal://sha256/{suite_identity}"
        record("R7I-B01-A24", "public verifier / valid signed process receipt detached from terminal ledger/root", lambda: self.public_verify_rejection("R7I-B01-A24", detached_locator))

        copied_root = self.output_root / "copied_evidence_root"
        copied_root.mkdir(exist_ok=False)
        copied_manifest: dict[str, str] = {}
        for name, locator in (
            ("events", self.candidate_payload["event_source_locator"]),
            ("observations", self.candidate_payload["observation_locator"]),
            ("traceability", self.candidate_payload["traceability_locator"]),
        ):
            identity = parse_locator(locator, "evidence")
            source = next(path for path in (EVIDENCE_ROOT / f"{identity}.json", EVIDENCE_ROOT / f"{identity}.bin") if path.is_file())
            target = copied_root / source.name
            shutil.copyfile(source, target)
            copied_manifest[name] = sha256_file(target)
        (copied_root / "manifest.json").write_bytes(canonical(copied_manifest))
        subject = dict(base_subject); subject["evidence_root"] = str(copied_root)
        record("R7I-B01-A25", "measured comparator / caller-selected copied evidence root", lambda: self.structural_compare("R7I-B01-A25", subject))

        return results

    def cleanup(self) -> None:
        for path in reversed(self.created_evidence):
            resolved = path.resolve()
            if resolved.parent != EVIDENCE_ROOT.resolve() or not resolved.name.endswith(".json"):
                raise RuntimeError(f"unsafe cleanup target: {resolved}")
            if resolved.exists():
                resolved.unlink()
            self.cleanup_records.append({"path": str(resolved), "recovery": "not applicable; task-created adversarial clone", "removed": True})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--fresh", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.attempt_id) != 64:
        raise SystemExit("attempt identity rejected")
    output_root = args.output.resolve().parent / (args.output.stem + "_raw")
    if output_root.exists():
        raise SystemExit(f"output root already exists: {output_root}")
    harness = Harness(output_root, args.candidate, args.fresh, args.attempt_id)
    start = checkpoint()
    control_record: dict[str, Any] | None = None
    results: list[dict[str, Any]] = []
    try:
        control_record = harness.compare(
            "R7I-B01-CONTROL",
            copy.deepcopy(harness.candidate_event),
            copy.deepcopy(harness.candidate_observation),
            copy.deepcopy(harness.candidate_trace),
        )
        if control_record["exit_code"] != 0 or control_record["rejected"]:
            raise RuntimeError("valid baseline comparator control did not conform")
        results = harness.run()
    finally:
        harness.cleanup()
    end = checkpoint()
    definitions_path = Path(__file__).resolve().with_name("r7i_b01_adversarial_probes_DRAFT.json")
    definitions = read_json(definitions_path)
    expected_ids = [row["probe_id"] for row in definitions["probes"]]
    actual_ids = [row["probe_id"] for row in results]
    all_passed = len(results) == 25 and actual_ids == expected_ids and all(row["status"] == "REJECTED_AS_REQUIRED" for row in results)
    summary = {
        "artifact_type": "R7I_B01_CURRENT_ADVERSARIAL_EXECUTION_RESULT",
        "baseline": {
            "attempt_id": args.attempt_id,
            "candidate_locator": args.candidate,
            "candidate_run_id": harness.candidate_payload["run_id"],
            "fresh_locator": args.fresh,
            "fresh_run_id": harness.fresh_payload["run_id"],
        },
        "case_authority_sha256": sha256_file(CASE_PATH),
        "cleanup": harness.cleanup_records,
        "control": control_record,
        "expectation_authority_sha256": sha256_file(EXPECTATION_PATH),
        "final_ledger": end,
        "initial_ledger": start,
        "outer_ledger_unchanged": start["sequence"] == end["sequence"] and start["root_hash"] == end["root_hash"],
        "policy_sha256": sha256_file(POLICY_PATH),
        "probe_definition_sha256": sha256_file(definitions_path),
        "probe_results": results,
        "public_verifier_sha256": sha256_file(PUBLIC_VERIFIER_PATH),
        "schema_version": "7.1.0-DRAFT",
        "service_sha256": sha256_file(INSTALL_ROOT / "RandleTerminalAuthority.exe"),
        "status": "PASS" if all_passed and start["sequence"] == end["sequence"] and start["root_hash"] == end["root_hash"] else "FAIL",
        "worker_sha256": sha256_file(WORKER_PATH),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(summary) + b"\n")
    print(json.dumps({"output": str(args.output), "probe_count": len(results), "sha256": sha256_file(args.output), "status": summary["status"]}, sort_keys=True, separators=(",", ":")))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
