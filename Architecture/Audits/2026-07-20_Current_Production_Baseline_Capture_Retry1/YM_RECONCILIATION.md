# YM Patch Reconciliation

Patch SHA-256: `0620D97E8A37A182D410273D9955859B53F6E8810F3BA20A50539D11136A6854`

All 20 hunks are recorded as `ALREADY PRESENT IN CURRENT DISK`. The patch was not applied, reversed, removed, or edited.

| Hunk | Path | Header | Classification |
| --- | --- | --- | --- |
| 1 | EntryAgent/entry_agent.py | @@ -1810,6 +1810,16 @@ def validate_session_liquidity_lock( | ALREADY PRESENT IN CURRENT DISK |
| 2 | EntryAgent/entry_agent.py | @@ -1819,6 +1829,9 @@ def build_session_locked_tv_context(tv_context: dict[str, Any] \| None) -> dict[s | ALREADY PRESENT IN CURRENT DISK |
| 3 | EntryAgent/entry_agent.py | @@ -1838,6 +1851,7 @@ def build_session_locked_tv_context(tv_context: dict[str, Any] \| None) -> dict[s | ALREADY PRESENT IN CURRENT DISK |
| 4 | EntryAgent/entry_agent.py | @@ -1847,6 +1861,8 @@ def build_session_locked_tv_context(tv_context: dict[str, Any] \| None) -> dict[s | ALREADY PRESENT IN CURRENT DISK |
| 5 | EntryAgent/entry_agent.py | @@ -1876,6 +1892,8 @@ def locked_session_liquidity_context(persisted_state: dict[str, Any], symbol: st | ALREADY PRESENT IN CURRENT DISK |
| 6 | EntryAgent/tv_context_server.py | @@ -16,7 +16,7 @@ import shutil | ALREADY PRESENT IN CURRENT DISK |
| 7 | EntryAgent/tv_context_server.py | @@ -79,6 +79,10 @@ SYMBOL_ALIASES = { | ALREADY PRESENT IN CURRENT DISK |
| 8 | EntryAgent/tv_context_server.py | @@ -391,6 +395,113 @@ def _rebuild_frozen_lock_from_latest_tv( | ALREADY PRESENT IN CURRENT DISK |
| 9 | EntryAgent/tv_context_server.py | @@ -504,13 +615,12 @@ def should_replace_stale_locked_liquidity_context( | ALREADY PRESENT IN CURRENT DISK |
| 10 | EntryAgent/tv_context_server.py | @@ -523,9 +633,6 @@ def should_replace_stale_locked_liquidity_context( | ALREADY PRESENT IN CURRENT DISK |
| 11 | EntryAgent/tv_context_server.py | @@ -535,11 +642,9 @@ def should_replace_stale_locked_liquidity_context( | ALREADY PRESENT IN CURRENT DISK |
| 12 | EntryAgent/tv_context_server.py | @@ -1104,6 +1209,15 @@ def has_valid_taylor_context(context: dict[str, Any]) -> bool: | ALREADY PRESENT IN CURRENT DISK |
| 13 | EntryAgent/tv_context_server.py | @@ -1112,20 +1226,28 @@ def locked_liquidity_context(context: dict[str, Any] \| None) -> dict[str, Any] \| | ALREADY PRESENT IN CURRENT DISK |
| 14 | EntryAgent/tv_context_server.py | @@ -1161,6 +1283,8 @@ def public_market_context(context: dict[str, Any] \| None) -> dict[str, Any] \| No | ALREADY PRESENT IN CURRENT DISK |
| 15 | EntryAgent/tv_context_server.py | @@ -1168,6 +1292,8 @@ def public_market_context(context: dict[str, Any] \| None) -> dict[str, Any] \| No | ALREADY PRESENT IN CURRENT DISK |
| 16 | EntryAgent/tv_context_server.py | @@ -1228,6 +1354,9 @@ def merge_session_liquidity_context(existing_context: dict[str, Any] \| None, inc | ALREADY PRESENT IN CURRENT DISK |
| 17 | EntryAgent/tv_context_server.py | @@ -1252,6 +1381,11 @@ def merge_session_liquidity_context(existing_context: dict[str, Any] \| None, inc | ALREADY PRESENT IN CURRENT DISK |
| 18 | EntryAgent/tv_context_server.py | @@ -1303,12 +1437,17 @@ def merge_session_liquidity_context(existing_context: dict[str, Any] \| None, inc | ALREADY PRESENT IN CURRENT DISK |
| 19 | EntryAgent/tv_context_server.py | @@ -2241,6 +2380,214 @@ def entry_reasoning_log() -> tuple[Any, int]: | ALREADY PRESENT IN CURRENT DISK |
| 20 | test_entry_agent_canonical_lock_reconstruction.py | @@ -0,0 +1,306 @@ | ALREADY PRESENT IN CURRENT DISK |
