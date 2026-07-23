#!/usr/bin/env python3
"""Externally executed one-time R6 run-authority issuer."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ISSUER_INTERFACE_VERSION = "RANDLE-R6-RUN-ISSUER-1"
_ORIGINAL_POPEN = subprocess.Popen


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def identity(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def issuer_main() -> int:
    request = json.loads(sys.stdin.buffer.read().decode("utf-8", "strict"))
    nonce = secrets.token_hex(32)
    # Windows clock granularity can yield the same microsecond text in
    # concurrently launched issuer processes.  Bind the measured nanosecond
    # clock value and all 256 random nonce bits below nanosecond precision.
    # RFC 3339 permits arbitrary fractional-second precision, while semantic
    # chronology remains the measured instant when consumers parse it.
    issued_ns = time.time_ns()
    issued_seconds, issued_fraction_ns = divmod(issued_ns, 1_000_000_000)
    issued = dt.datetime.fromtimestamp(issued_seconds, dt.timezone.utc).replace(
        microsecond=issued_fraction_ns // 1_000
    )
    nonce_decimal = str(int(nonce, 16)).zfill(78)
    issued_text = (
        dt.datetime.fromtimestamp(issued_seconds, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.")
        + f"{issued_fraction_ns:09d}{nonce_decimal}Z"
    )
    valid_until = issued + dt.timedelta(hours=2)
    authority = {
        "schema_version": "6.0.0-DRAFT",
        "interface_version": ISSUER_INTERFACE_VERSION,
        "attempt_id": "R6-REMEDIATION-20260722",
        "run_id": identity({"nonce": nonce, "issued": issued_text, "pid": os.getpid()}),
        "run_nonce": nonce,
        "issued_timestamp": issued_text,
        "valid_from": issued_text,
        "valid_until": valid_until.isoformat().replace("+00:00", "Z"),
        "issuing_authority": request["issuing_authority"],
        "specification_commit": request["specification_commit"],
        "case_set_identity": request["case_set_identity"],
        "expectation_identity": request["expectation_identity"],
        "enforcing_code_identity": request["enforcing_code_identity"],
        "schema_set_identity": request["schema_set_identity"],
        "event_recorder_authority": request["event_recorder_authority"],
        "comparator_authority": request["comparator_authority"],
        "mandatory_test_authority_identity": request["mandatory_test_authority_identity"],
        "one_time_use_state": "ISSUED_UNCONSUMED",
        "issuer_pid": os.getpid(),
        "issuer_parent_pid": os.getppid(),
        "issuer_process_start_ns": time.time_ns(),
    }
    authority["issuance_event_identity"] = identity(authority)
    sys.stdout.buffer.write(canonical(authority))
    return 0


def issue_fresh_run(authorities: Any, request: dict[str, Any], disposable_root: Path) -> dict[str, Any]:
    from governed_file_access_DRAFT import write_disposable_binary
    from r6_authority_verifier_DRAFT import code_object_fingerprint, require, strict_json_loads

    policy = authorities.load_json("fresh_run_issuance_policy")
    accepted = authorities.load_bytes("fresh_run_issuer_code")
    require(policy["issuer_raw_sha256"] == accepted.raw_sha256, "RUN_ISSUER_RAW")
    require(policy["issuer_git_blob"] == accepted.git_blob, "RUN_ISSUER_BLOB")
    require(policy["issuer_function_fingerprint"] == code_object_fingerprint(issue_fresh_run.__code__), "RUN_ISSUER_FUNCTION_REPLACED")
    require(subprocess.Popen is _ORIGINAL_POPEN, "RUN_ISSUER_POPEN_REPLACED")
    root = disposable_root / f"issuer-{secrets.token_hex(8)}"
    root.mkdir(parents=True, exist_ok=False)
    script = root / "fresh_run_issuer_R6_DRAFT.py"
    write_disposable_binary(script, accepted.raw)
    started = time.time_ns()
    process = _ORIGINAL_POPEN([sys.executable, "-I", "-S", str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(root))
    stdout, stderr = process.communicate(canonical(request))
    completed = time.time_ns()
    require(process.returncode == 0, "RUN_ISSUER_PROCESS", stderr.decode("utf-8", "replace"))
    authority = strict_json_loads(stdout)
    require(authority["interface_version"] == ISSUER_INTERFACE_VERSION, "RUN_ISSUER_INTERFACE")
    require(authority["issuer_pid"] > 0 and authority["issuer_parent_pid"] > 0, "RUN_ISSUER_PID")
    # A Windows venv executable may be a measured stub whose PID becomes the
    # real interpreter's parent.  Either direct or stub launch is bound.
    require(authority["issuer_pid"] == process.pid or authority["issuer_parent_pid"] == process.pid, "RUN_ISSUER_PARENT")
    require(started <= authority["issuer_process_start_ns"] <= completed, "RUN_ISSUER_TIME")
    require(authority["specification_commit"] == request["specification_commit"], "RUN_ISSUER_COMMIT")
    for field in ("case_set_identity", "expectation_identity", "enforcing_code_identity", "schema_set_identity", "event_recorder_authority", "comparator_authority", "mandatory_test_authority_identity"):
        require(authority[field] == request[field], "RUN_ISSUER_CONTEXT", field)
    proof = dict(authority)
    claimed = proof.pop("issuance_event_identity")
    require(identity(proof) == claimed, "RUN_ISSUER_PROOF")
    return authority


def consume_run_authority(authority: dict[str, Any], state_root: Path) -> str:
    from r6_authority_verifier_DRAFT import parse_timestamp, require, semantic_identity

    require(authority["one_time_use_state"] == "ISSUED_UNCONSUMED", "RUN_AUTHORITY_STATE")
    now = dt.datetime.now(dt.timezone.utc)
    require(parse_timestamp(authority["valid_from"], "run valid_from") <= now <= parse_timestamp(authority["valid_until"], "run valid_until"), "RUN_AUTHORITY_EXPIRED")
    state_root.mkdir(parents=True, exist_ok=True)
    marker = state_root / f"{authority['run_id']}.consumed"
    try:
        descriptor = os.open(str(marker), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("RUN_AUTHORITY_REUSED") from exc
    try:
        os.write(descriptor, authority["issuance_event_identity"].encode("ascii"))
    finally:
        os.close(descriptor)
    authority["one_time_use_state"] = "CONSUMED"
    return semantic_identity(authority)


if __name__ == "__main__":
    raise SystemExit(issuer_main())
