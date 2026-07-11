# Randle AI Modernization Charter

**Document Type:** Architecture Governance Charter
**Status:** Architecture Decision Document
**Authority:** Subordinate to the Constitution, Lifecycle Vocabulary, Lifecycle Engine Specification, and canonical lifecycle specifications
**Scope:** Future Randle AI modernization planning and implementation work
**Trading-Rule Authority:** None
**Lifecycle-Rule Authority:** None
**Implementation Authorization:** None

## 1. Purpose

This charter defines how Randle AI modernization work shall be planned, authorized, implemented, validated, and rolled back.

The modernization effort exists to strengthen identity, ownership, persistence, restoration, replay, isolation, projection safety, and auditability while preserving established system behavior. This charter governs engineering process. It does not define trading rules, lifecycle transitions, confirmation conditions, candle windows, market-pattern logic, risk rules, or execution rules.

## 2. Authority and Boundaries

Canonical architecture and trading-rule documents govern system meaning. This charter governs the method used to move the implementation toward that architecture.

Modernization work SHALL NOT:

- silently change established trading behavior;
- use an architecture migration to decide an unresolved trading rule;
- treat current implementation behavior as automatically canonical;
- treat a proposed architecture as authorization to alter production behavior;
- combine unrelated lifecycle, execution, risk, or operator-interface changes;
- remove legacy state before an equivalent replacement has been proven;
- extend continuation lifecycle implementation beyond its explicitly authorized scope.

When a task encounters an unresolved trading-rule question, implementation SHALL stop at the decision boundary. The question SHALL be documented and routed for explicit authorization.

## 3. Governing Principles

### 3.1 Preserve Established Trading Behavior

Established trading behavior SHALL remain unchanged unless an explicit trading-rule change is authorized through the governing change-control process. Architecture work SHALL preserve the accepted market-pattern rules, evaluation timing, confirmation behavior, retry behavior, and terminal behavior applicable to its authorized scope.

### 3.2 Separate Architecture From Trading Rules

Architecture hardening SHALL be planned, implemented, reviewed, and validated separately from trading-rule modification. A task SHALL state whether it changes architecture, trading rules, both, or neither. A task that changes both SHALL require separate authorization and separate evidence for each category.

### 3.3 Introduce Identity Before Enforcement

Lifecycle identity, parent identity, session identity, contract identity, candle identity, event identity, version metadata, and other ownership metadata SHALL be introduced additively before new enforcement depends on them.

Initial metadata introduction SHALL observe and record existing behavior. It SHALL NOT reject, reroute, terminate, reseed, or otherwise change production behavior merely because new metadata is incomplete or inconsistent.

### 3.4 Prefer Additive Dual-Write Migration

New authoritative structures SHALL first be written alongside legacy structures. The legacy representation SHALL remain available during the migration period.

Dual-write output SHALL be compared for:

- identity;
- ownership;
- timestamps;
- counts;
- frozen values;
- terminal results;
- persistence;
- restoration;
- projections.

Legacy structures SHALL NOT be removed until the replacement has passed the required equivalence gates.

### 3.5 Require Shadow Comparison Before Cutover

New processors, repositories, state models, projections, and replay paths SHALL operate in shadow mode before becoming authoritative whenever production-equivalent comparison is feasible.

Shadow processing SHALL:

- consume the same authorized inputs;
- produce independently inspectable output;
- avoid authoritative writes unless dual-write is explicitly authorized;
- record divergences with enough evidence for diagnosis;
- remain isolated from execution side effects.

Cutover SHALL require reviewed evidence that observed differences are either eliminated or explicitly authorized.

### 3.6 Preserve Legacy Behavior Until Equivalence

Legacy behavior SHALL remain controlling until the new architecture demonstrates equivalence for the authorized behavior set. Passing a narrow unit test is not sufficient by itself.

Equivalence evidence SHALL cover the applicable live path, persistence path, restart path, replay path, session boundary, duplicate handling, stale handling, out-of-order handling, status projection, and failure behavior.

### 3.7 Make Persistence Changes Additive Before Behavioral

Persistence modernization SHALL preserve existing payload behavior before changing lifecycle decisions.

Atomic writes, validation, schema metadata, revision control, backups, recovery records, writer identity, and migration support SHALL be introduced without simultaneously changing market evaluation or transition rules.

Any enforcement based on new revisions, event identities, session identities, or contract identities SHALL occur only after those values have been captured and validated across representative operation.

### 3.8 Separate Rejection and Continuation Safely

Rejection and continuation raw state SHALL be separated only after an equivalent replacement exists for every legacy read, write, restoration, projection, and handoff dependency.

Migration SHALL use additive records and compatibility paths until equivalence is proven. Rejection history SHALL not be deleted, renamed, or made unreachable merely because continuation begins using a new structure.

### 3.9 Decouple Read-Only Endpoints Only After Processor Equivalence

Read-only endpoints SHALL become projection-only only after an independent lifecycle processor reproduces the existing completed-bar cadence, ordering, persistence timing, restart behavior, and observable lifecycle output.

The independent processor SHALL run in shadow mode before cutover. Scheduler ownership, startup recovery, missed-event handling, retry behavior, and log creation SHALL be explicit before GET or status routes stop performing their current processing role.

### 3.10 Validate Every Migration Phase

Every migration phase SHALL validate, as applicable:

- deterministic replay;
- exact restart restoration;
- session rollover;
- duplicate-event handling;
- stale-event handling;
- out-of-order-event handling;
- endpoint nonmutation;
- persistence and recovery;
- projection equivalence;
- contract and symbol continuity.

Validation SHALL occur during each phase, not only after the final cutover.

### 3.11 Hold the Continuation Boundary

Continuation lifecycle implementation SHALL NOT begin until the rejection lifecycle through Step 4 has been certified for its authorized architecture and trading-rule scope.

Work may define and persist the minimum authorized continuation-eligibility handoff when explicitly in scope. It SHALL stop at that handoff and SHALL NOT infer or implement downstream continuation behavior.

### 3.12 Require a Complete Task Contract

Every implementation task SHALL define the following before work begins:

| Required Element | Required Content |
|---|---|
| Objective | The concrete outcome to be achieved |
| Scope | The components, files, lifecycle stages, and behaviors included |
| Exclusions | The code, rules, stages, and behaviors that must remain untouched |
| Success criteria | The observable conditions proving completion |
| Regression requirements | The tests, replay cases, restart checks, and comparisons required |
| Rollback criteria | The conditions requiring rollback and the safe restoration point |

A task missing any required element SHALL remain a planning task and SHALL NOT authorize implementation.

## 4. Migration Control Gates

Modernization changes SHALL move through the following gates in order:

| Gate | Required Result |
|---|---|
| Discovery | Current owners, writers, readers, persistence paths, and runtime call paths are documented |
| Decision | Trading-rule and architecture questions are classified and unresolved decisions are isolated |
| Additive design | New metadata or records coexist with legacy behavior |
| Dual write | New and legacy representations are produced from the same authorized processing |
| Shadow comparison | Differences are measured without replacing the authoritative path |
| Read cutover | Consumers move only after equivalent authoritative data exists |
| Enforcement | New guards activate only after their governing policies are approved |
| Legacy retirement | Old fields and fallbacks are removed only after rollback-safe equivalence |

No gate may be skipped solely to reduce implementation time.

## 5. Evidence Standard

Modernization evidence SHALL be reproducible and attributable to a specific code, rule, schema, and configuration version.

Required evidence SHALL include the smallest applicable set of:

- state ownership and mutation maps;
- before-and-after persistence records;
- transition comparisons;
- duplicate and ordering cases;
- restart checkpoints;
- archived replay checkpoints;
- session-rollover cases;
- read-only endpoint comparisons;
- shadow-versus-legacy output comparisons;
- exact regression commands and results.

Reasoning logs and operator displays may support investigation. They SHALL NOT replace authoritative market, lifecycle, persistence, or execution evidence.

## 6. Cutover Standard

A new architecture component may become authoritative only when:

- its ownership boundary is explicit;
- its input contract is versioned;
- its output is durably persisted where required;
- restart restores its exact committed result;
- duplicate processing is idempotent;
- stale and out-of-order behavior follows an approved policy;
- shadow comparison demonstrates required equivalence;
- rollback remains available;
- the cutover is explicitly authorized.

Cutover SHALL be narrow, observable, and reversible. Unrelated cleanup SHALL not be bundled into the authority change.

## 7. Rollback Standard

Every implementation phase SHALL identify a last-known-safe state and a documented rollback trigger.

Rollback SHALL occur when any applicable condition is observed:

- an unauthorized trading-rule change;
- lifecycle identity or parent drift;
- changed confirmation timing without authorization;
- loss of frozen or terminal facts;
- replay divergence not explained by authorized input differences;
- restart divergence;
- duplicate advancement;
- stale or prior-session overwrite;
- read-side lifecycle mutation;
- persistence corruption or unrecoverable migration failure;
- shadow output outside approved equivalence tolerances.

Rollback SHALL restore the prior authoritative path without deleting evidence needed to diagnose the failed migration.

## 8. Change Control

Architecture documents SHALL NOT be silently rewritten during implementation work. Any change to governing architecture, terminology, trading rules, migration policy, or acceptance criteria SHALL be made through an explicit documentation decision before dependent implementation is authorized.

Implementation findings that contradict an assumption SHALL be recorded as evidence. They SHALL NOT be resolved through an undocumented code workaround.

## 9. Charter Compliance

Every modernization plan, Codex instruction, implementation review, and cutover decision SHALL identify how it satisfies this charter.

Work that cannot demonstrate preservation, equivalence, validation, and rollback SHALL not replace the current authoritative implementation.
