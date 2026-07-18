# Randle AI Architecture

This README is the master entry point for the Randle AI Architecture library. It is a navigation and governance document only: it does not define trading rules, define lifecycle behavior, or authorize implementation.

## 1. Purpose

This directory contains the governing architecture for Randle AI. It keeps four concerns distinct:

- **Architecture** defines authoritative system meaning, terminology, ownership, and structural boundaries.
- **Implementation** is the code that realizes approved architecture and remains subordinate to it.
- **Production behavior** is the behavior observed in the running system and documented through evidence; it is not automatically architectural authority.
- **Migration strategy** defines how implementation may be moved toward the governing architecture through controlled, separately authorized work.

## 2. Current Architecture Library

- [`00_Randle_AI_Constitution.md`](00_Randle_AI_Constitution.md) — Establishes the foundational architecture authority, governing principles, sources of truth, and system-wide boundaries for Randle AI.
- [`01_Randle_AI_Lifecycle_Vocabulary.md`](01_Randle_AI_Lifecycle_Vocabulary.md) — Provides the binding domain terminology used across lifecycle architecture, implementation, tests, projections, and documentation.
- [`02_Randle_AI_Lifecycle_Engine_Specification.md`](02_Randle_AI_Lifecycle_Engine_Specification.md) — Defines canonical universal lifecycle-engine mechanics inherited by canonical specialized lifecycle specifications. It is subordinate to the Constitution and Lifecycle Vocabulary and does not specify downstream continuation behavior.
- [`03_Randle_AI_Rejection_Step2_Lifecycle_Specification.md`](03_Randle_AI_Rejection_Step2_Lifecycle_Specification.md) — Provides the canonical specialized contract for Candidate-owned Rejection Boundary formation, progression, and Rejection Step 2 Confirmation, which atomically creates one Rejection Lifecycle.
- [`04_Randle_AI_Rejection_Step4_Lifecycle_Specification_DRAFT.md`](04_Randle_AI_Rejection_Step4_Lifecycle_Specification_DRAFT.md) — Describes the proposed Rejection Step 4 phase within that same Rejection Lifecycle through continuation eligibility creation. It remains a draft, is not canonical, and does not authorize implementation.
- [`05_Randle_AI_Rejection_Lifecycle_Architecture_Gap_Analysis.md`](05_Randle_AI_Rejection_Lifecycle_Architecture_Gap_Analysis.md) — Compares current production architecture, proposed lifecycle architecture, and behavior that must be preserved. It is an Architecture Decision Document that records modernization gaps and strategy but authorizes no implementation changes.
- [`06_Randle_AI_Modernization_Charter.md`](06_Randle_AI_Modernization_Charter.md) — An Architecture Decision Document governing how future modernization work is planned, authorized, validated, controlled, and rolled back while preserving established behavior.
- [`07_Randle_AI_Modernization_Roadmap.md`](07_Randle_AI_Modernization_Roadmap.md) — An Architecture Decision Document sequencing future modernization phases and validation gates. It coordinates implementation planning but does not authorize implementation by itself.
- [`Decisions/`](Decisions/) — Contains both approved ADRs and explicitly status-marked proposed ADR drafts. Directory placement does not grant approval or canonical authority; each file's status and governance record control. Each approved ADR governs only its declared scope and does not itself authorize implementation.
  - [`ADR-006_Rejection_Step4_Count_Window.md`](Decisions/ADR-006_Rejection_Step4_Count_Window.md) — The approved authority for the Rejection Step 4 Count Window.
  - [`ADR-007_Rejection_Step4_Participation_Rule.md`](Decisions/ADR-007_Rejection_Step4_Participation_Rule.md) — The approved authority for the Rejection Step 4 Participation Rule.
  - [`ADR-008_Rejection_Step4_Continuation_Eligibility_Handoff.md`](Decisions/ADR-008_Rejection_Step4_Continuation_Eligibility_Handoff.md) — The approved contract for the handoff from accepted Rejection Step 4 Confirmation to Continuation Eligibility, subject only to ADR-009's narrow supersession of the copied-and-immediately-frozen Continuation Boundary model.
  - [`ADR-009_Boundary_Architecture.md`](Decisions/ADR-009_Boundary_Architecture.md) — The approved authority for Liquidity Level, Rejection Boundary, and Continuation Boundary semantics. Effective 2026-07-11, it is a narrow constitutional and architectural amendment limited to the Rejection Step 2 pattern and boundary statements identified in its supersession ledger.
  - [`ADR-014_Authoritative_Entry_Session_Rollover_Transaction.md`](Decisions/ADR-014_Authoritative_Entry_Session_Rollover_Transaction.md) — The approved authoritative Entry session rollover transaction. Governance records approved-content SHA-256 `BD76D1B398515EA00E230B9C8A00A540344E061A36B228BF112F784F6AC34F25`; the metadata-applied committed file is `528B3C7099D63DB41C6B85E381EAD37AD1E479867C07934FD077EBBD8B5EC321`, and the corresponding pre-metadata blob is not independently reconstructable from current history. Approval grants no implementation, runtime verification, deployment, `READY_LOCKED`, or trading authorization.
- [`Audits/`](Audits/) — Contains evidence-based assessments of current production behavior, architecture, and compliance. Audit findings inform decisions but do not redefine governing architecture.
  - [`00_Randle_AI_Rejection_Lifecycle_Compliance_Audit.md`](Audits/00_Randle_AI_Rejection_Lifecycle_Compliance_Audit.md) — Records the completed rejection-lifecycle compliance findings.
  - [`01_Randle_AI_Current_Production_Ground_Truth_Audit.md`](Audits/01_Randle_AI_Current_Production_Ground_Truth_Audit.md) — Preserves the completed production ground-truth findings used by the Gap Analysis.
  - [`02_Randle_AI_Rejection_Lifecycle_Migration_Review.md`](Audits/02_Randle_AI_Rejection_Lifecycle_Migration_Review.md) — Preserves the completed migration classification and sequencing review.

### ADR-010

- [`ADR-010_Continuation_Lifecycle_Creation_and_Initial_Boundary_Activation.md`](Decisions/ADR-010_Continuation_Lifecycle_Creation_and_Initial_Boundary_Activation.md) — The approved narrow cross-lifecycle amendment for authoritative one-minute candle sourcing, governing-Liquidity-Level consumption authority, pre-Creation Eligibility invalidation, Continuation Creation, initial Continuation Boundary formation, and Continuation Evaluation Start.

### ADR-011

- [`ADR-011_Continuation_Step4_Count_Window_and_Participation_Rule.md`](Decisions/ADR-011_Continuation_Step4_Count_Window_and_Participation_Rule.md) — The approved Continuation Step 2-to-Step 4 rule: Continuation Count 0, the fixed Count 1 through Count 4 Participation Window, current-candle opposing-wick and previous-Count directional-close Participation, and Step 4 outcomes.

## 3. Authority Order

Authority descends in the following order:

1. Constitution
2. Lifecycle Vocabulary
3. Lifecycle Engine Specification
4. Canonical Lifecycle Specifications
5. Architecture Decision Documents
6. Implementation
7. Tests
8. Operator projections

Lower authorities shall not redefine higher authorities.

Only explicitly canonical lifecycle specifications occupy authority level 4. The Gap Analysis, Modernization Charter, and Modernization Roadmap are Architecture Decision Documents at authority level 5. Draft documents are noncanonical, and audit documents provide evidence rather than architectural authority.

ADR-010 is an explicitly owner-approved, narrow cross-lifecycle amendment. It narrows the candle source for the Rejection-to-Continuation chain to the canonical authoritative completed one-minute series; governs next-Liquidity-Level consumption authority and its stated temporal consequences; defines the specific AVAILABLE-to-INVALIDATED Eligibility trigger before Creation; and supplies Continuation Creation, initial Boundary formation, and Evaluation Start. All unaffected ADR-006 through ADR-009 decisions remain governing.

ADR-011 is an explicitly owner-approved, separate Continuation lifecycle decision. It governs Continuation Count 0, the fixed Count 1 through Count 4 Participation Window, the adopted 34% opposing-wick formula, directional completed-close Participation, and Continuation Step 4 outcomes. ADR-006 and ADR-007 remain the Rejection Count Window and Rejection Participation authorities; ADR-011 independently adopts the stated structure and formula for Continuation.

ADR-009 is an explicitly owner-approved, narrow amendment limited to the Rejection Step 2 pattern and boundary statements in its supersession ledger. Those statements ceased to govern on 2026-07-11. ADR-009 does not generally override the Constitution, and every unaffected constitutional and universal invariant remains higher authority. Stale terminology or specialized-specification language cannot silently nullify that approved amendment and must be aligned through separately authorized documentation work.

## 4. Current Project Status

| Area | Status |
| --- | --- |
| Architecture Discovery | **COMPLETE** |
| Rejection Architecture | **COMPLETE THROUGH STEP 4** |
| Step 4 Specification | **DRAFT; ADR-006 AND ADR-007 GOVERN** |
| Boundary Architecture | **APPROVED — ADR-009** |
| Continuation Eligibility Handoff | **APPROVED — ADR-008** |
| Continuation Creation Architecture | **APPROVED — ADR-010** |
| Continuation Step 4 Architecture | **APPROVED — ADR-011** |
| Entry Session Rollover Transaction | **APPROVED — ADR-014; DOCUMENTATION AUTHORITY ONLY** |
| Implementation Modernization | **NOT STARTED** |

`COMPLETE THROUGH STEP 4` records completed architecture discovery and approved Rejection Step 4 decisions. It does not make the Step 4 draft canonical or authorize implementation. ADR-006 alone governs the approved Rejection Step 4 Count Window, and ADR-007 alone governs the approved Rejection Step 4 Participation Rule.

## 5. Current Scope

The current rejection lifecycle specification boundary ends at:

```text
Rejection Step 2
        ↓
Rejection Step 4
        ↓
Continuation Eligibility Creation

STOP
```

The parent Rejection lifecycle stops at Continuation Eligibility. The child Continuation lifecycle then proceeds under ADR-010 for Creation, initial Boundary formation, Evaluation Start, governing-Liquidity-Level lineage and consumption authority, and entry into ADR-009 Step 2 mechanics; ADR-011 governs the child from Continuation Step 2 Confirmation through Continuation Step 4. Later post-Step-4 behavior remains outside these ADRs.

The current boundary architecture governs the session-scoped Liquidity Level and the conceptual ABSENT, PROVISIONAL, and FROZEN derived-boundary value model, together with boundary ownership, formation, progression, confirmation, freeze, session custody, and independence. ADR-010 creates no ownerless Continuation Boundary and authorizes no Continuation Lifecycle with an ABSENT Boundary.

## 6. Current Draft Items

The following items remain unresolved:

- Liquidity Level formation-window start and end
- Liquidity Level price calculation and upper/lower output set
- Exact market-interval membership at 06:15 America/Los_Angeles time
- Versioned Liquidity Level Calculation Contract
- Corrected-candle policy
- Out-of-order policy
- Exact Rejection Candidate establishment sequencing before or with initial boundary formation
- Behavior after confirmed Continuation Step 4
- Multi-owner candle routing
- Precise Candidate or Lifecycle terminal-session deadlines
- Session rollover implementation and subordinate specification incorporation (ADR-014 approved; subordinate contract remains draft and noncanonical)
- Contract rollover policy

### Production recovery decision and Phase 3C1 drafts

ADR-014 is the approved governing Entry session decision. All other files listed below remain review drafts only. Their existence and repository provenance authorize no implementation, runtime verification, deployment, production `READY_LOCKED`, Bucket 0 completion, Bucket 1 work, entry-lock release, or trading:

- [`ADR-014_Authoritative_Entry_Session_Rollover_Transaction.md`](Decisions/ADR-014_Authoritative_Entry_Session_Rollover_Transaction.md) - approved indivisible per-symbol session transaction. The metadata-applied committed file is SHA-256 `528B3C7099D63DB41C6B85E381EAD37AD1E479867C07934FD077EBBD8B5EC321`; governance records the earlier approved-content SHA-256 `BD76D1B398515EA00E230B9C8A00A540344E061A36B228BF112F784F6AC34F25`, whose corresponding pre-metadata Git blob is not independently reconstructable from current repository history.
- [`ADR-015_Listener_Lifecycle_Supervision_Epoch_Fencing_and_Restart_Cancellation.md`](Decisions/ADR-015_Listener_Lifecycle_Supervision_Epoch_Fencing_and_Restart_Cancellation.md) - proposed listener-lifecycle authority; unapproved and noncanonical.
- [`ADR-016_Feed_Health_Authority_Durable_Publication_and_Bridge_Recycle_Control.md`](Decisions/ADR-016_Feed_Health_Authority_Durable_Publication_and_Bridge_Recycle_Control.md) - proposed health/bridge authority; unapproved and noncanonical.
- [`14_Randle_AI_Runtime_Recovery_Verification_Specification_DRAFT.md`](14_Randle_AI_Runtime_Recovery_Verification_Specification_DRAFT.md) - proposed recovery verification contract; draft and noncanonical.
- [`entry_session_rollover_contract_DRAFT.md`](../docs/lifecycle/entry_session_rollover_contract_DRAFT.md) - proposed executable support contract for approved ADR-014; draft and noncanonical.
- [`listener_supervision_and_health_authority_DRAFT.md`](../docs/architecture/listener_supervision_and_health_authority_DRAFT.md) - **WITHDRAWN — SUPERSEDED DRAFT**; noncanonical historical evidence only, not an authority source or implementation input.
- [`runtime_authority_store_schema_DRAFT.md`](../docs/architecture/runtime_authority_store_schema_DRAFT.md) - explanatory proposed Runtime Authority Store and typed-transaction contract; draft and noncanonical, pending independent Phase 3C1 review.
- [`runtime_authority_store_schema_v2_DRAFT.sql`](../docs/architecture/runtime_authority_store_schema_v2_DRAFT.sql) - executable proposed v2 SQLite `STRICT` schema; draft architecture implementation reference only, not production code and not authorized for runtime installation.
- [`production_startup_and_recovery_DRAFT.md`](../docs/architecture/production_startup_and_recovery_DRAFT.md) - proposed startup/recovery contract; draft and noncanonical.
- [`diagnostic_endpoint_purity_contract_DRAFT.md`](../docs/architecture/diagnostic_endpoint_purity_contract_DRAFT.md) - proposed diagnostic-purity contract; draft and noncanonical.
- [`2026-07-17_ADR014_016_Canonical_Amendments_Draft.md`](Audits/2026-07-17_ADR014_016_Canonical_Amendments_Draft.md) - proposed canonical amendments; not applied.
- [`2026-07-17_ADR014_016_Cross_Document_Conflict_Matrix.md`](Audits/2026-07-17_ADR014_016_Cross_Document_Conflict_Matrix.md) - Phase 3C1 active normative conflict disposition with retained historical rows; draft evidence.
- [`2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md`](Audits/2026-07-17_ADR015_016_Clause_Traceability_Registry_DRAFT.md) - historical rejected Phase 3B registry; preserved evidence only, not approval-ready or a substantive traceability source.
- [`2026-07-17_Approval_Remediation_Phase_3A_Redlines.md`](Audits/2026-07-17_Approval_Remediation_Phase_3A_Redlines.md) - preserved Phase 3A remediation evidence, superseded for approval readiness.
- [`2026-07-17_Approval_Remediation_Phase_3B_Redlines.md`](Audits/2026-07-17_Approval_Remediation_Phase_3B_Redlines.md) - Phase 3B remediation evidence; not approval evidence.
- [`2026-07-17_Approval_Remediation_Phase_3C1_Redlines.md`](Audits/2026-07-17_Approval_Remediation_Phase_3C1_Redlines.md) - Phase 3C1 normative architecture/schema remediation record; draft evidence, not approval.
- [`2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md`](Traceability/2026-07-17_Production_Recovery_Documentation_Traceability_Matrix.md) - package-level evidence index only; semantic forward/reverse mapping is deferred to Phase 3C2.
- [`2026-07-17_Production_Recovery_Documentation_Draft_Manifest.md`](Audits/2026-07-17_Production_Recovery_Documentation_Draft_Manifest.md) - Phase 3C1 draft package index with historical pre-remediation identities retained separately.

Phase 3C1 completes normative schema and architecture remediation only in draft. A coordinated approval review is not yet possible. Phase 3C2 will rebuild semantic clause/scenario/assertion traceability only against independently accepted Phase 3C1 hashes. ADR-015 and ADR-016 remain unapproved; the Store Schema, executable SQL, and all supporting documents remain draft/noncanonical. Canonical incorporation, implementation, runtime verification, deployment, production `READY_LOCKED`, Bucket 0 completion, Bucket 1 work, and trading remain unauthorized.

`DEBT-2026-07-17-012`, `DEBT-2026-07-17-013`, `DEBT-2026-07-17-014`, and `DEBT-2026-07-17-016` remain `BLOCKING`. `DEBT-2026-07-17-015` remains separately governed and outside this package absent an approved direct-dependency assessment.

## 7. Codex Usage

Future implementation work shall:

- begin with this README;
- follow the [`Randle AI Modernization Charter`](06_Randle_AI_Modernization_Charter.md);
- follow the [`Randle AI Modernization Roadmap`](07_Randle_AI_Modernization_Roadmap.md);
- preserve established trading behavior unless explicitly authorized otherwise.

Reading this library is a prerequisite for future implementation work. Neither this README nor the library's modernization documents authorize implementation without an explicitly approved task.

## 8. Documentation Rules

- Approved canonical architecture documents are authoritative within their declared scope.
- Implementation shall not silently redefine architecture.
- Draft documents shall not become canonical until explicitly approved.
- Audit documents describe evidence.
- Gap Analysis documents describe modernization strategy.
