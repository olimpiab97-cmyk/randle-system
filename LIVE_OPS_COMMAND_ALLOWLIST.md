# Live Ops Command Allowlist

## 1. Allowed Startup Commands

Startup commands must be run only from:

```text
C:\Webhook\RandleSystem
```

Mandatory first step for every Codex task:

```powershell
(Get-Location).Path
```

This must be the first and only action before the working directory check passes.

Codex must not attempt to interpret, classify, plan, summarize, investigate, or execute any user request until the output of `(Get-Location).Path` has been verified as exactly `C:\Webhook\RandleSystem`.

No other tool call, command, file read, directory listing, search, git command, test command, compile command, environment inspection, repo discovery, or planning step is allowed before this check passes.

If the output is not exactly:

```text
C:\Webhook\RandleSystem
```

Codex must stop immediately and report only:

- `workspace_guard_failed`
- actual directory
- instruction to restart Codex from `C:\Webhook\RandleSystem`

When outside the approved directory, Codex must not list directories, inspect environment variables, run git, run tests, inspect files, search for repo locations, infer a likely workspace, or run project commands. Commands like `Get-ChildItem`, `git`, `python`, `pytest`, `unittest`, and `Get-Content` are forbidden until the working directory check passes. Codex must not helpfully search for the repo when launched from the wrong directory.

Before any file inspection, project command, test, compile check, discovery command, or command using a relative path, Codex must confirm the working directory is exactly `C:\Webhook\RandleSystem` using the mandatory first step above.

Allowed startup commands:

```powershell
python .\executor.py
python .\Engines\trade_manager.py
```

Use only explicitly named project entry points. Do not start unrelated services or scripts.

## 2. Allowed Status / Debug Endpoint Checks

Allowed local status checks:

```powershell
Invoke-RestMethod http://127.0.0.1:6001/health
Invoke-RestMethod http://127.0.0.1:6001/orders
Invoke-RestMethod http://127.0.0.1:6001/positions
Invoke-RestMethod http://127.0.0.1:6001/debug/watchdog
Invoke-RestMethod http://127.0.0.1:6001/debug/watchdog_alert
Invoke-RestMethod http://127.0.0.1:6001/debug/feed_health
Invoke-RestMethod http://127.0.0.1:6001/debug/live_prices
Invoke-RestMethod http://127.0.0.1:7001/debug/watchdog
Invoke-RestMethod http://127.0.0.1:7001/debug/feed_health
```

Use local endpoints only unless explicitly approved.

## 3. Allowed Test / Compile Commands With Temp Pycache

Tests and compile checks must redirect pycache outside the project.

Tests and compile checks using relative paths must only be run from `C:\Webhook\RandleSystem`.

Allowed targeted test pattern:

```powershell
$env:PYTHONPYCACHEPREFIX = "$env:TEMP\randle_pycache_check"
python -m unittest .\<explicit_test_file>.py
Remove-Item -Recurse -Force "$env:TEMP\randle_pycache_check" -ErrorAction SilentlyContinue
```

Allowed targeted compile pattern:

```powershell
$env:PYTHONPYCACHEPREFIX = "$env:TEMP\randle_pycache_check"
python -m py_compile .\<explicit_python_file>.py
Remove-Item -Recurse -Force "$env:TEMP\randle_pycache_check" -ErrorAction SilentlyContinue
```

Only run explicitly requested test or compile files.

## 4. Forbidden Commands

Forbidden commands include:

- Broad process killing, including `Stop-Process -Name python -Force`
- Recursive deletes outside explicitly named temp pycache folders
- Broad cleanup commands
- Package installation commands
- Commands that modify Windows services, registry, firewall, startup apps, scheduled tasks, or system PATH
- Commands that access Desktop, Downloads, Documents, browser profiles, credential stores, cloud folders, or directories outside `C:\Webhook\RandleSystem`
- Commands that read, print, move, copy, edit, or delete secrets, credentials, tokens, account data, login files, environment files, or private configs
- Commands that reveal environment variable values containing credentials, tokens, secrets, account data, or API keys

## 5. Commands Requiring Explicit Approval

Explicit operator approval is required before:

- Stopping any process
- Starting any process not listed in this allowlist
- Running commands with elevated/admin permissions
- Touching files outside the allowed file list for the current task
- Running full test suites
- Running network commands against non-local endpoints
- Deleting any file or folder other than an explicitly named temp pycache folder created for the current command

## 6. Stop Conditions

Stop and ask if:

- The working directory is not exactly `C:\Webhook\RandleSystem`.
- A needed file is not listed as allowed for the current task
- A command requires admin rights
- A command could delete, overwrite, or expose unrelated data
- The task requires broad search, broad cleanup, or process killing
- The requested change would loosen existing validation
- The command could affect the whole machine

## 7. No Broad Process Killing

Do not kill processes broadly.

Before stopping any process, identify:

- Exact PID
- Executable name
- Reason the process must be stopped

Stop only the identified PID after explicit approval.

## 8. Delete Restrictions

Do not delete files or folders except explicitly named temp pycache folders created for the current test or compile command.

Allowed delete pattern:

```powershell
Remove-Item -Recurse -Force "$env:TEMP\randle_pycache_check" -ErrorAction SilentlyContinue
```

Do not run broad cleanup or wildcard delete commands.
