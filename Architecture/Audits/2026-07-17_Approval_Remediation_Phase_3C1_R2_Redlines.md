# Approval Remediation Phase 3C1-R2 — F6 Termination Evidence Redline Record

Status: **DRAFT — NONCANONICAL — NOT APPROVED**

Historical disposition: **SUPERSEDED FOR F6-R2-01 THROUGH F6-R2-05 NORMATIVE APPROVAL READINESS BY PHASE 3C1-R3 REMEDIATION RECORD**

Baseline: commit `67c09049f14b37eb9753f9fd37de0c25115568c7`, parent `174cb5001da13eff53d42dde40f35154fb7d1c22`, tree `ffeba5739554f3140f5b2dfb2e736bc257634177`, subject `docs(architecture): close phase 3c1-r1 invariant gaps`.

Approved dependency: ADR-014 remains unchanged at SHA-256 `528B3C7099D63DB41C6B85E381EAD37AD1E479867C07934FD077EBBD8B5EC321`. ADR-015, the accepted Entry Session Rollover Contract substance, and the approved Diagnostic Endpoint Purity Contract substance were not amended. The diagnostic inventory remains source-bound to tree `704fd715cad3aad281c534f8337840e3aab96234` at 31 registered GET entries, 13 mutating entries, and 13 unique mutating URL patterns.

## 1. Scope and supersession

This record remediates only the remaining F6 termination-result defect identified by the independent Phase 3C1-R1 review. F1–F5/F7/F8 and the accepted subscription identity/symbol-session constraints are not reopened. The F6 row in the R1 redline is historical and superseded for normative approval readiness by this record.

Semantic clause traceability was not generated. The historical registry remains `NOT APPROVAL READY — SEMANTIC TRACEABILITY REBUILD DEFERRED TO PHASE 3C2`. Phase 3C2 may begin only after independent acceptance of the exact R2 hashes.

## 2. Finding-to-correction record

| F6 rejected surface | Exact draft correction | Executable enforcement | Isolated evidence |
|---|---|---|---|
| result-level identity/time/schema/integrity absent | mandatory `observed_at_utc`, `recorded_at_utc`, `termination_schema_version=2`, `record_integrity_sha256`; cutoff freshness 5 seconds; recording delay 30 seconds | STRICT columns/checks, exact result/set FK, transaction-time equality, hash trigger | missing/ordering/delay/version/tamper negatives and canonical positive |
| evidence set not exact | new immutable `termination_evidence_sets` and `termination_evidence_set_producers` | one set/result; six closed producer roles; exact window checks | missing set/producer/window and current set positives |
| contributor membership incomplete | five closed direct roles with one globally unique evidence ID per contribution | composite FKs/PK/UNIQUE and structure trigger | missing/duplicate/sixth/cross-result/outside-set negatives |
| stale/cross identities accepted | every set, contributor, evidence, and result repeats current supervisor/epoch/bridge/process/observation | composite FKs and current-row structure trigger | stale generation/epoch/bridge and cross-process/observation negatives |
| five links did not prove source completeness | each of six producer instances supplies its exact authenticated closed window `expected_start_sequence..last_accepted_sequence` through cutoff; a first window starts at 1 and a later window starts at the prior accepted end plus 1 | producer/ingress unique keys, window equality, contiguous count/min/max and unmatched-row checks | gap, duplicate/out-of-order/restart/after-cutoff cases |
| conflicts not mechanically detected | evaluator decision is checked against all current in-window assertions for the role | known-conflict and UNKNOWN-conflict triggers | planned/crash, request/no-request, graceful/forced, initiator/identity conflict cases |
| `NONE` was self-declared | exact role-specific absence scopes require authenticated `STARTUP_TRANSITION` content and no contradictory current assertion | evidence CHECK plus conflict trigger | each valid absence; self-label, exception, incomplete, stale, contradiction negatives |
| `UNKNOWN` was underdefined | structural failure rejects whole result; complete current set uses field-specific `CONFLICT` or `INDETERMINATE` | structure, conflict, semantics, and integrity triggers | conflict UNKNOWN positive; incorrect reason/known value negatives |
| concrete values lacked positive proof | closed evidence-type mapping plus direct operator/request/provider/OS/bridge/listener membership | evidence CHECK and semantics trigger | matched crash positive; crash/plan/operator/process/provider/RAPI missing-proof negatives |
| startup could accept weak result | current termination proof is a read-only prerequisite under `SUPERVISOR_AUTHORITY_READY` | exact store query/trigger/hash predicates; startup never repairs or reclassifies | each invalid result leaves the gate unproven or fails startup |

## 3. Executable identity and inventory

| Identity | Phase 3C1-R2 value |
|---|---|
| SQL SHA-256 | `8b7bc314163b2fef65cb61221026ba6b962ff20797aa6be57f944c0dcd7ae4fc` |
| Canonical schema SHA-256 | `c3d60c3c943958a588ff744467c4eca56063851bfe0288054dba6f08ca5bfc2a` |
| Canonical writer-registry SHA-256 | `906286388a8a8c95ee1ae09b6537e969b998f9008e37ed9aae734a85361d0f20` |
| SQLite | 3.43.1 |
| Inventory | 40 STRICT tables; 552 columns (485 nonnull/67 nullable); 40 PK tables/49 PK columns; 133 FK declarations/173 mappings; one SHA-256 preflight view; 13 partial unique indexes; 21 triggers; 62 active routes; 11 writers; 55 operation IDs/52 database-commit types |

The writer-registry hash intentionally changes because `termination_evidence_sets` and `termination_evidence_set_producers` add two Health Durable Writer INSERT routes and all five termination routes carry the R2 termination writer-contract identity. The operation catalog remains the accepted closed 55-operation catalog; both new mutation paths belong to `TX-TERMINATION-CLASSIFY`.

## 4. Integrity contract

Every schema-creation, mutating, validation, startup, bootstrap, restore, and reinitialization connection registers `randle_sha256_hex_utf8(TEXT)` as `SQLITE_UTF8|SQLITE_DETERMINISTIC|SQLITE_INNOCUOUS` before executing the SQL. The function SHA-256 hashes the exact UTF-8 input bytes and returns lowercase hexadecimal. The preliminary direct call proves the empty-string digest; the schema-owned `randle_sha256_preflight_v` query proves innocuous use with `trusted_schema=OFF`. Missing, non-innocuous, nondeterministic, or wrong registration fails closed.

`termination_evidence.canonical_evidence_json` is the exact compact SQLite `json_object` byte form defined by its trigger. The evidence-set hash covers one header, six ordered producer windows, every ordered in-window evidence identity/hash, and five ordered contributor identities/roles. The result hash covers every result identity, all five fields, times, schema, generation/epoch/bridge/process/observation, decision/evaluator, transaction, nullable identities with the governed `-` sentinel, and the ordered contributors. All use UTF-8, tabs between fields, LF between/following rows, case-preserved SQLite text/integer rendering, and lowercase SHA-256.

## 5. Validation disposition

Isolated SQLite 3.43.1 validation compiled the complete SQL with the governed innocuous function, returned `integrity_check=ok` and zero `foreign_key_check` rows, reproduced all three hashes, and exercised every new trigger. Positive fixtures covered complete NONE, field-specific conflict UNKNOWN, and current matched bridge crash. Negative fixtures covered mandatory fields, time ordering/delay, schema/version/hash, contributor cardinality/membership, stale and cross identities, sequence completeness/cutoff, conflict, false absence, missing concrete evidence, and startup rejection. Accepted subscription, listener, terminal incident, calendar, writer succession, canonical recovery evidence, and candidate-store contracts remained regression-clean.

These are isolated document/schema validation exercises only. They are not production implementation or runtime verification.

## 6. Governance status

ADR-014 remains approved and unchanged. ADR-015 and ADR-016 remain unapproved. The schema/SQL and every amended supporting artifact remain draft and noncanonical. Canonical incorporation, implementation, runtime verification, deployment, `READY_LOCKED`, trading, Bucket 0 completion, and Bucket 1 remain unauthorized. DEBT-012, DEBT-013, DEBT-014, and DEBT-016 remain `BLOCKING`.

## 7. Phase 3C1-R3 supersession for five residual enforcement gaps

The independent Phase 3C1-R2 review found that the broad F6 design above remained incomplete in exactly five enforcement surfaces: supporting `UNKNOWN`, semantic-role binding for optional identities, authenticated normalized domain payload, durable producer arrival order, and mechanical proof of deterministic SHA-256 registration. The R2 corrections and validation claims remain historical evidence; they do not establish approval readiness for those five surfaces.

Each residual finding is reopened and superseded for normative approval readiness by `2026-07-17_Approval_Remediation_Phase_3C1_R3_Redlines.md`. Its active disposition is `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R3 REVIEW`. Phase 3C2 remains deferred and may operate only on exact independently accepted R3 hashes.
