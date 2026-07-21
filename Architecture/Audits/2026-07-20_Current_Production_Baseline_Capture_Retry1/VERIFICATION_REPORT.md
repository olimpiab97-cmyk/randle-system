# Isolated Verification Report

The full captured test scope was executed from the isolated candidate. Every pytest file was passed to pytest; no direct-execution zero-collection result is reported as a pass.

Broad pytest result: **571 passed, 179 failed, 3 skipped**. Failures were preserved without modifying source or tests.

| # | Command group | Kind | Exit | Passed | Failed | Skipped |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | compile_runtime_closure | static | 0 | — | — | — |
| 2 | import_and_route_construction | static | 0 | — | — | — |
| 3 | powershell_ast_launch_all | static | 0 | — | — | — |
| 4 | gateway_direct | direct | 0 | — | — | — |
| 5 | market_feed_direct | direct | 1 | — | — | — |
| 6 | step_2_1a_direct | direct | 1 | — | — | — |
| 7 | step_2_live_fixture_pytest | pytest | 1 | 4 | 5 | 0 |
| 8 | step_2_5_direct | direct | 1 | — | — | — |
| 9 | step_3_direct | direct | 0 | — | — | — |
| 10 | step_4_direct | direct | 0 | — | — | — |
| 11 | step_5_direct | direct | 0 | — | — | — |
| 12 | step_6_direct | direct | 0 | — | — | — |
| 13 | step_7_direct | direct | 0 | — | — | — |
| 14 | session_runtime_direct | direct | 0 | — | — | — |
| 15 | context_lock_stack_pytest | pytest | 1 | 87 | 8 | 0 |
| 16 | listener_atr_candle_pytest | pytest | 1 | 108 | 16 | 0 |
| 17 | startup_integration_pytest | pytest | 1 | 22 | 1 | 0 |
| 18 | broad_captured_entry_agent_pytest | pytest | 1 | 571 | 179 | 3 |

## Nonpassing groups

- `market_feed_direct`: captured assertion/exception failure from legacy direct test execution. The durable log preserves the direct-script traceback/output.
- `step_2_1a_direct`: captured assertion/exception failure from legacy direct test execution. The durable log preserves the direct-script traceback/output.
- `step_2_live_fixture_pytest`: captured pytest assertion failures; no source or test repair performed. Groups: `EntryAgent/test_step2_live_fixture_sync.py` (5: entry lifecycle engine or verification expectation divergence).
- `step_2_5_direct`: captured assertion/exception failure from legacy direct test execution. The durable log preserves the direct-script traceback/output.
- `context_lock_stack_pytest`: captured pytest assertion failures; no source or test repair performed. Groups: `test_nq_20260716_regressions.py` (5: canonical context, liquidity, or status-projection contract divergence), `test_preopen_ladder_projection.py` (2: canonical context, liquidity, or status-projection contract divergence), `test_ym_high1_reference_price_contract.py` (1: canonical context, liquidity, or status-projection contract divergence).
- `listener_atr_candle_pytest`: captured pytest assertion failures; no source or test repair performed. Groups: `test_atr_authority.py` (5: listener / ATR / candle-transport contract divergence), `test_atr_live_projection.py` (7: listener / ATR / candle-transport contract divergence), `test_rithmic_live_listener.py` (1: listener / ATR / candle-transport contract divergence), `test_step6_intrabar_transport.py` (3: listener / ATR / candle-transport contract divergence).
- `startup_integration_pytest`: captured pytest assertion failures; no source or test repair performed. Groups: `test_launch_all_path_authority.py` (1: startup and readiness contract divergence).
- `broad_captured_entry_agent_pytest`: captured pytest assertion failures; no source or test repair performed. Groups: `EntryAgent/market_feed_tests.py` (1: entry lifecycle engine or verification expectation divergence), `EntryAgent/session_runtime_tests.py` (7: entry lifecycle engine or verification expectation divergence), `EntryAgent/step_2_5_replay_tests.py` (7: replay, fixture, or isolated-data expectation divergence), `EntryAgent/step_4_replay_tests.py` (2: replay, fixture, or isolated-data expectation divergence), `EntryAgent/test_step2_live_fixture_sync.py` (5: entry lifecycle engine or verification expectation divergence), `test_atr_authority.py` (5: listener / ATR / candle-transport contract divergence), `test_atr_live_projection.py` (7: listener / ATR / candle-transport contract divergence), `test_data_root_paths.py` (4: replay, fixture, or isolated-data expectation divergence), `test_entry_agent_audit_logging.py` (2: replay, fixture, or isolated-data expectation divergence), `test_entry_agent_demo_harness.py` (4: replay, fixture, or isolated-data expectation divergence), `test_entry_agent_dry_run_injector.py` (4: entry lifecycle engine or verification expectation divergence), `test_entry_agent_intrabar_plumbing.py` (1: listener / ATR / candle-transport contract divergence), `test_entry_replay_audit_regressions.py` (4: replay, fixture, or isolated-data expectation divergence), `test_entry_status_endpoint.py` (90: canonical context, liquidity, or status-projection contract divergence), `test_launch_all_path_authority.py` (1: startup and readiness contract divergence), `test_nq_20260716_regressions.py` (5: canonical context, liquidity, or status-projection contract divergence), `test_preopen_ladder_projection.py` (2: canonical context, liquidity, or status-projection contract divergence), `test_rithmic_live_listener.py` (1: listener / ATR / candle-transport contract divergence), `test_step6_intrabar_transport.py` (3: listener / ATR / candle-transport contract divergence), `test_ym_high1_reference_price_contract.py` (1: canonical context, liquidity, or status-projection contract divergence).
