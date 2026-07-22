# Architecture Impact Assessment: Current Production Baseline Capture Boundary R2

Status: draft assessment; no canonical change.

## Scope

This assessment covers specification, schema, draft verifier, fixtures, traceability, and provenance only. Production source, production tests, launchers, deployment files, configuration, runtime databases, runtime data, and operational capture scripting are outside the change set.

## Demonstrated impacts

### Governance

The package separates accepted-specification authority from later operational-package, freeze, and execution authorities. A machine-readable withholding artifact covers fifteen protected domains. A fail-closed scanner observes every accepted package role plus the derived fixture result and remediation report.

### Repository provenance

Committed Git blobs are the authoritative package bytes. The local attribute policy pins package text to LF. Actual Git-object access, clean-filter behavior, object format, branch, HEAD, parent, index, status, and attributes are observed with long-path-safe commands. Derived review results are excluded from the accepted-specification input root to prevent self-reference, while the eventual commit still preserves them as provenance.

Accepted-specification Git-object derivation and physical inventory selection are separate authorities. Non-fixture inventory selection is read-only and is admitted only from an isolated non-production worktree that is clean and exactly at the separately frozen inventory commit. The active production root, a moved `HEAD`, and any dirty state are refused before inventory.

### Production recovery

The selection interface performs parser-backed dependency closure, complete terminal reconciliation, independent freeze reconstruction, and distinct external bindings. It makes no assertion about the correctness or operational fitness of production code.

### Test authority

The five questioned tests are bound by exact authority and evidence tuples, physical paths, content identities, and committed rule/configuration/verifier blobs. The historical regression artifact is parsed from the actual immutable log rather than synthesized.

### Runtime and deployment authority

The draft performs no runtime access and no production mutation. Runtime, deployment, restart, migration, cutover, and trading states remain withheld. Truthful future incident fields remain recordable and disqualify capture authority when true.

### Evidence durability

Required roles, classes, cardinalities, purposes, capture-pass relationships, immutability, and recovery flags exist in an independent evidence policy. Evidence instances reconcile to the policy and preserved attempt authority.

### Traceability

Machine traceability enumerates every schema property and conditional pointer and maps rules and source symbols to invoked cases, static expectations, fresh observations, and future obligations. The old `ALL_DECLARED_FIELDS` placeholder architecture is removed from enforcing code.

### Operational safety

All real-surface repository and filesystem mutations occur in disposable temporary roots. The suite uses actual NTFS streams, actual clean filters, actual controlled Git repositories, and an append-only test observer. It does not read runtime databases or invoke services.

### Reproducibility

The verification environment pins `jsonschema==4.25.1` and `PyYAML==6.0.2`. Fresh checkout tests cover `core.autocrlf=true`, `core.autocrlf=false`, long paths, object/worktree divergence, policy change, blob-only change, and worktree-only change. Canonical JSON is checked from Git objects.

## Canonical documents affected in a later task

| Canonical target | Future impact requiring explicit review |
|---|---|
| `Architecture/README.md` | Index the accepted boundary and authority separation. |
| `Architecture/06_Randle_AI_Modernization_Charter.md` | Reconcile recovery governance, execution boundaries, and trading separation. |
| `Architecture/07_Randle_AI_Modernization_Roadmap.md` | Place specification review, later operational-package review, freeze review, and capture as distinct gates. |
| `Architecture/10_Randle_AI_Architecture_Traceability_Specification.md` | Incorporate field/rule/function/case bidirectional trace requirements. |
| `Architecture/12_Randle_AI_Development_Process_Specification.md` | Incorporate checkout-byte policy, independent expectations, and comparison receipt requirements. |
| `CODEX_TASK_TEMPLATE.md` | Add preserved-prefix, external evidence, structured withholding, and separate-package checks. |
| Accepted successor to the Runtime Recovery Verification Specification | Integrate freeze reconstruction, attempt/evidence authority, and multi-pass observers. |
| `.gitattributes` or equivalent byte policy | Decide whether the narrowly scoped package policy should become a reusable canonical policy. |

Additional affected canonical material: any canonical evidence-retention or incident-ledger specification that later becomes the source of preserved-prefix or required-evidence authority.

No canonical target is changed here.

## Risk assessment

The primary residual risk is that this remains draft fixture code, not the future operational capture implementation. Independent review must reproduce the meta-mutations, actual historical parse, real ADS transitions, fresh checkouts, freeze reconstruction, and semantic trace before this draft can serve as an accepted specification.

## Continuing boundary

Baseline capture and operational capture-script work remain withheld. Merge, canonical incorporation, production implementation, deployment, restart, migration, NQ cutover, automated paper trading, live-money trading, Phase 3C2, and Phase 3C1-R11 acceptance remain withheld. Bucket 0 remains incomplete. Bucket 1 remains blocked.
