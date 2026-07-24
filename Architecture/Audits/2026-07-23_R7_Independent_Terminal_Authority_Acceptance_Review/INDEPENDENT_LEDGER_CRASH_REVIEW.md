# Independent ledger, checkpoint and crash-consistency review

`independent_ledger_verifier.cs` is a standalone review implementation that references no Randle assembly or package verifier. It strict-decodes canonical envelope bytes, verifies every RSA-PSS-SHA256 signature using only the public certificate, recomputes each entry hash and prior link, checks fixed ledger/trust/SID identities, verifies the signed checkpoint, and checks reservation/commit adjacency and subject pairing.

## Cryptographic continuity results

- entries verified: 678/678;
- missing sequences: 0;
- invalid signatures, entry hashes or prior links: 0;
- duplicate nonempty request nonces: 0;
- genesis raw envelope SHA-256: `4493f53bda400caf845659429e5f0f9c57ab77918cf6c427491736e732a124ee`;
- genesis entry/root: `666e54345c43a8b5d83391f9d37c34537f4291a7839c068aa4734fcb810a91e5`;
- final sequence/root: 678 / `87fdc1bbcef606ad134cf5cd2c0cad83dd4df25ed96544c05fd5adbeff5f82e5`;
- checkpoint SHA-256: `988f08177b04125e3f92f0696adac8c22b7d24ab0a4cba726145d97ea2958962`;
- terminal reservations/commits: 64/64, unmatched 0;
- reconciliation reservations/commits: 31/31, unmatched 0 (11 legacy plus 20 current);
- content-address filename/hash verification: Evidence 9,239, Receipts 64, Reconciliations 31, mismatches 0.

These results establish cryptographic chain integrity only. They do not establish semantic authority of child evidence or governance of the signing implementation.

## Ungoverned upgrade entries

The chain contains 11 `R7_SERVICE_UPGRADE_ACTIVATED` entries at sequences 6, 9, 16, 42, 157, 324, 327, 330, 333, 339 and 356. All signatures are valid, but all 11 content addresses resolve to no stored Evidence/Receipt/Reconciliation object. Service startup constructs an in-memory description of itself and self-appends its hash using the preserved v1 key. This is a signed self-claim, not an externally authorized upgrade receipt.

## Durable response and reusable-authority defect

The service appends authority inside `IssueAttempt`, `ExecuteRun` or `Reconcile`, returns from that operation, and only then stores the idempotent response at service line 435. Ten post-sequence-323 top-level requests have no durable response: runs 326, 329, 332 and 335; attempts 375, 378, 381, 544, 547 and 678.

Sequence 678 is direct evidence: a valid signed attempt (`subject_id` beginning `e8b59508...`, content `7159df8b...`) was appended, response storage was denied by the authored fault probe, and the client received `REQUEST_REJECTED`; the response file is absent. `ResolveAttempt` accepts any ledger-issued attempt, so the request reported as rejected left usable authority that can be consumed with a different run nonce. A clean chain does not cure this ambiguity.

## Checkpoint crash window

Append durably creates and flushes an entry, advances in-memory state, then replaces the checkpoint. Restart verification requires the checkpoint sequence/root to equal the final entry exactly. A crash after entry persistence and before checkpoint persistence therefore leaves a valid later entry with a stale checkpoint and no forward-recovery path; initialization rejects the state. Parent-directory durability is also not established.

## Incomplete seq-332 classification

Sequence 332 is a durable `R7_RUN_ISSUED` entry with no durable response, suite completion, terminal receipt, abort, cancellation or supersession record. Its BrokenPipe-era fixture evidence and retained junction remain. It is not terminal, but the implementation does not prove it permanently nonreusable.

## Authorization-limited tests

No stop/restart, crash injection, disk-full, access denial, partial write, stale-handle, power-loss, destructive ledger mutation, same-SID key use, or conflicting live authority request was executed. Those would change dedicated host/service/ledger state and were not pre-authorized. They are recorded as unverified, never as PASS. Static control flow and existing seq-678 evidence are sufficient to reject without performing them.
