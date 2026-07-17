# Randle AI Architecture Debt Registry

Status: Current Architecture Health Index
Governed By: `Architecture/11_Randle_AI_Architecture_Debt_Specification.md`
Last Reconciled: 2026-07-17
Next Blocking-Debt Review: 2026-07-18
Deployment Status: **NOT AUTHORIZED**

## Current health summary

| Measure | Count |
|---|---:|
| Non-retired debt | 15 |
| Blocking debt | 14 |
| Proposed debt | 0 |
| Active nonblocking debt | 1 |
| Accepted debt | 0 |
| Deferred debt | 0 |
| Retired debt | 3 |
| Overdue reviews | 0 |

Governance Verification cannot pass while any applicable record below remains `BLOCKING`.

## Debt registry

| Identifier | Title | Primary category | Risk | Deployment impact | Current owner | Status | Review date | Primary authority |
|---|---|---|---|---|---|---|---|---|
| [DEBT-2026-07-16-001](DEBT-2026-07-16-001_Status_Route_Read_Side_Persistence.md) | Status route performs authoritative persistence | Implementation Debt | HIGH | NONE | Entry Agent Component Owner | RETIRED | — | Constitution §16; ADR-012 §3.6 |
| [DEBT-2026-07-16-002](DEBT-2026-07-16-002_July16_Replay_and_Webhook_Provenance.md) | July 16 replay and original webhook provenance are incomplete | Verification Debt | HIGH | BLOCKS_SCOPE | Verification and Replay Owner | BLOCKING | 2026-07-23 | Constitution §20; Verification Specification §3 |
| [DEBT-2026-07-16-003](DEBT-2026-07-16-003_ADR013_YM_Rollout_and_Test_Alignment.md) | ADR-013 remains NQ-only in implementation and YM tests | Implementation Debt | HIGH | BLOCKS_SCOPE | Entry Agent Lifecycle Owner | BLOCKING | 2026-07-23 | ADR-013 §§3-7 |
| [DEBT-2026-07-16-004](DEBT-2026-07-16-004_Broad_Regression_Baseline_Unresolved.md) | Broad regression baseline has unresolved failures | Test Debt | HIGH | BLOCKS_ALL | Verification and Test Suite Owner | BLOCKING | 2026-07-23 | Engine §§40, 43.13 |
| [DEBT-2026-07-16-005](DEBT-2026-07-16-005_Dirty_Worktree_Traceability_Coverage.md) | Broader modified production hunks lack attributable traceability | Governance Debt | HIGH | BLOCKS_ALL | Architecture Governance Owner | BLOCKING | 2026-07-23 | Constitution §22B; Traceability Specification §§3-6 |
| [DEBT-2026-07-16-006](DEBT-2026-07-16-006_NQ_Premarket_Wick_Monotonicity.md) | NQ premarket observed wick can retract or change identity | Implementation Debt | HIGH | BLOCKS_SCOPE | Entry Agent Lifecycle Owner | BLOCKING | 2026-07-23 | Session Liquidity Lock Contract §4.1; Webhook Contract §8 |
| [DEBT-2026-07-16-007](DEBT-2026-07-16-007_TradingView_Level_Map_Source_and_Evidence_Provenance.md) | TradingView source and screenshot provenance reconciled | Verification Debt | HISTORICAL | NONE | TradingView Indicator and Verification Owner | RETIRED | — | Liquidity Ladder Calculation Contract; Verification Specification |
| [DEBT-2026-07-16-008](DEBT-2026-07-16-008_Automated_Pine_Compilation_Gap.md) | Repository has no automated Pine compilation path | Test Debt | MEDIUM | MANUAL_GATE | Verification Tooling Owner | ACTIVE | 2026-07-23 | Liquidity Ladder Verification Specification |
| [DEBT-2026-07-16-009](DEBT-2026-07-16-009_Prior_RTH_Stack_Ingress_Validation.md) | Liquidity stack structural ingress and restoration validation | Implementation Debt | HISTORICAL | NONE | Entry Agent Input Contract Owner | RETIRED | — | Liquidity Ladder Calculation Contract; Runtime Authority §4 |
| [DEBT-2026-07-16-010](DEBT-2026-07-16-010_Legacy_Prior_RTH_Stack_Fixture_Alignment.md) | Historical stack fixtures lack reconciled complete-span authority | Test Debt | HIGH | BLOCKS_SCOPE | Entry Agent Replay and Test Owner | BLOCKING | 2026-07-23 | Liquidity Ladder Calculation Contract; Verification Specification |
| [DEBT-2026-07-16-011](DEBT-2026-07-16-011_Erroneous_Prior_RTH_Categorical_Stack_Exclusion.md) | Erroneous categorical YH/YL exclusion and missing full-span invariant | Architectural Debt | CRITICAL | BLOCKS_SCOPE | Liquidity Ladder Architecture Owner | BLOCKING | 2026-07-17 | Liquidity Ladder Calculation Contract v1.1 |
| [DEBT-2026-07-17-012](DEBT-2026-07-17-012_Entry_Session_Rollover_Atomicity.md) | Entry session rollover is not one atomic validate-commit-expose transition | Architectural Debt | CRITICAL | BLOCKS_ALL | Entry Agent Session-Lock Authority Owner | BLOCKING | 2026-07-18 | Constitution section 15; approved ADR-014 |
| [DEBT-2026-07-17-013](DEBT-2026-07-17-013_Listener_Supervision_Recovery_Race.md) | Executor restart authority and accepted-tick ordering create repeated listener epochs | Architectural Debt | CRITICAL | BLOCKS_ALL | Listener Supervision Policy Owner | BLOCKING | 2026-07-18 | Constitution sections 6 and 16; proposed ADR-015 |
| [DEBT-2026-07-17-014](DEBT-2026-07-17-014_Feed_Health_Durability_and_Control_Authority.md) | Failed health persistence loses pending state and stale projection controls bridge lifecycle | Architectural Debt | CRITICAL | BLOCKS_ALL | Rithmic Runtime Health and Bridge Authority Owner | BLOCKING | 2026-07-18 | Runtime Authority section 1; proposed ADR-016 |
| [DEBT-2026-07-17-015](DEBT-2026-07-17-015_Shared_Boundary_Stack_Contract_Conflict.md) | Shared-boundary overlap intent conflicts with blanket overlap rejection text | Specification Debt | HIGH | BLOCKS_SCOPE | Liquidity Ladder Architecture Owner | BLOCKING | 2026-07-18 | Session Liquidity Lock Contract section 10 |
| [DEBT-2026-07-17-016](DEBT-2026-07-17-016_Unauthenticated_TradingView_Webhook_Sender.md) | Public TradingView webhook has no authenticated sender identity or sender-bound replay proof | Architectural Debt | CRITICAL | BLOCKS_ALL | TradingView Ingress Security Owner | BLOCKING | 2026-07-18 | Approved ADR-014 section 3.4.1; TradingView Webhook Contract |
| [DEBT-2026-07-17-017](DEBT-2026-07-17-017_Diagnostic_GET_Audit_Omits_Cache_Mutation.md) | Diagnostic GET audit omits Trade Manager ATR cache mutation | Specification Debt | HIGH | BLOCKS_ALL | Diagnostic Purity Specification Owner | BLOCKING | 2026-07-18 | Constitution section 16; proposed Diagnostic Purity Contract |
| [DEBT-2026-07-17-018](DEBT-2026-07-17-018_Startup_Readiness_Normative_Reconciliation_Gaps.md) | Startup readiness uses obsolete health facts and lacks debt/Executor authority gates | Specification Debt | CRITICAL | BLOCKS_ALL | Production Startup and Readiness Architecture Owner | BLOCKING | 2026-07-18 | Proposed Startup/Readiness Contract; approved ADR-014; proposed ADR-015 and ADR-016 |

## Category health

| Category | Open records | Blocking | Accountable owner role |
|---|---:|---:|---|
| Architectural Debt | 5 primary; 2 secondary | 7 | Architecture Owner |
| Specification Debt | 3 primary; 7 secondary | 10 | Owning Specification Maintainer |
| Verification Debt | 1 primary; 6 secondary | 6 | Verification Owner |
| Implementation Debt | 2 primary; 7 secondary | 9 | Owning Production Component |
| Test Debt | 3 primary; 8 secondary | 10 | Verification/Test Suite Owner |
| Operational Debt | 0 primary; 6 secondary | 5 | Runtime Operations Owner |
| Documentation Debt | 0 primary; 12 secondary | 12 | Documentation Owner with Architecture review |
| Governance Debt | 1 primary; 9 secondary | 10 | Architecture Governance Owner |

## Gate impact

| Completion gate | Blocking debt |
|---|---|
| Architecture | DEBT-2026-07-16-011; DEBT-2026-07-17-012 through 018 |
| Specification | DEBT-2026-07-16-011; DEBT-2026-07-17-012 through 018 |
| Implementation | DEBT-2026-07-16-003, DEBT-2026-07-16-006; DEBT-2026-07-17-012 through 018 |
| Verification | DEBT-2026-07-16-002 through 006, DEBT-2026-07-16-010 and 011; DEBT-2026-07-17-012 through 018 |
| Traceability | DEBT-2026-07-16-005, DEBT-2026-07-16-006, DEBT-2026-07-16-010; DEBT-2026-07-17-012 through 018 |

## Review history

- [2026-07-16 Initial Architecture Debt Review](Reviews/2026-07-16_Initial_Architecture_Debt_Review.md)
- [2026-07-16 Status Route Read-Side Purity Debt Review](Reviews/2026-07-16_Status_Route_Read_Side_Purity_Debt_Review.md)
- [2026-07-16 NQ Premarket Wick Debt Review](Reviews/2026-07-16_NQ_Premarket_Wick_Debt_Review.md)
- [2026-07-16 TradingView Liquidity Ladder Evidence Reconciliation](Reviews/2026-07-16_TradingView_Liquidity_Ladder_Evidence_Reconciliation.md)
- [2026-07-16 TradingView Liquidity Ladder Full-Span Correction](Reviews/2026-07-16_TradingView_Liquidity_Ladder_Full_Span_Correction.md)
- [2026-07-17 Production Recovery Pre-implementation Debt Reconciliation](Reviews/2026-07-17_Production_Recovery_Preimplementation_Debt_Reconciliation.md)
- [2026-07-17 Production Recovery Documentation-Phase Debt Reconciliation](Reviews/2026-07-17_Production_Recovery_Documentation_Phase_Debt_Reconciliation.md)
- [2026-07-17 Coordinated Authority Package Approval Review](../Audits/2026-07-17_Coordinated_Authority_Package_Approval_Review.md)

## Registry integrity

This registry is a projection of the individual records. Debt records preserve their full histories and control if a temporary index mismatch occurs. Neither this index nor any debt record creates architectural authority.
