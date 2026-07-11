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
- [`03_Randle_AI_Rejection_Step2_Lifecycle_Specification.md`](03_Randle_AI_Rejection_Step2_Lifecycle_Specification.md) — Provides the canonical specialized contract for Rejection Step 2, a phase within one Rejection Lifecycle.
- [`04_Randle_AI_Rejection_Step4_Lifecycle_Specification_DRAFT.md`](04_Randle_AI_Rejection_Step4_Lifecycle_Specification_DRAFT.md) — Describes the proposed Rejection Step 4 phase within that same Rejection Lifecycle through continuation eligibility creation. It remains a draft, is not canonical, and does not authorize implementation.
- [`05_Randle_AI_Rejection_Lifecycle_Architecture_Gap_Analysis.md`](05_Randle_AI_Rejection_Lifecycle_Architecture_Gap_Analysis.md) — Compares current production architecture, proposed lifecycle architecture, and behavior that must be preserved. It is an Architecture Decision Document that records modernization gaps and strategy but authorizes no implementation changes.
- [`06_Randle_AI_Modernization_Charter.md`](06_Randle_AI_Modernization_Charter.md) — An Architecture Decision Document governing how future modernization work is planned, authorized, validated, controlled, and rolled back while preserving established behavior.
- [`07_Randle_AI_Modernization_Roadmap.md`](07_Randle_AI_Modernization_Roadmap.md) — An Architecture Decision Document sequencing future modernization phases and validation gates. It coordinates implementation planning but does not authorize implementation by itself.
- [`Audits/`](Audits/) — Contains evidence-based assessments of current production behavior, architecture, and compliance. Audit findings inform decisions but do not redefine governing architecture.
  - [`00_Randle_AI_Rejection_Lifecycle_Compliance_Audit.md`](Audits/00_Randle_AI_Rejection_Lifecycle_Compliance_Audit.md) — Records the completed rejection-lifecycle compliance findings.
  - [`01_Randle_AI_Current_Production_Ground_Truth_Audit.md`](Audits/01_Randle_AI_Current_Production_Ground_Truth_Audit.md) — Preserves the completed production ground-truth findings used by the Gap Analysis.
  - [`02_Randle_AI_Rejection_Lifecycle_Migration_Review.md`](Audits/02_Randle_AI_Rejection_Lifecycle_Migration_Review.md) — Preserves the completed migration classification and sequencing review.

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

## 4. Current Project Status

| Area | Status |
| --- | --- |
| Architecture Discovery | **COMPLETE** |
| Rejection Architecture | **COMPLETE THROUGH STEP 4** |
| Step 4 Specification | **DRAFT** |
| Continuation Architecture | **NOT STARTED** |
| Implementation Modernization | **NOT STARTED** |

`COMPLETE THROUGH STEP 4` records completed architecture discovery and documentation coverage through the Step 4 boundary. It does not make the Step 4 draft canonical, resolve its open trading-rule decisions, or authorize implementation.

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

Continuation concepts may be referenced for vocabulary, ownership, state separation, and handoff context. Canonical continuation lifecycle behavior and continuation lifecycle implementation after eligibility creation remain outside the current specification scope.

## 6. Current Draft Items

The following items remain unresolved:

- Step 4 Count-window
- Candle A replacement
- Retry behavior
- Terminal window
- Corrected-candle policy
- Out-of-order policy
- Session rollover policy
- Contract rollover policy

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
