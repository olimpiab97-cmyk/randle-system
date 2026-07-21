import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = ROOT / "Data"
ENTRY_AGENT_DIR = ROOT / "EntryAgent"


class SharedDataRootPathTests(unittest.TestCase):
    def setUp(self):
        sys.dont_write_bytecode = True
        self._original_data_root_env = os.environ.get("RANDLE_DATA_ROOT")
        self._original_local_appdata_env = os.environ.get("LOCALAPPDATA")

    def tearDown(self):
        if self._original_data_root_env is None:
            os.environ.pop("RANDLE_DATA_ROOT", None)
        else:
            os.environ["RANDLE_DATA_ROOT"] = self._original_data_root_env
        if self._original_local_appdata_env is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original_local_appdata_env

    def _load_module(self, module_name, relative_path):
        for dependency in (
            "data_paths",
            "symbol_resolution",
            "market_feed",
            "entry_agent",
            "tv_context_server",
            "replay_audit",
        ):
            sys.modules.pop(dependency, None)
        sys.modules.pop(module_name, None)
        spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _load_module_with_stdout(self, module_name, relative_path):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            module = self._load_module(module_name, relative_path)
        return module, buffer.getvalue()

    def _load_entry_agent_module_with_stdout(self, module_name, relative_path):
        buffer = io.StringIO()
        sys.path.insert(0, str(ENTRY_AGENT_DIR))
        try:
            with contextlib.redirect_stdout(buffer):
                module = self._load_module(module_name, Path("EntryAgent") / relative_path)
        finally:
            try:
                sys.path.remove(str(ENTRY_AGENT_DIR))
            except ValueError:
                pass
        return module, buffer.getvalue()

    def test_trade_manager_resolves_persistence_state_under_randle_data_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir) / "shared-data"
            os.environ["RANDLE_DATA_ROOT"] = str(data_root)
            module, output = self._load_module_with_stdout(
                "trade_manager_data_root_test",
                Path("Engines") / "trade_manager.py",
            )
            self.assertTrue(data_root.exists())

        self.assertEqual(Path(module.PERSISTENCE_FILE), data_root / "persistence_state.json")
        self.assertEqual(Path(module.EXECUTOR_STATE_FILE), data_root / "executor_state.json")
        self.assertEqual(Path(module.TRADE_MANAGEMENT_RESEARCH_FILE), data_root / "trade_management_research.jsonl")
        self.assertEqual(Path(module.TRADE_SCREENSHOT_DIR), data_root / "trade_screenshots")
        self.assertIn("DATA ROOT component=trade_manager", output)
        self.assertIn("source=env", output)

    def test_executor_resolves_runtime_files_under_randle_data_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir) / "shared-data"
            os.environ["RANDLE_DATA_ROOT"] = str(data_root)
            module, output = self._load_module_with_stdout("executor_data_root_test", "executor.py")

        self.assertEqual(module.DATA_DIR, data_root.resolve())
        self.assertEqual(module.EXECUTOR_STATE_FILE, data_root / "executor_state.json")
        self.assertEqual(module.ACCOUNT_SNAPSHOT_FILE, data_root / "paper_account_snapshot.json")
        self.assertEqual(module.RITHMIC_FEED_HEALTH_FILE, data_root / "rithmic_feed_health.json")
        self.assertEqual(data_root / "fill_audit_log.jsonl", module.DATA_DIR / "fill_audit_log.jsonl")
        self.assertIn("DATA ROOT component=executor", output)
        self.assertIn("source=env", output)

    def test_listener_resolves_runtime_files_under_randle_data_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir) / "shared-data"
            os.environ["RANDLE_DATA_ROOT"] = str(data_root)
            module, output = self._load_module_with_stdout("listener_data_root_test", "rithmic_live_listener.py")

        self.assertEqual(module.ATR_SNAPSHOT_PATH, data_root / "rithmic_atr_snapshot.json")
        self.assertEqual(module.RECENT_BARS_PATH, data_root / "rithmic_recent_bars.json")
        self.assertEqual(module.FEED_HEALTH_PATH, data_root / "rithmic_feed_health.json")
        self.assertEqual(module.ATR_SHADOW_COMPARISON_PATH, data_root / "rithmic_atr_shadow_comparison.json")
        self.assertEqual(module.TRADE_MANAGER_PERSISTENCE_PATH, data_root / "persistence_state.json")
        self.assertIn("DATA ROOT component=rithmic_live_listener", output)
        self.assertIn("source=env", output)

    def test_feed_health_data_path_falls_back_to_local_runtime_root_when_data_root_unwritable(self):
        data_paths = self._load_module("data_paths_feed_health_fallback_test", "data_paths.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir) / "shared-data"
            local_appdata = Path(tmpdir) / "localappdata"
            os.environ["RANDLE_DATA_ROOT"] = str(data_root)
            os.environ["LOCALAPPDATA"] = str(local_appdata)
            def fake_directory_is_writable(path):
                return Path(path).resolve() != data_root.resolve()

            with mock.patch.object(data_paths, "directory_is_writable", side_effect=fake_directory_is_writable):
                resolved = data_paths.feed_health_data_path()

        self.assertEqual(
            resolved,
            (local_appdata / "RandleRuntimeData" / "rithmic_feed_health.json").resolve(),
        )

    def test_default_env_unset_uses_repo_local_data_root_and_warns(self):
        os.environ.pop("RANDLE_DATA_ROOT", None)
        module, output = self._load_module_with_stdout("symbol_resolution_default_data_root_test", "symbol_resolution.py")

        self.assertEqual(module.DATA_DIR, DEFAULT_DATA_ROOT.resolve())
        self.assertEqual(module.ATR_SNAPSHOT_PATH, DEFAULT_DATA_ROOT / "rithmic_atr_snapshot.json")
        self.assertEqual(module.RECENT_BARS_PATH, DEFAULT_DATA_ROOT / "rithmic_recent_bars.json")
        self.assertIn("DATA ROOT component=symbol_resolution", output)
        self.assertIn("source=default_local", output)
        self.assertIn("DATA ROOT WARNING component=symbol_resolution using_local_default_data_root", output)

    def test_executor_has_no_absolute_repo_local_data_bypass_for_feed_health(self):
        source = (ROOT / "executor.py").read_text(encoding="utf-8")
        self.assertNotIn('path = "C:\\\\Webhook\\\\RandleSystem\\\\Data\\\\rithmic_feed_health.json"', source)
        self.assertIn("path = RITHMIC_FEED_HEALTH_FILE", source)
        self.assertIn("RITHMIC_FEED_HEALTH_FILE = feed_health_data_path()", source)

    def test_listener_uses_shared_feed_health_path_helper(self):
        source = (ROOT / "rithmic_live_listener.py").read_text(encoding="utf-8")
        self.assertIn("FEED_HEALTH_PATH = feed_health_data_path()", source)

    def test_entry_agent_resolves_runtime_paths_under_randle_data_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir) / "shared-data"
            os.environ["RANDLE_DATA_ROOT"] = str(data_root)
            module, output = self._load_entry_agent_module_with_stdout(
                "entry_agent_data_root_test",
                "entry_agent.py",
            )

        self.assertEqual(module.DATA_DIR, data_root.resolve())
        self.assertEqual(module.ENTRY_AGENT_AUDIT_DIR, data_root / "entry_agent_audit")
        self.assertEqual(module.STEP2_OWNER_DIAGNOSTICS_PATH, data_root / "entry_step2_owner_diagnostics.jsonl")
        self.assertEqual(module.RITHMIC_ATR_SNAPSHOT_PATH, data_root / "rithmic_atr_snapshot.json")
        self.assertEqual(module.PERSISTENCE_STATE_PATH, data_root / "persistence_state.json")
        self.assertEqual(module.EXECUTOR_STATE_PATH, data_root / "executor_state.json")
        self.assertEqual(module.STATE_PATH, data_root / "entry_agent" / "entry_agent_state.json")
        self.assertEqual(module.SIGNALS_PATH, data_root / "entry_agent" / "signals.json")
        self.assertEqual(module.TV_CONTEXT_PATH, data_root / "entry_agent" / "tv_context.json")
        self.assertEqual(module.TV_CONTEXT_BY_SYMBOL_PATH, data_root / "entry_agent" / "tv_context_by_symbol.json")
        self.assertIn("DATA ROOT component=entry_agent", output)
        self.assertIn("source=env", output)

    def test_entry_agent_auxiliary_modules_resolve_shared_runtime_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir) / "shared-data"
            os.environ["RANDLE_DATA_ROOT"] = str(data_root)
            market_feed, _ = self._load_entry_agent_module_with_stdout(
                "entry_agent_market_feed_data_root_test",
                "market_feed.py",
            )
            tv_server, _ = self._load_entry_agent_module_with_stdout(
                "entry_agent_tv_server_data_root_test",
                "tv_context_server.py",
            )
            replay_audit, _ = self._load_entry_agent_module_with_stdout(
                "entry_agent_replay_audit_data_root_test",
                "replay_audit.py",
            )

        self.assertEqual(market_feed.RITHMIC_BARS_PATH, data_root / "rithmic_recent_bars.json")
        self.assertEqual(market_feed.EXECUTOR_STATE_PATH, data_root / "executor_state.json")
        self.assertEqual(tv_server.TV_CONTEXT_EVENTS_PATH, data_root / "entry_agent" / "tv_context_events.jsonl")
        self.assertEqual(tv_server.ENTRY_DECISIONS_LOG_PATH, data_root / "entry_agent" / "logs" / "entry_decisions.jsonl")
        self.assertEqual(tv_server.reasoning_log_path("2026-06-15"), data_root / "entry_reasoning_2026-06-15.jsonl")
        self.assertEqual(replay_audit.DATA_DIR, data_root.resolve())
        self.assertEqual(replay_audit.TV_CONTEXT_BY_SYMBOL_PATH, data_root / "entry_agent" / "tv_context_by_symbol.json")
        self.assertEqual(replay_audit.TV_CONTEXT_EVENTS_PATH, data_root / "entry_agent" / "tv_context_events.jsonl")

    def test_entry_agent_default_env_unset_preserves_local_runtime_paths(self):
        os.environ.pop("RANDLE_DATA_ROOT", None)
        module, output = self._load_entry_agent_module_with_stdout(
            "entry_agent_default_data_root_test",
            "entry_agent.py",
        )

        self.assertEqual(module.DATA_DIR, DEFAULT_DATA_ROOT.resolve())
        self.assertEqual(module.STATE_PATH, ENTRY_AGENT_DIR / "entry_agent_state.json")
        self.assertEqual(module.SIGNALS_PATH, ENTRY_AGENT_DIR / "signals.json")
        self.assertEqual(module.TV_CONTEXT_PATH, ENTRY_AGENT_DIR / "tv_context.json")
        self.assertEqual(module.TV_CONTEXT_BY_SYMBOL_PATH, ENTRY_AGENT_DIR / "tv_context_by_symbol.json")
        self.assertEqual(module.ENTRY_AGENT_AUDIT_DIR, DEFAULT_DATA_ROOT / "entry_agent_audit")
        self.assertIn("DATA ROOT component=entry_agent", output)
        self.assertIn("source=default_local", output)


if __name__ == "__main__":
    unittest.main()
