"""Governed in-process launch envelope for Command Center managed services.

The service choice is fixed and allow-listed.  This module exists so normal
Windows/Command Center launches reproduce the R5C write-authority envelope
without depending on a transient Temp cutover wrapper.
"""

from __future__ import annotations

import argparse
import os
import runpy
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SERVICE_TARGETS = {
    "entry_agent": ROOT / "EntryAgent" / "tv_context_server.py",
    "trade_manager": ROOT / "Engines" / "trade_manager.py",
}


def _probe_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    probe = root / f".command-center-service-launch-{uuid.uuid4().hex}.tmp"
    try:
        probe.write_bytes(b"command-center-production-write-authority\n")
        if probe.read_bytes() != b"command-center-production-write-authority\n":
            raise OSError("write_probe_readback_mismatch")
    finally:
        probe.unlink(missing_ok=True)


def configure_execution_envelope(service: str) -> Path:
    data_value = str(os.environ.get("RANDLE_DATA_ROOT") or "").strip()
    if not data_value:
        raise RuntimeError("RANDLE_DATA_ROOT is required for governed production launch")
    data_root = Path(data_value).expanduser().resolve()
    if not data_root.is_absolute():
        raise RuntimeError("RANDLE_DATA_ROOT must be absolute")

    ledger = data_root / "entry_agent" / "tv_context_acceptance_ledger.json"
    spool = data_root / "tv_context_spool"
    entry = data_root / "entry_agent"
    for root in (data_root, spool, entry):
        _probe_root(root)

    os.environ["TV_CONTEXT_ACCEPTANCE_LEDGER_PATH"] = str(ledger)
    os.environ["TV_CONTEXT_SPOOL_DIR"] = str(spool)
    os.environ["ENTRY_AGENT_TV_CONTEXT_URL"] = "http://127.0.0.1:7002/webhook/tv-context"
    os.environ.setdefault("RANDLE_TRADE_MANAGER_MODE", "qa_stability")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

    target = SERVICE_TARGETS[service].resolve()
    if not target.is_file() or ROOT not in target.parents:
        raise RuntimeError("governed service target missing or outside repository")
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(target.parent))
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch one governed Randle service")
    parser.add_argument("--service", required=True, choices=tuple(SERVICE_TARGETS))
    args = parser.parse_args()
    target = configure_execution_envelope(args.service)
    runpy.run_path(str(target), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
