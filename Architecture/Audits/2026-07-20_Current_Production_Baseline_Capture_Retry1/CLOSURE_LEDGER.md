# Current Production Baseline Closure Ledger

The fresh closure revalidation found **16 runtime modules**, **23 local import edges**, **35 verification tests**, **174 fixtures**, and **6 test-support files**. The total governed snapshot contains **234 paths**.

The authoritative listener is root-level `rithmic_live_listener.py`. `EntryAgent/rithmic_live_listener.py` does not exist and was not invented.

## Local import edges

| Parent | Target | Import | Line |
| --- | --- | --- | --- |
| EntryAgent/entry_agent.py | EntryAgent/blueprint_rules.py | blueprint_rules | 28 |
| EntryAgent/entry_agent.py | EntryAgent/gateway_engine.py | gateway_engine | 36 |
| EntryAgent/entry_agent.py | EntryAgent/levels.py | levels | 37 |
| EntryAgent/entry_agent.py | EntryAgent/liquidity_stack_validation.py | liquidity_stack_validation | 38 |
| EntryAgent/entry_agent.py | EntryAgent/market_feed.py | market_feed | 45 |
| EntryAgent/entry_agent.py | EntryAgent/step25_engine.py | step25_engine | 46 |
| EntryAgent/entry_agent.py | EntryAgent/step3_engine.py | step3_engine | 47 |
| EntryAgent/entry_agent.py | EntryAgent/step4_engine.py | step4_engine | 48 |
| EntryAgent/entry_agent.py | EntryAgent/step5_engine.py | step5_engine | 49 |
| EntryAgent/entry_agent.py | EntryAgent/step6_engine.py | step6_engine | 50 |
| EntryAgent/entry_agent.py | data_paths.py | data_paths | 26 |
| EntryAgent/market_feed.py | data_paths.py | data_paths | 19 |
| EntryAgent/step3_engine.py | EntryAgent/step7_engine.py | step7_engine | 7 |
| EntryAgent/step4_engine.py | EntryAgent/step7_engine.py | step7_engine | 8 |
| EntryAgent/step5_engine.py | EntryAgent/step6_engine.py | step6_engine | 8 |
| EntryAgent/step5_engine.py | EntryAgent/step7_engine.py | step7_engine | 9 |
| EntryAgent/step6_engine.py | EntryAgent/step7_engine.py | step7_engine | 8 |
| EntryAgent/tv_context_server.py | EntryAgent/entry_agent.py | entry_agent | 42 |
| EntryAgent/tv_context_server.py | EntryAgent/liquidity_stack_validation.py | liquidity_stack_validation | 35 |
| EntryAgent/tv_context_server.py | data_paths.py | data_paths | 34 |
| rithmic_live_listener.py | data_paths.py | data_paths | 23 |
| rithmic_live_listener.py | symbol_resolution.py | symbol_resolution | 31 |
| symbol_resolution.py | data_paths.py | data_paths | 5 |
