import pathlib
import re
import unittest


SCRIPT_PATH = pathlib.Path(__file__).with_name("launch_all.ps1")


class LaunchAllPathAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_symbol_variables_cannot_alias_path_authorities(self):
        # PowerShell variable names are case-insensitive.  A bare $root would
        # therefore alias $Root; the production launcher must contain neither.
        self.assertIsNone(re.search(r"\$root\b", self.script, flags=re.IGNORECASE))
        self.assertIn("$script:repositoryRoot", self.script)
        self.assertIn("$script:runtimeDataRoot", self.script)
        self.assertIn('foreach ($symbolRoot in @("NQ", "YM"))', self.script)

        governed_names = {
            "repositoryroot",
            "runtimedataroot",
            "ngrokexecutable",
            "ngrokworkingdirectory",
        }
        loop_names = {
            match.casefold()
            for match in re.findall(r"foreach\s*\(\$(\w+)\s+in\b", self.script, flags=re.IGNORECASE)
        }
        self.assertTrue(governed_names.isdisjoint(loop_names))

        assignments = [
            match.casefold()
            for match in re.findall(
                r"(?m)^\s*\$(?:script:)?([A-Za-z_]\w*)\s*=",
                self.script,
            )
        ]
        self.assertEqual(assignments.count("repositoryroot"), 1)
        self.assertEqual(assignments.count("runtimedataroot"), 1)

    def test_ngrok_directory_is_resolved_logged_and_guarded_before_start(self):
        ensure_ngrok = self.script.split("function Ensure-Ngrok {", 1)[1].split(
            "function Get-FinalDiagnostics {", 1
        )[0]

        resolve_index = ensure_ngrok.index("$ngrokExecutable = (Resolve-Path")
        derive_index = ensure_ngrok.index(
            "$ngrokWorkingDirectory = [IO.Path]::GetDirectoryName($ngrokExecutable)"
        )
        log_index = ensure_ngrok.index("ACTION=START_RESOLVED")
        guard_index = ensure_ngrok.index(
            "Test-Path -LiteralPath $ngrokWorkingDirectory -PathType Container"
        )
        start_index = ensure_ngrok.index(
            "Start-Process -FilePath $ngrokExecutable"
        )

        self.assertLess(resolve_index, derive_index)
        self.assertLess(derive_index, log_index)
        self.assertLess(log_index, guard_index)
        self.assertLess(guard_index, start_index)
        self.assertIn("invalid_working_directory", ensure_ngrok)
        self.assertIn("[IO.Path]::IsPathRooted", ensure_ngrok)
        self.assertIn('$ngrokWorkingDirectory -in @("NQ", "YM")', ensure_ngrok)
        self.assertIn('Set-ComponentResult "Ngrok" "FAILED"', ensure_ngrok)
        self.assertIn("EXECUTABLE={0}", ensure_ngrok)
        self.assertIn("WORKING_DIRECTORY={1}", ensure_ngrok)
        self.assertIn("ARGUMENTS={2}", ensure_ngrok)
        self.assertIn("LOG_PATH={3}", ensure_ngrok)
        self.assertIn("-ErrorAction Stop", ensure_ngrok)
        self.assertNotIn("[System.Diagnostics.Process]::Start", ensure_ngrok)

    def test_other_process_launches_use_the_script_scoped_repository_root(self):
        self.assertIn("WorkingDirectory = $script:repositoryRoot", self.script)
        self.assertGreaterEqual(
            self.script.count("-WorkingDirectory $script:repositoryRoot"), 2
        )
        self.assertNotIn("WorkingDirectory = $repositoryRoot", self.script)
        self.assertNotIn("-WorkingDirectory $repositoryRoot", self.script)

    def test_entry_agent_503_remains_fail_closed_with_exact_reason(self):
        probe = self.script.split("function Test-EntryAgentContract {", 1)[1].split(
            "function Test-TradingViewRelayContract {", 1
        )[0]

        self.assertIn('[int]$response.StatusCode -eq 503', probe)
        self.assertIn('$status.service_status -eq "REHYDRATING"', probe)
        self.assertIn("expected_fail_closed_rehydration", probe)
        self.assertIn("entry_agent_fail_closed_rehydrating", probe)
        self.assertIn("$status.rehydration_failures", probe)
        self.assertRegex(
            probe,
            r"return New-ProbeResult \$false \(\"entry_agent_fail_closed_rehydrating",
        )


if __name__ == "__main__":
    unittest.main()
