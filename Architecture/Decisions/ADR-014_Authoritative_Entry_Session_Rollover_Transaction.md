# ADR-014 - Authoritative Entry Session Rollover Transaction

## 1. Status

**APPROVED - GOVERNING ARCHITECTURE DECISION**

**Draft date:** 2026-07-17

**Approval date:** 2026-07-17

**Approval authority:** Explicit user architecture approval.

**Approved content SHA-256:** `BD76D1B398515EA00E230B9C8A00A540344E061A36B228BF112F784F6AC34F25`

**Approval binding:** Approval is bound exclusively to the file content identified by the approved SHA-256 above. That hash was verified immediately before this governance-only metadata application; no substantive decision text was amended.

**Implementation authorization:** None. Approval of this architecture decision does not authorize production code changes, persistence repair, process start, runtime verification, deployment, production `READY_LOCKED`, entry-lock clearing, or trading.

## 2. Context

The 2026-07-17 production incident preserved a valid current-session TradingView receiver payload while the canonical Entry Agent session remained on the prior date. The receiver's current projection, observation-reset date, frozen ladder, and canonical session authorization did not advance through one transaction.

The Constitution already requires a formal session transition, prior-session preservation, durable state before exposure, session isolation, and fail-closed behavior. The Session Liquidity Lock Contract already defines the first valid post-06:15 table as the session input. Existing authority does not define one indivisible commit joining receipt, validation, frozen lock, observation state, canonical Entry Agent state, session authorization, exposure, and prior-session retirement.

This missing transaction allowed two different session identities to appear as current truth on different surfaces.

## 3. Decision

### 3.1 Authoritative invariant

For each supported symbol, the current Entry session changes only through one indivisible Session Rollover Transaction. The transaction SHALL construct the complete candidate state without mutating the active state, durably commit one shared rollover identity across every authoritative member, and expose the new session only after durable success.

The prior aggregate SHALL remain immutable canonical history if validation or persistence fails. At the effective trading-date boundary it SHALL cease active/current applicability even when no replacement commit exists. It SHALL NOT authorize, seed, repair, or satisfy readiness for the new session. Until a valid current-session commit succeeds, the symbol SHALL be `STALE_PRIOR_SESSION_BLOCKED` or `NO_CURRENT_SESSION_CONTEXT` and SHALL remain nontradable.

A successful current-session commit SHALL atomically record the prior aggregate as historical/inactive and the new aggregate as active. A failed candidate SHALL leave the prior bytes and event history unchanged, but SHALL NOT restore the prior aggregate to active applicability or use it as fallback.

### 3.2 Authority ownership

- TradingView owns the transmitted source payload and its source timestamp/version.
- The receiver owns receipt validation and immutable candidate evidence archival.
- The Session-lock policy owns candidate lock eligibility and the rollover decision.
- The Entry Agent Session Commit Writer is the sole writer of the canonical session-lock fact, authoritative Entry Session Aggregate, per-symbol active pointer, and durable projection source.
- Entry Agent lifecycle evaluation consumes the committed aggregate and SHALL NOT independently advance the session-lock fact or active pointer.
- The Liquidity Level aggregate owns the frozen levels, stack membership, boundaries, and provenance produced by the committed lock.
- The observation owner owns pre-open observation values only within the committed current session.
- Command Center owns display projection only.
- Rithmic bars, ATR, a sender flag, a raw receiver cache, a test projection, and process availability cannot create or advance the canonical session commit.

### 3.3 Candidate identification

The receiver SHALL identify a `Candidate Current-Session Payload` from the complete accepted request object. Candidate identity SHALL include at least:

- receipt event ID;
- raw and normalized symbol;
- effective session date and time zone;
- source timestamp and receipt timestamp;
- payload schema/version;
- source identity;
- sender lock assertion when present;
- complete liquidity rows and statuses;
- explicit and row-derived stack/owner evidence;
- frozen threshold and market-side reference inputs; and
- a deterministic payload identity or content hash.

The candidate archive is noncurrent evidence. Archiving a July 17 candidate while July 16 remains active does not make the candidate a current raw-receiver truth surface.

A sender field such as `locked=true` is an input assertion required by the applicable webhook contract. It is never the receiver's canonical lock fact, rollover commit, or proof of durable state.

### 3.4 Validation before mutation

Before building or committing a rollover, the Session-lock layer SHALL validate:

1. complete payload shape and required fields;
2. supported and normalized symbol;
3. effective session identity and authorized lock window;
4. source timestamp, time zone, version, and ordering;
5. duplicate, stale, out-of-order, and prior-session handling;
6. sender/source authority;
7. all required Liquidity Level identities, states, prices, and provenance;
8. stack membership, reciprocal ownership, numbering, side, threshold, and structural rules under the separately governing liquidity contract;
9. explicit stack objects against row membership;
10. frozen-ladder ordering, boundaries, anchors, midpoint/exhaustion inputs where applicable; and
11. absence of an already committed different lock for the candidate session.

Validation SHALL operate on the complete candidate and SHALL NOT clear, retire, overwrite, or mutate the active canonical session.

#### 3.4.1 External TradingView trust boundary

ADR-014 separates three facts that SHALL NOT be treated as interchangeable:

1. `PUBLIC_ROUTE_TRAVERSAL_VERIFIED` proves that one request entered through the deployment-authorized public hostname, was received by the configured relay after tunnel activation, and was forwarded byte-for-byte to the Entry receiver under one receipt ID and payload hash.
2. `PAYLOAD_SESSION_ELIGIBLE` proves that the payload's schema/version, source and receipt times, effective session, lock window, symbol, ordering, duplicate identity, and complete content satisfy this ADR and the webhook/session contracts.
3. `SENDER_IDENTITY_AUTHENTICATED` proves that a separately approved sender-authentication authority authenticated the sender identity and cryptographically bound that identity to the exact payload bytes and freshness/replay evidence.

Public hostname, `Host`, source IP, user-agent text, TLS transport to the public endpoint, relay receipt, receipt time, payload timestamp, `session_date`, `locked=true`, or a payload hash SHALL NOT by themselves establish `SENDER_IDENTITY_AUTHENTICATED`. Route traversal proves a path, not a sender. Payload/session validation proves eligibility of content, not who sent it.

The production implementation evidenced on 2026-07-17 has no governed sender-identity authentication mechanism. It records route metadata and accepts JSON without a signature, authenticated principal, nonce, or sender-bound replay proof. Source timestamp and session date are sender assertions and may be absent; receipt-time fallback establishes receiver observation time only. Same-session locking and deterministic payload/commit identity can make an already accepted candidate idempotent, but they do not prevent an unauthenticated party from submitting the first candidate or replaying bytes before canonical commitment.

ADR-014 does not select or invent an authentication mechanism. Its transaction and rollover invariants are independently approvable, but a candidate SHALL NOT become a production current-session commit unless the separately governed sender-authentication result is `VERIFIED` for the exact receipt ID and payload hash. `UNAVAILABLE`, `FAILED`, identity/payload mismatch, or replay ambiguity SHALL archive the request as noncurrent evidence, leave the prior canonical bytes unchanged, make the prior session inapplicable after its date boundary, and keep the symbol fail-closed.

Production startup SHALL distinguish route traversal from sender authentication and SHALL fail with `WEBHOOK_SENDER_AUTHENTICATION_UNAVAILABLE` or the exact validation failure until both are positively proven. This unresolved security obligation is tracked separately as `DEBT-2026-07-17-016`; it is not merged into the session-rollover implementation scope and does not weaken the atomicity required by this ADR.

ADR-014 does not define or amend the stack-overlap rule. `DEBT-2026-07-17-015` remains separately governed. The rollover transaction consumes the structurally valid/invalid result produced by the then-approved liquidity contract without making that contract part of this recovery decision.

### 3.5 Complete candidate canonical state

After validation and before active-state mutation, the transaction SHALL build a complete immutable candidate aggregate containing at least:

- symbol and session identity;
- receiver receipt/payload identity;
- candidate session lock and lock time;
- complete frozen Liquidity Level map;
- explicit stack objects and resolved distinct ladder owners;
- complete ordered frozen ladder and derived entries authorized by the liquidity contract;
- canonical Entry Agent session/lifecycle baseline;
- pre-open observation state initialized for the new session;
- observation-reset identity;
- session-context authorization state;
- `trade_authorization_context_binding`, initialized as `BLOCKED_PENDING_RUNTIME_GATES` and containing symbol, session ID/date, and proposed rollover commit ID;
- source/version/provenance fields;
- prior active-session identity and historical archive reference;
- rule and schema versions; and
- the proposed rollover commit ID.

The candidate SHALL be complete and internally coherent before persistence begins. No projection file SHALL be treated as the authoritative candidate aggregate.

### 3.6 Shared rollover commit identity

One `session_rollover_commit_id` SHALL identify one symbol/session rollover transaction. It SHALL be stable for duplicate processing of the same accepted candidate and SHALL be bound to at least the symbol, effective session, accepted receipt/payload identity, and rollover contract version.

Every artifact labeled current, active, ready, authoritative, or exposed SHALL materialize the identical `session_rollover_commit_id`, symbol, session ID, session date, aggregate version, and aggregate integrity identity in its own serialized record. An indirect path reference, filename convention, modification time, or newest-file inference SHALL NOT satisfy this requirement. A projection that is missing or lacks the identity SHALL be treated as unexposed and fail-closed; it SHALL NOT be interpreted as a partial authority.

The identical materialized commit ID SHALL appear in:

- the receiver's committed session lock;
- canonical Entry Agent session state;
- every frozen ladder/level aggregate created by the transition;
- observation state and observation-reset state;
- session-context authorization state;
- trade-authorization context binding and every later opening-entry authorization request/decision;
- prior-session retirement record;
- exposure/publication records; and
- replay/audit evidence.

NQ and YM use independent per-symbol rollover commits. A composite startup/readiness result MAY reference both commit IDs but SHALL NOT merge them or allow one symbol's commit to authorize the other.

### 3.7 Indivisible commit and exposure sequence

The authoritative order SHALL be:

```text
CANDIDATE_RECEIVED
  -> CANDIDATE_ARCHIVED_NONCURRENT
  -> CANDIDATE_VALIDATED
  -> CANDIDATE_STATE_BUILT
  -> ROLLOVER_COMMITTING
  -> ROLLOVER_COMMITTED
  -> CURRENT_SESSION_EXPOSED
```

The transition SHALL:

1. acquire exclusive per-symbol rollover authority;
2. recheck current commit/version and duplicate identity;
3. begin one authoritative transaction and write the complete candidate aggregate, prior-session retirement, and new per-symbol active pointer without exposing the uncommitted state;
4. commit that transaction under `synchronous=FULL` and read back the aggregate, retirement record, active pointer, commit identity, version, and integrity identity;
5. expose receiver/current, Entry Agent, frozen-ladder, observation, authorization, and Command Center projections only from the verified commit; and
6. publish post-commit audit evidence.

The active pointer, prior-session retirement, and candidate aggregate SHALL become visible together at the durable transaction commit. No component SHALL observe or act on the uncommitted pointer value.

Multiple independently authoritative JSON writes do not satisfy indivisibility. If compatibility requires multiple files, one durable transaction record/aggregate SHALL determine authority; the files are commit-ID-bearing projections that MAY be retried after commit.

#### 3.7.1 Concrete authoritative store

`Entry Agent Session Commit Writer` SHALL use one local nonsynchronized SQLite control store at the absolute path resolved once at startup from `%LOCALAPPDATA%\RandleRuntimeData\control\entry_session_v1.sqlite3`. The resolved absolute path SHALL be recorded in startup evidence.

The store SHALL use one serialized writer connection, WAL journaling, `synchronous=FULL`, `foreign_keys=ON`, explicit schema/version records, `BEGIN IMMEDIATE` transaction boundaries, per-symbol compare-and-swap active versions, integrity verification, and one transaction that inserts the complete candidate commit and advances the active per-symbol pointer.

Receiver-current, frozen-ladder, observation, status, and Command Center files SHALL be projections only. No other process, module, status route, startup tool, or override path SHALL write the active pointer. Store unavailability or failed integrity verification SHALL produce `SESSION_STORE_DEGRADED` or `SESSION_STORE_CORRUPT` and SHALL block exposure and opening entries.

### 3.8 Prior-session retirement and preservation

Before the new commit succeeds, the prior aggregate remains intact as canonical historical truth. At the effective trading-date boundary it is inactive and ineligible for current-session readiness, entry authorization, session seeding, projection repair, or fallback.

The prior aggregate SHALL NOT be cleared, deleted, or rewritten in advance. Successful new-session commit SHALL atomically:

- preserve the prior canonical aggregate and event history unchanged;
- close its active-session applicability;
- mark its operator projection historical/inactive;
- record the superseding rollover commit ID; and
- prevent it from becoming a fallback for the new session.

Failure before commit leaves the prior record bytes and event history unchanged. It SHALL NOT make the prior session active or eligible as current-session input.

### 3.9 Observation-reset coupling

The observation-reset latch SHALL NOT advance from a Rithmic bar, status read, webhook pre-processing step, process startup, or projection refresh.

New-session observation initialization and `observation_reset_session_date` SHALL be members of the same rollover aggregate and carry the same commit ID. Duplicate application of the same commit is a no-op. No independent once-per-session latch SHALL make the session appear advanced before the frozen lock commits.

### 3.10 Session-context authorization

Session-context authorization states SHALL be explicit:

```text
NO_CURRENT_SESSION_CONTEXT
STALE_PRIOR_SESSION_BLOCKED
CANDIDATE_PENDING
COMMITTING
COMMITTED_FAIL_CLOSED
CURRENT_CONTEXT_READY
SESSION_PROJECTION_DIVERGED
SESSION_STORE_DEGRADED
SESSION_STORE_CORRUPT
```

`CURRENT_CONTEXT_READY` means only that the canonical session context transaction is coherent. It does not authorize a trade. Entry release still requires every independent runtime, lifecycle, risk, and execution precondition.

The rollover aggregate SHALL contain a `trade_authorization_context_binding` initialized as `BLOCKED_PENDING_RUNTIME_GATES` and containing symbol, session ID, session date, and `session_rollover_commit_id`. Every later opening-entry authorization request and decision SHALL carry `authorized_session_rollover_commit_id`. The authorization owner SHALL reject the request unless that ID equals the currently exposed verified rollover commit for the same symbol/session. A rollover commit SHALL NOT itself grant trading permission, and a later authorization decision SHALL NOT alter session identity.

`COMMITTED_FAIL_CLOSED` covers a committed context whose downstream identities are not yet coherent. `SESSION_PROJECTION_DIVERGED` is required when any current-labeled receiver/canonical/observation/frozen-ladder surface reports a different session or commit ID.

### 3.11 Raw/canonical divergence rule

A received candidate from another session MAY exist as noncurrent archived evidence. A raw receiver `current` projection and canonical production state SHALL NOT present different session or commit identities as normal operation.

If restore or audit detects a mismatch, the system SHALL:

- enter `SESSION_PROJECTION_DIVERGED`;
- keep entry authorization blocked;
- preserve both records unchanged;
- identify every mismatched session/commit surface;
- expose the first divergence for audit; and
- recover only from the authoritative committed aggregate or a governed replay procedure.

It SHALL NOT select the newest file, copy a test projection, clear the old lock, or infer authority from process time.

### 3.12 Failure, duplicate, and crash behavior

- Validation failure archives the rejected candidate and leaves active canonical state unchanged.
- Persistence failure leaves the transition uncommitted, preserves pending candidate/evidence, and exposes no new current session.
- A duplicate of the same accepted candidate returns the prior commit identity and creates no new reset, ladder, or retirement.
- A different candidate for an already committed session is rejected unless a separately approved correction/override procedure governs it.
- A stale or prior-session candidate cannot replace a newer committed session.
- After a crash, restoration SHALL find either one complete committed rollover or no committed rollover. A partial current session is prohibited.
- Committed but incompletely exposed projections remain pending exposure under the same commit ID and cannot revoke the commit.

### 3.13 Startup restoration and recovery

Startup SHALL use this complete decision table:

| Startup evidence | Required state and action |
|---|---|
| Verified current-session aggregate and every present current artifact has the same complete commit identity | Restore the aggregate; regenerate missing projections under the same commit; remain `COMMITTED_FAIL_CLOSED` until all required exposures verify; then permit `CURRENT_CONTEXT_READY`. |
| Verified committed aggregate with missing/partial exposure artifacts | The aggregate remains canonical; missing artifacts are pending exposure, never alternate authority; entries remain blocked until convergence. |
| Current-labeled artifacts disagree on session, commit, aggregate version, or integrity identity | Enter `SESSION_PROJECTION_DIVERGED`; preserve all artifacts; newest-file, date, or process-time fallback is prohibited. |
| Authoritative session store is corrupt, has a sequence gap, or cannot establish one verified active pointer | Enter `SESSION_STORE_CORRUPT`; do not recover from raw receiver, frozen JSON, status, test projection, or prior session; the Entry Agent startup result is `FAILED`. |
| Valid current-session candidate exists while only a stale prior aggregate is committed | Keep the candidate noncurrent; keep the prior aggregate historical/ineligible; execute the normal validate-build-commit transaction exactly once; remain blocked until success. |
| No current-session payload and no current-session commit | Restore prior history only as nonauthoritative archive; enter `NO_CURRENT_SESSION_CONTEXT`/WAIT. |
| Current-labeled artifact has no materialized commit ID | Treat it as invalid/unexposed and fail-closed; it SHALL NOT establish current authority. |

Startup restoration SHALL read the authoritative Entry Session Aggregate and active pointer before any compatibility projection. It SHALL verify schema, integrity, active version, materialized commit identities, and session-date applicability before exposure.

## 4. Consequences

- The receiver archive and receiver current projection become different concepts.
- Session rollover becomes a domain transaction rather than a sequence of clears/writes.
- The observation latch cannot lead the session lock.
- Prior sessions remain auditable without remaining active.
- Projection exposure MAY lag a durable commit, but every lag SHALL be explicit and fail-closed.
- Existing multi-file persistence requires an authoritative transaction record or transactional store before conformance can be claimed.

## 5. Scope and isolation

This ADR governs Entry session identity, session-lock commit, frozen-ladder custody during rollover, observation initialization, session-context authorization, and projection exposure for NQ and YM.

It does not change Pine, webhook field meanings other than distinguishing assertions from receiver commit facts, stack calculation/overlap rules, ATR mathematics, Step 2, Step 4, Trade Manager state, Executor behavior, execution, risk, or Command Center test-mode authorization.

DEBT-015 remains outside ADR-014 implementation and cannot delay the three-defect recovery unless a later evidence-backed AIA proves a direct dependency. Such a finding requires its own approved change to scope.

## 6. Required verification

Verification SHALL cover:

- prior-session-to-current-session replay for NQ and YM;
- exact valid 06:15 candidate committing once;
- duplicate idempotency;
- invalid/incomplete/unauthorized candidate preserving prior canonical history and remaining fail-closed;
- observation-reset inability to advance independently;
- crash injection before and after every commit boundary;
- committed-but-unexposed retry under one commit ID;
- restore from the authoritative commit rather than raw projections;
- explicit divergence detection for every session/commit surface;
- no prior-session fallback;
- raw receipt, canonical Entry ladder, and Command Center projection equality after exposure;
- public-route traversal and sender-authentication proofs independently positive, plus negative tests for user-agent/host spoof, absent timestamp, payload replay, duplicate receipt, identity/payload mismatch, and unavailable authentication authority; and
- unchanged single-stack/no-stack/current structural-validator behavior.

## 7. Relationship to existing authority and proposed amendments

- Constitution sections 3, 6, 12-17, 20, and 22 remain governing.
- Lifecycle Engine sections 11.3, 15-18, 26-32, 34-35, 39-40, and 43 remain governing.
- ADR-012 durable-before-exposure, input evidence, rehydration, and read-side separation remain governing.
- This ADR supplies the missing session aggregate, shared commit identity, exact transaction order, observation coupling, and explicit divergence behavior.
- Runtime Authority, Lifecycle Vocabulary, Lifecycle Engine session-rollover text, Session Liquidity Lock Contract, TradingView Webhook Contract, verification specifications, and startup/readiness contracts require the draft amendments registered for this decision.

## 8. Rejected alternatives

Rejected: recognizing more lock flags without a transaction; clearing prior state before commit; advancing observation from market data before lock; treating archive receipt as current truth; choosing the newest projection file; sequentially declaring several files authoritative; copying Command Center test state; manual lock repair; prior-session fallback; and weakening structural validation.

## 9. Architectural Exit Criteria

### What invariant now exists?

One shared commit identity atomically advances receiver lock, canonical Entry Agent state, frozen ladders, observation state, session-context authorization, exposure, and prior-session retirement for one symbol/session.

### Why was the previous architecture insufficient?

It required formal rollover, durability, and first-valid locking but did not join every session-bearing owner into one crash-consistent commit or prohibit observation/session projection from advancing separately.

### What future implementations are constrained?

Every receiver, Entry Agent persistence path, session reset, frozen-ladder restoration path, operator override, replay tool, readiness route, and Command Center current-session projection.

### How would an implementation violate this ADR?

By exposing a candidate before durable commit; using different commit IDs; clearing prior state first; advancing observation independently; treating a sender flag as the canonical lock; restoring from a raw projection; or presenting mismatched session identities without `SESSION_PROJECTION_DIVERGED` and a fail-closed block.

## 10. Expected Implementation and Verification

### Expected Implementation Areas

- `EntryAgent/tv_context_server.py`: candidate receipt/archive, complete validation, rollover transaction invocation, commit-ID projection, and noncurrent/current separation;
- `EntryAgent/entry_agent.py`: canonical session aggregate, observation initialization, session-context authorization, restoration, and divergence checks;
- the concrete Entry Agent Session Commit Writer and local SQLite store defined by section 3.7.1;
- Command Center/status serializers that expose session/commit identity without mutation; and
- startup readiness probes that compare committed identities rather than raw-file dates.

### Verification Areas

- dedicated ADR-014 rollover/atomicity/crash-injection suite;
- archived July 16-to-July 17 NQ/YM replay;
- Entry Agent status nonmutation and restart/recovery suites;
- received/canonical/Command Center parity evidence; and
- isolated cold/manual startup verification under the Runtime Recovery Verification Specification draft.

### Traceability Record

Draft and future conformance mappings are registered in `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md`.
