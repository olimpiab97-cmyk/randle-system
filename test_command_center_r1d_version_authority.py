from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from command_center_service_control import CONTROL_VERSION, load_control_version


ROOT = Path(__file__).resolve().parent
MANIFEST_RELATIVE = Path("Architecture") / "Command_Center" / "command_center_governed_service_manifest.json"


def listener_pids(port: int) -> set[int]:
    completed = subprocess.run(
        ["netstat.exe", "-ano", "-p", "TCP"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    result: set[int] = set()
    for line in completed.stdout.splitlines():
        columns = line.split()
        if len(columns) >= 5 and columns[0].upper() == "TCP" and columns[1].endswith(f":{port}") and columns[3].upper() == "LISTENING":
            result.add(int(columns[4]))
    return result


class _HealthHandler(BaseHTTPRequestHandler):
    payload: dict[str, object] = {}

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps(type(self).payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class CommandCenterR1DVersionAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="cc-r1d-version-", ignore_cleanup_errors=True)
        self.temp_root = Path(self.directory.name)

    def tearDown(self) -> None:
        self._stop_external_host()
        self.directory.cleanup()

    def _fixture_root(self) -> Path:
        fixture = self.temp_root / "portable_candidate"
        manifest = json.loads((ROOT / MANIFEST_RELATIVE).read_text(encoding="utf-8"))
        for relative in manifest["runtime_deployment"]["required_paths"]:
            source = ROOT / relative
            target = fixture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return fixture

    @staticmethod
    def _manifest(root: Path) -> dict:
        return json.loads((root / MANIFEST_RELATIVE).read_text(encoding="utf-8"))

    @staticmethod
    def _write_manifest(root: Path, payload: dict) -> None:
        (root / MANIFEST_RELATIVE).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _run_operator(self, root: Path) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "RANDLE_DATA_ROOT": str(self.temp_root / "runtime_data"),
            "RANDLE_COMMAND_CENTER_NO_BROWSER": "1",
            "RANDLE_COMMAND_CENTER_NO_PAUSE": "1",
            "RANDLE_PYTHON_EXE": sys.executable,
        }
        return subprocess.run(
            [os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe"), "/d", "/c", str(root / "open_command_center.cmd")],
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=25,
            check=False,
        )

    @staticmethod
    def _health() -> dict:
        with urllib.request.urlopen("http://127.0.0.1:7100/health", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _stop_external_host() -> None:
        for pid in listener_pids(7100):
            if pid == os.getpid():
                continue
            handle = ctypes.windll.kernel32.OpenProcess(0x0001 | 0x00100000, False, int(pid))
            if handle:
                try:
                    ctypes.windll.kernel32.TerminateProcess(handle, 0)
                    ctypes.windll.kernel32.WaitForSingleObject(handle, 5000)
                finally:
                    ctypes.windll.kernel32.CloseHandle(handle)
        deadline = time.time() + 5
        while time.time() < deadline and any(pid != os.getpid() for pid in listener_pids(7100)):
            time.sleep(0.05)

    def _fake_host(self, payload: dict[str, object]) -> tuple[HTTPServer, threading.Thread]:
        if listener_pids(7100):
            self.fail("port 7100 must be free for isolated version-handshake test")
        _HealthHandler.payload = dict(payload)
        server = HTTPServer(("127.0.0.1", 7100), _HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def test_exact_r1c_launcher_backend_drift_is_reproduced(self) -> None:
        backend = 'CONTROL_VERSION = "command_center_service_controls_r1c"'
        launcher = '$expectedVersion = "command_center_service_controls_r1a"'
        self.assertNotEqual(backend.rsplit('"', 2)[1], launcher.rsplit('"', 2)[1])

    def test_current_version_literal_has_one_production_authority(self) -> None:
        value = self._manifest(ROOT)["control_version"]
        runtime_sources = [
            ROOT / "command_center_service_control.py",
            ROOT / "command_center_host.py",
            ROOT / "open_command_center.cmd",
            ROOT / "open_command_center.ps1",
            ROOT / MANIFEST_RELATIVE,
        ]
        occurrences = sum(path.read_text(encoding="utf-8-sig").count(value) for path in runtime_sources)
        self.assertEqual(occurrences, 1)
        self.assertIn(value, (ROOT / MANIFEST_RELATIVE).read_text(encoding="utf-8"))

    def test_python_backend_consumes_manifest_version(self) -> None:
        expected = self._manifest(ROOT)["control_version"]
        self.assertEqual(CONTROL_VERSION, expected)
        self.assertEqual(load_control_version(ROOT), expected)

    def test_powershell_consumes_manifest_without_version_fallback(self) -> None:
        source = (ROOT / "open_command_center.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Resolve-CommandCenterControlVersion", source)
        self.assertIn("$controlAuthorityPath", source)
        self.assertNotIn('$expectedVersion = "command_center_service_controls_', source)

    def test_version_n_to_n_plus_one_requires_only_authority_edit(self) -> None:
        if listener_pids(7100):
            self.fail("port 7100 must be free for isolated upgrade test")
        fixture = self._fixture_root()
        manifest = self._manifest(fixture)
        powershell_sha = __import__("hashlib").sha256((fixture / "open_command_center.ps1").read_bytes()).hexdigest()
        manifest["control_version"] = "command_center_service_controls_r90"
        self._write_manifest(fixture, manifest)
        self.assertEqual(load_control_version(fixture), "command_center_service_controls_r90")

        first = self._run_operator(fixture)
        self.assertEqual(first.returncode, 0)
        self.assertEqual(self._health()["version"], "command_center_service_controls_r90")
        first_pids = listener_pids(7100)
        self.assertEqual(len(first_pids), 1)

        repeated = self._run_operator(fixture)
        self.assertEqual(repeated.returncode, 0)
        self.assertEqual(listener_pids(7100), first_pids)

        manifest["control_version"] = "command_center_service_controls_r91"
        self._write_manifest(fixture, manifest)
        self.assertEqual(load_control_version(fixture), "command_center_service_controls_r91")
        stale = self._run_operator(fixture)
        self.assertNotEqual(stale.returncode, 0)
        self.assertEqual(listener_pids(7100), first_pids)
        self.assertEqual(__import__("hashlib").sha256((fixture / "open_command_center.ps1").read_bytes()).hexdigest(), powershell_sha)

        self._stop_external_host()
        upgraded = self._run_operator(fixture)
        self.assertEqual(upgraded.returncode, 0)
        self.assertEqual(self._health()["version"], "command_center_service_controls_r91")
        self.assertEqual(len(listener_pids(7100)), 1)

    def test_missing_canonical_authority_fails_closed(self) -> None:
        fixture = self._fixture_root()
        (fixture / MANIFEST_RELATIVE).unlink()
        with self.assertRaisesRegex(ValueError, "control_version_authority_unresolved"):
            load_control_version(fixture)

    def test_malformed_canonical_authority_fails_closed(self) -> None:
        fixture = self._fixture_root()
        (fixture / MANIFEST_RELATIVE).write_text("{not-json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "control_version_authority_unresolved"):
            load_control_version(fixture)

    def test_invalid_canonical_version_fails_closed(self) -> None:
        fixture = self._fixture_root()
        manifest = self._manifest(fixture)
        manifest["control_version"] = "not a governed version"
        self._write_manifest(fixture, manifest)
        with self.assertRaisesRegex(ValueError, "control_version_authority_invalid"):
            load_control_version(fixture)

    def test_host_missing_version_is_rejected(self) -> None:
        server, thread = self._fake_host({"ok": True, "service": "command_center_host", "repository_root": str(ROOT)})
        try:
            completed = self._run_operator(ROOT)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(listener_pids(7100), {os.getpid()})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_wrong_host_version_is_rejected_without_replacement(self) -> None:
        server, thread = self._fake_host({"ok": True, "service": "command_center_host", "version": "command_center_service_controls_r99", "repository_root": str(ROOT)})
        try:
            completed = self._run_operator(ROOT)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(listener_pids(7100), {os.getpid()})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_generation_source_mismatch_fails_closed(self) -> None:
        fixture = self._fixture_root()
        with (fixture / "command_center_host.py").open("ab") as handle:
            handle.write(b"\n# mismatched generation\n")
        with self.assertRaisesRegex(ValueError, "control_generation_source_mismatch"):
            load_control_version(fixture)

    def test_deployment_missing_version_artifact_fails_authority(self) -> None:
        fixture = self._fixture_root()
        manifest = self._manifest(fixture)
        authority = str(MANIFEST_RELATIVE).replace("\\", "/")
        manifest["runtime_deployment"]["required_paths"].remove(authority)
        manifest["runtime_deployment"]["rollback_required_paths"].remove(authority)
        self._write_manifest(fixture, manifest)
        with self.assertRaisesRegex(ValueError, "control_runtime_deployment_authority_invalid"):
            load_control_version(fixture)

    def test_rollback_missing_version_artifact_fails_authority(self) -> None:
        fixture = self._fixture_root()
        manifest = self._manifest(fixture)
        authority = str(MANIFEST_RELATIVE).replace("\\", "/")
        manifest["runtime_deployment"]["rollback_required_paths"].remove(authority)
        self._write_manifest(fixture, manifest)
        with self.assertRaisesRegex(ValueError, "control_runtime_deployment_authority_invalid"):
            load_control_version(fixture)

    def test_portable_candidate_root_has_no_machine_specific_authority(self) -> None:
        fixture = self._fixture_root()
        self.assertNotEqual(fixture, ROOT)
        self.assertEqual(load_control_version(fixture), CONTROL_VERSION)
        production_sources = "\n".join((fixture / name).read_text(encoding="utf-8-sig") for name in ("command_center_service_control.py", "open_command_center.ps1"))
        self.assertNotIn(r"C:\Users\Trader\AppData\Local\Temp", production_sources)

    def test_cmd_preserves_powershell_failure_exit_code(self) -> None:
        source = (ROOT / "open_command_center.cmd").read_text(encoding="utf-8-sig")
        self.assertIn('set "RANDLE_COMMAND_CENTER_EXIT=%ERRORLEVEL%"', source)
        self.assertIn("exit /b %RANDLE_COMMAND_CENTER_EXIT%", source)

    def test_runtime_deployment_and_rollback_sets_are_identical(self) -> None:
        manifest = self._manifest(ROOT)
        required = set(manifest["runtime_deployment"]["required_paths"])
        rollback = set(manifest["runtime_deployment"]["rollback_required_paths"])
        self.assertEqual(required, rollback)
        self.assertIn(str(MANIFEST_RELATIVE).replace("\\", "/"), required)


if __name__ == "__main__":
    unittest.main()
