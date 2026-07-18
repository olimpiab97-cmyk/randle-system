# Entry Session Rollover Lifecycle Contract

Version: Draft 0.3 - Phase 3A remediation

Status: **DRAFT - NOT CANONICAL - NOT APPROVED**

Governing Dependency: ADR-014 is approved and governs this draft. This contract remains draft/noncanonical; Constitution sections 6, 12-17, and 22 and the current canonical Lifecycle Engine remain governing. Proposed Runtime Authority amendments remain noncanonical.

Implementation Authorization: None

## 1. Purpose

Define the executable lifecycle contract for changing the current Entry session without allowing receiver lock, canonical Entry Agent state, frozen ladder, observation state, session-context authorization, or Command Center projection to advance independently.

## 2. Aggregate and owner

The `Entry Session Aggregate` is per logical symbol. The `Entry Session Commit Writer` is its sole canonical writer and sole owner of the active-session pointer. The Session-lock Validator owns candidate lock/rollover eligibility and supplies a validation result; it SHALL NOT write or advance canonical state. Entry Agent consumes the committed aggregate and owns no independent session identity, observation-reset identity, frozen-ladder activation, or authorization activation.

The aggregate SHALL contain:

- `symbol`;
- `session_id` and `session_date`;
- `session_rollover_commit_id`;
- `candidate_receipt_id` and payload identity;
- canonical receiver lock;
- frozen Liquidity Level map and frozen ladders;
- observation initialization/reset identity;
- session-context authorization state;
- `trade_authorization_context_binding`, initialized as `BLOCKED_PENDING_RUNTIME_GATES` and bound to symbol/session/proposed commit ID;
- `authorized_session_rollover_commit_id`, initialized and retained in the rollover aggregate as immutable `null`/not authorized; every later separate opening-entry request/decision record carries the active commit ID without mutating the aggregate;
- prior-session archive reference;
- rule/schema/source versions;
- committed/exposed times and projection cursors; and
- validation and divergence state.

## 3. Lifecycle states

```text
NO_CURRENT_SESSION_CONTEXT
  -> CANDIDATE_PENDING
  -> CANDIDATE_VALIDATED
  -> COMMITTING
  -> COMMITTED_FAIL_CLOSED
  -> CURRENT_CONTEXT_READY
```

Failure states:

```text
CANDIDATE_REJECTED
COMMIT_FAILED
SESSION_PROJECTION_DIVERGED
STALE_PRIOR_SESSION_BLOCKED
SESSION_STORE_DEGRADED
SESSION_STORE_CORRUPT
```

`COMMITTED_FAIL_CLOSED` means the session aggregate committed but one or more downstream runtime identities have not reconciled. It is not trading authorization.

### 3.1 Complete state transition contract

| State | Entry event | Sole transition/record authority | Required durable record | Permitted exits | Restart and retry behavior | Terminal/recoverable | Active-session and opening-entry effect |
|---|---|---|---|---|---|---|---|
| `NO_CURRENT_SESSION_CONTEXT` | Startup/date-boundary evaluation proves no applicable current commit | Entry Session Commit Writer | symbol/session expectation, store cursor, evaluation identity, `authorized_session_rollover_commit_id=null` | `CANDIDATE_PENDING`; `SESSION_STORE_DEGRADED`; `SESSION_STORE_CORRUPT` | Restores identically; no implicit candidate synthesis; a real eligible receipt MAY start a new candidate | Recoverable only by a valid current-session candidate/commit | No active current session; opening entries blocked |
| `STALE_PRIOR_SESSION_BLOCKED` | Trading-date boundary makes the prior committed session inapplicable before a replacement commits | Entry Session Commit Writer | prior session/commit, required current date, inapplicability reason, prior binding disposition, `authorized_session_rollover_commit_id=null` for the new date | `CANDIDATE_PENDING`; `SESSION_STORE_DEGRADED`; `SESSION_STORE_CORRUPT` | Restores as blocked history; prior session cannot be retried as current | Terminal for prior-session applicability; recoverable for the symbol only by a new valid commit | Prior bytes remain canonical history but inactive; opening entries blocked |
| `CANDIDATE_PENDING` | Receiver archives one immutable current-session candidate and the writer registers its noncurrent identity | Entry Session Commit Writer; receiver supplies archive evidence only | receipt/payload hash, session, source/version, sender-authentication result reference, expected active version | `CANDIDATE_VALIDATED`; `CANDIDATE_REJECTED`; store failure states | Restart resumes validation by candidate identity; duplicate receipt is idempotent | Recoverable | Active authority unchanged/inapplicable for new date; opening entries blocked |
| `CANDIDATE_VALIDATED` | Session-lock Validator returns one complete successful validation result | Entry Session Commit Writer records; Session-lock Validator supplies eligibility result only | validator/policy identity, complete result hash, expected active version, candidate aggregate hash including both authorization-binding fields | `COMMITTING`; `CANDIDATE_REJECTED` only if precommit revalidation now fails; store failure states | Restart revalidates identity/version before commit; no active mutation | Recoverable | Active authority unchanged; opening entries blocked |
| `CANDIDATE_REJECTED` | Validation or precommit revalidation fails | Entry Session Commit Writer | immutable rejection code/evidence, candidate identity, policy/version, active version observed | New independently eligible candidate MAY enter `CANDIDATE_PENDING`; store failure states | The rejected candidate SHALL NOT auto-retry or become current; exact duplicate returns same rejection | Terminal for that candidate | Active authority unchanged; prior session remains historical/inapplicable after date boundary; opening entries blocked |
| `COMMITTING` | Writer acquires per-symbol authority and begins the all-or-none transaction | Entry Session Commit Writer | transaction/commit ID, expected active version, complete aggregate hash, prior-retirement mutation, both authorization-binding fields | `COMMITTED_FAIL_CLOSED`; `COMMIT_FAILED`; store failure states | Restart resolves from SQLite commit/readback only: one complete commit or no commit | Recoverable only through deterministic commit resolution | Uncommitted candidate is invisible; opening entries blocked |
| `COMMIT_FAILED` | Transaction, flush, COMMIT, or readback does not establish one complete commit | Entry Session Commit Writer | candidate/transaction identity, exact failed stage, SQLite outcome, preserved active version, pending evidence; never a current pointer | `COMMITTING` only after exact no-commit proof and same-candidate/version revalidation; store failure states; a conflicting candidate is rejected | No blind retry. Restart first proves commit/no-commit; ambiguous outcome enters `SESSION_STORE_CORRUPT` | Recoverable only after authoritative no-commit proof | No new active session/retirement/authorization; opening entries blocked |
| `COMMITTED_FAIL_CLOSED` | Atomic COMMIT/readback activates candidate and retires prior applicability, but required authoritative runtime/exposure identities are not coherent | Entry Session Commit Writer | complete aggregate/active pointer/prior retirement/exposure cursors, shared commit ID, `trade_authorization_context_binding=BLOCKED_PENDING_RUNTIME_GATES`, `authorized_session_rollover_commit_id=null` | `CURRENT_CONTEXT_READY`; `SESSION_PROJECTION_DIVERGED`; store failure states; next date to `STALE_PRIOR_SESSION_BLOCKED` | Restart restores from the committed aggregate and resumes exposure under the same commit ID | Recoverable | Current session is canonical but session context remains fail-closed; opening entries blocked |
| `CURRENT_CONTEXT_READY` | Required authoritative session exposures and runtime identity checks agree with the committed aggregate | Entry Session Commit Writer records session-context readiness; separate opening-entry authorization owner remains independent | verified exposure identities, active pointer, shared commit ID, runtime-gate snapshot; binding remains present | `SESSION_PROJECTION_DIVERGED`; store failure states; next date to `STALE_PRIOR_SESSION_BLOCKED` | Restart re-verifies; never assumes readiness from prior process memory | Recoverable current state | Session context MAY be consumed, but opening entry requires a separate decision that sets/carries the exact authorized commit ID |
| `SESSION_PROJECTION_DIVERGED` | Any current-labeled required surface disagrees with canonical session/commit/integrity identity | Entry Session Commit Writer records divergence from owner-supplied observations | canonical identity, every mismatched surface, first divergence, detection identity | `COMMITTED_FAIL_CLOSED` after projection regeneration; `CURRENT_CONTEXT_READY` only after full reverification; store failure states | Restart preserves divergence and repairs only from the canonical aggregate | Recoverable only from canonical authority/governed replay | Canonical commit remains; opening entries blocked |
| `SESSION_STORE_DEGRADED` | Store cannot commit/read back but corruption is not established | Entry Session Commit Writer | exact I/O/contention failure and last verified cursor/active identity | Prior state after verified recovery; `SESSION_STORE_CORRUPT` if integrity cannot be established | Restart performs owner recovery before exposure; no projection fallback | Recoverable only by verified store recovery | No new activation/retirement/authorization; opening entries blocked |
| `SESSION_STORE_CORRUPT` | Integrity, sequence, identity, or commit-state verification fails | Entry Session Commit Writer | corruption/recovery incident, store identities, failed checks, quarantine evidence | Governed recovery result only; no automatic normal-state exit | Startup remains failed until separately governed recovery succeeds | Terminal for automatic startup | No trustworthy current authority inferred; opening entries blocked |

Only the named authority may write each transition. A read, projection, receiver cache, startup script, Session-lock Validator, Entry lifecycle evaluator, or Command Center SHALL NOT write or infer a transition.

Every state transition not listed as a permitted exit in section 3.1 is prohibited for all twelve declared states. A retry, restart, projection repair, operator action, later candidate, date boundary, or store recovery SHALL use only the exit explicitly named in the current state's row; it SHALL NOT synthesize an intermediate state, reopen a terminal candidate outcome, bypass `COMMIT_FAILED` resolution, or mutate active-session authority outside the Entry Session Commit Writer transaction.

## 4. Candidate receipt

The receiver SHALL archive the complete received payload as immutable noncurrent evidence before it is considered for rollover. The archive SHALL preserve exact payload/version/source/receipt/session identities and acceptance/rejection disposition.

The archive SHALL distinguish:

- sender assertion such as `locked=true`;
- receiver candidate status;
- receiver canonical lock fact; and
- committed current-session projection.

Only the final two are created by the Session Rollover Transaction. A sender assertion is required when the webhook contract requires it but is never sufficient to create authority.

## 5. Validation contract

Validation SHALL complete before active-state mutation and SHALL include:

- payload completeness/schema;
- source and sender authority;
- supported normalized symbol;
- timestamp, time zone, session, and lock-window identity;
- duplicate, stale, out-of-order, and prior-session handling;
- all required level identities, status, price, source, and provenance;
- structural validation under the separately governing liquidity/stack contract;
- explicit stack object, row membership, distinct owner, numbering, and ladder-order consistency;
- boundary/anchor/source input completeness; and
- conflict with an existing current-session commit.

The structural validator's behavior is an input to this lifecycle. This draft does not amend stack-overlap authority and does not incorporate DEBT-015 into ADR-014 scope.

Source/content eligibility and sender identity are separate validation results. `PUBLIC_ROUTE_TRAVERSAL_VERIFIED` SHALL identify the authorized public hostname, tunnel activation, relay receipt, Entry receipt, one receipt ID, and one exact payload hash. `PAYLOAD_SESSION_ELIGIBLE` SHALL validate freshness, version, intended session, ordering, duplication, and replay disposition. `SENDER_IDENTITY_AUTHENTICATED` SHALL be supplied only by a separately approved sender-authentication authority and SHALL bind the authenticated sender to the same receipt ID, payload hash, and freshness/replay evidence.

The current production webhook path does not authenticate sender identity. Host, source address, user-agent, TLS to the public route, `locked=true`, sender timestamp/session fields, receipt time, and payload hash are not sender authentication. Until the separate security contract represented by `DEBT-2026-07-17-016` exists and returns `VERIFIED`, a received payload MAY be preserved as noncurrent evidence but SHALL NOT commit a production Entry Session Aggregate. ADR-014 remains the authority for transaction atomicity; the security record remains the authority for the missing sender-authentication decision.

## 6. Candidate build contract

After successful validation, Entry Agent SHALL build the complete candidate aggregate in memory or an isolated transaction workspace. It SHALL not mutate the active aggregate, raw-current receiver projection, observation latch, frozen files, or authorization state.

The candidate build SHALL resolve all fields needed for one restart/replay without consulting mutable current projections. It SHALL include `trade_authorization_context_binding=BLOCKED_PENDING_RUNTIME_GATES` bound to the symbol, session ID/date, and proposed commit ID, and `authorized_session_rollover_commit_id=null`. A candidate SHALL NOT inherit either field from the prior session.

## 7. Commit identity

`session_rollover_commit_id` SHALL be deterministic or durably deduplicated for the accepted symbol/session/payload identity. The same ID SHALL bind:

| Commit member | Required identity |
|---|---|
| Receiver lock | symbol, session, receipt/payload, commit ID |
| Canonical Entry Agent aggregate | symbol, session, version, commit ID |
| Every frozen ladder/level projection | symbol, session, source version, commit ID |
| Observation state | symbol, session, initialization/reset, commit ID |
| Session-context authorization | symbol, session, state, commit ID |
| Trade-authorization context binding | symbol, session, `BLOCKED_PENDING_RUNTIME_GATES`, commit ID |
| Opening-entry authorization identity | symbol, session, `authorized_session_rollover_commit_id=null` at rollover; later decision must equal the active commit ID |
| Prior-session retirement record | prior session, superseding session, commit ID |
| Exposure cursor | destination, commit ID, version/sequence |

No member SHALL carry an independently generated rollover identity.

## 8. Durable commit contract

The authoritative transaction record SHALL include candidate insertion, current-session activation, prior-session retirement, observation initialization, frozen-ladder activation, receiver lock, session authorization, `trade_authorization_context_binding`, `authorized_session_rollover_commit_id=null`, and pending exposure cursors before it is durably committed. The persistence implementation SHALL provide:

- exclusive per-symbol compare-and-swap/version protection;
- one atomic all-or-none authority commit for every listed member;
- flush/fsync or transactional durability appropriate to the store;
- integrity/version verification;
- duplicate idempotency;
- crash recovery with all-or-none authority; and
- pending exposure tracking for compatibility projections.

Several sequential JSON replacements cannot jointly be the authority boundary. Compatibility JSON files SHALL be derived, commit-ID-bearing projections from one durable aggregate/transaction record.

## 9. Atomic activation, retirement, and exposure

The authority transaction SHALL atomically commit one authoritative session state. In the same transaction and under the same `session_rollover_commit_id`, it SHALL:

1. insert the complete validated candidate aggregate;
2. mark the previously active session, when one exists, noncurrent and retired by this commit;
3. advance the sole active-session pointer to the candidate; and
4. activate the candidate's `trade_authorization_context_binding=BLOCKED_PENDING_RUNTIME_GATES` and `authorized_session_rollover_commit_id=null`; and
5. create pending exposure cursors for receiver current, Entry Agent, frozen ladder, observation, authorization, and Command Center projections.

The commit SHALL be rejected unless the new active session, prior-session retirement, observation initialization, frozen-ladder activation, receiver lock, session authorization state, both trade-authorization fields, and exposure cursors form one internally complete transaction record. There SHALL NOT be a committed state in which the current session is active while the prior session is not retired, the prior session is retired without the new session active, either authorization field is absent/inherited, or any member carries another commit identity.

Only after durable COMMIT and readback verification SHALL projection workers publish current-labeled surfaces. Projection success or failure does not perform activation or retirement. Failed exposure remains pending under the committed identity and keeps the affected symbol fail-closed.

If the transaction fails, the prior canonical record/history remains byte-for-byte authoritative evidence, but it SHALL enter `STALE_PRIOR_SESSION_BLOCKED` when its session date is earlier than the required trading date. Its retirement/inapplicability evidence SHALL preserve the prior `trade_authorization_context_binding` and prior authorized commit identity for audit, record the superseding commit ID only on successful rollover, and make both prior authorization fields ineligible for the new date. It SHALL NOT remain tradable or serve as fallback for the new date. Successful retirement never deletes or rewrites prior canonical history.

## 10. Observation rule

Observation initialization/reset is legal only as a member of a committed rollover. A completed bar MAY update observation values after that commit under the observation contract; it SHALL NOT initialize the session, advance `observation_reset_session_date`, or create a new reset identity.

Repeated processing of the same rollover commit SHALL not reset observation twice.

## 11. Authorization and readiness

The session-context authorization state and `trade_authorization_context_binding` SHALL remain `BLOCKED_PENDING_RUNTIME_GATES` until the rollover commit is durable and all required current identities expose the same session and commit ID. Rollover SHALL leave `authorized_session_rollover_commit_id=null`.

Even `CURRENT_CONTEXT_READY` does not authorize entries. Entry readiness also requires current listener epoch, bridge generation where required, bar, ATR, contract, lifecycle, risk, Trade Manager, and Executor identities.

Every later opening-entry request SHALL carry `authorized_session_rollover_commit_id` equal to the active aggregate's commit ID and SHALL carry the immutable `trade_authorization_context_binding` identity it evaluated. Every opening-entry authorization decision SHALL materialize the same ID in its separate decision record and SHALL reject `null`, missing, stale, prior-session, other-symbol, or mismatched IDs. The separate authorization owner MAY create that decision record only after every independent runtime gate succeeds; it SHALL NOT alter the session aggregate's immutable null field, active pointer, retirement, or rollover commit identity.

NQ and YM SHALL be evaluated independently. One symbol's committed context cannot authorize or repair the other.

## 12. Divergence handling

If a required authoritative receiver-lock, canonical Entry Agent, frozen-ladder, observation, or authorization materialization differs in session or commit ID:

- enter `SESSION_PROJECTION_DIVERGED`;
- block entries;
- preserve every record;
- publish mismatch identities and first divergence;
- retry exposure from the committed aggregate when safe; and
- require governed recovery/replay when the authoritative commit itself is ambiguous.

Newest timestamp, file modification time, receiver cache, test projection, or prior-session fallback SHALL NOT resolve authority.

A status or Command Center display mismatch SHALL fail only its observational projection-alignment gate and remain visible with the first mismatch. It SHALL NOT write `SESSION_PROJECTION_DIVERGED`, change the active aggregate, veto or close an authoritative session transition, or supply session/authorization authority. The separately mandatory parity gate SHALL keep startup and entries blocked without reclassifying the committed session.

## 13. Failure and recovery table

| Failure | Canonical result | Exposure/result |
|---|---|---|
| Candidate validation fails | no new commit; prior canonical history preserved | candidate rejected/archived; current session remains blocked |
| Commit write/flush/verification fails | no new commit | no new current exposure; pending evidence retained |
| Crash before commit | no new commit | candidate MAY be reprocessed idempotently |
| Crash after commit before projection | committed new aggregate controls | projections retry under same commit ID; fail closed until coherent |
| Duplicate accepted candidate | existing commit returned | no reset, retirement, or duplicate exposure effect |
| Different later candidate for locked session | rejected/quarantined | no mutation absent separately governed correction |
| Prior-session payload | historical/rejected as applicable | never current |
| Prior canonical session exists after its trading date with no valid current candidate | prior record remains history/evidence and enters `STALE_PRIOR_SESSION_BLOCKED` | no current-session exposure or authorization |
| Startup aggregate lacks/mismatches `trade_authorization_context_binding` or `authorized_session_rollover_commit_id` | current-labeled aggregate is incomplete/diverged; prior binding cannot be inherited | startup/entries blocked; recover only from verified committed aggregate or governed replay |
| Session store cannot commit/read back | `SESSION_STORE_DEGRADED` | no activation, retirement, repair, or projection fallback; startup/entries blocked |
| Session store is corrupt, partial, or identity-inconsistent | `SESSION_STORE_CORRUPT` | quarantine/governed recovery required; no current authority inferred |

## 14. Read-side rule

Status, health, debug, Command Center, and audit GET/HEAD requests SHALL NOT receive candidates, perform validation with side effects, commit rollovers, initialize observation, repair projections, or persist state.

## 15. Required verification

Verification SHALL include exact NQ/YM prior-to-current replay, valid first-lock exactly once, invalid lock fail-closed, duplicate/stale/out-of-order cases, crash injection before/during/after the atomic active-pointer/prior-retirement/authorization-binding update, proof that no split activation/retirement state can commit, both authorization fields on candidate/aggregate/commit/retirement/startup and every later opening request/decision, every state-table entry/exit/restart/retry path including `CANDIDATE_REJECTED` and `COMMIT_FAILED`, pending exposure, restart restore, all store failure states, observation coupling, explicit divergence detection, receiver/canonical/Command Center equality, separate public-route and sender-authentication proofs, and negative sender/replay cases.

## 16. Expected Implementation and Verification

Expected implementation areas:

- `EntryAgent/tv_context_server.py` candidate archive/validation/transaction entry;
- `EntryAgent/entry_agent.py` aggregate, observation, authorization, restore, and projection;
- approved session transaction persistence helper/store;
- Entry status and Command Center serializers; and
- startup session/readiness probes.

Expected verification areas:

- ADR-014 atomic rollover suite;
- archived 2026-07-16 to 2026-07-17 NQ/YM replay;
- crash/restart and status-purity suites; and
- isolated cold/manual startup integration.

Traceability: `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md`.

Clause-level traceability: every normative clause in this draft is assigned a stable `ESR-REQ-###` identity with forward and reverse verification mapping in `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md`. The external recovery matrix is a package-level index only and SHALL NOT substitute for the clause-level registry.
