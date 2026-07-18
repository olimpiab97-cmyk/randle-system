# Approval Remediation Phase 3C1-R1 — F1-F8 Targeted Normative Redline Record

Status: **DRAFT EVIDENCE — NONCANONICAL — NOT APPROVED — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW**

Purpose: correct only findings F1 through F8 from the independent review of commit `174cb5001da13eff53d42dde40f35154fb7d1c22`. This is remediation, not an approval review, implementation, production verification, deployment, or Phase 3C2 traceability.

## 1. Bound baseline

| Identity | Verified value |
|---|---|
| Phase 3C1 commit | `174cb5001da13eff53d42dde40f35154fb7d1c22` |
| Parent | `b9ab95b66c30d2745bf6573d8e1efb079685a55b` |
| Tree | `bbd94a779f3f8898c3f704ec43a8c9146d1e31b6` |
| Subject | `docs(architecture): close phase 3c1 normative schema defects` |
| ADR-014 SHA-256 | `528B3C7099D63DB41C6B85E381EAD37AD1E479867C07934FD077EBBD8B5EC321` |
| Diagnostic source tree | `704fd715cad3aad281c534f8337840e3aab96234` |

ADR-014 and the frozen thirteen-route diagnostic inventory were not reopened. The diagnostic contract's substantive route rows remain unchanged.

## 2. Exact finding disposition

| Finding | Rejected condition | Exact R1 correction | Isolated proof | Status |
|---|---|---|---|---|
| F1 | `date()`/`julianday()` and shape-only checks accepted impossible dates | Every concrete date/UTC column uses ASCII digits, exact separators, Gregorian month/leap bounds, year 0001–9999, second 00–59, six fractions, uppercase Z, and full SQLite round trip; no registered function | ordinary/leap/boundary positives; non-leap, Feb 30, month/day/hour/minute/second/separator/fraction/Z negatives | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F2 | Active unique index did not close successor ordering; TSV fields admitted delimiters | `trg_writer_registry_successor_guard` requires retired predecessor and strictly later effective sequence; serialized identity excludes empty, sentinel, TAB/LF/CR | retire 100/install 101 succeeds; 100/99/1 and contaminated identities fail; registry hash reproduces | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F3 | Cancellation described a versioned unchanged branch that SQL prohibited | Authorized `TX-LSN-CANCEL` may commit only `SUSPECT -> HEALTHY` or exact reason-bound/versioned `SUSPECT -> SUSPECT`; the self-edge trigger requires the exact two-writer set; every other self-edge fails | both positive branches, wrong-writer-set, and unauthorized self-edge exercised | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F4 | Required supervisor/epoch/start/registry/producer/session/bridge mutations lacked operation IDs | Added 18 exact commit operations, yielding 55 total/52 commit types; `TX-LSN-FENCE` includes Epoch Writer | transaction allowlist, writer sets, route coverage, pre/post-crash and retry rules validated | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F5 | Incident could be inserted terminal and terminal link checked too little | Direct terminal insert trigger; terminal update requires own outcome, same completion/recovery transaction, exact incident transition/version, and closed predecessor/outcome mapping | direct, cross-incident, mismatched transaction/recovery negatives; valid terminal update positive | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F6 | Subscription/termination rows omitted required identities and closed vocab/evidence relationship | Composite symbol/session and generation/epoch FKs; authenticated event equality for contract/session/request/provider/freshness/proof identities; closed five-field checks; new `termination_result_evidence` table and basis trigger | matching/cross-symbol/stale/wrong/missing/mismatched-provider/duplicate subscription and vocabulary/NONE/UNKNOWN/crash-evidence cases | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F7 | JSON profile, Windows durability, and scaling bounds were incomplete | complete bespoke `RANDLE-RECOVERY-JCS-1`; exact Unicode/key/integer/hash/file bytes; `CreateFileW`/`FlushFileBuffers`/same-volume `MoveFileExW`/readback/restart-cleanup contract without directory-flush claim; 64KiB/16MiB/4096 bounds | independent Python/Node serializers, Unicode/duplicate/NFC/surrogate/order/control/boundary and actual temporary-file replacement/readback simulation | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |
| F8 | Candidate row sets and first replacement CAS were incomplete; current migration test remained | Exact bootstrap/restore/reinitialize rows and order; mandatory external prepared-evidence sequence/hash on each store recovery row; explicit Runtime baseline and Entry initialization; current migration test removed/future-only | three candidate stores pass integrity/FK/startup/evidence-binding proof; first post-replacement operations and rollback exercised | `CORRECTED IN DRAFT — PENDING INDEPENDENT PHASE 3C1-R1 REVIEW` |

## 3. Executable schema disposition

Schema version remains 2. Inventory after R1 is 38 STRICT tables, 500 columns (440 nonnull/60 nullable), 38 primary keys/46 PK columns, 124 FK declarations/132 mappings, 13 partial unique indexes, 14 triggers, 60 active routes, and 11 writer identities. The added table is `termination_result_evidence`; no table was removed. The two added nullable recovery columns are mandatory together only for store bootstrap/restore/reinitialization and bind those rows to the external prepared-evidence sequence/hash.

Canonical schema hash is `10dab0b154fa34cabcbbf79ef3ef1966f6418e7e45a19543da2d6825aa260423`; writer-registry hash is `899bf56cbbae55068b136990c6baa1a01e4422da784119541089de9ecf3a3e28`; committed SQL-artifact SHA-256 is `fbc64af7bf9dc064e6a2e46172a253ea81d0d891ae2763c9cc65a74917fa8cc5`. The SQL remains a draft architecture implementation reference and is not authorized production code.

## 4. Governance boundary

The prior Phase 3C1 redline is preserved but superseded for normative approval readiness by this record. Semantic traceability remains `NOT APPROVAL READY — SEMANTIC TRACEABILITY REBUILD DEFERRED TO PHASE 3C2`. Phase 3C2 did not run. ADR-015/016 remain unapproved; all supporting documents remain draft/noncanonical; canonical incorporation, implementation, runtime verification, deployment, `READY_LOCKED`, trading, Bucket 0 completion, and Bucket 1 remain unauthorized.
