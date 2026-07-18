# ADR-014 through ADR-016 - Cross-Document Conflict Matrix

Document Type: Pre-approval authority reconciliation

Status: **PHASE 3A REMEDIATED DRAFT - PENDING INDEPENDENT APPROVAL REVIEW - NONCANONICAL - NOT APPROVED**

Production/Implementation Authorization: None

## 1. Conflict matrix

| Existing source | Existing rule | Conflict, overlap, or gap | Proposed reconciliation | Draft owner | Debt |
|---|---|---|---|---|---|
| Constitution sections 3.1 and 3.3 | Market truth is immutable; UI/status is projection | Feed-health projection was consumed as live control | No doctrine change. ADR-016 distinguishes direct current-epoch facts, local durable control record, and asynchronous projection | ADR-016 | DEBT-014 |
| Constitution section 6 | Market layer owns market data; Executor owns execution; Command Center display | No owner is named for full listener process lifecycle; Executor currently acts as supervisor | Listener Supervisor exclusively owns listener lifecycle/epoch; listener retains market truth; Executor only produces health/requests | ADR-015 | DEBT-013 |
| Constitution sections 12 and 16 | Restart preserves truth; reads are nonmutating | Executor watchdog/debug GETs can restart listener; health reads can cause control effects | Diagnostic Purity Contract prohibits all GET/HEAD process/control mutations | ADR-015/016 | DEBT-013, DEBT-014 |
| Constitution sections 14-15 | Prior session cannot become current; rollover is formal transition preserving history | Receiver/observation/canonical session can advance independently; prior lock can remain active fallback | One ADR-014 transaction commits all session members and retires prior applicability only after success | ADR-014 | DEBT-012 |
| Constitution section 17 | Projection/reconnect does not reset ATR; explicit epoch is a legal reset authority event | Existing text can be misread as mandatory destructive reset on every listener restart | Apply the closed ADR-015 RETAIN/REHYDRATE/INVALIDATE/REBUILD matrix; only four named invalidation reasons are legal | ADR-015 plus ADR-012 amendment | DEBT-013 |
| Constitution sections 20 and 22 | Complete evidence; preserve valid state on failure | Candidate receipt and current receiver projection are not distinguished | Candidate is immutable noncurrent evidence; current exposure occurs only after commit; failure preserves prior aggregate | ADR-014 | DEBT-012 |
| Lifecycle Vocabulary sections 2.1, 16, 18 | Defines Session, reset, REHYDRATING, authority epoch | Missing rollover commit, bridge generation, restart incident/fence, health commit/projection, degraded/diverged terms | Add exact noninterchangeable terms in amendment ledger | ADR-014/015/016 | DEBT-012 through 014 |
| Lifecycle Engine sections 11.3 and 26-31 | Atomic durable transitions, crash recovery, session rollover | Does not define aggregate members, shared session commit ID, or exposure order | Add Engine 31.6-31.9 and standalone Entry Session Rollover Contract | ADR-014 | DEBT-012 |
| Lifecycle Engine section 32 | Status/health/debug routes are read-only | Existing Executor routes call a mutating restart builder; health reads can drive bridge recycle | Extend prohibition to restart requests/fences/process actions/cursor flushes | ADR-015/016 | DEBT-013, DEBT-014 |
| Lifecycle Engine section 35 | Listener owns feed-health and tick freshness; Executor execution | `feed-health` currently conflates direct fact ownership, durable commit, projection, and process control | Listener owns direct facts; Health Durable Writer owns durable commit; Supervisor owns incident/fence/generation grant; Bridge Controller only executes the fenced command | ADR-015/016 | DEBT-013, DEBT-014 |
| ADR-012 sections 3.1-3.3 | Durable accepted facts survive exposure failure; epoch change is a legal reset reason | Does not distinguish bridge generation from listener epoch or exact continuity-preserved reconstruction | Clarify bridge no-reset and epoch rehydration before any reset disposition | ADR-015/016 amendment to ADR-012 | DEBT-013, DEBT-014 |
| ADR-012 section 3.6 | Read-side persistence prohibited | Does not explicitly name process lifecycle/restart mutation | Extend to restart/recycle/fence/cursor/session control effects | ADR-015/016 amendment to ADR-012 | DEBT-013, DEBT-014 |
| Runtime Authority section 1 | Shared health JSON/status/UI are projections | Current listener/launcher use shared health as bridge/readiness control | Retain projection rule and add direct/local-durable authority hierarchy | ADR-016 | DEBT-014 |
| Runtime Authority section 3.2 | Session/contract/epoch/history events are legal ATR reset families | Exact bridge/restart/cold-start continuity disposition absent | Add bridge, listener-epoch, cold-start rehydration table and continuity-preserved outcome | ADR-015/016 | DEBT-013, DEBT-014 |
| Runtime Authority section 4 | TradingView owns transmitted context; archive exact payload | Sender assertion, candidate archive, receiver lock, canonical session commit are not distinguished | Add candidate/current separation and ADR-014 shared commit | ADR-014 | DEBT-012 |
| Runtime Authority section 5 | LIVE requires candle/ATR/session/contract/lifecycle coherence | Missing session commit, listener epoch, bridge generation, health commit/supervisor state | Extend LIVE predicate and fail-closed states | ADR-014/015/016 | DEBT-012 through 014 |
| Runtime Authority sections 8-10 | Audit/deployment/expected areas | Missing rollover/restart/bridge/health/startup audit events and tests | Add event taxonomy, new verification specification, forward areas | ADR-014/015/016 | DEBT-012 through 014 |
| NQ Live Continuity Verification sections 2.1 and 2.5 | NQ ATR continuity/readiness tests | Incident-specific and insufficient for system-wide restart/session/health behavior | Retain NQ regression and cross-reference new system-wide draft | ADR-015/016 | DEBT-013, DEBT-014 |
| Session Liquidity Lock Contract sections 1-4 | First valid table becomes immutable session map; observation reset allowed by normal session reset | No candidate/commit/exposure transaction; reset latch can advance separately | Add ADR-014 candidate, commit ID, observation coupling, prior-session ordering, divergence state | ADR-014 | DEBT-012 |
| Session Liquidity Lock Contract section 10 / Liquidity Ladder Verification section 2 | Blanket overlap rejection conflicts with separately required exact shared-boundary behavior | Confirmed specification conflict, but no evidence that ADR-014 transaction architecture depends on resolving it | Keep unchanged in ADR-014-016; track only through DEBT-015; require new AIA before scope linkage | Separate governance | DEBT-015 |
| TradingView Webhook Contract sections 4 and 7 | `locked` sender field required; first valid payload locks | Sender assertion can be confused with receiver-created canonical lock | Define sender assertion as input only; rollover commit creates canonical lock | ADR-014 | DEBT-012 |
| TradingView Webhook Contract section 11 | Complete accepted payload archived | Archive event and current exposure are not distinct lifecycle facts | Archive candidate noncurrent; separately record validation, commit ID, exposure | ADR-014 | DEBT-012 |
| TradingView Webhook Contract / production ingress | No approved sender-authentication authority or sender-bound freshness/replay contract exists; current route accepts JSON | Public-route traversal, payload/session eligibility, and authenticated sender identity were conflated as `sender/source authority` | ADR-014 defines the three distinct facts but selects no mechanism; startup requires separate positive sender authority; create separate blocking security decision/debt | Separate TradingView ingress security governance | DEBT-2026-07-17-016 |
| Entry Pipeline | Valid signal proceeds to trade creation/submission | No explicit runtime/session/epoch/health precondition before Step 1 | Add fail-closed runtime authority precondition; no read-side recovery effects | ADR-014/015/016 | DEBT-012 through 014 |
| Persistence and Recovery | Trade Manager owns durable trade lifecycle | Could be overgeneralized as runtime supervisor/session/health store | Add explicit scope boundary and cross-references; Trade Manager ownership unchanged | Specification amendment | DEBT-012 through 014 |
| Safety Rails section 15 | Uncertainty protects capital | Does not say projection staleness cannot become process-death authority | Add runtime authority safety block | ADR-015/016 | DEBT-013, DEBT-014 |
| Architecture README draft list | Session rollover listed unresolved; no ADR-014-016 index | Draft package would otherwise be undiscoverable or look approved if placed under approved ADRs | Index under Current Draft Items only | Documentation | DEBT-012 through 014 |
| Live Ops Command Allowlist section 2 | Allows GET watchdog/health calls | Allowlist does not state those GETs must be pure; current watchdog GETs mutate | Add observation-only constraint; mutating GET must be removed until corrected | Diagnostic Purity Contract | DEBT-013, DEBT-014 |
| `launch_all.ps1` | Starts listener directly; reads shared feed-health JSON for readiness; launcher exits | Conflicts with sole supervisor and projection-only health control; no durable handoff | Future implementation must start/command supervisor and read direct/local committed readiness | ADR-015/016 future implementation | DEBT-013, DEBT-014 |
| `run_system.ps1` | Broadly kills Python and directly starts listener | Conflicts with exact ownership, fencing, evidence, and safe startup | Deprecate/replace in future implementation; manual path uses same supervisor contract | ADR-015 future implementation | DEBT-013 |
| `executor.py` watchdog/restart paths | Executor restarts listener; accepted recovery uses previous timestamp; GETs mutate | Direct implementation nonconformance and missing prior architecture | Executor becomes producer/requester only; pure snapshot reads; commit-before-evaluate | ADR-015 future implementation | DEBT-013 |
| `rithmic_live_listener.py` health/bridge paths | Multiple health writers; pending clear before swallowed failure; shared projection drives recycle | Conflicts with durable pending retention, single writer, projection authority, bridge fence | Local writer, explicit result/pending/cursor, direct decision, current-generation fence | ADR-016 future implementation | DEBT-014 |
| RAPI Plus 13.7 `AlertType`/`AlertInfo` documentation and `rithmic_live_listener.py` callback wrapper | SDK distinguishes opened/closed/broken/login failed/forced logout/shutdown signal but does not provide one reliable process-terminal cause for every disappearance | A single terminal reason overloaded initiator, requested action, execution method, cause, and result | Preserve raw alert/`RpCode`/message; derive five independent closed fields with `UNKNOWN` per unproven dimension; disappearance alone cannot act | ADR-016 | DEBT-014 |
| Listener shared-feed topology and thresholds | NQ/YM currently share one listener/bridge/MarketData connection; symbol freshness is independent; no canonical threshold owner/schema existed | Implementation constants could become process-lifecycle authority and global symbol aggregation could restart both | Listener Supervisor alone declares runtime shared failure; approved digest-bound policy owns topology, values/ranges/defaults/debounce/cancellation/cooldown/rate/escalation | ADR-015 | DEBT-013 |
| ADR-016 health SQLite startup recovery | Prior draft detected corruption but did not define quarantine, sources, approval, epoch/generation preservation, migration, rollback, or audit | Projection or an empty/new store could become an implied unsafe fallback | Verified quarantine; no automatic restore; only qualifying local/offline backups; no-source fail closed; staged migration; pre-first-commit rollback only; three approvals and audit | ADR-016/startup draft | DEBT-014 |

## 2. Existing ADR reconciliation

| ADR | Effect of ADR-014 through ADR-016 drafts |
|---|---|
| ADR-006 | Unchanged. Rejection Step 4 count window is outside recovery scope |
| ADR-007 | Unchanged. Rejection Step 4 participation is outside recovery scope |
| ADR-008 | Unchanged. Continuation Eligibility handoff is outside recovery scope |
| ADR-009 | Unchanged. Boundary architecture is outside recovery scope |
| ADR-010 | Unchanged. Continuation creation/initial boundary is outside recovery scope |
| ADR-011 | Unchanged. Continuation Step 4 is outside recovery scope |
| ADR-012 | Requires the exact continuity/read-side amendment in the amendment ledger; its durable-before-exposure invariant remains governing |
| ADR-013 | Unchanged. Candidate routing/anchors are outside recovery scope |
| ADR-014 | **APPROVED governing dependency.** Every revised session clause preserves its indivisible validate-build-commit-expose transaction, Session-lock policy as sole eligibility/rollover-decision authority, `Entry Agent Session Commit Writer` as sole durable writer/transaction executor, and both `trade_authorization_context_binding` and `authorized_session_rollover_commit_id`. ADR-015/ADR-016 and supporting drafts neither reopen nor redefine ADR-014 |

No approved ADR currently assigns Listener Supervisor authority or defines durable health control. ADR-015 and ADR-016 are new decisions, not reinterpretations of ADR-013 or the stack contracts.

## 3. Supervisor ownership reconciliation

There is one lifecycle decision/grant owner and one bounded executor:

- Listener Supervisor: full listener process, Listener Authority Epoch, bridge incident/fence decision, and Bridge Generation grant/adoption.
- Bridge Controller within the listener: executes exactly one authenticated Supervisor-fenced bridge child command and reports exact results; it owns no lifecycle decision or authority grant.

Executor, launcher, status endpoints, health projections, and Command Center own neither. Launcher/manual startup MAY bootstrap or command the supervisor but SHALL NOT become a competing supervisor.

## 4. Session authority reconciliation

Candidate archive, sender lock assertion, receiver canonical lock, canonical Entry aggregate, frozen ladder, observation state, session-context authorization, and display projection are distinct facts. One ADR-014 commit ID joins all authoritative current-session members. Candidate evidence MAY precede commit but is explicitly noncurrent.

Public-route traversal, payload/session eligibility, and sender identity authentication are also distinct. Current production proves no authenticated sender identity. ADR-014 can be reviewed for atomic session-transition correctness without selecting a security mechanism, but production candidate commitment/startup remains blocked by `DEBT-2026-07-17-016` until a separately approved sender-authentication authority returns a payload-bound `VERIFIED` result.

## 5. Health authority reconciliation

Direct current-epoch/generation facts are immediate liveness authority. The local serialized durable store is control recovery/audit authority. Shared/OneDrive JSON and Command Center are observational projections. They SHALL NOT initiate, influence, reinforce, confirm, participate in, or contribute to control, lifecycle, death, recovery, fencing, cancellation, session authority, or authorization. Command Center parity MAY satisfy or fail only the separate observational `COMMAND_CENTER_ALIGNED` startup gate; it SHALL NOT close Listener Supervisor `REHYDRATING`, mutate canonical state, or supply any underlying readiness proof.

The WinError 5 cause statement remains bounded: atomic replacement denial is proven; the conflicting handle owner is not.

RAPI callback classification is evidence-bounded. Initiator, requested action, execution method, observed cause, and result are independent fields; `UNKNOWN` applies per unproven dimension. `ConnectionBroken` is recoverable and `ConnectionOpened` is positive recovery; `LoginFailed` does not prove invalid credentials. Planned/operator shutdown, startup, controlled recycle, listener shutdown, and listener replacement cannot satisfy BDP-01.

Corrupt local health control does not transfer authority to a projection. Automatic restoration is prohibited; approved qualifying backup, full staged validation, preserved identity/history, new supervisor generation, process-ambiguity reconciliation, and recovery audit are required. No qualifying source leaves startup `CONTROL_STORE_RECOVERY_REQUIRED` and terminally failed.

## 6. ATR reconciliation

- Bridge generation change and same-epoch symbol recovery: RETAIN completed bars/RMA; REHYDRATE only the incomplete minute under complete proof.
- Stale epoch/generation: reject without current ATR effect.
- Full listener epoch change, cold startup, and interrupted startup recovery: REHYDRATE exact authority or apply exactly one closed `DURABLE_HISTORY_GAP`, `DURABLE_HISTORY_CORRUPT`, `CONTRACT_IDENTITY_CHANGED`, or `SESSION_VOLATILITY_RESET_REQUIRED` INVALIDATE/REBUILD disposition.
- Session rollover: remains a legal authority boundary under current architecture but does not by itself authorize discarding continuous listener-owned history unless the approved volatility/session contract requires and records that disposition.

## 7. DEBT-015 separation

DEBT-015 is confirmed but outside ADR-014 through ADR-016 documentation, implementation, and exit criteria. The recovery architecture references the separately approved structural validator result and does not define overlap behavior. Only a new evidence-backed AIA and explicit scope approval MAY establish a direct dependency.

## 8. Reviewed sources requiring no behavioral amendment

| Reviewed source | Disposition |
|---|---|
| `Architecture/03_Randle_AI_Rejection_Step2_Lifecycle_Specification.md` | Unchanged; recovery readiness may block input before this lifecycle, but Step 2 semantics are not amended |
| `Architecture/04_Randle_AI_Rejection_Step4_Lifecycle_Specification_DRAFT.md` | Unchanged and remains a draft; recovery does not alter Step 4 |
| `Architecture/05_Randle_AI_Rejection_Lifecycle_Architecture_Gap_Analysis.md` | Evidence/strategy scope unchanged |
| `Architecture/06_Randle_AI_Modernization_Charter.md` | Existing five-gate governance applies; no new process behavior required |
| `Architecture/07_Randle_AI_Modernization_Roadmap.md` | No recovery behavior authority; no amendment required |
| `Architecture/10_Randle_AI_Architecture_Traceability_Specification.md` | Applied by the new matrix; schema/invariants unchanged |
| `Architecture/11_Randle_AI_Architecture_Debt_Specification.md` | Applied by updated debt records; lifecycle/schema unchanged |
| `Architecture/12_Randle_AI_Development_Process_Specification.md` | Applied by the documentation-only phase; workflow unchanged |
| `Architecture/13_Randle_AI_TradingView_Liquidity_Ladder_Verification_Specification.md` | Unchanged; DEBT-015 remains its separate contract problem |
| `docs/lifecycle/tradingview_liquidity_ladder_calculation_contract.md` | Unchanged; ADR-014 consumes its validation result without defining it |
| `docs/lifecycle/trade_lifecycle.md`, `docs/trade_manager_rules_v1-1.md`, `docs/trade_state_schema_v1.md`, `docs/trade_state_transitions_v1.md` | Trade truth/ownership remain unchanged; startup draft requires preservation/reconciliation only |
| Broker/execution architecture and schemas | Unchanged; existing execution truth and protective orders remain under Executor/Trade Manager owners |

No existing canonical production-startup specification assigns listener supervision. The new startup/recovery draft fills that gap; `launch_all.ps1`, `run_system.ps1`, and the Live Ops allowlist are the current operational/implementation surfaces requiring later conformance.

## 9. Historical coordinated-review rejection findings

The approval review at `Architecture/Audits/2026-07-17_Coordinated_Authority_Package_Approval_Review.md` is the historical rejection authority. It identified the following conflicts in the pre-remediation drafts:

| Conflict identified by the rejected review | Drafts/surfaces at rejection | Blocking debt |
|---|---|---|
| ADR-015 permits the bridge attempt that exceeds its configured maximum | ADR-015 shared-feed policy | DEBT-013 |
| ADR-015 SFF-02 permits a publication-fence result to corroborate its own pre-fence predicate | ADR-015 listener lease-loss predicate | DEBT-013 |
| quiet-market/market-data-expected state has no named input authority/schema | ADR-015, startup, verification | DEBT-013, DEBT-018 |
| ATR invalidation reason-to-state handling remains discretionary and the amendment ledger uses open-ended invalidity wording | ADR-015, ADR-012 amendment, verification | DEBT-013 |
| ADR-016 single terminal reason mixes initiator, action, execution, and observed cause and is not mutually exclusive | ADR-016, listener specification, verification | DEBT-014 |
| ADR-016 BDP-01 omits planned-shutdown exclusion despite planned shutdown being an explicit nonpredicate | ADR-016 | DEBT-014 |
| Entry contract places active-pointer/prior-retirement changes after durable success instead of inside the commit and omits store failure states | ADR-014 supporting contract | DEBT-012 |
| Listener specification permits shared projection as nonsolo control and describes a non-SQLite journal/snapshot write boundary | ADR-016 supporting contract | DEBT-014 |
| Startup uses obsolete health fact names and lacks positive applicable-debt/Executor-authority gates | ADR-016, startup | DEBT-018; DEBT-014, DEBT-2026-07-17-016 |
| Diagnostic GET audit misses Trade Manager ATR cache fill | diagnostic specification, `Engines/trade_manager.py` | DEBT-017 |
| Runtime verification and canonical amendment ledger do not encode the current security, policy, terminal, store-recovery, readiness, and purity contracts | verification/amendment drafts | DEBT-012 through 014, DEBT-2026-07-17-016, DEBT-017, DEBT-018 |

The table above records the rejected package and is not the current remediation disposition.

## 10. Phase 1 remediation reconciliation

| Previously open conflict | Exact reconciled rule | Identical draft surfaces | Status |
|---|---|---|---|
| Restart attempt could exceed maximum | The durable monotonic rolling-window count is checked before execution; count equal to maximum causes `FAILED_RECOVERY_EXHAUSTED` without process action; no implicit/reset retry | ADR-015 3.11.5; ADR-016 3.8/3.11; verification 4.6; amendment ledger 5A/5B | Corrected in draft — pending independent approval |
| Circular SFF-02 evidence | Only epoch grant, Health Ingress heartbeat/publication, command challenge, and exact OS handle are inputs; fence/action/replacement results are prohibited | ADR-015 3.11.6; verification 4.5; amendment ledger 5A | Corrected in draft — pending independent approval |
| Market-data-expected authority absent | Supervisor's Market Data Expectation Evaluator owns current classification from a deployment-bound calendar, subscription intent, lifecycle, and correlated clock with explicit startup/expiry/shutdown behavior | ADR-015 3.11.3; startup 6; verification 4.6; amendment ledger 5A | Corrected in draft — pending independent approval |
| ATR disposition discretionary | Closed RETAIN/REHYDRATE/INVALIDATE/REBUILD matrix and exactly four invalidation reasons | ADR-015 3.12; startup 6.1/9; verification 6; ADR-012/runtime amendment text | Corrected in draft — pending independent approval |
| Terminal reason overloaded | Five independent closed fields: initiator, requested action, execution method, observed cause, result; deterministic `NONE`/`UNKNOWN` evidence rules apply independently | ADR-016 3.9.1; verification 5.4; amendment ledger 5B | Corrected in draft — pending independent approval |
| BDP-01 included planned transitions | BDP-01 requires unexpected exit and excludes planned/operator shutdown, startup, controlled recycle, listener shutdown, and listener replacement | ADR-016 3.10; verification 5.4; amendment ledger 5B | Corrected in draft — pending independent approval |
| Session activation/retirement split | Candidate activation and prior retirement are atomic members of one commit; store failure states and authorization-binding fields are explicit | Entry Session Contract 2/3/8/9/13; verification 3; amendment ledger 3/4/6 | Corrected in draft — pending independent approval |
| Listener support spec contradicted SQLite/projection/controller authority | SQLite `BEGIN IMMEDIATE`/COMMIT/readback is the writer boundary; projection cannot participate; Supervisor State Evaluator fences/grants and Controller only executes/acknowledges | ADR-016; startup 5; verification 5/8; amendment ledger 4/6 | Corrected in draft — pending independent approval |
| Startup obsolete facts/missing authority and debt gates | Uses raw RAPI observations plus derived UP, `SUBSCRIPTION_VERIFIED`, zero applicable blocking debt, Executor/Supervisor/current epoch/session/ATR/frozen-ladder/sender gates | Startup 4-6/10-11; verification 8; amendment ledger 16 | Corrected in draft — pending independent approval |
| Diagnostic audit omitted mutations | Inventory now contains all nineteen confirmed GET paths, both TradingView ATR caches, all lazy pipeline paths, persistence/config/cache/index mutation, corrupt-store backup, and the transitive account proxy | Diagnostic Purity 5-7; verification 9; amendment ledger 5C/14 | Corrected in draft — pending independent approval |

The Phase 1 rows are historical remediation inputs. Their current wording is superseded by the Phase 2 reconciliation below. No row constitutes approval, incorporation, implementation, verification, or deployment evidence.

## 11. Historical Phase 2 independent-review finding disposition

This table records what Phase 2 claimed and is superseded for approval-readiness purposes by section 13. Its `Yes`/`No` cells are historical assertions, not current status concepts and not approval evidence.

| Independent-review finding | Final draft reconciliation | Identified | Corrected in draft | Pending independent approval | Approved | Canonically incorporated | Implemented | Verified | Deployed |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Restart cancellation was an action without an incident outcome | `RESTART_CANCELED` is a durable terminal incident outcome with sole writer, evidence, reevaluation, forbidden transitions, restart recovery, and tests | Yes | Yes | Yes | No | No | No | No | No |
| Bridge recovery exhaustion vocabulary diverged | Both ADRs use only `FAILED_RECOVERY_EXHAUSTED` with identical entry predicates, persistence, escalation, no-retry behavior, and SFF-03 effect | Yes | Yes | Yes | No | No | No | No | No |
| Time-authority degradation was not a lifecycle state | `HEALTH_TIME_AUTHORITY_DEGRADED` has entry, writer, durability, recovery, startup, permitted/prohibited, readiness, escalation, and verification rules | Yes | Yes | Yes | No | No | No | No | No |
| Bridge subscription used `ACTIVE` and `SUBSCRIPTION_VERIFIED` inconsistently | `SUBSCRIPTION_VERIFIED` is the sole ready subscription state; `ACTIVE` is not a lifecycle state | Yes | Yes | Yes | No | No | No | No | No |
| Termination `NONE` versus `UNKNOWN` was discretionary | Each of the five fields applies the same complete-proof `NONE` and deficient-evidence `UNKNOWN` rule | Yes | Yes | Yes | No | No | No | No | No |
| Nonzero exit incorrectly proved `BRIDGE_CRASH` | Crash requires matched authoritative crash/exception evidence; unmatched unexpected nonzero exit retains `UNKNOWN` cause | Yes | Yes | Yes | No | No | No | No | No |
| ADR-014 authorization fields were omitted | Both mandatory fields are present in candidate, aggregate, commit, persistence, activation, startup, retirement, requests, and decisions | Yes | Yes | Yes | No | No | No | No | No |
| Rollover writer/transaction owner was assigned to session-lock policy | `Entry Agent Session Commit Writer` is sole writer/owner; session-lock policy supplies input only | Yes | Yes | Yes | No | No | No | No | No |
| Bridge Controller shared bridge-generation grant authority | Listener Supervisor State Evaluator solely grants; Bridge Controller only authenticates execution acknowledgement/result | Yes | Yes | Yes | No | No | No | No | No |
| ATR startup proof omitted recovery and finalized-bar identity | ATR gate binds contract, session, epoch, recovery/continuity identity, disposition, and exact `BARS_FINALIZED` cursor; no-new-bar reuse is closed | Yes | Yes | Yes | No | No | No | No | No |
| Startup expectation vocabulary was undefined | Startup uses only `EXPECTATION_STARTUP_UNPROVEN` | Yes | Yes | Yes | No | No | No | No | No |
| Command Center projection acknowledgement closed lifecycle state | Command Center parity is only `COMMAND_CENTER_ALIGNED`; it cannot close `REHYDRATING` or supply domain authority | Yes | Yes | Yes | No | No | No | No | No |
| Mutating GET inventory and transitive effects were incomplete | Nineteen routes and every reachable hydration/repair/backup/cache/index/config/pipeline/proxy mutation are inventoried, migrated, and verified | Yes | Yes | Yes | No | No | No | No | No |
| Canonical ledger omitted current ownership, states, and purity clauses | Ledger carries the sole rollover writer, three new outcomes/states, full purity language, and correct approval sequencing | Yes | Yes | Yes | No | No | No | No | No |
| Verification/traceability metadata was stale or incomplete | Verification recognizes approved ADR-014, maps obligations both directions, and adds the new lifecycle, termination, readiness, and purity cases | Yes | Yes | Yes | No | No | No | No | No |

## 12. Superseded Phase 2 vocabulary and ownership registry

The following registry is retained as Phase 2 history. It is not the active vocabulary mapping and is superseded by section 14 and the Phase 3B clause/scenario/assertion registry.

Where `RESTART_PENDING`, `FENCED`, `REHYDRATING`, or `FAILED` appears in both the restart-incident and current full-listener domains, the incident value identifies the durable decision/execution record and the current full-listener value identifies operational eligibility. They SHALL carry the same incident/recovery identity while that incident controls the listener, but neither record is a substitute writer for the other. `RESTART_CANCELED` and `COMPLETED` are incident outcomes only; `HEALTHY` and `SUSPECT` are current full-listener states only.

| Normative identity/state | One definition | Sole transition authority / writer | Durable evidence | Restart behavior | Readiness effect | Verification |
|---|---|---|---|---|---|---|
| `session_rollover_commit_id` / active Entry session | Approved ADR-014 atomic aggregate identity | Entry Agent Session Commit Writer | Complete Entry Session Aggregate plus active pointer and prior retirement in one commit | Recover committed aggregate or fail closed; never synthesize | Current matching commit required | `RRV-SR-001`, `RRV-SR-002` |
| `trade_authorization_context_binding` | ADR-014 authorization binding member | Entry Agent Session Commit Writer | Same aggregate commit | Restore only with matching aggregate | Required; initial value blocks entries | `RRV-SR-001`, `RRV-SR-002` |
| `authorized_session_rollover_commit_id` | Authorization decision's exact active-session identity | Entry Agent Session Commit Writer initializes the aggregate member as immutable null; opening authorization owner writes only a separate decision record under ADR-014 gates | Aggregate plus separate authorization decision record | Mismatch/null remains blocked; aggregate is never mutated by authorization | Exact match required | `RRV-SR-001`, `RRV-SR-002` |
| Entry Session states: `NO_CURRENT_SESSION_CONTEXT`, `STALE_PRIOR_SESSION_BLOCKED`, `CANDIDATE_PENDING`, `CANDIDATE_VALIDATED`, `CANDIDATE_REJECTED`, `COMMITTING`, `COMMIT_FAILED`, `COMMITTED_FAIL_CLOSED`, `CURRENT_CONTEXT_READY`, `SESSION_PROJECTION_DIVERGED`, `SESSION_STORE_DEGRADED`, `SESSION_STORE_CORRUPT` | Entry Session Contract section 3.1 complete transition table under approved ADR-014 | Entry Agent Session Commit Writer | Per-state evidence defined by that table | Restore/retry behavior is state-specific; no projection synthesis | Every state except fully reverified `CURRENT_CONTEXT_READY` blocks session readiness, and even READY does not authorize entry | `RRV-SR-001`, `RRV-SR-002` |
| `listener_epoch_id` | Listener Authority Epoch | Listener Supervisor State Evaluator / Listener Supervisor durable writer | Supervisor epoch grant/fence record | Restore exact epoch or fence and recover; stale input rejected | Current epoch required | `RRV-LS-001`, `RRV-LS-002` |
| `supervisor_generation_id` | Supervisor incarnation fence | Listener Supervisor bootstrap/recovery transaction | Durable generation record | New generation invalidates stale futures | Current generation required | `RRV-LS-001` |
| `bridge_generation_id` | Bridge child generation within one listener epoch | Listener Supervisor State Evaluator | Durable generation grant plus authenticated Controller acknowledgement | Bridge recycle changes generation, not listener epoch | `SUBSCRIPTION_VERIFIED` on current generation required | `RRV-FH-001` |
| `restart_incident_id` / fencing token | One listener restart decision and no-cancel boundary | Listener Supervisor State Evaluator | Durable incident/version/fence record | At most one effective restart per fenced incident | Pending/fenced incident blocks readiness | `RRV-LS-001`, `RRV-LS-002` |
| `RESTART_CANCELED` | Durable terminal no-action incident outcome | Listener Supervisor State Evaluator / incident writer | Cancellation record plus recovery fact and reevaluation result | Restored terminal; cannot execute/reopen/retry | Only post-cancel `HEALTHY` reevaluation can pass | `RRV-LS-002` |
| Restart-incident states: `RESTART_PENDING`, `RESTART_CANCELED`, `FENCED`, `EXECUTING`, `REHYDRATING`, `COMPLETED`, `FAILED` | ADR-015 sections 3.4-3.10 incident machine | Listener Supervisor / supervisor durable incident writer | Versioned incident/request/fence/execution/rehydration/completion record | Restore the exact incident state, adopt/resolve the same execution, and never create a second effective restart | Pending through failed blocks listener readiness; canceled uses its separate current-state reevaluation; completed contributes only with current authoritative domain acknowledgements | `RRV-LS-001`, `RRV-LS-002` |
| Full-listener states: `STOPPED`, `STARTING`, `REHYDRATING`, `HEALTHY`, `SUSPECT`, `RESTART_PENDING`, `FENCED`, `STOPPING`, `FAILED`, `AMBIGUOUS_PROCESS_AUTHORITY`, `SUPERVISOR_STORE_FAILED` | ADR-015 sections 3.4-3.10; `RESTART_CANCELED` remains a terminal incident outcome, not a substitute current state | Listener Supervisor / supervisor durable incident writer | Supervisor state/incident/epoch/execution records | ADR-015 recovery/adoption rules apply; no other component SHALL advance them | Only current `HEALTHY` after all authoritative acknowledgements can satisfy listener readiness | `RRV-LS-001`, `RRV-LS-002` |
| `FAILED_RECOVERY_EXHAUSTED` | Terminal bridge recovery limit/deadline outcome | Listener Supervisor State Evaluator / Health Durable Writer | Incident/count/deadline/current identity/escalation record | No implicit retry; separate fenced SFF-03 decision only | Blocks readiness | `RRV-LS-003`, `RRV-FH-002` |
| `HEALTH_TIME_AUTHORITY_DEGRADED` | Trustworthy clock-correlation unavailable | Listener Supervisor State Evaluator / Health Durable Writer | Clock evidence, identities, pending cursor, recovery samples | Restored degraded until closed recovery succeeds | Blocks startup and runtime readiness | `RRV-FH-003` |
| `SUBSCRIPTION_VERIFIED` | Current-generation accepted-subscription proof | Listener Supervisor State Evaluator from authenticated RAPI/direct evidence | Current epoch/generation/subscription evidence | Must be reproved for a new bridge generation | Required | `RRV-FH-001`, `RRV-ST-001` |
| Bridge states/outcomes: `BRIDGE_STARTUP_UNPROVEN`, `BRIDGE_STARTING`, `BRIDGE_READY`, `BRIDGE_SUSPECT`, `RECYCLE_PENDING`, `RECYCLE_CANCELED`, `BRIDGE_FENCED`, `RECYCLE_EXECUTING`, `BRIDGE_REHYDRATING`, `BRIDGE_FAILED`, `FAILED_RECOVERY_EXHAUSTED`, `PLANNED_SHUTDOWN`, `LISTENER_EPOCH_TRANSITION` | ADR-016 section 3.9 complete state table | Listener Supervisor State Evaluator / Health Durable Writer | State-specific current-generation grant/incident/evidence records | State-specific restore/adopt/no-action rules in the same table | Only `BRIDGE_READY` with every independent startup gate can contribute to readiness | `RRV-FH-001`, `RRV-FH-002`, `RRV-FH-003` |
| Health degradation states: `HEALTH_PERSISTENCE_DEGRADED`, `HEALTH_STORE_CORRUPT`, `HEALTH_TRANSPORT_DEGRADED`, `HEALTH_AUTHENTICATION_FAILED`, `HEALTH_AUTHORITY_DIVERGED`, `HEALTH_TIME_AUTHORITY_DEGRADED` | ADR-016 state/failure matrix | Listener Supervisor State Evaluator; Health Durable Writer where persistence is available | Exact health incident or explicitly non-durable degradation evidence | Restore degraded and run only the named recovery transaction; never projection fallback | Blocks affected/all readiness as specified | `RRV-FH-001`, `RRV-FH-002`, `RRV-FH-003` |
| Five termination fields | Independent Initiator, Requested Action, Execution Method, Observed Cause, Result | Listener Supervisor State Evaluator / Health Durable Writer | Complete per-field evidence references | Recovered as recorded; deficiencies become `UNKNOWN` | Unresolved unsafe state blocks affected recovery/readiness | `RRV-FH-002` |
| `recovery_transaction_id` / `continuity_identity` | One ATR/bar rehydration or continuity disposition | Listener Supervisor coordinates; canonical bar/ATR owners acknowledge domain results | Recovery record plus exact finalized-bar cursor and ATR identity | Resume or fail closed; no projection reconstruction | Matching canonical ATR proof required | `RRV-ATR-001` |
| `EXPECTATION_STARTUP_UNPROVEN` | Market-data expectation lacks startup proof | Market Data Expectation Evaluator | Current policy digest/calendar/subscription/lifecycle/clock evidence | Recomputed under restored supervisor authority | Blocks readiness | `RRV-LS-003`, `RRV-ST-001` |
| `COMMAND_CENTER_ALIGNED` | Observational canonical-to-projection parity gate | Startup Orchestrator evaluates immutable projection; no canonical writer | Comparison evidence only | Re-evaluate projection; never change listener/session/recovery state | MAY fail observational startup gate only | `RRV-ST-001` |
| Shared/OneDrive health projection | Asynchronous observational projection | Projection Publisher writes projection only | Projection sequence/source commit identity | Rebuildable; never restores authority | Supplies no underlying readiness proof | `RRV-FH-001` |
| Diagnostic immutable snapshot | Prepublished read model | Owning startup/event/command transaction publishes; GET has no writer authority | Snapshot identity/epoch/generation/status | Missing/wrong snapshot returns read-only disposition | Never creates readiness; MAY report it | `RRV-DP-001`, `RRV-DP-002` |

The Phase 2 completion statement was disproved by the subsequent independent review and is superseded. Canonical incorporation, implementation, verification, deployment, `READY_LOCKED`, Bucket 0 completion, Bucket 1 authorization, and trading remain unauthorized. `DEBT-2026-07-17-012` and `DEBT-2026-07-17-016` remain `BLOCKING`; DEBT-015 remains separately governed.

## 13. Superseded Phase 3A conflict disposition

The rows below preserve the Phase 3A reconciliation as historical evidence. The independent Phase 3A review disproved its storage-schema, session-authority, diagnostic-inventory, and semantic-traceability completion claims. Section 14 supersedes these rows for approval-readiness purposes.

| Conflict | Final normative reconciliation | Surfaces | Status |
|---|---|---|---|
| ADR-014 status and contract drift | ADR-014 is approved; the support contract remains draft, preserves both authorization fields and the sole Session Commit Writer, and prohibits every unlisted exit | ADR-014; Entry Session Contract; ledger; README | `APPROVED` for ADR-014; `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` for support text |
| Competing listener specification | The old combined support draft is noncanonical historical evidence only and removed from active normative and implementation dependencies | Withdrawn support draft; README; ledger; traceability | `WITHDRAWN — SUPERSEDED DRAFT` |
| Restart cancellation | `RESTART_CANCELED` is a terminal durable incident outcome with atomic current-listener `HEALTHY`/`SUSPECT` reevaluation and no process action, reopen, or retry | ADR-015 3.4.2; verification 4.1-4.2 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Full-listener versus bridge exhaustion | `RECOVERY_RATE_LIMITED_FAILED` is the full-listener terminal pre-fence outcome; `FAILED_RECOVERY_EXHAUSTED` is the bridge terminal outcome | ADR-015 3.4.2/3.11.7; ADR-016 3.9; verification 4.6 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Shared-feed policy-invalid token | `SHARED_FEED_POLICY_INVALID` is a policy-validation disposition and startup failure reason, not a state or incident outcome; it produces zero speculative process action | ADR-015 3.11.2.1; startup; verification 4.6 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Incomplete health transitions | Separate persistence, transport, authentication, authority-coherence, and time state machines define every permitted edge; every unlisted edge is prohibited | ADR-016 3.9.1; verification 5.8 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Unenforceable cross-database identity reference | Pattern A uses one physical SQLite database, same-database constraints, table writer authorization, and a mechanical nonauthority coordinator | ADR-015 3.3; ADR-016 3.6; startup; verification 5.8 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Session exit openness | Every exit not expressly permitted by the twelve-state table is prohibited | Entry Session Contract 3.1 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Startup and trading circularity | Startup terminates `READY_LOCKED` or `FAILED`; only later may a separate governed decision evaluate `TRADING_PERMITTED`, which supplies no startup evidence | Startup 6.2/11; verification 8; ledger 16 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Diagnostic approval versus implementation conformance | Nineteen routes remain source nonconformances and migration obligations; architecture approval, implementation, runtime purity verification, and deployment remain distinct | Diagnostic Purity 5-8; verification 9 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Clause-level traceability deferred | The completed clause registry assigns stable IDs to every mandatory clause and reverse-maps all verification IDs | Clause Registry; Verification 2.1 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Subscription roles collapsed | Listener produces authenticated proof, State Evaluator decides, Health Durable Writer commits `SUBSCRIPTION_VERIFIED`; the committed state is authority | ADR-016 3.3.4; startup; verification 5.8 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Command Center projection authority | `COMMAND_CENTER_ALIGNED` is observational parity only and cannot close listener rehydration or supply domain authority | ADR-015 3.12; startup; verification 7-8 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Amendment ledger and verification omissions | Ledger carries the Phase 3A vocabulary, storage, role, and ordering obligations; verification carries positive, negative, restart, persistence, and escalation cases | Ledger 18; Verification 2.1/4.6/5.8/8 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |

No Phase 3A row is `CANONICALLY INCORPORATED`, `IMPLEMENTED`, `VERIFIED`, or `DEPLOYED`.

### 13.1 Active closed vocabulary and ownership mapping

| Domain | Closed values or facts | Owner and transition authority | Logical writer or evidence producer | Restart and readiness rule | Verification |
|---|---|---|---|---|---|
| Entry Session | Twelve states in Entry Session Contract 3.1 | Entry Agent Session Commit Writer | Same writer; receiver and policy provide input only | State-specific recovery; only reverified current context can satisfy session gate | `RRV-SR-001/002` |
| Full listener | `STOPPED`, `STARTING`, `REHYDRATING`, `HEALTHY`, `SUSPECT`, `FENCED`, `STOPPING`, `LISTENER_FAILED`, `AMBIGUOUS_PROCESS_AUTHORITY`, `SUPERVISOR_STORE_FAILED` | Listener Supervisor State Evaluator | Listener Supervisor Incident and Epoch Writers | Restore exact state; only `HEALTHY` contributes readiness | `RRV-LS-001/002/003` |
| Restart incident | `RESTART_PENDING`, `RESTART_FENCED`, `RESTART_EXECUTING`, `RESTART_REHYDRATING`; outcomes `RESTART_CANCELED`, `RECOVERY_RATE_LIMITED_FAILED`, `RESTART_COMPLETED`, `RESTART_FAILED` | Listener Supervisor State Evaluator | Listener Supervisor Incident Writer | Terminal outcomes survive restart; no automatic retry for canceled or rate-limited outcome | `RRV-LS-001/002/003` |
| Shared-feed policy | `SHARED_FEED_POLICY_INVALID` validation disposition | Listener Supervision Policy Evaluator | Listener Supervisor Incident Writer | Blocks startup; no process action; corrected version must revalidate | `RRV-LS-003`, `RRV-ST-001` |
| Bridge | ADR-016 3.9 bridge states plus terminal `FAILED_RECOVERY_EXHAUSTED` | Listener Supervisor State Evaluator | Health Durable Writer; Bridge Controller only acknowledges and executes | Exact-state restoration; only ready current generation contributes | `RRV-FH-001/002/003` |
| Health control | Startup-unproven plus persistence, transport, authentication, authority-coherence, and time ready/degraded/corrupt states in ADR-016 3.9.1 | State Evaluator | Health Durable Writer; external recovery writer only during corrupt-store governance | Restore exact durable state; degraded, unproven, and corrupt states block their named readiness | `RRV-FH-001/002/003` |
| Subscription | `SUBSCRIPTION_PROOF_OBSERVED` evidence fact; `SUBSCRIPTION_VERIFIED` committed positive state | State Evaluator | Listener produces evidence; Health Durable Writer commits state | Reprove for current generation; only committed state contributes | `RRV-FH-001`, `RRV-ST-001` |
| Termination | Independent Initiator, Requested Action, Execution Method, Observed Cause, Result; deterministic concrete, `NONE`, or `UNKNOWN` per field | State Evaluator | Authenticated producers provide evidence; Health Durable Writer commits | Restore as committed; unsafe unknown blocks affected action | `RRV-FH-002` |
| Runtime identities | supervisor generation, listener epoch, bridge generation, incident, fence, and recovery identities | Named ADR-015/016 evaluator | Ownership-separated logical writers in one physical runtime-authority database | Same-database validation; stale identities reject | `RRV-LS-001/002`, `RRV-FH-001` |
| ATR continuity | Closed retain, rehydrate, invalidate, and rebuild dispositions and four invalidation reasons | Canonical bar and ATR owners under Supervisor recovery coordination | Domain owners publish acknowledgement and evidence | Exact recovery identity and finalized cursor required | `RRV-ATR-001` |
| Startup | Required gates in Startup section 6; terminal `READY_LOCKED` or `FAILED` | Startup Orchestrator evaluates owner proofs | Domain writers; orchestrator writes only startup result | No indefinite or partial terminal state | `RRV-ST-001` |
| Post-start trading | `TRADING_PERMITTED` | Separate deployment and trading authorization authority | Separate decision writer | Never contributes to startup, Bucket 0, or Bucket 1 authority | `RRV-ST-001`, `RRV-GOV-001` |
| Projection and parity | Shared health projection; `COMMAND_CENTER_ALIGNED` | Projection Publisher and Startup parity evaluator | Projection writer only | Observational; no domain authority or lifecycle closure | `RRV-FH-001`, `RRV-ST-001` |
| Diagnostic snapshot | Immutable prepublished snapshot or `UNINITIALIZED`, `UNAVAILABLE`, or `STALE` | Owning domain publisher | GET has no writer | Reads never create readiness or recover state | `RRV-DP-001/002` |

Every transition not explicitly permitted by its governing state table is prohibited. The exhaustive clause mapping is `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md`; this summary is not a substitute.

### 13.2 Governance-stage status

| Artifact or stage | Status |
|---|---|
| ADR-014 | `APPROVED` |
| ADR-015, ADR-016, active supporting drafts, ledger, matrix, and clause registry | `PENDING INDEPENDENT APPROVAL` |
| Withdrawn combined listener support draft | `WITHDRAWN — SUPERSEDED DRAFT` |
| Canonical incorporation | `IDENTIFIED` as a future separately authorized stage |
| Implementation | `IDENTIFIED` as a future separately authorized stage |
| Runtime verification | `IDENTIFIED` as a future separately authorized stage |
| Deployment | `IDENTIFIED` as a future separately authorized stage |

This matrix itself remains draft evidence. It does not approve, incorporate, implement, verify, or deploy any proposal.

## 14. Phase 3B active conflict disposition

Every row below is `CORRECTED IN DRAFT` and `PENDING INDEPENDENT APPROVAL` unless ADR-014 or the withdrawn artifact is expressly stated. No row is canonically incorporated, implemented, verified, or deployed.

| Conflict | Phase 3B normative correction | Exact surfaces | Status |
|---|---|---|---|
| ADR-014 baseline | Approved ADR-014 remains unchanged; the metadata-applied hash is `528B3C7099D63DB41C6B85E381EAD37AD1E479867C07934FD077EBBD8B5EC321`; the earlier recorded content hash is not reconstructable from current history | ADR-014; Entry Session Contract; README; Phase 3B redline | `APPROVED` for ADR-014 only |
| Competing listener draft | Combined support draft is historical, noncanonical, not an authority or implementation input | Withdrawn draft; README; ledger; traceability | `WITHDRAWN — SUPERSEDED DRAFT` |
| Runtime store prose was not implementable | New Runtime Authority Store Schema defines database identity, every table/column/nullability/key/check/FK, writer allowlists, typed transactions, crash/replay and reconstruction | Store Schema; ADR-015 3.3; ADR-016 3.6; Startup 6/6.3; Verification 5.8-5.9 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Acknowledgement/current-listener storage undefined | Exact `listener_current`, transition, rehydration, required-domain, and domain-acknowledgement tables bind current generation/epoch/recovery identities; Command Center is excluded | Store Schema 4.3/7.1; ADR-015 3.3 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Cross-writer atomicity generic | Closed `TX-LSN-*`, `TX-BRG-*`, `TX-HEALTH-*`, and `TX-STORE-*` catalogs define preconditions, writer sets, writes, result, idempotency, crash and rollback | Store Schema 7-10; ADR-015; ADR-016; Verification 5.9 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Entry policy decision conflated with persistence | Session-lock policy solely decides eligibility/rollover; Entry Agent Session Commit Writer solely writes and executes the atomic transaction; mechanical rejection transfers no policy authority | Entry Session Contract 2-3; ledger 5; traceability | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Startup store gates relied on prose readiness | Gates now query schema identity/FKs/writer registry/current generation/listener/incident/ack/bridge/six health dimensions/aggregate/cursors with 19 fixed failure results | Startup 6/6.3; Store Schema 10 | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Diagnostic inventory was not source-bound and was inaccurate | Current inventory is exactly thirteen service/path entries proven against commit `869b3f...`, tree `704fd715...`; absent paths/symbols are removed; Entry Agent persistence/logging paths are added; future commits regenerate the manifest | Diagnostic Purity 5; Verification 9; ledger 18; external traceability | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Traceability was count-complete boilerplate | Registry is regenerated after Phase 3B and gives each requirement a clause-specific scenario, assertion, preconditions, stimulus, evidence, result, negative/failure and applicable restart/corruption case | Clause Registry; Verification 2.1; external traceability | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Writer/owner mappings drifted | Registry and store contract distinguish evidence producer, ingress validator, evaluator/decision authority, transition authority, logical durable writer, and mechanical transaction coordinator | Store Schema 6; ADR-015/016; Entry Session; Startup; Clause Registry | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |
| Phase 3A completion claims remained active | Phase 3A record is retained and marked superseded; Phase 3B record documents each overstatement and final draft correction | Phase 3A and Phase 3B redlines | `CORRECTED IN DRAFT`; `PENDING INDEPENDENT APPROVAL` |

### 14.1 Phase 3B ownership and evidence closure

| Domain/fact | Decision or transition authority | Durable writer | Evidence producer | Readiness/restart effect |
|---|---|---|---|---|
| Entry candidate eligibility and rollover | Session-lock policy | Entry Agent Session Commit Writer | receiver/validator/integrity producer | fail closed on rejection/failure; writer cannot decide eligibility |
| Listener lifecycle and incidents | Listener Supervisor State Evaluator | Listener State/Incident/Epoch/Acknowledgement Writers per typed transaction | listener, Health Ingress, OS, authoritative domains | only exact committed state; no projection closure |
| Bridge grant/lifecycle | Supervisor State Evaluator | Bridge Generation Writer for grant; Health Durable Writer for lifecycle | Bridge Controller acknowledgement/execution evidence | current generation only; exhaustion distinct from listener rate exhaustion |
| Health dimensions/aggregate | State Evaluator | Health Durable Writer | authenticated listener/bridge/RAPI/OS sources through Health Ingress | six dimensions recompute one aggregate; degradation blocks named gates |
| Store mechanics | domain authorities named above | logical writers named above | transaction plans and source evidence | Coordinator only serializes/enforces/commits; supplies no domain authority |
| Diagnostic projection | authoritative owner publishes immutable snapshot | no GET writer | snapshot owner | observational; source commit inventory regenerated for later trees |
| Command Center parity | Startup parity evaluator | projection writer only | canonical owners | observational gate only; cannot close rehydration or grant readiness authority |

### 14.2 Phase 3B governance stages

| Stage | Status |
|---|---|
| ADR-014 | `APPROVED` |
| ADR-015, ADR-016, Store Schema, supporting drafts, ledger, matrix, registry | `PENDING INDEPENDENT APPROVAL` |
| Canonical incorporation | `IDENTIFIED` future authorization only |
| Implementation | `IDENTIFIED` future authorization only |
| Runtime verification | `IDENTIFIED` future authorization only |
| Deployment | `IDENTIFIED` future authorization only |

The only active statuses are the concepts listed above. A draft correction is not approval. This matrix does not authorize implementation, verification, deployment, `READY_LOCKED`, Bucket 0 completion, Bucket 1, or trading.
