#!/usr/bin/env python3
"""Measured R6 process boundary and parent-side non-callable launch interface."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


LAUNCHER_INTERFACE_VERSION = "RANDLE-R6-PROCESS-LAUNCH-1"
_ORIGINAL_POPEN = subprocess.Popen


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: str) -> str:
    digest = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _sanitized_environment() -> dict[str, str]:
    allowed = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "PATH"}
    result = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    result.pop("PYTHONPATH", None)
    result.pop("PYTHONHOME", None)
    result["PYTHONNOUSERSITE"] = "1"
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    result["PYTHONHASHSEED"] = "0"
    return result


def _read_all(path: str) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _write_exclusive(path: str, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
    finally:
        os.close(descriptor)


def boundary_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-nonce", required=True)
    parser.add_argument("--process-nonce", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    started_ns = time.time_ns()
    command = [sys.executable, "-I", "-S", args.worker, "--mode", args.mode, "--subject", args.subject]
    command_identity = _sha(_canonical(command))
    require_original = subprocess.Popen is _ORIGINAL_POPEN
    if not require_original:
        sys.stderr.write('{"code":"PROCESS_LAUNCH_SURFACE_REPLACED"}\n')
        return 91
    payload = _read_all(args.input)
    process = _ORIGINAL_POPEN(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_sanitized_environment(),
        cwd=str(Path(args.worker).parent),
    )
    stdout, stderr = process.communicate(payload)
    completed_ns = time.time_ns()
    try:
        worker_envelope = json.loads(stdout.decode("utf-8", "strict")) if process.returncode == 0 else None
        result = worker_envelope["result"] if worker_envelope is not None else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        result = None
    receipt = {
        "schema_version": "6.0.0-DRAFT",
        "interface_version": LAUNCHER_INTERFACE_VERSION,
        "mode": args.mode,
        "run_id": args.run_id,
        "run_nonce": args.run_nonce,
        "process_nonce": args.process_nonce,
        "launcher_pid": os.getpid(),
        "worker_pid": worker_envelope["worker_process_id"] if worker_envelope is not None else process.pid,
        "worker_parent_pid": worker_envelope["worker_parent_process_id"] if worker_envelope is not None else os.getpid(),
        "parent_pid": os.getppid(),
        "process_start_time_ns": started_ns,
        "process_completion_time_ns": completed_ns,
        "python_executable": os.path.normcase(os.path.abspath(sys.executable)),
        "python_executable_sha256": _file_sha(sys.executable),
        "interpreter_flags": ["-I", "-S"],
        "environment_identity": _sha(_canonical(_sanitized_environment())),
        "command_identity": command_identity,
        "worker_raw_sha256": _file_sha(args.worker),
        "subject_raw_sha256": _file_sha(args.subject),
        "input_identity": _sha(payload),
        "output_identity": _sha(stdout),
        "stdout_sha256": _sha(stdout),
        "stderr_sha256": _sha(stderr),
        "exit_status": process.returncode,
        "completion_status": "COMPLETE" if process.returncode == 0 and result is not None else "FAILED",
    }
    receipt["issuance_proof"] = _sha(_canonical(receipt))
    envelope = {"result": result, "receipt": receipt, "worker_stderr": stderr.decode("utf-8", "replace")}
    sys.stdout.buffer.write(_canonical(envelope))
    return 0 if receipt["completion_status"] == "COMPLETE" else 92


def launch_measured(
    authorities: Any,
    mode: str,
    run_authority: dict[str, Any],
    payload: dict[str, Any],
    subject_role: str,
    disposable_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Launch the accepted boundary and verify fresh process proof; no callable launcher is accepted."""
    from governed_file_access_DRAFT import write_disposable_binary
    from r6_authority_verifier_DRAFT import canonical_json_bytes, code_object_fingerprint, require, semantic_identity, sha256, strict_json_loads, thaw, validate_json_schema

    authority = authorities.load_json("process_launch_authority")
    accepted_launcher = authorities.load_bytes("process_launch_code")
    accepted_worker = authorities.load_bytes("isolated_worker_code")
    accepted_subject = authorities.load_bytes(subject_role)
    require(authority["launcher_git_blob"] == accepted_launcher.git_blob, "PROCESS_LAUNCHER_BLOB")
    require(authority["launcher_raw_sha256"] == accepted_launcher.raw_sha256, "PROCESS_LAUNCHER_RAW")
    require(authority["launcher_function_fingerprint"] == code_object_fingerprint(launch_measured.__code__), "PROCESS_LAUNCH_FUNCTION_REPLACED")
    require(subprocess.Popen is _ORIGINAL_POPEN, "PROCESS_PARENT_POPEN_REPLACED")
    process_nonce = secrets.token_hex(32)
    isolated = disposable_root / f"process-{mode}-{process_nonce[:16]}"
    isolated.mkdir(parents=True, exist_ok=False)
    launcher_path = isolated / "process_launch_boundary_R6_DRAFT.py"
    worker_path = isolated / "isolated_worker_R6_DRAFT.py"
    subject_path = isolated / Path(accepted_subject.path).name
    input_path = isolated / "input.json"
    write_disposable_binary(launcher_path, accepted_launcher.raw)
    write_disposable_binary(worker_path, accepted_worker.raw)
    write_disposable_binary(subject_path, accepted_subject.raw)
    write_disposable_binary(input_path, canonical_json_bytes(payload))
    command = [
        sys.executable, "-I", "-S", str(launcher_path),
        "--mode", mode,
        "--run-id", run_authority["run_id"],
        "--run-nonce", run_authority["run_nonce"],
        "--process-nonce", process_nonce,
        "--worker", str(worker_path),
        "--subject", str(subject_path),
        "--input", str(input_path),
    ]
    start_wall = time.time_ns()
    process = _ORIGINAL_POPEN(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_sanitized_environment(), cwd=str(isolated))
    stdout, stderr = process.communicate()
    end_wall = time.time_ns()
    require(process.returncode == 0, "PROCESS_BOUNDARY_FAILED", stderr.decode("utf-8", "replace"))
    envelope = strict_json_loads(stdout)
    receipt = envelope["receipt"]
    result = envelope["result"]
    require(receipt["interface_version"] == LAUNCHER_INTERFACE_VERSION, "PROCESS_INTERFACE")
    require(receipt["mode"] == mode, "PROCESS_MODE")
    require(receipt["run_id"] == run_authority["run_id"], "PROCESS_RUN_ID")
    require(receipt["run_nonce"] == run_authority["run_nonce"], "PROCESS_RUN_NONCE")
    require(receipt["process_nonce"] == process_nonce, "PROCESS_NONCE_REPLAY")
    require(receipt["launcher_pid"] == process.pid or receipt["parent_pid"] == process.pid, "PROCESS_LAUNCHER_PID")
    require(start_wall <= receipt["process_start_time_ns"] <= receipt["process_completion_time_ns"] <= end_wall, "PROCESS_TIME_WINDOW")
    require(receipt["worker_pid"] != receipt["launcher_pid"], "PROCESS_NOT_ISOLATED")
    require(receipt["worker_raw_sha256"] == accepted_worker.raw_sha256, "PROCESS_WORKER_BLOB")
    require(receipt["subject_raw_sha256"] == accepted_subject.raw_sha256, "PROCESS_SUBJECT_BLOB")
    require(receipt["input_identity"] == sha256(canonical_json_bytes(payload)), "PROCESS_INPUT_IDENTITY")
    proof = dict(receipt)
    claimed_proof = proof.pop("issuance_proof")
    require(claimed_proof == sha256(canonical_json_bytes(proof)), "PROCESS_ISSUANCE_PROOF")
    require(receipt["completion_status"] == "COMPLETE" and receipt["exit_status"] == 0, "PROCESS_INCOMPLETE")
    validate_json_schema(authorities.load_json("process_execution_receipt_schema"), receipt, f"process_receipt:{mode}")
    return result, receipt


if __name__ == "__main__":
    raise SystemExit(boundary_main())
