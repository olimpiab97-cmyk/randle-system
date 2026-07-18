# 2026-07-17 Production Recovery - Documentation-Phase Architecture Traceability Matrix

Task: ADR-014 through ADR-016 and coordinated specification drafts

Effective date: ADR-014 approved 2026-07-17; ADR-015, ADR-016, and supporting drafts have no canonical effective date

Implementation scope: **NONE - documentation only**

Canonical authority status: ADR-014 is **APPROVED / GOVERNING**. Governance records approved-content SHA-256 `BD76D1B398515EA00E230B9C8A00A540344E061A36B228BF112F784F6AC34F25`; the metadata-applied committed file is `528B3C7099D63DB41C6B85E381EAD37AD1E479867C07934FD077EBBD8B5EC321`, and the corresponding pre-metadata blob is not independently reconstructable from current repository history. ADR-015, ADR-016, and supporting specification drafts are **NOT APPROVED / NONCANONICAL**.

Traceability coverage result: **PHASE 3C1 NORMATIVE REMEDIATION DRAFTED; SEMANTIC TRACEABILITY DEFERRED TO PHASE 3C2 — NOT APPROVAL READY**

Historical clause-level source: `Architecture/Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md`. It is rejected Phase 3B evidence, not a current semantic mapping source. This matrix remains only a package-level evidence/debt index. Phase 3C2 will rebuild semantic forward/reverse traceability only after independent acceptance of the Phase 3C1-R1 hashes.

Implementation conformance result: **FAIL / NOT STARTED**

Applicable recovery debt: `DEBT-2026-07-17-012`, `DEBT-2026-07-17-013`, `DEBT-2026-07-17-014`

Separate nondependency debt: `DEBT-2026-07-17-015`

Separate blocking ingress-security debt: `DEBT-2026-07-17-016`

Approval-review specification debt: `DEBT-2026-07-17-017`, `DEBT-2026-07-17-018`

Repository-wide blocker: `DEBT-2026-07-16-005` and other registry blockers

Deployment authorization: **NONE**

## 1. Existing implementation to authority and proposed correction

No production file was modified in this phase. The rows below preserve the backtrace from known nonconforming implementation to existing authority and the proposed draft that would govern a future correction.

| Production file | Implementation unit | Existing behavior | Existing canonical authority | Proposed draft target | Conformance | Debt |
|---|---|---|---|---|---|---|
| `Engines/trade_manager.py` / `EntryAgent/tv_context_server.py` | public `/webhook/tv-context` relay and Entry receiver | Public route accepts/forwards JSON and records route metadata without authenticated sender identity or sender-bound freshness/replay proof | TradingView Webhook Contract; Constitution sections 3, 6, 12-16, 20, 22 | ADR-014 section 3.4.1; startup sections 6 and 10; separate future ingress-security decision | **FAIL - unchanged; security authority absent** | DEBT-016 |
| `EntryAgent/tv_context_server.py` | `should_replace_stale_locked_liquidity_context`, `merge_session_liquidity_context`, `receive_tv_context` session receipt/persistence boundary | Pre-merge sender/receiver lock distinction and sequential raw/canonical writes permit session identity split | Constitution sections 12-16, 22; Engine sections 26, 29, 31; ADR-012 sections 3.5-3.6; Runtime Authority sections 4-5 | ADR-014 sections 3.3-3.12; Entry Session Rollover Contract sections 4-13 | **FAIL - unchanged** | DEBT-012 |
| `EntryAgent/tv_context_server.py` | operator lock override/raw-context write boundary | Raw and canonical files can be written sequentially under separate failure points | Constitution sections 6, 15-16, 22; Engine sections 26, 29, 31 | ADR-014 sections 3.6-3.12 | **FAIL - unchanged** | DEBT-012 |
| `EntryAgent/entry_agent.py` | `apply_observation_cycle_reset` and observation persistence | Observation session latch can advance without committed current-session frozen lock | Constitution sections 6, 15, 17, 22; Lock Contract section 4.1 | ADR-014 sections 3.5-3.10; rollover contract sections 6-11 | **FAIL - unchanged** | DEBT-012 |
| `EntryAgent/entry_agent.py` | session aggregate persistence/restoration/status | Prior truthy lock can remain active while receiver session advances | Constitution sections 12-16; Engine sections 28-32; Runtime Authority section 5 | ADR-014 sections 3.6-3.12 | **FAIL - unchanged** | DEBT-012 |
| `executor.py` | `ExecutorTickPipeline.accept`, `apply_executor_tick_record`, `record_valid_watchdog_tick` | Accepted recovery event is evaluated against prior watchdog timestamp before liveness commit | Constitution sections 12-17, 22; ADR-012 sections 3.3, 3.6 | ADR-015 sections 3.6-3.8 | **FAIL - unchanged** | DEBT-013 |
| `executor.py` | `build_watchdog_state`, `execute_listener_restart`, `reject_if_watchdog_blocks_action` | Executor owns direct process restart; restart is level-triggered/in-memory | Constitution section 6; Engine sections 15, 26-29, 35; Runtime Authority section 1 | ADR-015 sections 3.1-3.11 | **FAIL - unchanged** | DEBT-013 |
| `executor.py` | `/debug/watchdog`, `/debug/watchdog_alert` and other GET/read paths | GET can create/execute restart effects | Constitution section 16; Engine section 32; ADR-012 section 3.6 | ADR-015 section 3.13; Diagnostic Purity Contract | **FAIL - unchanged** | DEBT-013 |
| `rithmic_live_listener.py` | `atomic_write_text`, `write_feed_health`, `TickWorker.flush_feed_health` | Write failure can be swallowed; pending clears before verified durable success; multiple producers replace shared target | Constitution sections 12, 17, 22; ADR-012 sections 3.1-3.2; Runtime Authority sections 1-2 | ADR-016 sections 3.3-3.7; Phase 3B clause/scenario/assertion registry `ADR016-REQ-*`; Store Schema `STORE-REQ-*` | **FAIL - unchanged** | DEBT-014 |
| `rithmic_live_listener.py` | feed-health refresh/dead-restart/bridge termination path | Stale shared projection can declare death and terminate a live bridge without current-generation durable fence | Constitution sections 3, 6, 12, 16-17, 22; Runtime Authority section 1 | ADR-016 sections 3.8-3.13 | **FAIL - unchanged** | DEBT-014 |
| `Engines/trade_manager.py` | `get_tradingview_atr_route` -> `get_tradingview_atr` cold-cache path | Diagnostic GET populates `TRADINGVIEW_ATR_CACHE`; diagnostic draft incorrectly classified it nonmutating | Constitution section 16; Engine section 32; ADR-012 section 3.6 | Diagnostic Purity Contract sections 2, 5, 7 after correction | **FAIL - unchanged; audit rejected** | DEBT-017 |
| `data_paths.py` | feed-health path selection | Same shared path serves durable-looking control and projection roles | Runtime Authority section 1 projection boundary | ADR-016 sections 3.2-3.7 | **FAIL - unchanged** | DEBT-014 |
| `launch_all.ps1` | `Ensure-ListenerBridge`, `Test-ListenerBridgeContract`, feed-health readiness | Launcher starts listener directly and reads shared health projection as readiness/control evidence | Constitution sections 6, 12, 16; Runtime Authority sections 1, 5 | ADR-015 sections 3.1, 3.14; ADR-016 sections 3.2, 3.7; Startup Contract | **FAIL - unchanged** | DEBT-013, DEBT-014 |
| `run_system.ps1` | broad stop and direct process start | Broad Python termination and direct listener start bypass supervisor/fencing/evidence | Constitution sections 6, 12, 22; Engine sections 28-29, 35 | ADR-015 sections 3.1, 3.14; Startup Contract sections 2-5, 11-12 | **FAIL - unchanged** | DEBT-013 |
| Trade Manager / Entry Agent / Command Center | epoch/generation/session/ATR readiness consumers | Complete deterministic behavior across bridge/listener/cold-start transitions is not implemented/proven | Constitution sections 12, 14, 17; Runtime Authority sections 3, 5 | ADR-015 section 3.12; Startup Contract sections 7-9 | **PARTIAL/UNVERIFIED - unchanged** | DEBT-013, DEBT-014 |
| Startup/readiness future implementation | ADR-016 connection/login/subscription proof, Executor authority, debt gate | Draft names obsolete facts and lacks positive zero-applicable-Blocking-debt/Executor-authority states | Debt Specification sections 3, 6, 8; approved ADR-014; proposed ADR-015 and ADR-016 | Startup Contract sections 6 and 11 after correction | **FAIL - specification rejected** | DEBT-018; DEBT-014, DEBT-016 |

## 2. Approved and proposed authority to expected implementation and verification

| Authority | Architectural invariant | Expected implementation | Verification | Current coverage | Debt |
|---|---|---|---|---|---|
| ADR-014 sections 3.3-3.5 | Complete candidate is archived, validated, and built without active mutation | Entry receiver, shared validator adapter, Entry session aggregate builder | Runtime Recovery Verification sections 3.1-3.3 | **APPROVED AUTHORITY / IMPLEMENTATION AND VERIFICATION MISSING** | DEBT-012 |
| ADR-014 section 3.4.1 | Route traversal, payload/session eligibility, and sender authentication are separate; production commit requires separately verified sender authority | Trade Manager relay, Entry receiver/validator, future sender-authentication authority | Future security decision plus public-route/sender/replay verification suite | **APPROVED BOUNDARY / SECURITY MECHANISM INTENTIONALLY UNRESOLVED** | DEBT-016 |
| ADR-014 sections 3.6-3.8 | One commit ID atomically joins all session members and prior retirement | Entry session transaction store/helper, receiver/Entry/frozen/observation/authorization projections | Verification sections 3.1, 3.4 | **APPROVED AUTHORITY / IMPLEMENTATION AND VERIFICATION MISSING** | DEBT-012 |
| ADR-014 sections 3.9-3.12 | Observation cannot lead commit; divergence/failure/duplicate/restart are fail-closed/idempotent | Entry observation/session restore/status/Command Center projection | Verification sections 3.2-3.5, 8 | **APPROVED AUTHORITY / IMPLEMENTATION AND VERIFICATION MISSING** | DEBT-012 |
| ADR-015 sections 3.1-3.5 | One Listener Supervisor owns full listener lifecycle/epoch and durable incidents | New supervisor/store, launcher/manual client, listener adoption/grant | Verification sections 4.3-4.5, 8 | **PARTIAL - draft only** | DEBT-013 |
| ADR-015 sections 3.6-3.8 | Accepted recovery data commits before evaluation; pending restart cancels before fence; one fence executes once | Executor intake/health/request; supervisor evaluator/fence/executor | Verification sections 4.1-4.4 | **PARTIAL - draft only** | DEBT-013 |
| ADR-015 sections 3.10-3.12 | Bridge generation differs from epoch; cross-symbol shared failure explicit; downstream deterministic | listener Bridge Controller, Executor/Trade Manager/Entry Agent/Command Center consumers | Verification sections 4.5, 6-8 | **PARTIAL - draft only** | DEBT-013 |
| ADR-015 section 3.11 | NQ/YM shared physical topology, sole runtime declaration, policy owner/schema/defaults/ranges/digest, BDP-before-SFF escalation, debounce/cancel/cooldown/rate failure | Listener Supervisor policy loader/evaluator/store; deployment policy artifact/manifest | policy validation plus all SFF boundary/cancellation/rate/escalation cases | **PARTIAL - exact draft only** | DEBT-013 |
| ADR-015 sections 3.13-3.14 | Diagnostics pure; startup/manual path has one supervisor | All GET/read routes; launchers/manual tooling | Verification sections 8-9 | **PARTIAL - draft only** | DEBT-013 |
| ADR-016 sections 3.1-3.4 | Direct health, local durable control, and shared projection are separate authorities | listener/Executor producers, local writer/store, projection publisher | Verification sections 5.2-5.3 | **PARTIAL - draft only** | DEBT-014 |
| ADR-016 sections 3.5-3.7 | Pending survives failed durable write; cursor/ack only after verification; shared projection async | health writer/store, data paths, publisher | Verification sections 5.1-5.3 | **PARTIAL - draft only** | DEBT-014 |
| ADR-016 sections 3.8-3.10 | Bridge recycle requires current-generation durable fence; store failure blocks automatic fences/entries | Bridge Controller, health decision store, readiness consumers | Verification sections 5.4-5.5 | **PARTIAL - draft only** | DEBT-014 |
| ADR-016 sections 3.6.5-3.6.7 | Corruption detection/quarantine, approved sources, no-source fail-closed recovery, preserved identities, staged migration/rollback/audit | Health Durable Writer recovery tool/store; startup owner disposition | corruption/quarantine/restore/reinitialize/migration/rollback/audit matrix | **PARTIAL - exact draft only** | DEBT-014 |
| ADR-016 sections 3.9.2-3.10 | Raw documented RAPI alerts plus process/intent evidence produce five independent fields; ambiguity is field-specific `UNKNOWN`; only BDP-01..04 recycle | listener raw evidence producer; State Evaluator; Health Durable Writer; Bridge Controller executor | callback/`RpCode`/intent/exit matrix, recovery cancellation, disappearance/unknown cases | **PARTIAL - exact draft only** | DEBT-014 |
| ADR-016 sections 3.11-3.16 | Corruption/recycle/degradation behavior isolates health from ATR/session and keeps reads pure | health recovery, listener ATR boundary, endpoints | Verification sections 5.6, 6, 9 | **PARTIAL - draft only** | DEBT-014 |

## 3. Specification draft to enforcement and proof

| Draft specification/amendment | Expected enforcement areas | Expected proof | Status | Debt |
|---|---|---|---|---|
| Entry Session Rollover Lifecycle Contract sections 2-13 | Entry receiver/session store, observation, projections, startup probes | ADR-014 suite/replay/crash/divergence | **DRAFT / MISSING IMPLEMENTATION** | DEBT-012 |
| Withdrawn Listener Supervision and Feed-Health Authority Contract | None; retained only as historical evidence | None; removed from active implementation dependencies | **WITHDRAWN — SUPERSEDED DRAFT** | DEBT-013, DEBT-014 remain governed by ADR-015/016 proposal |
| Production Startup, Recovery, and Readiness Contract sections 3-12 | supervisor bootstrap, store recovery, split public-route/sender proof, startup/manual/shutdown, every component readiness | isolated cold/manual/shutdown integration plus trust-boundary and restore matrix | **DRAFT / MISSING IMPLEMENTATION** | DEBT-012 through 014; DEBT-016 |
| Diagnostic Endpoint Purity Contract sections 1-6 | all GET/HEAD/health/status/debug/watchdog/audit/Command Center routes | static reachability plus byte/in-memory/process nonmutation | **DRAFT / MISSING IMPLEMENTATION** | DEBT-013, DEBT-014 |
| Runtime Recovery Verification Specification sections 3-10 | all corrected production and integration units | named deterministic/fault/integration artifacts | **DRAFT / NOT EXECUTED** | DEBT-012 through 014 |
| Exact Canonical Amendment Draft sections 2-14 | Constitution alignment, Vocabulary, Engine, ADR-012, Runtime Authority, contracts, safety/ops docs | approval diff review plus later conformance suites | **DRAFT / NOT APPLIED** | DEBT-012 through 014 |

## 4. Existing canonical authority amendment-target index

This is a document-target index only. A `Yes` value means the draft names an amendment location; it does not assert clause-level, forward/reverse, semantic, scenario, assertion, implementation, or verification completeness.

| Existing authority | Exact draft amendment location | Draft target identified? | Status/debt |
|---|---|---:|---|
| Constitution sections 3, 6, 12-17, 20, 22 | Amendment Draft section 2 | Yes | Pending approval; DEBT-012 through 014 |
| Lifecycle Vocabulary sections 2.1, 16, 18 | Amendment Draft section 3 | Yes | Pending approval; DEBT-012 through 014 |
| Lifecycle Engine sections 31, 32, 35, 40 | Amendment Draft section 4 | Yes | Pending approval; DEBT-012 through 014 |
| ADR-012 sections 3.3, 3.6, 6, 10 | Amendment Draft section 5 | Yes | Pending approval; DEBT-013, DEBT-014 |
| Runtime Authority sections 1, 3-5, 8-10 | Amendment Draft section 6 | Yes | Pending approval; DEBT-012 through 014 |
| NQ Continuity Verification sections 2.1, 2.5, 5-6 | Amendment Draft section 7 | Yes | Pending approval; DEBT-013, DEBT-014 |
| Session Liquidity Lock Contract sections 1, 3, 4.1, 10-11 | Amendment Draft section 8 | Yes | Pending approval; DEBT-012 |
| TradingView Webhook Contract sections 4, 7, 11-12 | Amendment Draft section 9 plus ADR-014 section 3.4.1 | **No for sender authentication** - rollover wording is drafted, but the separate security decision/mechanism remains intentionally unresolved | Pending approval; DEBT-012, DEBT-016 |
| Entry Pipeline precondition | Amendment Draft section 10 | Yes | Pending approval; DEBT-012 through 014 |
| Persistence and Recovery scope | Amendment Draft section 11 | Yes | Pending approval; DEBT-012 through 014 |
| Safety Rails system safety | Amendment Draft section 12 | Yes | Pending approval; DEBT-013, DEBT-014 |
| Architecture README draft index | Amendment Draft section 13 | Yes | Documentation index only |
| Live Ops Command Allowlist section 2 | Amendment Draft section 14 | Yes | Pending approval; DEBT-013, DEBT-014 |

## 5. Explicitly unchanged/separate authority

| Authority/scope | Disposition |
|---|---|
| ADR-006 through ADR-011 | Unchanged |
| ADR-013 | Unchanged |
| TradingView Liquidity Ladder Calculation Contract | Unchanged |
| TradingView Liquidity Ladder Verification Specification | Unchanged by ADR-014-016 |
| DEBT-015 shared-boundary contract conflict | Separate; not an ADR-014-016 dependency or exit criterion absent a newly approved AIA |
| DEBT-016 TradingView sender authentication | Separate security governance; blocks production readiness/candidate commitment but does not alter ADR-014 atomic transaction ordering |
| Pine, Step 2, Step 4, ATR formula, execution, risk | Unchanged |

## 6. Verification artifact register

All correction artifacts are future and currently **NOT EXECUTED**:

- ADR-014 rollover/atomicity/crash suite;
- archived prior/current NQ/YM rollover replay;
- ADR-015 threshold/cancel/fence/exactly-one/cross-symbol suite;
- ADR-016 write-failure/pending/corruption/bridge suite;
- ATR bridge/listener/cold-start rehydration suite;
- diagnostic endpoint purity suite;
- isolated cold/manual startup and shutdown integration;
- broad regression/replay report;
- RAPI callback/process/intent five-field termination and per-field `UNKNOWN` suite;
- shared-feed policy schema/digest/threshold/debounce/cancel/cooldown/rate/escalation suite;
- control-store quarantine/restore/no-source/reinitialize/migrate/rollback/audit suite; and
- TradingView public-route versus sender-authentication/spoof/replay/freshness suite after a security decision exists.

## 7. Five-gate and Governance Verification

| Gate | Documentation-phase result | Full recovery result | Debt |
|---|---|---|---|
| Architecture | **FAIL** - ADR-014 is approved; ADR-015 and ADR-016 remain rejected and unapproved | **FAIL** | DEBT-012 through 014; DEBT-016, DEBT-018 |
| Specification | **FAIL** - Entry, listener/health, startup, diagnostic, verification, and amendment drafts rejected | **FAIL** | DEBT-012 through 014; DEBT-016 through 018 |
| Implementation | **NOT IN AUTHORIZED SCOPE** | **FAIL / NOT STARTED** | DEBT-012 through 014; DEBT-016 through 018 |
| Verification | **FAIL** - verification specification rejected and no suites executed | **FAIL / NOT STARTED** | DEBT-012 through 014; DEBT-016 through 018 |
| Traceability | **PASS for approval-review findings -> debt mapping** | **PARTIAL pending corrected authority, implementation, and tests** | DEBT-012 through 014; DEBT-016 through 018; repository DEBT-005 |

Task-level Governance Verification: **FAIL** because ADR-015, ADR-016, and supporting draft authority remain unapproved and applicable Blocking debt remains.

Repository-wide Governance Verification: **FAIL** because applicable and broader Blocking debt remains.

Deployment/production restart/trading authorization: **NONE**.

## 8. Coordinated approval-review decisions and blocking corrections

| Candidate | Decision | Blocking mapping |
|---|---|---|
| ADR-014 | **APPROVED** by explicit user action, bound to SHA-256 `BD76D1B398515EA00E230B9C8A00A540344E061A36B228BF112F784F6AC34F25` | Implementation/security/verification remain DEBT-012, DEBT-016 |
| ADR-015 | **REJECT** | excess bridge attempt; circular SFF-02 evidence; unnamed data-expected authority; discretionary ATR disposition - DEBT-013, DEBT-018 |
| ADR-016 | **REJECT** | overlapping terminal dimensions; planned-exit BDP contradiction - DEBT-014 |
| Entry Session Rollover Contract | **REJECT** | incomplete states and postcommit current/retirement wording - DEBT-012 |
| Listener Supervision/Health Contract | **REJECT** | missing generation/version fields; wrong durable-write model; supplemental projection authority; fence/grant ownership - DEBT-013, DEBT-014 |
| Production Startup/Readiness Contract | **REJECT** | obsolete facts and missing debt/Executor gates - DEBT-018; DEBT-014, DEBT-016 |
| Diagnostic Purity Contract | **REJECT** | omitted ATR GET cache mutation - DEBT-017 |
| Runtime Recovery Verification Specification | **REJECT** | security/policy/terminal/store/startup/purity proof incomplete or contradictory - DEBT-012 through 014, DEBT-016 through 018 |
| Canonical Amendment Ledger | **REJECT** | does not carry current security/policy/terminal/store/readiness contracts and retains weak/open wording - DEBT-012 through 014, DEBT-016 through 018 |

Full findings: `Architecture/Audits/2026-07-17_Coordinated_Authority_Package_Approval_Review.md`.

## 9. Approval Remediation Phase 1 traceability

| Rejected requirement | Remediated decision/contract | Verification obligation | Debt status |
|---|---|---|---|
| No bridge attempt beyond maximum | ADR-015 3.11.5; listener contract 7 | Runtime Recovery Verification 4.6 exact count boundary/no action | DEBT-013 remains BLOCKING pending approval/implementation/test |
| Acyclic SFF-02 evidence | ADR-015 3.11.6; listener contract 7 | Verification 4.5 complete producer/evidence chain and forbidden action inputs | DEBT-013 remains BLOCKING |
| Named market-data-expected authority | ADR-015 3.11.3; startup `MARKET_DATA_EXPECTATION_READY` | Verification 4.6 and 8 startup/expiry/shutdown/clock/intent cases | DEBT-013/018 remain BLOCKING |
| Deterministic ATR disposition | ADR-015 3.12; listener contract 14; startup 9; amendment ledger ADR-012/runtime text | Verification 6 all retain/invalidate/rebuild/rehydrate cases | DEBT-013 remains BLOCKING |
| Independent termination meanings | ADR-016 3.9.1; listener contract 13 | Verification 5.4 five-field cross-product and per-field UNKNOWN | DEBT-014 remains BLOCKING |
| Unexpected-only BDP-01 | ADR-016 3.10 | Verification 5.4 all planned/transition exclusions | DEBT-014 remains BLOCKING |
| Projection never participates in control | ADR-016 3.8; listener contract 12; amendment ledger 5B | Verification 5.3 projection mutation with byte-identical decisions | DEBT-014 remains BLOCKING |
| Atomic current activation/prior retirement | Entry Session Contract 8-9, 13; amendment ledger sections 3, 4, 6 | Verification 3 split-commit crash/fault cases | DEBT-012 remains BLOCKING |
| Positive startup authority/debt gates | Startup sections 4-6, 10-11 | Verification 8 zero-debt, Executor/Supervisor, epoch/session/ATR/ladder/sender proofs | DEBT-016/018 remain BLOCKING |
| Complete diagnostic GET audit | Diagnostic Purity 5-7 | Verification 9 both ATR cold-cache routes plus Executor tick debug and Trade Manager tick debug/health lazy-initialization cold/warm cases | DEBT-017 remains BLOCKING |

Phase 1 evidence record: `Architecture/Audits/2026-07-17_Approval_Remediation_Phase_1_Redlines.md`.

## 10. Superseded Phase 3A package-level reconciliation

This section preserves Phase 3A history. Its current-schema, nineteen-route, and semantic-traceability completion claims are superseded by section 11 and the Phase 3B remediation record.

| Phase 3A obligation | Normative source | Verification family | Package status |
|---|---|---|---|
| Closed listener and restart-incident vocabulary, including `RECOVERY_RATE_LIMITED_FAILED` | ADR-015 3.4.2, 3.11.7 | `RRV-LS-001/002/003` | Draft; pending independent approval |
| `SHARED_FEED_POLICY_INVALID` validation disposition | ADR-015 3.11.2.1; Startup | `RRV-LS-003`, `RRV-ST-001` | Draft; pending independent approval |
| Complete health-control transition tables | ADR-016 3.9.1 | `RRV-FH-001/002/003` | Draft; pending independent approval |
| One physical runtime-authority database with ownership-separated writers | ADR-015 3.3; ADR-016 3.6 | `RRV-LS-001`, `RRV-FH-001/003` | Draft; pending independent approval |
| Producer, evaluator, and writer separation for subscription and major facts | ADR-016 3.3.4; Startup | `RRV-FH-001`, `RRV-ST-001` | Draft; pending independent approval |
| Every unlisted Entry Session transition prohibited | Entry Session Contract 3.1 | `RRV-SR-001/002` | Draft support for approved ADR-014; pending independent approval |
| Startup terminal result precedes post-startup `TRADING_PERMITTED` decision | Startup 6.2, 11 | `RRV-ST-001`, `RRV-GOV-001` | Draft; pending independent approval |
| Nineteen identified diagnostic GET migration obligations remain unimplemented | Diagnostic Purity 5.1-7 | `RRV-DP-001/002` | Draft architecture; source nonconformance unchanged |
| Clause-level bidirectional traceability | Phase 3A Clause Registry | All `RRV-*` families | Historical structural claim rejected; semantic traceability not approval-ready |
| Combined listener support draft | Withdrawn support document header | None | `WITHDRAWN — SUPERSEDED DRAFT` |

ADR-014 remains approved. ADR-015 and ADR-016 remain unapproved. No row is canonical incorporation, implementation, runtime verification, deployment, `READY_LOCKED`, Bucket 0 completion, Bucket 1 authorization, or trading authorization.

## 11. Phase 3B package-level reconciliation

Source evidence below is bound to commit `869b3f08df5c5dbfa975246547455ad185288605`, tree `704fd715cad3aad281c534f8337840e3aab96234`. It is not runtime verification and is regenerated for a later source commit.

| Obligation | Normative source | Evidence/verification mapping | Status |
|---|---|---|---|
| Complete implementable Runtime Authority Store | Store Schema sections 2-10; ADR-015 3.3; ADR-016 3.6 | `RRV-STORE-001`; `STORE-REQ-*` scenario/assertion rows | Draft; pending independent approval; not implemented |
| Closed writer routing and mechanical-only Coordinator | Store Schema 6-8 | `RRV-STORE-001`; writer-denial/version/idempotency/crash scenarios | Draft; pending independent approval |
| Listener and bridge typed transactions | Store Schema 7; ADR-015/016 exact references | `RRV-LS-*`, `RRV-FH-*`, `RRV-STORE-001` | Draft; pending independent approval |
| Session policy versus writer separation | Entry Session Contract 2-3 | `RRV-SR-001/002`; `ESR-REQ-*` scenario/assertion rows | Draft support for approved ADR-014; pending independent approval |
| Store-bound startup evidence | Startup 6 and 6.3 | `RRV-ST-001`, `RRV-STORE-001` | Draft; pending independent approval |
| Source-bound diagnostic purity inventory | Diagnostic Purity 5; Verification 9 | `RRV-DP-001/002`; thirteen route-specific `SCN-DEP-*` scenarios | Draft architecture; current source nonconforming |
| Clause-specific semantic traceability | Phase 3B Clause Registry | Historical generated requirement/scenario/assertion rows only | Rejected as substantive traceability; deferred to Phase 3C2; no runtime test executed |

### 11.1 Exact diagnostic source-bound findings

| Service | Current mutating GET routes in `869b3f...` | Demonstrated mutation family |
|---|---|---|
| Executor | `/debug/watchdog`; `/debug/watchdog_alert`; `/sync_snapshot` | restart/process control; working-order clear and state write |
| Entry Agent | `/debug/entry-liquidity`; `/entry/status` | `build_entry_status` -> `run_once(..., persist=True)`, pipeline-state persistence, and decision/reasoning log append |
| Trade Manager | `/debug/risk_state`; `/trades`; `/replay/<trade_id>`; `/debug/tradingview/atr/<symbol>`; `/debug/tradingview/atr_status`; `/debug/noon_runner_flatten`; `/events`; `/debug/atr_trade/<trade_id>` | reconciliation/noon/state writes; ATR cache writes; persistence load/normalization and corruption backup path |

Absent Phase 3A route/symbol claims are not current-source facts: Executor `/debug/tick_pipeline`; Entry Agent `/entry/executor_status`; Trade Manager `/debug/tick_pipeline`, `/health`, `/debug/nonclosed_trades`, `/paper_account_snapshot`, and `/config/trade_manager_mode`; `PERSISTENCE_STATE_CACHE`; `PERSISTENCE_STATE_CACHE_LOADED`; active-index mutation; lazy tick-pipeline initialization. Executor `/account_snapshot` is a local JSON snapshot read in this tree, not a Trade Manager proxy.

ADR-014 remains approved and unchanged. ADR-015, ADR-016, the Store Schema, and all supporting drafts remain noncanonical and unapproved. This matrix supplies no implementation, runtime verification, deployment, `READY_LOCKED`, Bucket 0 completion, Bucket 1, or trading authority.

This update records draft remediation only. The historical rejection decisions in section 8 remain the last approval decisions until a new coordinated review. No debt is retired, no gate result is promoted, and no implementation/deployment authority exists.

## 12. Historical Phase 3C1 package-level remediation index

This section is preserved as superseded Phase 3C1 package evidence and is intentionally not a one-row-per-clause registry. Section 13 is the active Phase 3C1-R1 package index. Detailed semantic clause-to-scenario traceability remains Phase 3C2 work.

| Normative defect family | Corrected draft source | Future proof family | Phase 3C1 status |
|---|---|---|---|
| Executable SQLite `STRICT` schema, exact types/checks/tables/keys/indexes/triggers | Store Schema; executable v2 SQL | `RRV-STORE-001` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1 REVIEW` |
| Exact FK parents/actions/deferral and insertion order | Store Schema section 4; executable v2 SQL | `RRV-STORE-001` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1 REVIEW` |
| Active writer exclusivity and registry version/hash | Store Schema sections 5-7; executable v2 SQL | `RRV-STORE-001` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1 REVIEW` |
| Reproducible schema hash | Store Schema section 3; executable v2 SQL marker block | `RRV-STORE-001` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1 REVIEW` |
| Initial bootstrap and unidentified-store quarantine | Store Schema sections 9-12; ADR-016; Startup | `RRV-STORE-001`, `RRV-ST-001` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1 REVIEW` |
| Operation-specific transaction envelopes and external recovery evidence | Store Schema sections 10-12; ADR-016; Startup | `RRV-STORE-001`, `RRV-FH-*` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1 REVIEW` |
| Listener stop completion, rate exhaustion, and corrected writer ownership | ADR-015; Store Schema transaction catalog | `RRV-LS-*`, `RRV-STORE-001` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1 REVIEW` |
| Subscription and bridge-generation ownership/version | ADR-016; Store Schema writer/trigger catalog | `RRV-FH-*`, `RRV-STORE-001` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1 REVIEW` |
| Twelve-state exact Entry Session transitions and recovery classifications | Entry Session Contract section 3; ledger section 18.2 | `RRV-SR-*` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1 REVIEW` |
| Exact startup store/supervisor evidence | Startup sections 5-6; Store Schema | `RRV-ST-001`, `RRV-STORE-001` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1 REVIEW` |
| Frozen diagnostic inventory | Diagnostic Purity Contract; Verification section 9 | `RRV-DP-*` | Preserved exactly: 31 registered GET entries, 13 mutating entries, 13 unique patterns |
| Semantic clause traceability | Future Phase 3C2 registry against accepted Phase 3C1-R1 hashes | Future exact semantic mappings | `DEFERRED TO PHASE 3C2 — NOT APPROVAL READY` |

ADR-014 remains approved and unchanged. ADR-015 and ADR-016 remain unapproved. The Store Schema, executable SQL, and supporting documents are draft/noncanonical. No approval review, canonical incorporation, implementation, production/runtime verification, deployment, `READY_LOCKED`, Bucket 0 completion, Bucket 1 authorization, or trading authorization occurs here.

## 13. Phase 3C1-R1 package-level F1-F8 index

This is not semantic clause traceability. It only indexes the targeted defect families for a later independent review.

| Finding | Normative sources | Isolated schema/specification proof family | Status |
|---|---|---|---|
| F1 calendar-valid date/UTC | Store Schema 14.1; SQL | `RRV-STORE-001` calendar vectors | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F2 writer succession/serialization | Store Schema 3.2/7/14.2; SQL | `RRV-STORE-001` route/succession/hash | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F3 cancellation consistency | ADR-015 3.4; Store Schema 14.4; SQL | `RRV-LS-001`, `RRV-STORE-001` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F4 operation closure | ADR-015/016; Store Schema 11/14.3 | `RRV-LS-*`, `RRV-FH-*`, `RRV-STORE-001` mutation coverage | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F5 terminal incident/outcome | ADR-015 3.9; Store Schema 14.4; SQL | `RRV-LS-002`, `RRV-STORE-001` terminal cases | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F6 subscription/termination | ADR-016 3.3/3.9; Store Schema 14.5; SQL | `RRV-FH-001/002`, `RRV-STORE-001` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F7 recovery evidence profile | Store Schema 14.6; ADR-016; Startup | `RRV-STORE-001`, `RRV-FH-003` canonical/atomic/bounds | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F8 candidate/replacement state | Store Schema 14.7; Entry Session 3.2; Startup | `RRV-STORE-001`, `RRV-SR-*`, `RRV-ST-001` | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| Semantic clause traceability | Future Phase 3C2 registry against independently accepted Phase 3C1-R1 hashes | Not built in this task | `DEFERRED TO PHASE 3C2 — NOT APPROVAL READY` |
