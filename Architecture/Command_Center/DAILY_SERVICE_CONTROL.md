# Command Center daily service control

Command Center R1 keeps the Command Center host separate from the governed
trading-service stack. The host remains available while Executor, Entry Agent,
Trade Manager, Rithmic listener, and ngrok are offline.

## Open Command Center

Double-click `open_command_center.cmd`. It starts (or reuses) the loopback-only
Command Center host and opens `http://127.0.0.1:7100`. No PowerShell command has
to be typed. Do not open `command_center.html` directly when service controls
are needed; direct-file mode intentionally disables them.

### Python runtime authority

The operator launcher and the canonical service launcher share
`resolve_python_runtime.ps1`. The resolver requires Python 3.12 x64 and proves
the Command Center, Flask/CORS, requests, and Werkzeug imports before starting
anything. Its fixed hierarchy is:

1. an explicitly configured `RANDLE_PYTHON_EXE`, when present and valid;
2. the unique validated interpreter resolved by `py.exe -3.12`;
3. exactly one validated, normalized `python.exe` application candidate.

WindowsApps execution aliases, zero-byte files, and reparse aliases are
rejected. Duplicate references to the same physical path are deduplicated. If
zero or multiple fully valid interpreters remain, launch fails closed with
**COMMAND CENTER NOT STARTED — PYTHON RUNTIME AUTHORITY UNRESOLVED**. PATH order
is never used to break interpreter ambiguity.

## Morning

1. Open Command Center.
2. Press **START SYSTEM** once. No service starts.
3. Confirm the button reads **PUSH AGAIN TO CONFIRM START**.
4. Press it again within five seconds.
5. Wait for **SYSTEM READY**. Before 06:15, the truthful status may be
   **SYSTEM SERVICES READY — WAITING FOR 06:15 TV LADDER**.
6. Before trading, verify every governed service is ready and TV Ladder reads
   **READY** for the current session.

If the stack is already ready, START is idempotent and reports **SYSTEM ALREADY
READY**. Duplicate, foreign, unknown, or unhealthy partial runtimes fail closed
with the affected service shown.

R1A separates process trust from readiness. An exact governed wrapper whose
dependency is unavailable is shown as **TRUSTED / NOT READY**, not as a foreign
process. If Executor is trusted but stopped, START may bring it up without first
calling its unavailable orders/positions APIs. Before opening the Executor
listener, the launcher proves that the exact source-derived persisted Executor
store has no working order or nonzero position and that Trade Manager has no
pending/orphan action. It then starts Executor, replaces the persisted
corroboration with live orders/positions authority, and only afterward starts
execution-capable downstream services or public ingress.

## End of day

1. Press **SHUTDOWN SYSTEM** once. Nothing stops.
2. Confirm the button reads **PUSH AGAIN TO CONFIRM SHUTDOWN**.
3. Press it again within five seconds.
4. Command Center reads Executor orders and positions plus Trade Manager
   executable/pending state.
5. Only a zero-order, zero-position, zero-pending state proceeds to the fixed
   shutdown order: ngrok, Rithmic listener, Trade Manager, Entry Agent,
   Executor.
6. Wait for **SYSTEM OFFLINE**. Command Center remains open and can start the
   stack on the next session.

## If shutdown is blocked

**SHUTDOWN BLOCKED — ACTIVE TRADING STATE** means at least one active order,
nonzero position, pending executable Trade Manager action, or orphan exposure
exists. Resolve that state through the governed trading workflow. Do not kill
processes manually and do not look for a normal-screen force-shutdown control;
R1 intentionally provides none.

If safety state cannot be read, shutdown also fails closed.

Specifically, an unavailable Executor exposure API displays **SHUTDOWN BLOCKED
— TRADING STATE UNAVAILABLE**. Persisted counts can guard a START while Trade
Manager is stopped, but never substitute for live authority at SHUTDOWN.

## Governed process identity

Entry Agent and Trade Manager launch through the tracked
`command_center_service_launcher.py` execution envelope. It fixes the repository
source, working directory, safe operating mode, and the production runtime,
spool, and Entry persistence roots, and proves write/read/delete authority before
loading the service in the same process. Exact R5C cutover wrappers are accepted
only as pinned transitional identities so an already accepted runtime is not
misclassified. Their temporary paths are not canonical launch authority.

Shutdown owns the authenticated wrapper root PID and its descendants. It never
accepts a PID or executable path from the browser.

## Manual fallback

If the Command Center host itself cannot be started, open a governed local
PowerShell session at the exact deployed repository root and run:

```powershell
.\launch_all.ps1
```

This is the existing canonical bounded launcher. It preserves healthy
instances, rejects duplicates, verifies readiness, and writes startup evidence.
There is no casual manual shutdown fallback: use the separately governed
emergency procedure if Command Center cannot safely perform shutdown.

## Security boundary

The host binds only to `127.0.0.1:7100`. Mutating endpoints require a local
same-origin browser session and an ephemeral CSRF token. No command text,
executable path, PID, service name, credential, or URL is accepted from the UI.
The public TradingView/ngrok route continues to forward only to Trade Manager
on port 7001 and cannot reach Command Center controls.
