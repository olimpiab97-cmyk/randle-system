# 2026-07-17 Coordinated Authority Package - Approval Review

Document Type: Decision package submitted for explicit approval action

Status: **REVIEW COMPLETE - NONCANONICAL REVIEW RECORD - ADR-014 SUBSEQUENTLY APPROVED BY EXPLICIT USER ACTION**

Implementation/Canonical Amendment/Restart/Deployment/Trading Authorization: **NONE**

## 1. Required decisions

| Candidate | Decision |
|---|---|
| ADR-014 - Authoritative Entry Session Rollover Transaction | **APPROVE** |
| ADR-015 - Listener Lifecycle Supervision, Epoch Fencing, and Restart Cancellation | **REJECT** |
| ADR-016 - Feed-Health Authority, Durable Publication, and Bridge-Recycle Control | **REJECT** |
| Entry Session Rollover Lifecycle Contract | **REJECT** |
| Listener Supervision and Feed-Health Authority Contract | **REJECT** |
| Production Startup, Recovery, and Readiness Contract | **REJECT** |
| Diagnostic Endpoint Purity Contract | **REJECT** |
| Runtime Recovery Verification Specification | **REJECT** |
| Proposed Canonical Amendment Ledger | **REJECT** |

No candidate receives `APPROVE WITH NONBLOCKING EDITORIAL CORRECTIONS`. The required corrections below change normative state, authority, predicates, readiness, or verification and are therefore blocking rather than editorial.

Subsequent governance action on 2026-07-17 formally approved ADR-014 only, bound exclusively to SHA-256 `BD76D1B398515EA00E230B9C8A00A540344E061A36B228BF112F784F6AC34F25`. This approval does not change any rejection or authorization conclusion for ADR-015, ADR-016, supporting drafts, implementation, runtime verification, deployment, production `READY_LOCKED`, or trading.

The Remaining Architecture Questions Resolution, Cross-Document Conflict Matrix, Traceability Matrix, and Debt Registry are review/governance evidence, not proposed runtime authority. They remain noncanonical evidence and are updated by this review rather than approved as behavioral specifications.

## 2. ADR-014 review - APPROVE

ADR-014 unambiguously establishes one per-symbol `CANDIDATE_RECEIVED -> ARCHIVED_NONCURRENT -> VALIDATED -> STATE_BUILT -> COMMITTING -> COMMITTED -> EXPOSED` sequence. One SQLite transaction writes the complete aggregate, prior-session retirement, and active pointer; `synchronous=FULL` commit and readback precede every current projection.

The same materialized `session_rollover_commit_id`, session identity, version, and integrity identity are required on receiver lock, canonical Entry Agent state, frozen ladder/levels, observation/reset, authorization binding, prior retirement, exposure, replay, and audit. Observation cannot advance independently. Prior-session applicability closes at the date boundary even if no replacement commits. Validation/persistence failure preserves prior bytes/history but cannot make it current for the later date. Startup has explicit complete, partial, mismatched, corrupt/gapped, stale-prior/current-candidate, no-current, and missing-ID outcomes.

The TradingView trust boundary is explicit: route traversal, payload/session eligibility, and authenticated sender identity are separate. No mechanism is invented. `DEBT-2026-07-17-016` prevents production commit and startup READY until a separate security authority returns a payload-bound `VERIFIED` result.

No blocking ADR-014 ambiguity remains. Approval of ADR-014 alone would establish documentation authority only; it would not cure the rejected Entry contract, verification, amendment ledger, implementation, or security debt and therefore would not make the coordinated package promotable or production-ready.

## 3. ADR-015 review - REJECT

The sole Listener Supervisor, launcher handoff/exit, Executor requester-only role, commit-before-stale ordering, cancellable pending incident, durable fence, generation recovery, exactly-one effective restart, manual command path, bridge/listener distinction, and proposed NQ/YM policy ownership are otherwise explicit.

Blocking normative findings:

1. **Bridge rate limit permits an excess attempt.** Section 3.11.4 states that *more than* `max_bridge_recycles_per_window` attempts triggers exhaustion. That permits the attempt that exceeds the named maximum. It SHALL instead prohibit and classify an attempt that **would exceed** the maximum before process action, matching the full-listener rule.
2. **SFF-02 contains circular/undefined corroboration.** Section 3.11.5 permits a `current-epoch publication-fence fact` to corroborate lost listener authority while the section is defining the predicate that precedes the restart fence. It does not identify an independent predecision fact or owner. The predicate SHALL use closed, preexisting evidence and SHALL prohibit a fence/action result from proving its own prerequisite.
3. **Market-data-expected authority is unnamed.** Section 3.11.3 depends on `session calendar`, `subscription intent`, and `market-data-expected state` to distinguish quiet/closed markets from staleness, but the policy schema names no producer, authority, version, freshness, or proof for those inputs. The owner and closed input schema SHALL be defined before those states can suppress or create staleness.
4. **ATR reset result remains discretionary.** Section 3.12 says invalid/gapped history `MAY` produce `canonical_atr_reset`. The later closed reason list constrains reasons but does not define the deterministic disposition for each reason. The contract SHALL define whether each closed invalidation reason requires reset/WARMUP or another exact state; implementation discretion is prohibited.

## 4. ADR-016 review - REJECT

The named-pipe transport, Windows identity/PID/build binding, capability/HMAC model, canonical frame, fact types, freshness, epoch/generation matching, single SQLite writer, commit/readback acknowledgement, pending retention, projection isolation, persistence degradation, quarantine/restoration/migration framework, and explicit UNKNOWN behavior are concrete.

Blocking normative findings:

1. **The single terminal-reason enum is not mutually exclusive.** Section 3.9.1 requires exactly one `terminal_reason`, but `OPERATOR_REQUESTED_SHUTDOWN`, `LISTENER_REQUESTED_RECYCLE`, and `SUPERVISOR_FORCED_TERMINATION` are initiator/execution dimensions that can coexist with `EXPECTED_BRIDGE_SHUTDOWN`, `BRIDGE_CRASH`, or another terminal outcome. An operator-requested shutdown followed by forced termination can satisfy multiple rows. The model SHALL separate at least `initiator`, `requested_action`, `execution_disposition`, and `observed_terminal_cause`, or define complete mutually exclusive precedence.
2. **BDP-01 conflicts with the explicit planned-shutdown nonpredicate.** BDP-01 requires current-generation exit identity and absence of a replacement but does not require absence of a matching planned bridge/listener shutdown. Section 3.10 later says planned bridge shutdown SHALL NOT contribute to any recycle predicate. BDP-01 SHALL explicitly exclude matching planned/operator/listener shutdown and already-fenced transition intents before creating `RECYCLE_PENDING`.

Until those conditions are closed, a planned or multiply classified termination can enter the recycle path inconsistently; this is process-control authority and cannot be treated as editorial.

## 5. Entry Session Rollover Contract review - REJECT

Blocking normative findings:

1. Its lifecycle state set omits ADR-014 states `STALE_PRIOR_SESSION_BLOCKED`, `SESSION_STORE_DEGRADED`, and `SESSION_STORE_CORRUPT`, leaving startup/failure transitions incomplete.
2. Section 9 places `make the new aggregate current` and `make the prior active session historical/inactive` under “After durable success.” ADR-014 requires both to be members of the same authoritative durable transaction. The contract SHALL distinguish commit-time authority changes from postcommit projection exposure and SHALL NOT imply a second postcommit current/retirement transition.
3. The owner statement SHALL name the ADR-014 Entry Agent Session Commit Writer as sole canonical writer and distinguish Session-lock validation eligibility from durable aggregate/pointer ownership; “Entry Agent for durable canonical lifecycle projection” is weaker and can be read as projection-only ownership.

## 6. Listener Supervision and Feed-Health Authority Contract review - REJECT

Blocking normative findings:

1. The restart request schema omits ADR-015-required `supervisor_generation_id` and `expected incident_version`, so stale generation/request fencing cannot be enforced from the specification.
2. The health algorithm describes a local journal/snapshot and “atomic replace where applicable,” rather than the sole SQLite `BEGIN IMMEDIATE`/`COMMIT`/readback protocol mandated by ADR-016. It also says directory durability applies “where supported,” weakening a mandatory durability boundary.
3. Section 12 says shared/OneDrive projection SHALL never be the **sole** control source. ADR-016 prohibits projection data from participating in control alone **or in combination**. The supporting specification therefore still permits supplemental projection authority.
4. Its bridge recycle sequence says the Controller validates, fences, and allocates the next generation, while ADR-016 assigns predicate decision/fence/grant to the Supervisor State Evaluator and only execution to the Controller. The command/grant ownership SHALL be restated without a second authority.

## 7. Production Startup, Recovery, and Readiness Contract review - REJECT

The contract correctly makes process/endpoint/file existence insufficient, separates public-route delivery from sender authentication, and explicitly makes current production unable to reach READY while DEBT-016 remains blocking.

Blocking normative findings:

1. `RITHMIC_CONNECTED` requires `CONNECTION_UP` and `LOGIN_UP`, and `SYMBOLS_SUBSCRIBED` requires `SUBSCRIPTION_ACTIVE`. Those are not fact types in ADR-016's closed direct-evidence schema. ADR-016 defines raw `RAPI_ALERT_OBSERVED`, derived `connection=UP`/`login=UP`, and `SUBSCRIPTION_VERIFIED`. Readiness SHALL cite the exact accepted/committed authority records.
2. No readiness row or terminal criterion proves that **zero applicable BLOCKING debt** remains. `no blocker` is undefined and does not identify the debt registry snapshot, applicability decision, review currency, or governance owner. A positive, version/hash-bound governance-debt gate is mandatory.
3. `EXECUTOR_RECONCILED_LOCKED` proves flat/reconciled/locked state but no separate positive Executor authority/readiness grant for current build/config, current supervisor epoch intake, command ownership, and authorization capability. `TRADING_PERMITTED` is correctly later and separate, but the requested startup Executor-authority proof still needs an explicit nontrading state.

Because `WEBHOOK_SENDER_AUTHORITY_VERIFIED` is mandatory, the specification **may be approved once corrected even while DEBT-016 makes current production incapable of READY**. The debt is not the reason for rejection; the three contract defects above are.

## 8. Diagnostic Endpoint Purity Contract review - REJECT

The invariant, replacement command boundaries, migration order, and repeated/concurrent GET tests are strong, but the asserted complete audit misses a confirmed mutation:

- `GET /debug/tradingview/atr/<symbol>` calls `get_tradingview_atr()` (`Engines/trade_manager.py` lines 9091-9095). On a cache miss, that function writes `TRADINGVIEW_ATR_CACHE[normalized_symbol]` (`Engines/trade_manager.py` lines 7290-7299). The draft's section 2 expressly prohibits GET-side cache mutation, yet section 5.3 classifies this route as “No domain mutation identified.”

The route SHALL be added to the mutating GET table. Its pure replacement SHALL read an immutable snapshot without cache fill; cache population/refresh SHALL occur only at the owning POST/event boundary. Sequential, error-path, concurrent, and cold-cache GET tests SHALL prove no cache/state/persistence/timestamp change.

Because the approval check requires every current mutating GET to be identified, the omission is blocking.

## 9. Runtime Recovery Verification Specification review - REJECT

Blocking coverage and contradiction findings:

1. ADR-014 verification does not independently prove public-route traversal, authenticated sender identity, exact payload binding, freshness/replay, or DEBT-016-unavailable terminal startup behavior.
2. ADR-015 verification does not enumerate policy schema/version/digest/default/range rejection, market-data-expected authority, exact debounce/cooldown/rate-window boundaries, excess-attempt prohibition, or `RECOVERY_RATE_LIMITED_FAILED` restart persistence.
3. ADR-016 verification does not test every terminal classification dimension, overlapping initiator/outcome evidence, planned-exit BDP exclusion, documented RAPI recovery callbacks, or deterministic `UNKNOWN_TERMINATION` nonaction.
4. Section 5.6 says to recover the highest contiguous verified local commit from corruption, but ADR-016 requires verified quarantine, qualifying approved restore source, no-source `CONTROL_STORE_RECOVERY_REQUIRED`, identity/process reconciliation, staged migration, rollback boundary, and audit. The verification text could validate an automatic recovery path that ADR-016 prohibits.
5. Startup integration omits the exact same-session/same-epoch readiness matrix, sender-authentication dependency, zero-applicable-blocking-debt gate, and explicit Executor authority proof.
6. Diagnostic verification does not include the known cold-cache mutation case or require the replacement command/idempotency proofs for every row in the diagnostic audit.

## 10. Proposed Canonical Amendment Ledger review - REJECT

The ledger does not yet reconcile the current drafts and would leave weaker/competing canonical language:

1. TradingView Webhook, Runtime Authority, Entry Pipeline, and Lifecycle amendments do not add the route/content/sender distinction, the required payload-bound authentication result, or DEBT-016 production commitment/READY prohibition.
2. Listener amendments omit the NQ/YM topology version, sole shared-failure declarer, governed policy owner/schema/digest/default/ranges, market-data-expected input authority, debounce/cancellation/cooldown/rate/exhaustion behavior, and supervisor generation recovery details.
3. Feed-health amendments omit the concrete transport/authentication contract, terminal/UNKNOWN model, closed BDPs, corrupt-store quarantine/restore/no-source/migration/rollback/audit rules, and the prohibition on projection participation in control even as supplemental input.
4. The ADR-012 redline permits “otherwise canonically invalid history” and says it `may` reset, while ADR-015 supplies a closed reason set and requires deterministic handling. The open-ended/discretionary wording SHALL be removed.
5. Source-ownership redlines say the Bridge Controller owns Bridge Generation without distinguishing Supervisor predicate/fence/grant authority from Controller execution. This leaves overlapping control authority.
6. Verification redlines reference generic corruption and shared-feed tests rather than the exact corrected contracts and therefore would not obligate the missing proof.

## 11. Cross-document reconciliation result

**NOT RESOLVED.** The remaining conflicts are:

| Conflict | Authoritative drafts involved | Required resolution |
|---|---|---|
| Bridge retry maximum versus excess attempt | ADR-015 / policy | prohibit before exceeding maximum |
| Circular SFF lease-loss corroboration | ADR-015 | closed independent predecision evidence |
| Quiet-market/data-expected input ownership | ADR-015 / startup | named authority/schema/version/freshness |
| Deterministic ATR reset disposition | ADR-015 / ADR-012 ledger / verification | closed reason-to-state mapping with mandatory language |
| Overlapping terminal reason dimensions | ADR-016 / listener specification / verification | orthogonal fields or complete precedence |
| Planned exit satisfying BDP-01 | ADR-016 | explicit planned-intent exclusion |
| Session contract postcommit current/retirement wording | ADR-014 / Entry contract | commit-time authority versus postcommit exposure |
| Projection as possible supplemental control | ADR-016 / listener specification / amendment ledger | prohibit all control participation |
| Obsolete health fact names in readiness | ADR-016 / startup | exact raw/derived/committed names |
| Missing blocking-debt and Executor-authority readiness | startup / debt governance | positive versioned readiness rows |
| Missed diagnostic cache mutation | diagnostic contract / production GET | add route, command boundary, cold-cache purity proof |
| Verification and canonical amendment ledger lag current drafts | all | exact coordinated redraft before approval |

DEBT-015 remains separate and is not made part of this recovery implementation by these findings.

## 12. Security dependency

`DEBT-2026-07-17-016` remains separately governed and BLOCKING. No sender-authentication mechanism is invented here. Current production has no authenticated TradingView sender identity. Production session commitment, startup READY, deployment, and trading remain prohibited until the security decision, implementation, verification, traceability, and deployment authorization are complete.

## 13. Five-gate Governance status

| Gate | Decision |
|---|---|
| Architecture | **FAIL** - ADR-014 subsequently approved by explicit user action; ADR-015 and ADR-016 remain rejected and unapproved |
| Specification | **FAIL** - every supporting specification has a blocking normative issue |
| Implementation | **FAIL / NOT STARTED / NOT AUTHORIZED** |
| Verification | **FAIL / NOT STARTED**; verification specification itself is rejected |
| Traceability | **PARTIAL** - review findings are mapped, but authority/specification/code/test closure cannot complete |

Task-level Governance Verification: **FAIL**.

Repository-wide Governance Verification: **FAIL**.

## 14. Promotion and authorization determination

The coordinated package SHALL NOT be promoted to canonical authority. A subsequent explicit user action approved ADR-014 only, bound exclusively to SHA-256 `BD76D1B398515EA00E230B9C8A00A540344E061A36B228BF112F784F6AC34F25`. This review record does not approve ADR-015, ADR-016, any supporting draft, or any coordinated canonical amendment.

Even a later canonical documentation approval authorizes documentation authority only. It SHALL NOT authorize production implementation, canonical code changes, process restart, deployment, entry-lock clearing, trading permission, or live verification. Each requires its separately governed authorization and completed gates.
