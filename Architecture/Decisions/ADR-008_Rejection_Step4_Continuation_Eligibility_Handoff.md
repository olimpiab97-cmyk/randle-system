# ADR-008: Rejection Step 4 Continuation-Eligibility Handoff Contract

## Status

APPROVED

## Date

2026-07-11

## Purpose

ADR-010 Narrow Amendment Record: Effective 2026-07-13, the accepted Rejection Step 4 source candle in this lifecycle chain is an authoritative completed one-minute candle. ADR-010 supplies the specific pre-Creation invalidation rule: consumption of the exact inherited governing Liquidity Level transitions AVAILABLE Eligibility to INVALIDATED. ADR-010 also authorizes same-source Step-4-to-Creation routing only after this ADR has created AVAILABLE Eligibility. All other handoff, identity, uniqueness, cardinality, lineage, session, atomicity, idempotency, CONSUMED, and EXPIRED decisions remain governing.

ADR-011 Relationship Record: ADR-011 governs the child Continuation lifecycle only after its Step 2 Confirmation. It does not alter this ADR's accepted Rejection Step 4-to-Eligibility handoff, Eligibility identity, uniqueness, one-child cardinality, lineage, session isolation, handoff atomicity, or idempotency.

This Architecture Decision Record establishes the authoritative handoff contract from an accepted Rejection Step 4 Confirmation to Continuation Eligibility. It governs only the creation, identity, ownership, cardinality, frozen parent references, and terminal outcomes of the eligibility record. It does not create a continuation lifecycle; form, own, progress, or freeze a Continuation Boundary; define continuation evaluation behavior; or authorize implementation.

## Governing Decisions

### 1. Eligibility-Producing Event

Accepted Rejection Step 4 Confirmation is both necessary and sufficient to produce Continuation Eligibility.

There are no unspecified additional eligibility prerequisites.

Continuation Eligibility SHALL be created atomically with the accepted Rejection Step 4 Confirmation transition.

A Rejection Lifecycle whose Step 4 phase failed, expired, was invalidated, was cancelled, or otherwise did not confirm cannot produce Continuation Eligibility.

### 2. Eligibility Is Not Continuation Creation

Continuation Eligibility records that a completed rejection is authorized to seed a future continuation lifecycle.

It does not:

- create a continuation lifecycle;
- create continuation Step 2;
- begin continuation evaluation;
- confirm continuation;
- reopen or extend the completed Rejection Lifecycle.

Continuation Creation and Continuation Evaluation Start remain outside the scope of ADR-008.

### 3. Parent Lifecycle Immutability

The completed Rejection Lifecycle remains terminal, immutable, independently identifiable, and independently auditable.

Continuation processing SHALL NOT:

- reopen the Rejection Lifecycle;
- modify its Step 2 or Step 4 facts;
- reuse its lifecycle identity;
- rename it as a continuation;
- clear or repurpose its state.

Any future continuation lifecycle SHALL receive a separate lifecycle identity and retain an immutable reference to exactly one rejection parent.

### 4. Eligibility Identity and Cardinality

Each accepted Rejection Step 4 Confirmation SHALL produce exactly one Continuation Eligibility record with one stable eligibility identity.

Each eligibility record:

- belongs to exactly one Rejection Lifecycle;
- references exactly one accepted Rejection Step 4 Confirmation;
- may produce at most one continuation lifecycle;
- cannot be duplicated by replay, polling, restart, or repeated processing.

One Rejection Lifecycle SHALL NOT seed multiple continuation lifecycles.

Continuation Creation consumes the eligibility record. A consumed eligibility record cannot create another continuation lifecycle.

### 5. Frozen Parent References

The eligibility record SHALL preserve immutable references to the accepted parent facts required to identify and audit the handoff, including:

- Rejection Lifecycle identity;
- symbol;
- session identity;
- direction;
- liquidity identity;
- Step 2 Confirmation identity;
- Count 0 identity;
- Rejection Boundary;
- accepted Rejection Step 4 Confirmation identity;
- Step 4 confirmation timestamp;
- confirming Count identity;
- governing rule version.

These remain parent-owned facts. Recording their identities or values in the eligibility record does not transfer ownership or permit mutation.

### 6. Continuation Boundary

Continuation Eligibility does not form, own, progress, or freeze a Continuation Boundary. The continuation handoff is not a Continuation Boundary owner.

The Rejection Boundary SHALL NOT be copied as, transferred to, promoted to, or automatically transformed into a Continuation Boundary.

A Continuation Boundary is owned exclusively by its Continuation Lifecycle from first formation onward. It cannot exist before that Continuation Lifecycle identity exists.

Before Continuation Creation, the confirmed Rejection Lifecycle coexists with no Continuation Boundary object.

ADR-008 does not itself select Continuation Creation sequencing. ADR-010 selects the atomic Creation-and-initial-Boundary sequence. ADR-008 does not authorize a Continuation Lifecycle with an ABSENT boundary and introduces no Continuation Candidate or other pre-lifecycle provisional owner.

The source Rejection Lifecycle and source Rejection Boundary remain traceable as parent lineage. Lineage does not transfer boundary ownership or create numerical coupling.

The Continuation Boundary and Rejection Boundary remain distinct architectural facts even when their numeric values are identical.

ADR-008 does not introduce multiple continuation reference boundaries. Any such boundary requires separate approval through later architecture.

### 7. Eligibility Record Outcomes

Continuation Eligibility has the following permitted outcomes:

- **AVAILABLE:** Created atomically with accepted Rejection Step 4 Confirmation and available for one future Continuation Creation.
- **CONSUMED:** A continuation lifecycle has been created from it.
- **EXPIRED:** It reached the terminal session boundary without being consumed.
- **INVALIDATED:** ADR-010 authorizes the specific pre-Creation event in which the exact inherited governing Liquidity Level is consumed.

ADR-008 does not independently define a market condition for invalidation. The ADR-010 consumption trigger is the approved exception; no other intrawindow movement independently invalidates Eligibility.

Eligibility from a previous session SHALL NOT silently become current-session eligibility.

Terminal eligibility records remain preserved for audit and SHALL NOT return to AVAILABLE.

### 8. Idempotency and Atomicity

The following SHALL form one atomic handoff:

- accepted Rejection Step 4 Confirmation;
- Continuation Eligibility creation;
- frozen parent references.

Duplicate delivery or repeated evaluation of the same accepted Rejection Step 4 Confirmation SHALL return the existing eligibility identity rather than create a second record.

Partial handoff states are prohibited.

### 9. Permitted Transitions

The architecture permits:

- `Rejection Step 4 Confirmation → Continuation Eligibility AVAILABLE`;
- `Continuation Eligibility AVAILABLE → Continuation Eligibility CONSUMED` only through future-defined Continuation Creation;
- `Continuation Eligibility AVAILABLE → Continuation Eligibility EXPIRED` at the governing session boundary if unused;
- `Continuation Eligibility AVAILABLE → Continuation Eligibility INVALIDATED` when ADR-010's governing-Liquidity-Level-consumption rule applies before Creation.

### 10. Prohibited Transitions

The architecture explicitly prohibits:

- eligibility before accepted Rejection Step 4 Confirmation;
- eligibility from Step 4 expiration or any other nonconfirmation result;
- duplicate eligibility for one rejection;
- multiple continuation children from one rejection;
- multiple continuation children from one eligibility record;
- treating eligibility as Continuation Creation;
- treating eligibility as Continuation Evaluation Start;
- treating eligibility as continuation Step 2 confirmation;
- reopening or mutating the rejection parent;
- reusing the Rejection Lifecycle identity;
- copying the Rejection Boundary as, transferring it to, promoting it to, or automatically transforming it into a Continuation Boundary at Eligibility creation;
- forming, owning, progressing, or freezing a Continuation Boundary through Continuation Eligibility or its handoff;
- carrying AVAILABLE eligibility into another session;
- returning CONSUMED, EXPIRED, or INVALIDATED eligibility to AVAILABLE;
- introducing continuation counts or activation rules in ADR-008.

## Scope Boundary

ADR-008 stops at Continuation Eligibility.

It does not define:

- the market event that creates the continuation lifecycle;
- Continuation Evaluation Start;
- continuation Step 2;
- continuation Count 0-through-Count 4 behavior;
- continuation participation;
- continuation confirmation;
- continuation trading or entry rules.

Those matters belong to a subsequent Continuation Lifecycle ADR.

## Authority

This ADR is an approved Architecture Decision Document governed by the authority hierarchy established in `Architecture/README.md`. It is subordinate to the Randle AI Constitution, Lifecycle Vocabulary, Lifecycle Engine Specification, and canonical lifecycle specifications.

ADR-009 narrowly supersedes only ADR-008's copied-and-immediately-frozen Continuation Boundary model. Within that expressly limited scope, ADR-009's replacement rules govern; this is not a general reversal of the architecture authority hierarchy.

The following ADR-008 decisions remain governing: accepted Rejection Step 4 Confirmation produces Continuation Eligibility; Eligibility creation is atomic with that accepted confirmation; Eligibility is unique and may produce at most one Continuation Lifecycle; Continuation Creation consumes Eligibility; the Rejection parent remains terminal and immutable; parent and Eligibility lineage, session isolation, idempotency, duplicate protection, and terminal Eligibility behavior remain governing. Continuation Creation and Evaluation Start remain outside ADR-008 itself and are governed by ADR-010.

ADR-008 does not alter the completed Rejection Step 2 or Rejection Step 4 architecture. It authorizes future architecture-document alignment within its approved scope only.

It does not authorize implementation, code changes, test changes, runtime-state changes, or executable behavior.
