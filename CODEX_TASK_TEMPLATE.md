# Codex Task Template

## 1. Working Directory

Codex must work only in:

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

stop immediately and report only:

- `workspace_guard_failed`
- actual directory
- instruction to restart Codex from `C:\Webhook\RandleSystem`

When outside the approved directory, do not list directories, inspect environment variables, run git, run tests, inspect files, search for repo locations, infer a likely workspace, or run project commands. Commands like `Get-ChildItem`, `git`, `python`, `pytest`, `unittest`, and `Get-Content` are forbidden until the working directory check passes. Do not helpfully search for the repo when launched from the wrong directory.

Do not operate from any other directory.

Before any file inspection, code edit, test, compile check, discovery command, or project command, confirm the working directory is exactly `C:\Webhook\RandleSystem` using the mandatory first step above.

Commands using relative paths, including `.\...`, must only be run from `C:\Webhook\RandleSystem`.

## 2. Policy Reference

Follow `AGENT_SAFETY_POLICY.md`.

If this task conflicts with the policy, stop and ask for clarification before taking action.

## 3. Objective

Describe the single objective for this task:

```text
<objective>
```

## 4. Allowed Files

Codex may inspect or modify only these files:

```text
<allowed file 1>
<allowed file 2>
```

Do not inspect or modify any file not listed here.

## 5. Forbidden Files / Areas

Codex must not access, inspect, modify, copy, move, delete, or expose:

- Files outside `C:\Webhook\RandleSystem`
- Files not listed in Allowed Files
- Desktop, Downloads, Documents, browser profiles, credential stores, or cloud folders
- Credentials, secrets, API keys, tokens, account numbers, login files, environment files, or private config files

## 6. Security Constraints

- Make only the requested change.
- Do not loosen existing validation or safety checks.
- Do not modify trading, execution, risk, listener, or lifecycle logic unless explicitly in scope.
- Do not install packages.
- Do not run commands that affect the whole machine.
- Do not use elevated/admin permissions unless explicitly approved.
- Do not write persistent files unless explicitly listed in Allowed Files.
- Do not read, print, store, copy, or modify credentials or credential files.
- Do not run commands that reveal environment variable values containing credentials, tokens, secrets, account data, or API keys.

## 7. Efficiency Instructions

- Keep changes minimal and localized.
- Reuse existing helpers and patterns where possible.
- Avoid unrelated refactors.
- Avoid broad searches.
- Prefer targeted reads of explicitly allowed files.

## 8. Task Steps

1. Run only `(Get-Location).Path` before interpreting or planning the request; if the output is not exactly `C:\Webhook\RandleSystem`, stop immediately with the required `workspace_guard_failed` report.
2. Inspect only files listed in Allowed Files.
3. Make the smallest necessary change.
4. Run only the listed Verification Commands.
5. Report only the requested output.

## 9. Acceptance Criteria

- `<criterion 1>`
- `<criterion 2>`
- `<criterion 3>`

## 10. Verification Commands

List exact commands Codex may run:

```powershell
<verification command 1>
<verification command 2>
```

For Python compile or test commands, redirect pycache outside the project:

```powershell
$env:PYTHONPYCACHEPREFIX = "$env:TEMP\randle_pycache_check"
<python command>
Remove-Item -Recurse -Force "$env:TEMP\randle_pycache_check" -ErrorAction SilentlyContinue
```

Do not run unlisted tests or compile commands.

## 11. Output Format

Final output must include only:

- Changed files
- Relevant patch sections or relevant content
- Test or compile results
- Skipped steps with reasons

Do not expose secrets, tokens, account identifiers, or unrelated file contents.

## 12. Stop Conditions

Stop and ask if:

- The working directory is not exactly `C:\Webhook\RandleSystem`.
- A needed file is not listed in Allowed Files.
- A command requires admin rights.
- A command could delete, overwrite, or expose unrelated data.
- The task requires broad search, broad cleanup, or process killing.
- The requested change would loosen existing validation.
- The task requires touching secrets, credentials, configs, account data, or files outside the allowed file list.
