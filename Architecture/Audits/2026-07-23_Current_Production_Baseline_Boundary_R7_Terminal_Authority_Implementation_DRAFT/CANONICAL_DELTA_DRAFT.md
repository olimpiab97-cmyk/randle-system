# Canonical Delta — R7 real-execution terminal authority (proposal only)

No canonical object is changed by this implementation. This document records only the deltas that would require separate authority after an independent R7 review.

| Potential canonical surface | Delta demonstrated by the implementation | Current authority state |
|---|---|---|
| Current Production Baseline Boundary Specification | Replace self-attested terminal status with the complete real-execution chain: immutable case → independent expectation → public-interface evidence → derived observation → independent comparison → external terminal verification → durable receipt → public verification → external reconciliation. | Proposal only |
| Runtime Authority Specification | Classify runtime, subject code, pipe clients, event constructors, and workers as proposers/evidence producers; deny them signing, ledger, terminal-status, and reconciliation authority. | Proposal only |
| R7 case registry | Register 178 requirement-derived cases, their governing Git objects, 20 expected acceptances, 158 expected rejections, public-interface mapping, evidence obligations, and reverse trace. | Draft blobs only |
| Expectation registry | Register the separately authored 178-case expectation artifact and prohibit regeneration from events or observations. | Draft blob only |
| Terminal authority contract | Register closed interface `3.0.0-DRAFT`, strict request shapes, fixed roots, restricted service principal, measured children, complete-graph verification, and append-before-response semantics. | Implemented review input; not canonical |
| Evidence contract | Register request/response bytes, process receipts, subject launch and ledger evidence, event source, observations, comparator rows/discrepancies, trace rows, and immutable locator resolution rules. | Draft schemas only |
| Receipt and reconciliation contract | Require durable reservation/commit membership, complete child resolution, distinct candidate/fresh provenance, equivalent governed semantics, and rejection of structurally matching synthetic executions. | Draft schemas and implementation only |
| Trust registry | Register the existing public certificate identity, service SID, nonexportable LocalMachine CNG key role, service/worker/client/verifier/helper binary roles, policy identity, and ledger identity. | Provisioned trust preserved; incorporation withheld |
| Recovery and lifecycle procedures | Define fail-closed interrupted issuance, durable-response failure, restart continuation, binary/policy upgrade, rotation, revocation, checkpoint recovery, and disaster recovery. | Further governance required |
| Adversarial registry | Register the 25 R7I-B01 synthetic-evidence attacks plus retained principal, key, IPC, ledger, replay, retry, concurrency, restart, and service-stopped probes. | Implementation evidence only |
| Traceability registry | Register bidirectional mappings across authority objects, case/expectation bytes, interface invocation, process/evidence objects, receipt fields, ledger entries, source, binaries, and host policy. | Draft only |

The correction retains R6 canonical/NFC/schema controls, historical-log identity and arithmetic, validator capabilities, mandatory-five semantics, candidate/fresh separation, short/long checkout behavior, both `autocrlf` modes, protected ancestry, and active-root preservation.

It explicitly rejects predetermined conforming events, policy-identity echoing, expectation-to-observation copying, constructed zero discrepancies, unresolved case-set identities, caller-selected authority inputs, prior-run substitution, fabricated request/response or process evidence, signed unresolved child graphs, detached receipts, copied evidence roots, and reconciliation of two synthetic receipts.

No draft receipt or result supersedes canonical authority. This task does not authorize R7 acceptance, canonical incorporation, merge, capture-package/script work, baseline capture, deployment, production or trading-service changes, runtime migration, NQ cutover, paper/live trading, Phase 3C2, Phase 3C1-R11 acceptance, Bucket 0 completion, or Bucket 1 work.
