# Approval Remediation Phase 3C1-R3 — F6 Evidence Semantics Redline Record

Status: **DRAFT — NONCANONICAL — NOT APPROVED**

Active disposition: **F6-R2-01 THROUGH F6-R2-05 CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R3 REVIEW**

Baseline: commit `94bbb2ff8c8444394e0e608f7f68790b1bd620a2`, parent `67c09049f14b37eb9753f9fd37de0c25115568c7`, tree `a643d25d6d8cd572475e067463a8bb1c758d56a3`, subject `docs(architecture): close phase 3c1-r2 termination evidence`.

ADR-014 remains approved and unchanged at SHA-256 `528B3C7099D63DB41C6B85E381EAD37AD1E479867C07934FD077EBBD8B5EC321`. ADR-015, the Entry Session Contract, and the Diagnostic Endpoint Purity Contract are unchanged. The frozen diagnostic identity remains source tree `704fd715cad3aad281c534f8337840e3aab96234`: 31 registered GET service/path entries, 13 mutating entries, and 13 unique mutating URL patterns.

## 1. Scope and supersession

This record corrects only the five residual F6 enforcement gaps reported by the independent Phase 3C1-R2 review. It does not reopen F1–F5, subscription symbol/session coherence, F7, F8, the 55-operation catalog except for narrowing the existing termination-evidence operation name, or any previously accepted document substance. The Phase 3C1-R2 redline is retained as historical evidence and is superseded only for these five findings.

Semantic clause traceability was not generated. The historical registry remains `NOT APPROVAL READY — SEMANTIC TRACEABILITY REBUILD DEFERRED TO PHASE 3C2`. Phase 3C2 may operate only after an independent review accepts the exact Phase 3C1-R3 hashes.

## 2. Finding-to-correction record

| Review finding | Exact draft correction | Executable enforcement | Isolated validation family | Status |
|---|---|---|---|---|
| F6-R2-01 supporting `UNKNOWN` omitted | all authenticated, current, in-window assertions are evaluated for their exact classified role; unresolved `UNKNOWN`, `INDETERMINATE`, unavailable, or uncertainty-positive support rejects `NONE` and concrete values for that role; independently proven roles do not inherit unrelated uncertainty | `trg_termination_results_supporting_uncertainty`, complete producer-window structure, fail-closed startup query | absence plus `UNKNOWN`; concrete plus `UNKNOWN`; multiple and role-local uncertainty; startup rejection | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R3 REVIEW` |
| F6-R2-02 semantic-role identity membership | every optional result identity is bound to one closed direct contributor role, producer/domain, normalized payload, evidence set, result, generation, epoch, process, and observation; `request_identity` is exactly `REQUESTED_ACTION_EVIDENCE` | composite keys plus `trg_termination_results_semantics` role/domain predicates | correct role; every wrong role; cross-set/result/process/generation/observation | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R3 REVIEW` |
| F6-R2-03 self-declared labels | normalized command, OS/process, provider/RAPI, bridge, listener/supervisor, and derivation payload tables carry authenticated facts; evidence labels are derived claims only; concrete and absence predicates require exact normalized payload content | six `STRICT` payload tables, payload/evidence FKs, `trg_termination_evidence_payload_semantics`, result predicates, payload bytes in evidence/set/result hashes | every concrete payload; label without payload; mismatch; false absence; tampering; cross-domain correlation | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R3 REVIEW` |
| F6-R2-04 arrival order not durable | one `termination_producer_cursors` row per producer instance records accepted producer/ingress sequence, observation, transaction, state version, time, and writer; the first accepted row is sequence 1 and every later ingest is exact +1 under cursor CAS | narrowed `TX-TERMINATION-EVIDENCE-INGEST`; exact transaction/idempotency predicates; init/guard/fence/evidence/advance triggers | 1→2; 2-before-1; duplicate; concurrent stale cursor; exact replay; payload conflict; restart; stale producer; late evidence | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R3 REVIEW` |
| F6-R2-05 deterministic flag not mechanically proved | every schema-owning connection registers `randle_sha256_hex_utf8(TEXT)` before DDL; expression-index creation requires deterministic registration, `trusted_schema=OFF` requires innocuous registration, and direct/view preflights verify exact output | `ix_randle_sha256_deterministic_guard`, `randle_sha256_preflight_v`, direct empty-string digest `CHECK` | missing; wrong output; deterministic/non-innocuous; innocuous/nondeterministic; correct deterministic/innocuous | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R3 REVIEW` |

## 3. Normative result rules

Uncertainty propagation is field-specific. An unresolved assertion for Initiator, Requested Action, Execution Method, Observed Cause, or Result invalidates `NONE` and every concrete token for that same field. There is no implicit cross-field propagation. A dependency becomes cross-field only where a concrete predicate expressly requires another field—for example, planned shutdown requires authenticated intent plus execution/result proof—so a failed dependency rejects that concrete result.

Absence is content-derived. Each field's `NONE` contributor is an evaluator derivation whose canonical payload identifies the exact six producer windows and cutoff and asserts zero qualifying positive facts, zero relevant uncertainty facts, zero conflicts, zero gaps, and zero unavailable producers. SQL independently recomputes those properties from the accepted windows; an absence label cannot prove itself.

Concrete tokens require the closed payload predicates stated by ADR-016 and Store Schema section 14.5.1. A nonzero exit code alone is never `BRIDGE_CRASH`. All normalized payload JSON is canonical and hash-bound; tampering invalidates the evidence hash, then the set hash, then the result hash.

## 4. Executable identity and inventory

| Identity | Phase 3C1-R3 value |
|---|---|
| SQL SHA-256 | `bed772dfcfaffed0a5ad19176e560cebd139f19fce555482cbce6f7320e43636` |
| Canonical schema SHA-256 | `304dce825d2542b8c7a69f56b0322376daa8fe2670848e0bbfbef528b12a4180` |
| Canonical writer-registry SHA-256 | `7ab99f5802bb6d9e20f73b2ecbf9372ce5cf8fbd093e0d9cf1bd571bf1c31c28` |
| SQLite | 3.43.1 |
| Inventory | 47 `STRICT` tables; 670 columns; 152 FK declarations/203 mappings; 14 partial unique indexes; 27 triggers; one SHA-256 preflight view; 70 active routes; 11 writers; 55 governed operation IDs/52 database-commit types |

The writer registry adds the exact Health Durable Writer routes for six payload tables and the cursor insert/update paths. `TX-TERMINATION-EVIDENCE-INGEST` narrows and replaces the prior broad termination-evidence operation ID without increasing the closed catalog count.

## 5. Validation disposition

Isolated SQLite 3.43.1 validation compiled the complete artifact only with correct deterministic and innocuous SHA-256 registration, returned `integrity_check=ok` and zero `foreign_key_check` rows, and reproduced the two canonical hashes by independent serializers. Missing/wrong-output, innocuous+nondeterministic, and deterministic+non-innocuous registrations failed at their distinct governed checks. Executed fixtures proved exact 1→2 cursor admission, immediate 2-before-1/duplicate/stale rejection, retirement-before-replacement, zero-row retirement, successor-at-1, idempotency conflict, complete six-window/five-role `NONE`, supporting-`UNKNOWN` rejection, normalized bridge-crash admission, self-label and payload-tamper rejection, and correct-versus-wrong Requested Action role binding. The startup predicates remain read-only and classify each invalid result as unproven. Representative calendar, writer succession, subscription/listener/incident, recovery/candidate, Entry Session, and accepted-document identity checks remained regression-clean. Exact commands and results are recorded in the Phase 3C1-R3 remediation report; these are document/schema validation only, not implementation or runtime verification.

## 6. Governance status

ADR-014 remains approved and unchanged. ADR-015 and ADR-016 remain unapproved. The Store Schema, SQL, and all amended supporting artifacts remain draft and noncanonical. No approval review, canonical incorporation, implementation, runtime verification, deployment, `READY_LOCKED`, trading, Bucket 0 completion, or Bucket 1 authorization occurs. DEBT-012, DEBT-013, DEBT-014, and DEBT-016 remain `BLOCKING`.
