# AI Agent Safety Policy

## 1. Authorized Working Directory

Codex is authorized to work only inside:

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

Codex must not operate from any other directory. If a task requires access outside this directory, Codex must stop and ask for explicit approval after the working directory check has passed.

Before any file inspection, code edit, test, compile check, discovery command, or project command, Codex must confirm the working directory is exactly `C:\Webhook\RandleSystem` using the mandatory first step above. If Codex starts in `C:\Windows\system32` or any non-project directory, it must stop immediately.

Commands using relative paths, including `.\...`, must only be run from `C:\Webhook\RandleSystem`.

## 2. Forbidden Directories

Codex must not access, inspect, modify, copy, move, delete, or search:

- Desktop
- Downloads
- Documents
- Browser profiles
- Credential stores
- Cloud folders
- Any directory outside `C:\Webhook\RandleSystem`

## 3. Forbidden File Types And Secrets

Codex must not read, print, edit, move, copy, delete, or expose:

- Credentials
- Secrets
- API keys
- Tokens
- Account numbers
- Rithmic login files
- Environment files
- Config files containing private or account-specific data

These files may be touched only when explicitly named by the operator and required for the task.

Codex must not read, print, store, copy, or modify credentials or credential files. Codex must not run commands that reveal environment variable values containing credentials, tokens, secrets, account data, or API keys.

## 4. Forbidden Commands

Codex must not run commands that:

- Affect the whole machine
- Install packages
- Modify Windows services
- Modify the registry
- Modify firewall rules
- Modify startup apps
- Modify scheduled tasks
- Modify system PATH
- Delete recursively
- Perform broad cleanup
- Kill processes without exact PID, executable, and reason
- Delete, overwrite, or expose data outside the project

If elevated or administrator permissions are required, Codex must stop and report why.

## 5. Allowed Command Types

Allowed default command types are:

- `Get-Content` for explicitly named files
- `Select-String` for explicitly named files
- `python -m unittest` for explicitly named test files
- `python -m py_compile` for explicitly named Python files, with pycache redirected outside the project
- Targeted edits to explicitly named files only

## 6. Compile And Test Pycache Rule

Compile and test commands must not write pycache or compile artifacts into `C:\Webhook\RandleSystem`.

Use a temp pycache path outside the project, for example:

```powershell
$env:PYTHONPYCACHEPREFIX = "$env:TEMP\randle_pycache_check"
python -m py_compile .\executor.py
Remove-Item -Recurse -Force "$env:TEMP\randle_pycache_check" -ErrorAction SilentlyContinue
```

Only remove the explicitly created temp pycache folder.

## 7. Process-Kill Restrictions

Codex must not kill processes unless all of the following are known:

- Exact PID
- Executable name
- Reason the process must be stopped

Codex must not kill Python processes broadly.

## 8. Cleanup Restrictions

Codex must not run recursive delete commands or broad cleanup commands.

Cleanup is allowed only for explicitly identified artifacts created by Codex during the current task, and only when the target path is verified.

## 9. Output Format Requirements

Codex final output must include only:

- Changed files
- Relevant patch sections or relevant content
- Test or compile results
- Skipped steps with reasons

Codex must not expose secrets, tokens, account identifiers, or unrelated file contents.

## 10. One Security Fix At A Time

Codex must perform one security fix at a time.

Codex must not combine unrelated security, trading, execution, listener, configuration, or cleanup changes in the same task.
