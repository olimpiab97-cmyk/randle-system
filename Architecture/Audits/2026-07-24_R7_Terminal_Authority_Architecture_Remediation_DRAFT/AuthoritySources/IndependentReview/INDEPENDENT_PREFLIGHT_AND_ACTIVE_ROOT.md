# Independent preflight and active-root preservation

The review began from exact candidate `35add65e8900ce9a48c3a7175e5e61e5e0868a84` in isolated worktree
`C:\Users\Trader\AppData\Local\Temp\randle_r7_independent_review_20260723_35add65` on branch
`governance/r7-independent-acceptance-review-20260723`.

The active production root was inspected but not used as the review worktree:

- path: `C:\Webhook\RandleSystem`;
- branch: `laptop_saved_work`;
- HEAD: `e84774e8b3681ae0aeb8390390dafea8a4b8cfd4`;
- exact status command: `git -c core.longpaths=true -c safe.directory=C:/Webhook/RandleSystem status --porcelain=v2 -z --branch --untracked-files=all`;
- stdout: 84,230 bytes, 1,022 NUL-delimited records, SHA-256 `45dab4e1b8e26a0cd5941e4d0a50aabeeeedde5996e7e5e6a8e854b1d7794b2c`;
- stderr: 6,358 bytes, 60 warnings, SHA-256 `6785fe51ed5b0258744cfe310a7a87ad4da103b9a4c15596bdcdb96d309f0ddb`;
- captured raw bytes: `C:\Users\Trader\AppData\Local\Temp\r7_independent_acceptance_review_20260723_preflight\active_status_z.stdout.bin` and `.stderr.bin`;
- ten-second recursive writer watch: 10.00485 seconds, zero events; result file `active_root_writer_watch.json` in the same preflight directory.

No Git lock, unmerged path, or active recursive writer was found. Neither complete R7 record is an ancestor of the candidate, active root, review branch, or inspected protected refs. No implementation path was edited. No service stop/restart, host configuration change, ACL change, trust change, key use, or ledger write was performed by this review.

The final command-scoped capture in the same sandbox/permission context reproduced the preflight bytes exactly: stdout 84,230 / SHA-256 `45dab4e1...`, stderr 6,358 / SHA-256 `6785fe51...`, 1,022 records and 60 warnings. A separate elevated diagnostic enumerated additional paths and was intentionally not compared to the non-elevated preflight; it made no change. Active-root preservation is confirmed.
