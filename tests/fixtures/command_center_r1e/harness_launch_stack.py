"""Deterministic disposable equivalent of the governed launch_all orchestration."""

from __future__ import annotations

import ctypes
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(os.environ["R1E_FIXTURE_ROOT"]).resolve()
STATE = Path(os.environ["R1E_STATE_PATH"]).resolve()
HELPERS = ROOT / "tests" / "fixtures" / "command_center_r1e"


def read_state() -> dict[str, Any]:
    return json.loads(STATE.read_text(encoding="utf-8"))


def write_state(payload: dict[str, Any]) -> None:
    temporary = STATE.with_name(f"{STATE.name}.{uuid.uuid4().hex}.launcher.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    deadline = time.monotonic() + 2.0
    while True:
        try:
            os.replace(temporary, STATE)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.02)


def alive(pid: int | None) -> bool:
    if not pid:
        return False
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def wait_listener(port: int, timeout: float = 6.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.1)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f"fixture_listener_not_ready:{port}")


def launch(service: str, command: list[str], mode: str) -> None:
    state = read_state()
    current = (state.get("services", {}).get(service) or {}).get("pid")
    if alive(current):
        return
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("RANDLE_CC_R1E_HARNESS", None)
    logs = Path(os.environ["RANDLE_DATA_ROOT"]) / "r1e_logs"
    logs.mkdir(parents=True, exist_ok=True)
    stdout = (logs / f"{service}.stdout.log").open("ab")
    stderr = (logs / f"{service}.stderr.log").open("ab")
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        close_fds=True,
    )
    stdout.close()
    stderr.close()
    state = read_state()
    state.setdefault("services", {})[service] = {"pid": process.pid, "mode": mode}
    state.setdefault("start_events", []).append(service)
    write_state(state)
    wait_listener(int(os.environ[f"R1E_PORT_{service.upper()}"]))


def main() -> int:
    python = str(Path(os.environ.get("RANDLE_PYTHON_EXE") or sys.executable).resolve())
    dummy = str(HELPERS / "harness_service.py")
    wrapper = str(ROOT / "command_center_service_launcher.py")

    launch("executor", [python, dummy, "--service", "executor"], "GOVERNED_DIRECT")
    state = read_state()
    if state.get("orders") or any(abs(float(value or 0)) > 0 for value in state.get("positions", {}).values()):
        state.setdefault("startup_blocks", []).append("executor_live_exposure")
        write_state(state)
        return 23

    launch("entry_agent", [python, wrapper, "--service", "entry_agent"], "GOVERNED_WRAPPED_CANONICAL")
    launch("trade_manager", [python, wrapper, "--service", "trade_manager"], "GOVERNED_WRAPPED_CANONICAL")
    launch("rithmic_listener", [python, dummy, "--service", "rithmic_listener"], "GOVERNED_DIRECT")
    launch("ngrok", [python, dummy, "--service", "ngrok"], "GOVERNED_DIRECT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
