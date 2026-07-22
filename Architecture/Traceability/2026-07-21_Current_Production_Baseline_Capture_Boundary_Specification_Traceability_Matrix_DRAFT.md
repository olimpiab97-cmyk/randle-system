# Traceability Narrative: Current Production Baseline Capture Boundary R3

Status: draft narrative; machine authority is `semantic_traceability_R3_DRAFT.json`.

## Immutable trace chain

Each R3 row binds an explicit `CPB-R3-nn` clause in the authoritative specification Git blob to its clause semantic hash, an existing schema pointer, a committed rule, an AST-resolved enforcing function, an invoked positive case, an invoked mutation case, the corresponding independent expectations, current-run observations, and a future obligation.

The verifier independently loads the specification, schema, rule registry, and enforcing source from immutable Git objects. It rejects nonexistent or altered clauses, wrong hashes, missing pointers or rules, absent or never-invoked functions, missing or prior-run observations, wrong observed codes, identifier-only placeholders, and incomplete reverse mappings.

## R3 mapping summary

| Requirement | Primary authority | Enforcing surface |
|---|---|---|
| R3-01 | governed package/file bytes | long-path-safe access, stat, enumeration, reparse and access failures |
| R3-02 | committed Git blobs | authoritative byte-claim validation across checkout transformations |
| R3-03 | committed result and external comparator | `MATCHED`-only terminal reconciliation |
| R3-04 | bounded batch grammar | literal launcher dependency closure |
| R3-05 | separate-binding policy and role map | derived obligation enforcement |
| R3-06 | pinned validator and frozen timestamps | schema format and semantic chronology |
| R3-07 | attempt and timestamp issuance objects | external freeze reconstruction |
| R3-08 | attempt-prefix authority bytes | raw, blob, semantic, schema, role and ledger binding |
| R3-09 | evidence-policy bytes | role, class, cardinality, purpose and recovery binding |
| R3-10 | historical-evidence authority | exact path, size, hash, parse and logical identity |
| R3-11 | observer-source authority | exact append-only source, implementations, sequence and attempt |
| R3-12 | comparison authority | externally authorized comparator and receipt validation |
| R3-13 | authorization policy | structured and conservative free-text withholding grammar |
| R3-14 | immutable clauses and current observations | bidirectional semantic traceability |
| R3-15 | actual manifest and review bytes | future-package interface validation |
| R3-16 | assessment and delta Git blobs | architecture-document claim and content validation |

## Boundary

This trace demonstrates draft enforcement only. It does not authorize baseline capture, operational capture-script work, merge, canonical incorporation, production implementation, deployment, restart, migration, cutover, trading, Phase 3C2, Phase 3C1-R11 acceptance, Bucket 0 completion, or Bucket 1 work.
