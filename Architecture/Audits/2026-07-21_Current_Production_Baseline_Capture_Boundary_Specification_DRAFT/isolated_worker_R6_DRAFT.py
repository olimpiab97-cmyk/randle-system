#!/usr/bin/env python3
"""Stdlib-only isolated R6 worker for parser, comparator, recorder, and access probes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def load_subject(path: str) -> Any:
    name = f"r6_measured_{hashlib.sha256(path.encode()).hexdigest()[:16]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("WORKER_SUBJECT_SPEC")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--subject", required=True)
    args = parser.parse_args(argv)
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "strict"))
    subject = load_subject(args.subject)
    if args.mode == "historical_parser":
        with open(payload["physical_path"], "rb") as stream:
            data = stream.read()
        result = subject.parse_historical_log(data, payload["logical_evidence_id"], payload["expected_sha256"])
    elif args.mode == "comparator":
        result = subject.compare(payload["expectations"], payload["observations"], payload["context"])
    elif args.mode == "event_recorder":
        result = subject.record_cases(payload)
    elif args.mode == "runtime_access":
        result = subject.run_access_probe(payload)
    else:
        raise RuntimeError("WORKER_MODE")
    sys.stdout.buffer.write(canonical({"worker_process_id": os.getpid(), "worker_parent_process_id": os.getppid(), "result": result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
