# RandleSystem

Local trading-system workspace for the Randle Command Center, Trade Manager, Entry Agent, replay/audit tooling, tests, and supporting scripts.

## GitHub Backup And Remote Restore

This repository is intended to store source code, tests, docs, UI files, scripts, config templates, and replay audit tooling. It intentionally excludes runtime state, generated logs, broker credentials, Rithmic runtime files, local tunnel URLs, databases, caches, and dependency folders.

## Clone On Another Computer

```powershell
git clone git@github.com:YOUR_GITHUB_USER/randle-system.git
cd randle-system
```

If you use HTTPS instead of SSH:

```powershell
git clone https://github.com/YOUR_GITHUB_USER/randle-system.git
cd randle-system
```

## Restore Dependencies

Python dependencies are currently not pinned in a root `requirements.txt`. Create a local virtual environment and install the packages used by the app and tests for that machine.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

The `tv-panel` frontend has its own Node package metadata:

```powershell
cd tv-panel
npm install
cd ..
```

## Local Files To Recreate Manually

These files and folders are intentionally not committed and must be recreated locally on each machine as needed:

- `.env` or machine-specific environment variables.
- Rithmic credentials: `RITHMIC_USER`, `RITHMIC_PASSWORD`, connection points, account identifiers, certificates, and any broker login files.
- Local Rithmic API/runtime folders and downloaded SDK files.
- Local ngrok or public tunnel URLs, including webhook URLs.
- Runtime state: `Data/executor_state.json`, `Data/persistence_state.json`, `EntryAgent/entry_agent_state.json`.
- Runtime market snapshots: `Data/rithmic_atr_snapshot.json`, `Data/rithmic_recent_bars.json`, feed-health snapshots, TradingView context snapshots, and Entry Agent level/context JSON.
- Databases such as `randle.db` and `trade_manager.db`.
- Logs, reset backups, temporary files, and generated caches.

## Keep Secrets Out Of GitHub

- Do not commit `.env`, credentials, broker passwords, account identifiers, certificates, Rithmic runtime configs, ngrok URLs, databases, logs, or state snapshots.
- Before every push, run:

```powershell
git status --short
git diff --cached --name-only
git grep -n -i "password\|secret\|token\|api_key\|apikey\|ngrok\|RITHMIC_PASSWORD" -- .
```

- If a secret is ever committed, treat it as compromised: rotate the credential, remove it from history, and force-push only after confirming the private repo is clean.

