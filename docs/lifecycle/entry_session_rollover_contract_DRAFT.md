# Entry Session Rollover Lifecycle Contract

Version: Draft 0.5 - Phase 3C1 normative remediation

Status: **DRAFT - NOT CANONICAL - NOT APPROVED**

Governing Dependency: ADR-014 is approved and governs this draft. This contract remains draft/noncanonical; Constitution sections 6, 12-17, and 22 and the current canonical Lifecycle Engine remain governing. Proposed Runtime Authority amendments remain noncanonical.

Implementation Authorization: None

## 1. Purpose

Define the executable lifecycle contract for changing the current Entry session without allowing receiver lock, canonical Entry Agent state, frozen ladder, observation state, session-context authorization, or Command Center projection to advance independently.

## 2. Aggregate and owner

The `Entry Session Aggregate` is per logical symbol. Approved ADR-014 assigns the Session-lock policy sole candidate lock eligibility and rollover-decision authority. The `Entry Agent Session Commit Writer` is the sole canonical durable writer, atomic transaction executor, and owner of the active-session pointer. The receiver produces receipt/archive evidence; the Session-lock Validator produces structural validation evidence for the policy; and the Entry Session Store Integrity Validator produces persistence/constraint/readback evidence. The Commit Writer may mechanically reject a malformed, stale, unauthorized, version-conflicting, or constraint-invalid write request, but that mechanical rejection does not transfer business-policy rollover-decision authority from the Session-lock policy. Entry Agent consumes the committed aggregate and owns no independent session identity, observation-reset identity, frozen-ladder activation, or authorization activation.

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

| State | Triggering fact/event | Evidence producer | Eligibility authority | Rollover/state-decision authority | Transition authorization | Durable writer / executor | Durable evidence | Exact legal destinations; all unlisted destinations prohibited | Retry and restart behavior | Active-session / opening-entry effect |
|---|---|---|---|---|---|---|---|---|---|---|
| `NO_CURRENT_SESSION_CONTEXT` | Current-date evaluation finds no applicable commit | Session expectation evaluator and read-only store validator | Session-lock policy | Session-lock policy | policy decision plus verified cursor | Entry Agent Session Commit Writer | symbol/date expectation, cursor, policy decision, null authorized commit | `CANDIDATE_PENDING`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` | restore identically; no synthetic candidate | no active session; entries blocked |
| `STALE_PRIOR_SESSION_BLOCKED` | Date boundary makes prior commit inapplicable | Session expectation evaluator | Session-lock policy | Session-lock policy | decision bound to prior/current date | Entry Agent Session Commit Writer | prior session/commit, dates, reason, null new-date authorization | `CANDIDATE_PENDING`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` | prior never retries as current | prior historical/inactive; entries blocked |
| `CANDIDATE_PENDING` | Receiver archives immutable current-session candidate | Receiver | Session-lock policy | Session-lock policy | policy-signed candidate registration | Entry Agent Session Commit Writer | receipt/payload/session/source/authentication and active version | `CANDIDATE_VALIDATED`, `CANDIDATE_REJECTED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` | exact duplicate idempotent | active authority unchanged; entries blocked |
| `CANDIDATE_VALIDATED` | Complete structural/authority validation succeeds | Session-lock Validator and sender-authority validator | Session-lock policy | Session-lock policy | decision bound to validation/aggregate hashes and expected version | Entry Agent Session Commit Writer | policy/validator identities, result and candidate aggregate hashes | `COMMITTING`, `CANDIDATE_REJECTED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` | restart revalidates identity/version | active authority unchanged; entries blocked |
| `CANDIDATE_REJECTED` | Validation/precommit policy check fails | exact failing validator | Session-lock policy | Session-lock policy | rejection bound to candidate/result hash | Entry Agent Session Commit Writer | immutable rejection, candidate, policy/version, active version | `CANDIDATE_PENDING`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` | only a new candidate identity enters pending; duplicate returns rejection | active authority unchanged; entries blocked |
| `COMMITTING` | Policy issues exact rollover and writer accepts authorized request | Session-lock policy decision plus Store Integrity Validator preflight | Session-lock policy | Session-lock policy | writer verifies authorization/hashes/version/constraints | Entry Agent Session Commit Writer | transaction/commit/policy IDs, expected version, aggregate, retirement, both authorization fields | `CURRENT_CONTEXT_READY`, `COMMIT_FAILED`, `COMMITTED_FAIL_CLOSED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` | restart resolves exact COMMIT/readback before retry | invisible until complete commit; entries blocked |
| `COMMIT_FAILED` | Precommit rollback is proven or commit result is unresolved | Entry Session Store Integrity Validator | Session-lock policy remains owner | Store Integrity Classifier classifies mechanical result only | failure classification and preserved policy decision | Entry Agent Session Commit Writer | failure stage/result, candidate, preserved active version, no-commit or ambiguity evidence | `COMMITTING`, `CANDIDATE_REJECTED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` | `COMMITTING` only after durable no-commit proof and policy revalidation; ambiguity goes corrupt | no activation/retirement; entries blocked |
| `COMMITTED_FAIL_CLOSED` | Commit is durable but exposure/readiness proof incomplete | commit readback and authoritative domain owners | committed Session-lock policy decision | Runtime-gate evaluator decides only exposure state | committed aggregate plus incomplete-gate evidence | Entry Agent Session Commit Writer | aggregate/pointer/retirement/cursors/shared ID/binding | `CURRENT_CONTEXT_READY`, `SESSION_PROJECTION_DIVERGED`, `STALE_PRIOR_SESSION_BLOCKED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` | restore same commit and resume exposure | canonical current; opening entries blocked |
| `CURRENT_CONTEXT_READY` | All required authoritative exposures agree | authoritative domain owners and pure comparator | committed Session-lock policy decision | Runtime-gate evaluator decides only ready exposure | complete identity proof | Entry Agent Session Commit Writer | exposure identities, pointer, commit, runtime gate, binding | `CANDIDATE_PENDING`, `STALE_PRIOR_SESSION_BLOCKED`, `SESSION_PROJECTION_DIVERGED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` | restart re-verifies; memory insufficient | separate opening-entry authorization still required |
| `SESSION_PROJECTION_DIVERGED` | Required current-labeled surface mismatches canonical commit | surface owner and pure comparator | committed Session-lock policy unchanged | Runtime-gate evaluator classifies mismatch | canonical/mismatch evidence | Entry Agent Session Commit Writer | canonical identity, surfaces, first mismatch, detector | `COMMITTED_FAIL_CLOSED`, `CURRENT_CONTEXT_READY`, `STALE_PRIOR_SESSION_BLOCKED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` | repair only from canonical aggregate and reverify | canonical retained; entries blocked |
| `SESSION_STORE_DEGRADED` | I/O/readback unavailable without proven corruption | Entry Session Store Integrity Validator | Session-lock policy blocked from advancing eligibility | Store Integrity Classifier | exact failure/cursor classification | Entry Agent Session Commit Writer when writable; external evidence uses Runtime Authority Recovery Evidence Writer | I/O/contention failure, last verified cursor/active identity, external recovery record when needed | `NO_CURRENT_SESSION_CONTEXT`, `STALE_PRIOR_SESSION_BLOCKED`, `COMMITTED_FAIL_CLOSED`, `CURRENT_CONTEXT_READY`, `SESSION_STORE_CORRUPT` | only section 3.2 classification mapping may exit; no projection fallback | no new activation/authorization; entries blocked until mapped result commits |
| `SESSION_STORE_CORRUPT` | Integrity/sequence/identity/commit verification fails | Entry Session Store Integrity Validator | Session-lock policy blocked | Store Integrity Classifier classifies corruption; Recovery Authorization controls file action | exact corruption and completed recovery evidence | Entry Agent Session Commit Writer writes state when possible; Runtime Authority Recovery Evidence Writer writes external evidence only | incident, failed checks, quarantine/restore/reinitialize evidence | `NO_CURRENT_SESSION_CONTEXT`, `STALE_PRIOR_SESSION_BLOCKED`, `COMMITTED_FAIL_CLOSED`, `CURRENT_CONTEXT_READY` | only completed section 3.2 recovery mapping may exit; no automatic retry/import | no authority inferred; entries blocked until mapped result commits |

### 3.2 Exact degraded/corrupt recovery transitions

The Entry Session Store Integrity Validator is the recovery-evidence producer for read-only integrity, schema, cursor, commit, active-pointer, retirement, authorization-binding, and exposure checks. The Recovery Controller produces file-operation evidence. The Runtime Authority Recovery Evidence Writer defined by the Runtime Authority Store Schema is the sole writer of the external canonical recovery JSONL chain when the Entry Session store is unavailable or corrupt. It writes evidence only and cannot decide a session transition.

The Entry Session Store Integrity Classifier is the sole authority for one of these closed storage classifications:

| Classification | Exact proof | Exact destination |
|---|---|---|
| `EMPTY_VERIFIED` | healthy identified store, zero current commit, zero ambiguous/uncommitted transaction | `NO_CURRENT_SESSION_CONTEXT` |
| `PRIOR_ONLY_VERIFIED` | healthy identified store, exactly one internally consistent prior-date commit, no current-date commit | `STALE_PRIOR_SESSION_BLOCKED` |
| `CURRENT_COMMIT_VERIFIED_EXPOSURE_UNVERIFIED` | healthy identified store, exact current aggregate/pointer/retirement/bindings commit, incomplete exposure parity | `COMMITTED_FAIL_CLOSED` |
| `CURRENT_COMMIT_AND_EXPOSURE_VERIFIED` | the prior classification plus exact canonical/runtime/projection identity equality | `CURRENT_CONTEXT_READY` |
| `CORRUPTION_CONFIRMED` | any failed integrity/schema/cursor/identity/commit-chain check | `SESSION_STORE_CORRUPT` |

For `SESSION_STORE_DEGRADED`, a fresh read-only recovery validation must produce exactly one classification. Session-lock policy consumes that classification and is the sole authority deciding its eligibility effect and authorizing the corresponding table destination; it cannot alter the classification. Entry Agent Session Commit Writer alone compare-and-swaps the current state/version and writes the transition under the exact classification/evidence identity. `CORRUPTION_CONFIRMED` moves to `SESSION_STORE_CORRUPT`; the four verified classifications move to their one mapped destination.

For `SESSION_STORE_CORRUPT`, quarantine alone has no clearing effect. A completed authorized restore or reinitialization must be present in the verified external chain, its activated store hash must match the file, and the new store must pass read-only validation. Reinitialization may yield only `EMPTY_VERIFIED -> NO_CURRENT_SESSION_CONTEXT`; it cannot import current/prior authority. A restore may yield any of the four verified classifications only when its exact governed backup preserved the Entry Session store identity and commit chain. Unidentified legacy/projected data never yields a verified classification. Session-lock policy then authorizes only the mapped destination, and Entry Agent Session Commit Writer performs the sole state transition.

Every recovery request has an idempotency key and evidence hash. Same key/same evidence returns the committed classification/transition; changed evidence conflicts. A crash before the Entry Agent Session Commit Writer commit leaves the failure state. A crash after commit reconstructs the mapped destination from state version/transition/evidence and never repeats a file action. Failed/unavailable validation leaves the current failure state; restart re-verifies the external chain and store before any retry. No recovery record itself authorizes rollover, readiness, opening entry, deployment, or trading.

Only the named decision authority may decide its stated fact, and only the Entry Agent Session Commit Writer may durably write or execute the Entry Session transaction. A read, projection, receiver cache, startup script, Session-lock Validator, Entry lifecycle evaluator, integrity classifier, or Command Center SHALL NOT acquire rollover-decision authority or write a transition.

Every state transition not listed as a permitted exit in section 3.1 is prohibited for all twelve declared states. A retry, restart, projection repair, operator action, later candidate, date boundary, or store recovery SHALL use only the exit explicitly named in the current state's row; it SHALL NOT synthesize an intermediate state, reopen a terminal candidate outcome, bypass `COMMIT_FAILED` resolution, or mutate active-session authority outside the Entry Agent Session Commit Writer transaction.

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

Verification SHALL include exact NQ/YM prior-to-current replay, valid first-lock exactly once, invalid lock fail-closed, duplicate/stale/out-of-order cases, crash injection before/during/after the atomic active-pointer/prior-retirement/authorization-binding update, proof that no split activation/retirement state can commit, both authorization fields on candidate/aggregate/commit/retirement/startup and every later opening request/decision, every state-table entry/exit/restart/retry path including `CANDIDATE_REJECTED`, `COMMIT_FAILED`, `SESSION_STORE_DEGRADED`, and `SESSION_STORE_CORRUPT`, pending exposure, restart restore, observation coupling, exact `SESSION_PROJECTION_DIVERGED` detection, receiver/canonical/Command Center equality, separate public-route and sender-authentication proofs, and negative sender/replay cases.

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

Clause-level traceability is not complete. `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md` is preserved only as historical rejected Phase 3B evidence. Semantic forward/reverse mappings for this amended draft are intentionally deferred to Phase 3C2 and may be rebuilt only from independently accepted Phase 3C1 hashes. The external recovery matrix remains a package-level index and is not a substitute.
