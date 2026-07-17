# 2026-07-17 Remaining Architecture Questions - Resolution for Approval Review

Document Type: Pre-approval substantive resolution

Status: **DRAFT REVIEW RECORD - NONCANONICAL - NOT APPROVED**

Implementation/Restart/Deployment/Trading Authorization: **NONE**

## 1. Decision summary

| Question | Resolution/classification | Approval consequence |
|---|---|---|
| TradingView sender authentication | No existing governed sender-authentication authority exists. ADR-014 closes its internal transaction boundary by separating route, content/session, and sender facts. Authentication is separately governed as blocking `DEBT-2026-07-17-016`; no mechanism is invented. | ADR-014 is review-ready for atomic rollover architecture. Production candidate commitment, startup READY, deployment, and trading remain blocked until the separate security authority returns `VERIFIED`. |
| Rithmic/RAPI terminal-reason mapping | Closed in ADR-016 with raw callback preservation, exact process/intent correlation, a closed taxonomy, and mandatory `UNKNOWN_TERMINATION` for ambiguous disappearance. | ADR-016 no longer depends on inferred PID cause or invented terminal-login reason. |
| Shared-feed policy and thresholds | Closed in ADR-015. Listener Supervisor alone declares runtime shared failure. NQ/YM topology, policy owner/schema/default/ranges/digest, per-symbol rules, BDP/SFF separation, debounce/cancel/cooldown/rate/escalation are explicit. | ADR-015 is review-ready; values remain unapproved until the ADR/policy is approved. |
| Corrupt control-store restoration/migration | Closed in ADR-016 and startup. Detection, verified quarantine, no automatic restore, valid sources, approvals, identity preservation, no-source fail closed, staged migration, rollback boundary, and audit are explicit. | ADR-016/startup are review-ready; absence of a qualifying backup deterministically produces terminal FAILED, not fallback. |

## 2. TradingView sender authentication

### 2.1 Current production trust boundary

- Approved-route traversal is evidenced only by correlation of the configured Ngrok hostname/tunnel activation, Trade Manager relay receipt/forwarding, Entry receipt, times, and payload bytes. Current production records host/source/user-agent metadata but does not yet record one cryptographically joined receipt/payload hash across every hop.
- Payload freshness/intended session is currently inferred from sender-supplied timestamp/session fields when present, payload version/shape, lock-window/session validation, and receiver observation time. Sender timestamp/session fields are not authenticated and may be absent; receiver time proves observation only.
- Existing first-lock/merge behavior limits some same-session duplicate effects. The draft deterministic payload/commit identity makes an already accepted candidate idempotent. Neither is sender-bound replay protection and neither prevents an unauthenticated first candidate or precommit replay.
- Sender identity is not authenticated today. TLS to the public endpoint, `Host`, source address through a relay, user-agent `TradingView Webhook`, `locked=true`, receipt time, and payload hash are not identity proof.

### 2.2 Classification

The sender mechanism is not required to define or approve ADR-014's all-or-none session transition. It is required before any externally received candidate may become production authority and before startup may report `READY_LOCKED`. No existing ADR, webhook contract, or runtime authority defines the missing authenticated principal/freshness/replay mechanism.

The gap is therefore **separately governed and BLOCKING**, not silently deferred. `DEBT-2026-07-17-016` blocks public production readiness, candidate commitment, deployment, and trading. The separate security review must determine actual TradingView capabilities and select the mechanism; this package does not invent one.

### 2.3 Exact draft changes

- ADR-014 section 3.4.1 now defines `PUBLIC_ROUTE_TRAVERSAL_VERIFIED`, `PAYLOAD_SESSION_ELIGIBLE`, and `SENDER_IDENTITY_AUTHENTICATED`; prohibits route/content metadata from satisfying sender identity; records the current absence; requires `VERIFIED` for commit; and fails closed for unavailable/failed/mismatched/replay-ambiguous results.
- Entry Session Rollover Contract section 5 mirrors the three results and binds the missing mechanism to DEBT-016.
- Startup readiness splits `REAL_PUBLIC_ROUTE_DELIVERY_PROVEN` from `WEBHOOK_SENDER_AUTHORITY_VERIFIED`; section 10 records the exact current trust boundary and terminal `WEBHOOK_SENDER_AUTHENTICATION_UNAVAILABLE` result.

## 3. Rithmic/RAPI terminal reasons

### 3.1 Evidence boundary

The mapping is based on the bundled official RAPI Plus 13.7 namespace documentation and the production wrapper's raw callback/process evidence. The SDK defines callback types and `AlertInfo` fields but not one reliable terminal cause for every child-process disappearance. In particular, `ConnectionBroken` is automatically recovering, `ConnectionOpened` is initial/recovered connection, `ConnectionClosed` can follow normal logout/destruction, `LoginFailed` means login was not accepted without proving invalid credentials, `ForcedLogout` is provider initiated, and `ShutdownSignal` makes the engine inert without proving why.

### 3.2 Closed canonical distinction

ADR-016 section 3.9.1 requires raw `RAPI_ALERT_OBSERVED` and derives exactly one reason only after joining current epoch/generation, exact process handle/exit, durable intent, incident/fence/execution, callback/`RpCode`/message, subscription evidence, and exceptions:

| Reason | Evidence rule | Conservative action |
|---|---|---|
| `EXPECTED_BRIDGE_SHUTDOWN` | matching durable planned bridge intent/fence/execution precedes expected exit | complete planned action; no failure escalation |
| `BRIDGE_CRASH` | no planned intent plus exact owned-handle abnormal exit or captured unhandled exception | BDP-01 only |
| `AUTHENTICATION_FAILURE` | current `LoginFailed`; no unsupported credential narrowing | fail readiness; no automatic full restart |
| `CONNECTION_LOSS` | current `ConnectionBroken`; wait for SDK recovery/`ConnectionOpened` | debounce; BDP-02 only if unrecovered |
| `SUBSCRIPTION_FAILURE` | exact request error or bounded exact-contract verification/recovery failure | block symbol; BDP-03 only after all-required exhaustion |
| `LISTENER_REQUESTED_RECYCLE` | authenticated request accepted into Supervisor incident | request only; Supervisor decides/acts |
| `LISTENER_SHUTDOWN` | matching durable listener shutdown intent/epoch/process | planned fenced stop; no recovery loop |
| `SUPERVISOR_FORCED_TERMINATION` | durable fence/execution plus exact forced-stop record | continue only same already-fenced action |
| `OPERATOR_REQUESTED_SHUTDOWN` | authenticated operator command durably accepted before action | execute through Supervisor transaction |
| `UNKNOWN_TERMINATION` | disappearance, unmatched close, missing/conflicting evidence, unsupported code | block/preserve; no automatic recycle/restart/epoch |

`ForcedLogout`, `ShutdownSignal`, `ConnectionClosed`, and `ServiceError` retain their raw values. Any more precise future provider mapping requires an approved schema/policy amendment. This is **closed in ADR-016**, with uncertainty intentionally represented rather than guessed.

## 4. Shared-feed policy and thresholds

### 4.1 Ownership/topology

ADR-015 section 3.11 now states that topology `randle-rapi-feed-topology-v1` uses one physical RAPI MarketData connection, bridge, and listener for NQ/YM while subscription/tick/bar/ATR state remains per symbol/contract. Listener Supervisor is the sole runtime `SHARED_FEED_FAILURE` declarer. `Listener Supervision Policy Owner` authors values/schema, Architecture Governance approves the version, and Deployment Authorization binds its SHA-256; none becomes a competing runtime supervisor.

### 4.2 Exact governed policy

The deployment artifact `config/runtime/listener_shared_feed_policy_v1.json` has a closed schema and approved defaults/ranges for required symbols/topology, 1-second heartbeat, 3/5-second lease states, 30/90-second per-symbol freshness, 15-second connection/all-symbol debounce, 2-second pre-fence evidence age, three five-second subscription recovery attempts, 60-second bridge cooldown, three bridge recycles per 900 seconds, 180-second bridge recovery timeout, 300-second listener restart cooldown, and two listener restarts per 1800 seconds. Every nondefault requires a new approved version/digest/trace. Environment, CLI, launcher, source constants, status, and projection overrides are prohibited.

### 4.3 Action separation

- One-symbol staleness/unavailability/subscription failure blocks that symbol and cannot recycle/restart shared lifecycle authority.
- ADR-016 BDP-01..04 alone permit bridge recycle.
- ADR-015 `SFF-01_LISTENER_EXITED`, `SFF-02_LISTENER_LEASE_LOST`, or `SFF-03_BRIDGE_RECOVERY_EXHAUSTED` alone permit a full-listener pending incident.
- Recovery before fence cancels; the fence is the no-cancel boundary.
- Cooldown/rate excess enters `RECOVERY_RATE_LIMITED_FAILED`, blocks both symbols, preserves evidence, and requires governed operator recovery.

This question is **closed in ADR-015**. The configuration values are proposed architecture, not implementation-selected constants, and remain unapproved until architecture approval.

## 5. Corrupt store restoration and migration

ADR-016 sections 3.6.5-3.6.7 now require:

1. detection from SQLite/WAL recovery, exact application/schema/policy/store/migration identity, quick/foreign-key checks, checksums, contiguous cursors, epoch/generation ancestry, and legal incident/fence/execution state;
2. closed handles and a flushed/hash-verified quarantine set/manifest under local nonsynchronized storage before recovery;
3. no automatic restore and no projection/log/status/memory/operator-edit authority;
4. restoration only from a qualifying local owner-produced SQLite backup or governance-controlled offline backup with same store UUID, cursor, schema/policy, ancestry, checksum, integrity, and chain of custody;
5. Runtime Operations request, Architecture Governance approval, and Deployment Authorization approval of exact staged output;
6. preservation of store/cursor/incident/epoch/generation history, allocation of a new supervisor generation, no imported freshness, and exact ambiguous-process reconciliation;
7. no-source terminal `CONTROL_STORE_RECOVERY_REQUIRED`; a new empty store is a separately approved reinitialization with a new store UUID and every prior identity fenced;
8. offline staged/versioned/hash-bound migration only, with deterministic tool/transformation/evidence;
9. rollback only before activation/first new commit; afterward recovery moves forward; and
10. append-only recovery audit, whose failure prevents activation.

Startup section 4.1 makes each store owner return `VERIFIED_CURRENT`, `RECOVERY_REQUIRED`, or `FAILED`, adds `CONTROL_STORES_VERIFIED`, and prohibits public exposure/listener start when recovery is unresolved. This question is **closed in ADR-016 and the startup draft**. Whether a qualifying backup physically exists is an evidence/operations fact; absence has a complete fail-closed outcome and is not an architectural fallback gap.

## 6. Updated authority-conflict matrix

| Potential conflict | Resolution | Remaining state |
|---|---|---|
| Public route treated as sender identity | Three distinct trust facts; route never authenticates sender | Separate DEBT-016 blocks production |
| Security mechanism folded into ADR-014 | ADR-014 consumes a separately governed result and chooses no mechanism | No ADR-014 scope expansion |
| Listener, Executor, policy owner, or launcher declares shared failure | Listener Supervisor alone declares/acts; others provide evidence/approved policy | Closed in ADR-015 draft |
| Implementation constants own restart policy | Immutable versioned/digest-bound policy with owner/ranges/defaults/deployment trace | Closed in ADR-015 draft |
| RAPI callback/PID disappearance asserts precise cause | Raw callback plus intent/handle evidence; otherwise UNKNOWN | Closed in ADR-016 draft |
| Bridge condition directly restarts full listener | BDP bridge transaction precedes SFF; only recovery exhaustion can escalate | Closed across ADR-015/016 drafts |
| Corrupt store transfers authority to projection/new empty DB | Projection prohibited; qualifying restore or terminal fail; reinitialize separately governed | Closed in ADR-016/startup drafts |
| Restored old generation becomes fresh/current | Preserve history, allocate new supervisor generation, re-prove direct current evidence | Closed in ADR-016/startup drafts |
| DEBT-015 expands recovery scope | Still separate; no direct dependency established | Separately governed, unchanged |

## 7. Traceability update

| Requirement | Draft authority | Expected implementation | Required verification | Debt |
|---|---|---|---|---|
| TV route/content/sender separation | ADR-014 3.4.1; rollover contract 5; startup 6/10 | relay/receiver plus future security authority | route-hop/hash; spoof/replay/freshness/auth unavailable/failed | DEBT-016 |
| RAPI terminal mapping | ADR-016 3.9.1 | raw listener producer; Supervisor classifier/process adapter | every callback/reason/intent/exit/UNKNOWN combination | DEBT-014 |
| Shared-feed policy | ADR-015 3.11 | Supervisor policy loader/evaluator/store | schema/digest/range/default, BDP/SFF, debounce/cancel/cooldown/rate | DEBT-013 |
| Store recovery/migration | ADR-016 3.6.5-3.6.7; startup 4.1/6 | Health writer recovery tool and startup disposition | corruption/quarantine/restore/no-source/reinit/migrate/rollback/audit | DEBT-014 |

The bidirectional matrix at `Architecture/Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md` contains the production-unit and verification mappings. No implementation/test artifact exists yet.

## 8. Debt reconciliation

- `DEBT-2026-07-17-013`: owner assigned to Listener Supervision Policy Owner; policy/topology/threshold/cancellation/rate exit criteria added; remains BLOCKING.
- `DEBT-2026-07-17-014`: RAPI UNKNOWN and full corruption-recovery exit criteria added; remains BLOCKING.
- `DEBT-2026-07-17-015`: unchanged and separately governed.
- `DEBT-2026-07-17-016`: new BLOCKING Architectural Debt for missing TradingView sender authentication; no deferral or exception approved.

## 9. Approval-readiness recommendation

| Draft | Recommendation for next approval review | Blocking distinction |
|---|---|---|
| ADR-014 | **READY FOR APPROVAL REVIEW** | Atomic rollover architecture is closed. DEBT-016 separately blocks production candidate commitment/deployment, not review of transaction ordering. |
| ADR-015 | **READY FOR APPROVAL REVIEW** | Shared-feed owner, topology, policy, thresholds, action separation, cancellation, rate, and escalation are explicit. |
| ADR-016 | **READY FOR APPROVAL REVIEW** | Terminal taxonomy and corrupt-store recovery no longer rely on inference or fallback. |
| Entry Session Rollover Contract | **READY FOR APPROVAL REVIEW WITH ADR-014** | Sender security remains an explicit external blocking prerequisite. |
| Listener Supervision and Feed-Health Contract | **READY FOR APPROVAL REVIEW WITH ADR-015/016** | No competing lifecycle owner remains in the draft. |
| Production Startup/Readiness Contract | **READY FOR APPROVAL REVIEW AS A FAIL-CLOSED CONTRACT** | Current production cannot reach READY until DEBT-016 is resolved and all recovery implementation/proof exists. |

No draft is approved by this record. No canonical authority or production source was amended. No implementation, process start, deployment, lock clearing, or trading authorization occurred.

## 10. Remaining unresolved architectural questions

1. The actual TradingView sender-authentication/freshness/replay mechanism remains a separate **blocking security architecture decision**. It is intentionally not resolved or deferred here.
2. Exact vendor-specific interpretation of any unsupported RAPI `RpCode` remains UNKNOWN unless a later approved provider mapping supplies direct evidence. This is safe and does not block ADR-016 approval.
3. Existence and chain-of-custody eligibility of a restorable health-store backup is an implementation/operations evidence question. If none exists, the approved architecture requires terminal fail-closed operator recovery; no architecture ambiguity remains.
4. Proposed policy values and recovery roles still require architecture approval. They are no longer arbitrary implementation choices.

## 11. Coordinated approval-review disposition

The later coordinated approval review at `Architecture/Audits/2026-07-17_Coordinated_Authority_Package_Approval_Review.md` found that this resolution was sufficient to begin approval review but not sufficient for coordinated approval. It recommended ADR-014 `APPROVE` and rejected ADR-015, ADR-016, every supporting specification, and the canonical amendment ledger for the blocking normative conflicts recorded there. At the time of that review, no document was marked approved. A subsequent explicit user action on 2026-07-17 formally approved ADR-014 only, bound exclusively to SHA-256 `BD76D1B398515EA00E230B9C8A00A540344E061A36B228BF112F784F6AC34F25`; every other rejection and authorization restriction remains unchanged.
