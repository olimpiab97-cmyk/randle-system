# Current Production Baseline Capture — Governed Remediation Investigation

## 1. Primary disposition

`RECAPTURE REQUIRED`

B5 decision: `B5_RECAPTURE_REQUIRED`.

## 2. Executive summary

The existing capture cannot be repaired as a complete production-disk baseline through provenance-only follow-up records. The preliminary deterministic test-scope scan selected all five questioned non-backup tests. The final capture replaced that selection with a 35-path manual test allowlist, omitted all five paths, and recorded none of them in its exclusion ledger. No preserved final selection specification gives a deterministic rule or path-specific decision that explains the removals.

Commit A consequently does not bind the active capture-time working-tree bytes for two modified tracked tests and contains no objects for three untracked tests. The exact capture-time bytes of those five active files cannot now be independently established from the governed capture evidence. The current production root still contains all five and reproduces the captured overall status identity, but Git porcelain status does not hash working-tree or untracked file content. Current bytes therefore cannot be declared identical to the unbound capture-time bytes.

Mandatory sequencing stops remediation at B5. B1, B2, B3, and B4 were not remediated, no corrective completeness record was created, and the original capture remains rejected.

## 3. Preflight results

- Repository: `C:\Webhook\RandleSystem`.
- Candidate worktree: `C:\Webhook\RandleSystem_CurrentBaselineCapture_Retry1`.
- Candidate branch: `recovery/current-production-baseline-capture-retry1`.
- Candidate branch was clean at preflight and remained at Commit B.
- Commit B was contained only by the candidate branch and the pre-existing independent-review branch; it was not contained by `main`, `laptop_saved_work`, or any remote canonical reference.
- No Git lock file was present under `C:\Webhook\RandleSystem\.git`.
- No active Git, Git LFS, fixture, capture, review, editor, or automation subprocess was found writing the repository. A second Codex host process was present but had no child command process; a terminal was open at the repository but had no active Git or writer child. Long-lived production Python services were observed but were not repository-writing capture/remediation processes.
- The production-root porcelain-v2 `-z` status was read twice with `GIT_OPTIONAL_LOCKS=0`; both reads were 222,035 bytes and SHA-256 `C8CFE4677054337A896A92D624505A09125A72C1F1941B25764209B4348605CB`.
- The original successful-retry durable manifest remained 65,348 bytes with SHA-256 `061005C2AF07381A3EC92B4AA359253A157EC8A81ED16B05108AF1CB817D7EDA`.
- The isolated remediation worktree is `C:\Users\Trader\AppData\Local\Temp\RandleSystem_CurrentBaselineCapture_Remediation_20260721` on branch `remediation/current-production-baseline-capture-20260721`, created directly at Commit B.

## 4. Commit A and Commit B integrity

Commit A was read as a committed Git object and matched:

- Identity: `28a4faa8e6abf3c8b4e642c20ca6dc31c4991fc6`
- Parent: `e84774e8b3681ae0aeb8390390dafea8a4b8cfd4`
- Tree: `c0916dc3b71de85c7748db0792bb62f7fd9c85e4`
- Subject: `recovery(entry-agent): capture current production disk state`

Commit B was read as a committed Git object and matched:

- Identity: `37c30269ce8fdc9cb0e62fe879058d8279e74799`
- Parent: `28a4faa8e6abf3c8b4e642c20ca6dc31c4991fc6`
- Tree: `bb92c8884afe02a8239e6fcf63ada527f53afcce`
- Subject: `docs(recovery): record current production baseline capture`

Neither object was altered by the independent review or this investigation.

## 5. B5 investigation and exact decision

### Preliminary selection process

The preliminary scan was generated at `2026-07-21T03:16:25.058397+00:00`. Its result is preserved as a 45,637-byte artifact with SHA-256 `0F465B27DB2EFE40E83B66CB72964C54E82AC21C15F75F5D06965D7D334269EA` and is listed with that identity in the unstable-attempt manifest whose SHA-256 is `872ECD2A36F4931996DA02247CDF4521F26AC32FB480ED207288951291CCE03C`.

The exact generating command was recoverable only from the prior Codex session record, not from the governed capture evidence. The command applied these rules:

1. Recursively discover repository `*.py` files.
2. Exclude any path component equal to `.git`, `EntryAgent_laptop_backup`, `.phase3c1-r11-worktree`, `.phase3c1-r4-worktree`, `.phase3c1-r7-worktree`, `.phase3c1-r9-worktree`, or `__pycache__`, and any component beginning `.tmp`.
3. Treat a file as a test candidate if its name begins `test_`, ends `_tests.py`, or contains `replay_tests`.
4. Parse each candidate with Python AST. A parse error excludes the candidate.
5. Include a candidate if it directly imports a token derived from the 16-file captured runtime closure, contains an `EntryAgent/` or `EntryAgent\` path reference, is under `EntryAgent/`, or its filename matches a governed-category pattern.
6. Category patterns were:
   - `entry_agent`: `entry[_-]?agent|entry_status|entry_replay`
   - `steps`: `step[_-]?(?:2|3|4|5|6|7)|gateway`
   - `context_lock_stack`: `context|canonical_lock|liquidity|stack|overlap|preopen|nq_20260716|ym_high`
   - `listener_candle_atr`: `rithmic_live_listener|listener|completed_candle|closed.bar|atr_authority|atr_live|tick_receiver`
   - `session_persistence`: `session|rollover|rehydrat|persist`
   - `diagnostic`: `read_only|diagnostic`
   - `startup`: `launch_all|startup_live_path`
   - `symbol_data_paths`: `symbol_resolution|data_root_paths`
7. Explicitly deny a root test named `test_trade_manager_*` or `test_executor_*` unless it directly imports a captured-runtime token or references an EntryAgent path.
8. Discover existing literal fixture references ending in `.json`, `.txt`, `.md`, `.csv`, `.yaml`, or `.yml`, limited to strings of at most 260 characters and resolved relative to the test or repository root.

This process found 66 candidates, selected 40, and excluded 26. It also incorrectly selected one backup path because `Backups` was not among the discovery exclusions.

### Final 234-path selection process

The final capture script used no test discovery, category evaluation, import closure, or documented transformation of the preliminary 40-test set. It constructed scope from hard-coded lists and four directory expansions:

- 16 `RUNTIME_FILES`
- 3 `LAUNCH_AND_STATIC_FILES`
- 6 `TEST_SUPPORT_FILES`
- 35 `TEST_FILES`
- 3 `STATIC_TEST_FILES`
- 153 files under `Data/entry_agent_demo_cases` with `.json` or `.gitkeep`
- 11 files under `EntryAgent/scenarios` with `.json` or `.md`
- 2 files under `tests/fixtures/tradingview` without an extension filter
- 5 files under `Architecture/Impact_Assessments/Evidence/2026-07-16_TradingView_Liquidity_Ladder` without an extension filter

All hard-coded and expanded paths had to exist as regular files. Paths were canonicalized with `Path(...).as_posix()`, duplicate paths would be merged by dictionary key, and the final records were sorted by repository-relative path. The independently simulated result was exactly 234 unique paths and matched preserved Pass A bidirectionally with no missing or extra path.

The final script contained nine explicit exclusions plus four dynamically enumerated demo-case Markdown exclusions, for 13 total. None of the five questioned paths appeared in that exclusion ledger. Each of the 35 allowed tests received only the blanket reason `Directly governs captured Entry Agent/listener/receiver behavior`; no evidence records the rule by which the questioned tests failed that standard.

The first capture script version was created before Pass A with the same 35-test allowlist and none of the questioned names. Its source was recoverable from the session event as 21,564 bytes with SHA-256 `0D0893E303181C20031A3BCC4453B4A519C1FF555616F17908371CC8761B0772`. The retry changed the evidence path and status parser only; it did not change the allowlist. The surviving retry script is 22,862 bytes with SHA-256 `9863B2ABF52247E359DE1D279C127F66D875B8EA0A5E7C11D648FD14ACA20638`.

Neither script identity, the generating command, nor a path-specific exclusion decision was included in the original or retry durable capture manifests. The surviving script is a mutable temporary file. The session record is external to the governed evidence and was not capture-bound. A static allowlist can reproduce the chosen 234 paths, but it cannot prove that the five removals were governed rather than undocumented operator judgment.

Decision: `B5_RECAPTURE_REQUIRED` because exclusion cannot be proven reproducibly and capture-time active bytes were not bound.

## 6. Individual disposition of the five questioned paths

| Path | Preliminary rule result | Capture-time status evidence | Commit A binding | Deterministic final exclusion | Disposition |
|---|---|---|---|---|---|
| `test_command_center_listener_watchdog.py` | Included by six governed categories | Modified tracked (`.M`) | Parent/index blob `828221cd9dae9980701edba5c24db1d3315b5ab2`; active bytes not bound | None | Must be resolved in a new capture; historical active bytes are unproven |
| `test_offline_replay.py` | Included by `session_persistence`, `symbol_data_paths`, and direct import of captured `symbol_resolution` | Modified tracked (`.M`) | Parent/index blob `eb08c72d2eba571afd43590a4c5f9e67bfd4ef24`; active bytes not bound | None | Must be resolved in a new capture; historical active bytes are unproven |
| `test_kpi_liquidity_atr_distance_report.py` | Included by `context_lock_stack` and `session_persistence` | Untracked | Absent | None | Must be resolved in a new capture; historical active bytes are unproven |
| `test_tick_receiver_pipeline.py` | Included by `context_lock_stack`, `listener_candle_atr`, and `session_persistence` | Untracked | Absent | None | Must be resolved in a new capture; historical active bytes are unproven |
| `test_tick_receiver_throughput.py` | Included by `listener_candle_atr` and `session_persistence` | Untracked | Absent | None | Must be resolved in a new capture; historical active bytes are unproven |

Commit A and its parent contain the same two tracked blobs. The three untracked paths do not exist in either tree. Thus Commit A did not preserve any questioned path's active capture-time bytes.

Current disk observations are not promoted to capture-time evidence. All five files remain present, their modification times predate the capture, and the overall production status identity remains unchanged; however, the status stream records state class and index object identifiers, not working-tree/untracked byte hashes. Exact historical identity therefore remains unprovable.

## 7. Whether a new capture is required

Yes. A new governed production baseline capture is required. Before its Pass A, it must freeze and preserve the complete inventory-selection specification and make a deterministic, reviewable decision for all five paths. Any included path must have its then-current active bytes copied and Git object bound. Any excluded path must have a path-specific, pre-Pass-A rule and evidence proving it is outside the governed boundary.

This new capture will record the production state at its own capture time. It cannot retroactively recreate the unbound bytes of the rejected historical capture unless an independently immutable source of those exact bytes is discovered and verified.

## 8. B1 corrective-manifest result

Not performed. Mandatory sequencing forbids B1 remediation after `B5_RECAPTURE_REQUIRED`. The original long-path manifest defect remains unresolved and the original manifest remains unchanged.

## 9. B2 durable-evidence binding result

Not performed. No corrective completeness registry or provenance repair commit was created. The missing immutable bindings remain unresolved.

## 10. B3 failure-classification result

Not performed. The missing individual classification of 23 `SUBFAILED` outcomes remains unresolved. No existing failure record was modified.

## 11. B4 attempt-ledger result

Not performed. The no-artifact and unstable attempts remain unreconciled in a corrective attempt ledger. No attempt record was rewritten.

## 12. Negative and mutation checks

All checks were read-only and in-memory; no candidate, production, or durable evidence was mutated.

- Reconstructing the final algorithm produced 234 unique paths and exactly matched Pass A.
- Adding `test_command_center_listener_watchdog.py` to the final set produced 235 paths and one detectable extra path.
- Adding all five questioned paths produced 239 paths and five detectable extras.
- Removing one required final path produced 233 paths and one detectable missing path.
- Comparing the preliminary selection with final tests produced six preliminary-only paths: one backup plus the five questioned paths.
- Comparing in the reverse direction found one final-only test, `test_synthetic_scenario_runner.py`.
- The five questioned paths were all preliminary-selected and none were final-selected.

These mutation checks show that set changes are detectable once an authoritative set is supplied. They do not repair the absence of an authoritative, evidence-backed rule for choosing the final set.

## 13. Exact artifacts and repository paths changed

The only investigation artifact is this report:

`Architecture/Audits/2026-07-21_Current_Production_Baseline_Capture_Remediation/B5_RECAPTURE_REQUIRED.md`

No production source, test, launcher, deployment file, runtime data, durable original capture evidence, Commit A, Commit B, candidate branch, or R11 artifact was changed.

## 14. Evidence identities used

| Role | Canonical path | Bytes | SHA-256 | Authority assessment |
|---|---|---:|---|---|
| Unstable-attempt manifest binding the preliminary result | `C:\Users\Trader\OneDrive\RandleRuntimeData\provenance\current_production_baseline_capture_20260720\metadata\durable_capture_manifest.json` | 83,208 | `872ECD2A36F4931996DA02247CDF4521F26AC32FB480ED207288951291CCE03C` | Preserved external evidence; superseded attempt |
| Preliminary selection result | `C:\Users\Trader\OneDrive\RandleRuntimeData\provenance\current_production_baseline_capture_20260720\metadata\preliminary_test_scope_scan.json` | 45,637 | `0F465B27DB2EFE40E83B66CB72964C54E82AC21C15F75F5D06965D7D334269EA` | Preserved and listed by unstable manifest |
| Successful-retry original manifest | `C:\Users\Trader\OneDrive\RandleRuntimeData\provenance\current_production_baseline_capture_20260720_retry1\metadata\durable_capture_manifest.json` | 65,348 | `061005C2AF07381A3EC92B4AA359253A157EC8A81ED16B05108AF1CB817D7EDA` | Original authoritative capture evidence; incomplete but unchanged |
| Successful-retry Pass A scope | `C:\Users\Trader\OneDrive\RandleRuntimeData\provenance\current_production_baseline_capture_20260720_retry1\metadata\capture_scope_pass_a.json` | 1,143,717 | `4D40BAB79C9FBE38ECD2E96C778BD4D7FD2DB7A803EE0B7CE586990823FED9FB` | Preserved final 234-path result |
| Successful-retry Pass B scope | `C:\Users\Trader\OneDrive\RandleRuntimeData\provenance\current_production_baseline_capture_20260720_retry1\metadata\capture_scope_pass_b.json` | 303,890 | `CC31AD4945857A1D6F8F6ACF9E3BBABE2322593739FC5419BD39231002B55268` | Preserved stability result |
| Successful-retry precondition | `C:\Users\Trader\OneDrive\RandleRuntimeData\provenance\current_production_baseline_capture_20260720_retry1\metadata\precondition.json` | 473,634 | `2EA5153261A6142D0F449615C07EAAE29E6F36D5D2DE08A8C5D6C123208AB141` | Preserved external precondition evidence |
| Production status artifacts | Five `active_git_status_*_porcelain_v2.z` files under the successful-retry `metadata` directory | 222,035 each | `C8CFE4677054337A896A92D624505A09125A72C1F1941B25764209B4348605CB` each | Preserve status classes, not questioned active bytes |
| Surviving retry capture script | `C:\Users\Trader\AppData\Local\Temp\randle_current_baseline_capture.py` | 22,862 | `9863B2ABF52247E359DE1D279C127F66D875B8EA0A5E7C11D648FD14ACA20638` | Mutable temporary evidence; not capture-bound |
| Prior Codex session record | `C:\Users\Trader\.codex\sessions\2026\07\19\rollout-2026-07-19T21-06-52-019f7db4-8dc4-7d01-9d1d-3d86c23cd487.jsonl` | 23,570,515 | `A5B3AD4A8DA436F8C52840A4C9926FF72C958AF3776D48B0A9D1A7AFE9745121` | Secondary recovered evidence; external and not capture-bound |

## 15. Branch and worktree status

- Candidate branch remains `recovery/current-production-baseline-capture-retry1` at Commit B, clean and unmerged into canonical branches.
- Remediation branch is isolated from the production root and descends directly from Commit B.
- This report may be committed as a report-only provenance record. Such a commit does not repair or represent the capture as complete.

## 16. Remaining blocking findings

1. B5: final exclusion of all five questioned paths is not deterministically or immutably proven.
2. B5: active capture-time bytes for all five questioned paths were not bound by Commit A.
3. B1: the original durable manifest remains incomplete for two long-path artifacts.
4. B2: recovery-critical external evidence remains incompletely bound by committed records.
5. B3: 23 `SUBFAILED` outcomes remain individually unclassified.
6. B4: distinct prior attempts remain unreconciled in an authoritative attempt ledger.

There are no nonblocking findings; all listed findings remain blocking.

## 17. Exact next governed action

Design and independently review a deterministic capture-boundary specification, then start a new production baseline capture under a separate governed authorization. Freeze the specification, selection output, script identity, and all path-specific exclusion decisions before Pass A. Bind the then-current active bytes of every included path. Include all five questioned paths unless the new pre-Pass-A specification independently proves a specific path outside scope.

After the new capture and complete B1–B4-equivalent provenance are produced, submit that new capture to a new independent review before any merge consideration.

## 18. Explicit authorization statement

This investigation does not authorize merge, canonical incorporation, implementation, deployment, service restart, runtime migration, NQ cutover, automated paper trading, live-money trading, Phase 3C2, independent Phase 3C1-R11 acceptance during this task, Bucket 0 completion, or Bucket 1 work. Candidate merge and every operational or trading action remain withheld.

CURRENT PRODUCTION BASELINE CAPTURE REMEDIATION — RECAPTURE REQUIRED
