from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
RESOLVER = ROOT / "resolve_python_runtime.ps1"


def ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_ps(script: str, *, env: dict[str, str] | None = None, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    return subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=ROOT,
        env=process_env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def contract_ps() -> str:
    return "[pscustomobject]@{Major=3;Minor=12;ArchitectureBits=64;RequiredModules=@('command_center_service_control');ConfigurationVariable='RANDLE_PYTHON_EXE';LauncherName='py.exe'}"


def listener_pids(port: int) -> set[int]:
    completed = subprocess.run(
        ["netstat.exe", "-ano", "-p", "TCP"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    pids: set[int] = set()
    for line in completed.stdout.splitlines():
        columns = line.split()
        if len(columns) >= 5 and columns[0].upper() == "TCP" and columns[1].endswith(f":{port}") and columns[3].upper() == "LISTENING":
            pids.add(int(columns[4]))
    return pids


class CommandCenterR1BPythonResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="cc-r1b-python-", ignore_cleanup_errors=True)
        self.temp_root = Path(self.directory.name)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def candidate(self, relative: str) -> Path:
        path = self.temp_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"MZ-r1b-governed-test")
        return path

    def select(self, paths: list[Path], probe_body: str) -> subprocess.CompletedProcess[str]:
        candidates = ",".join(ps_quote(path) for path in paths)
        script = (
            f". {ps_quote(RESOLVER)}; "
            f"$contract={contract_ps()}; "
            f"$probe={{param($Path,$Root,$Contract) {probe_body}}}; "
            f"try{{$result=Select-RandleValidatedPythonCandidate -CandidatePaths @({candidates}) -RepositoryRoot {ps_quote(ROOT)} -Contract $contract -ProbeScript $probe; "
            "$payload=[pscustomobject]@{ok=$true;result=$result;type=$result.GetType().FullName}}"
            "catch{$payload=[pscustomobject]@{ok=$false;error=$_.Exception.Message}}; $payload|ConvertTo-Json -Compress"
        )
        return run_ps(script)

    @staticmethod
    def payload(completed: subprocess.CompletedProcess[str]) -> dict:
        if completed.returncode != 0:
            raise AssertionError(f"PowerShell failed: {completed.stdout}\n{completed.stderr}")
        return json.loads(completed.stdout.strip().splitlines()[-1])

    def test_original_two_python_collection_defect_is_replaced_by_scalar_resolution(self):
        good = self.candidate("real/python.exe")
        alias = self.candidate("Microsoft/WindowsApps/python.exe")
        completed = self.select(
            [good, alias],
            "[pscustomobject]@{Ok=$true;Path=[string]$Path;Reason='pass'}",
        )
        payload = self.payload(completed)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["type"], "System.String")
        self.assertEqual(Path(payload["result"]), good)

    def test_validated_unique_candidate_is_selected(self):
        good = self.candidate("governed/python.exe")
        payload = self.payload(self.select([good], "[pscustomobject]@{Ok=$true;Path=[string]$Path;Reason='pass'}"))
        self.assertTrue(payload["ok"])
        self.assertEqual(Path(payload["result"]), good)

    def test_two_fully_valid_candidates_fail_closed(self):
        first = self.candidate("first/python.exe")
        second = self.candidate("second/python.exe")
        payload = self.payload(self.select([first, second], "[pscustomobject]@{Ok=$true;Path=[string]$Path;Reason='pass'}"))
        self.assertFalse(payload["ok"])
        self.assertIn("validated_candidate_count=2", payload["error"])

    def test_store_alias_and_real_python_selects_real(self):
        real = self.candidate("real/python.exe")
        alias = self.candidate("Microsoft/WindowsApps/python.exe")
        payload = self.payload(self.select([alias, real], "[pscustomobject]@{Ok=$true;Path=[string]$Path;Reason='pass'}"))
        self.assertTrue(payload["ok"])
        self.assertEqual(Path(payload["result"]), real)

    def test_no_python_fails_closed(self):
        payload = self.payload(self.select([], "[pscustomobject]@{Ok=$true;Path=[string]$Path;Reason='pass'}"))
        self.assertFalse(payload["ok"])
        self.assertIn("validated_candidate_count=0", payload["error"])

    def test_wrong_version_is_rejected(self):
        wrong = self.candidate("python311/python.exe")
        payload = self.payload(self.select([wrong], "[pscustomobject]@{Ok=$false;Path=[string]$Path;Reason='unsupported_python_version'}"))
        self.assertFalse(payload["ok"])

    def test_missing_required_module_is_rejected(self):
        missing = self.candidate("missing-module/python.exe")
        payload = self.payload(self.select([missing], "[pscustomobject]@{Ok=$false;Path=[string]$Path;Reason='required_module_or_runtime_probe_failed'}"))
        self.assertFalse(payload["ok"])

    def test_duplicate_same_physical_path_is_deduplicated(self):
        good = self.candidate("same/python.exe")
        payload = self.payload(self.select([good, good, good], "[pscustomobject]@{Ok=$true;Path=[string]$Path;Reason='pass'}"))
        self.assertTrue(payload["ok"])
        self.assertEqual(Path(payload["result"]), good)

    def test_space_in_path_is_preserved_as_one_scalar(self):
        good = self.candidate("Python Runtime With Spaces/python.exe")
        payload = self.payload(self.select([good], "[pscustomobject]@{Ok=$true;Path=[string]$Path;Reason='pass'}"))
        self.assertTrue(payload["ok"])
        self.assertEqual(Path(payload["result"]), good)
        self.assertEqual(payload["type"], "System.String")

    def test_live_machine_multi_python_resolution_returns_governed_scalar(self):
        script = (
            f". {ps_quote(RESOLVER)}; "
            f"$commands=@(Get-Command python.exe -All -CommandType Application); "
            f"$result=Resolve-RandlePythonExecutable -RepositoryRoot {ps_quote(ROOT)}; "
            "[pscustomobject]@{count=$commands.Count;result=$result;type=$result.GetType().FullName}|ConvertTo-Json -Compress"
        )
        payload = self.payload(run_ps(script))
        self.assertGreaterEqual(payload["count"], 2)
        self.assertEqual(payload["type"], "System.String")
        self.assertNotIn("\\Microsoft\\WindowsApps\\", payload["result"])

    def test_shared_resolver_governs_host_and_service_launcher(self):
        opener = (ROOT / "open_command_center.ps1").read_text(encoding="utf-8-sig")
        launcher = (ROOT / "launch_all.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Resolve-RandlePythonExecutable", opener)
        self.assertIn("Resolve-RandlePythonExecutable", launcher)
        self.assertNotIn("Select-Object -First 1", opener)
        self.assertNotIn("Select-Object -First 1", RESOLVER.read_text(encoding="utf-8-sig"))
        self.assertNotIn("Get-Command python.exe -ErrorAction Stop).Source", launcher)

    def test_duplicate_path_key_casing_is_normalized_before_start_process(self):
        script = (
            f". {ps_quote(RESOLVER)}; "
            "$before=@([Environment]::GetEnvironmentVariables('Process').Keys|Where-Object{[string]$_ -ieq 'Path'}).Count; "
            "$result=Repair-RandleProcessEnvironmentKeyCasing; "
            "$after=@([Environment]::GetEnvironmentVariables('Process').Keys|Where-Object{[string]$_ -ieq 'Path'}).Count; "
            "[pscustomobject]@{ok=$result.Ok;before=$before;after=$after}|ConvertTo-Json -Compress"
        )
        payload = self.payload(run_ps(script))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["after"], 1)

    def test_actual_cmd_powershell_python_entry_and_repeat_are_idempotent(self):
        if listener_pids(7100):
            self.skipTest("port 7100 already has a listener")
        runtime = self.temp_root / "runtime"
        env = {
            "RANDLE_DATA_ROOT": str(runtime),
            "RANDLE_COMMAND_CENTER_NO_BROWSER": "1",
        }
        cmd = ROOT / "open_command_center.cmd"
        host_pid: int | None = None
        try:
            first = subprocess.run(
                [os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe"), "/d", "/c", str(cmd)],
                cwd=ROOT,
                env={**os.environ, **env},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
            self.assertEqual(first.returncode, 0)
            with urllib.request.urlopen("http://127.0.0.1:7100/health", timeout=5) as response:
                health = json.loads(response.read().decode("utf-8"))
            self.assertTrue(health["ok"])
            self.assertEqual(Path(health["repository_root"]), ROOT)
            pids = listener_pids(7100)
            self.assertEqual(len(pids), 1)
            host_pid = next(iter(pids))

            second = subprocess.run(
                [os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe"), "/d", "/c", str(cmd)],
                cwd=ROOT,
                env={**os.environ, **env},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
            self.assertEqual(second.returncode, 0)
            self.assertEqual(listener_pids(7100), {host_pid})
        finally:
            if host_pid is not None:
                subprocess.run(
                    ["taskkill.exe", "/PID", str(host_pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
                deadline = time.time() + 5
                while time.time() < deadline:
                    if not listener_pids(7100):
                        break
                    time.sleep(0.1)
                time.sleep(0.75)


if __name__ == "__main__":
    unittest.main()
