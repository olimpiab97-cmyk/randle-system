# R7I-B01 correction requirements (draft implementation authority)

Status: implementation-only; no R7 acceptance, merge, canonical incorporation, deployment, or production/trading authorization.

This artifact records the implementation obligations supplied by the separately authorized R7I-B01 correction task. It is content-addressed before case execution and remains draft proposal material until a separately authorized independent R7 review acts on the resulting commit.

## R7I-B01-01 — immutable case and expectation authority

Every executed case resolves from finalized Git-blob bytes. Independently authored expectations resolve from a different finalized Git blob. Neither authority may be supplied through a caller-selected path, inline object, mutable policy identity, or observed result.

## R7I-B01-02 — governed public-interface execution

Each terminal run launches one fresh measured subject service directly from the restricted terminal-authority service and invokes the applicable governed R7 direct public interface for every immutable case through a one-shot case token. The subject service is an execution target, never terminal authority. The exact request and response bytes, OS process and token identity, parent identity, measured Python and source identities, current outer and subject run identities, per-case ledger boundaries, suite process receipt, recorder event, and observed side effects are retained and content-addressed.

## R7I-B01-03 — evidence-only events

Events are derived only after a current process has completed. They report actual outcome, response classification, process receipt, request/response identities, ledger evidence, side-effect evidence, and raw locators. They do not contain caller-authored or producer-assigned conformity authority.

## R7I-B01-04 — independent observations and comparison

A fresh observation stage derives actual observations from current raw events without receiving expectations. A separately isolated comparator resolves immutable definitions, independent expectations, raw evidence, process receipts, events, observations, trace rows, and fixed host identities, then emits explicit discrepancies.

## R7I-B01-05 — terminal semantic verification

The service independently repeats the per-case provenance checks before signing. Correct counts, matching strings, valid hashes, or a valid signature cannot substitute for real current execution and resolvable child evidence. Durable append precedes every terminal-success response.

## R7I-B01-06 — external reconciliation

Candidate and fresh receipts arise from distinct actual runs. Reconciliation accepts immutable receipt locators only, resolves all child evidence and ledger memberships, proves disjoint provenance, and rejects synthetic or unresolved pairs even when their summaries match.

## R7I-B01-07 — synthetic-provenance rejection

The verifier rejects predetermined results, policy-identity echoing, expectation copying, constructed zero-discrepancy output, unresolved case bytes, mutable or alternate authorities, missing/duplicate/extra cases, stale process or event evidence, fabricated request/response evidence, wrong callers/binaries, forbidden ledger effects, success without durable append, synthetic pair reconciliation, false traceability, unresolved signed children, detached receipts, and copied evidence roots.

## R7I-B01-08 — preserved infrastructure boundary

The correction preserves the restricted service SID, repository denial, nonexportable LocalMachine key, public trust, fixed ledger root and continuity, authenticated bounded IPC, replay/idempotency controls, and public-only verification. It makes no TPM, HSM, remote-signer, elevated-administrator, kernel, or offline-privileged protection claim.
