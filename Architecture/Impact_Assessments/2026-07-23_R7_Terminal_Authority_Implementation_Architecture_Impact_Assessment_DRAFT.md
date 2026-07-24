# R7 real-execution terminal-authority correction — Architecture Impact Assessment (draft)

Status: implementation evidence and proposal-only architectural assessment. It does not accept R7, alter canonical authority, authorize merge, or authorize operational use.

## Decision context

R6 commit `87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94` defined the deterministic R7 boundary. The complete R7 records at `06c6805ed52a0d539a73088c097c60dec335462a` and `8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6` showed why a caller-local object or reconstructed dictionary could not supply terminal authority. Provisioning commit `bb04ac54fb328516d0c785f4e6551e6a20d73759` established the restricted Windows service, isolated nonexportable key, public trust, fixed ledger, and public verifier without accepting R7.

The first implementation candidate externalized cryptography and durability but still converted policy identities into predetermined conforming events, copied matching values into observations, constructed a zero-discrepancy comparison, and signed that synthetic graph. Its measured binary and valid signature did not prove that the R7 public controls ran. The correction therefore treats semantic execution provenance—not signature validity or internally consistent hashes—as the architectural boundary.

## Implemented architecture

The dedicated `RandleTerminalAuthority` service remains the sole outer authority. Its closed `3.0.0-DRAFT` pipe interface accepts attempt, run, locator retrieval, and candidate/fresh reconciliation operations; it has no generic sign, append, payload, path, root, or status endpoint. The caller cannot select authority bytes or author a result.

Four content-addressed inputs are fixed before execution: case definitions, independent expectations, R7I-B01 attack definitions, and correction requirements. The 178 cases are derived from R7-01 through R7-15 and retain their real semantic IDs. The expectation artifact is separate and contains no actual-run values.

For each terminal phase the service launches a fresh measured subject through a measured launcher under the restricted service token. It invokes each required public control, captures canonical request and response bytes, process/file/token evidence, inner subject recorder and ledger evidence, outer ledger boundaries, and measured fixture evidence where a physical path mutation is required. Events are constructed only from those current bytes.

A fresh measured observation worker derives actual values from event evidence. A different measured comparator process independently loads the cases, expectations, events, observations, request/response objects, process receipts, ledger evidence, and trace rows. It emits explicit per-case discrepancies. The service then independently resolves the entire graph before it can reserve, sign, store, commit, and checkpoint a terminal receipt.

The resulting flow is:

```text
immutable R6/R7 authority
  -> immutable cases + separate expectations
  -> fresh subject process
  -> actual public controls
  -> raw current-run evidence
  -> current events
  -> separately derived observations
  -> separately measured comparator
  -> complete-graph terminal verifier
  -> fixed-ledger reservation and commit
  -> public-only verification
  -> distinct execution pair
  -> measured complete-graph reconciliation
```

## Authority and data-flow effects

Runtime and subject components are explicitly nonauthoritative. A subject response, event field, observation, comparator summary, process receipt, signature, or content hash is insufficient alone. Authority exists only when the service resolves all required child bytes, proves current execution and provenance, confirms bidirectional trace and zero blocking discrepancies, and durably commits the signed receipt to the fixed ledger.

The outer ledger is not used as a per-case subject recorder. Case evidence records pre/post outer sequence and proves the expected zero outer authority delta during subject invocation; the subject's own fixed recorder and ledger supply case-level side effects. Outer entries are reserved for attempt/run state, terminal reservation/commit, reconciliation reservation/commit, idempotency, activation, and governed failure evidence.

Candidate and fresh phases share immutable semantics but share no run, nonce, process receipt, subject process, event root, evidence root, terminal receipt, or provenance identity. The reconciler resolves both full graphs and rejects two structurally matching receipts if either graph is synthetic or unresolved.

## Lifecycle, concurrency, and failure behavior

- Exact retries return the service-owned response; nonce reuse with different bytes rejects.
- Concurrent duplicate requests serialize on the fixed ledger and produce one authority transition.
- A phase or candidate/fresh pair is one-time and state-bound.
- Service startup verifies the fixed binary path, policy and helper identities, trust, key usability, roots, complete ledger chain, and checkpoint before accepting requests.
- Terminal success is returned only after reservation, immutable receipt storage, commit append, and checkpoint persistence.
- A durable-response failure returns no success and retains all durable history, including a reservation if that was already appended.
- Service absence, partial/oversized/malformed IPC, unknown operations, wrong caller, unresolved evidence, trust substitution, copied executable, signature failure, or ledger inconsistency fails closed.
- Completed receipts, reconciliations, and the ledger are publicly verifiable while the service is stopped.
- Restart continues from the same checkpoint and ledger root; history is never truncated or rewritten.

## Security and trust impact

The correction preserves service name `RandleTerminalAuthority`, restricted SID `S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948`, certificate thumbprint `21961cfc1b10824e539172fd04efa83ad2be9203`, public trust SHA-256 `b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285`, ledger identity `899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52`, and the nonexportable LocalMachine CNG RSA-3072 key. The repository remains unwritable from the service principal, and the interactive caller cannot open or export the private key.

The installed service binary becomes `9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526`; worker `b2971b85de73d999bfa801d047b22c2ec6fc3d6bc5cb5923ea4a9ab240ed4401`; client `8d5a5e803c9b7c17f06a488ef815b138d9de1dcd666ab1d4c333414801d4b6e9`; public verifier `88c4e631035af0c7ec366256c78f4d1f21994554a30201b30b4d6bf775314a3d`; fixture helper `7a82bab5acfa36555d0e3b9cf29084101f8276b4ceba93cd48cc1e85fadf1454`; and subject launcher `3445e5effd6398b648afa6898391f4e2b5de34f696dd91bfedc2dc29be4e3877`.

The threat model covers a hostile filtered interactive caller, mutable caller objects, replay, substitution within the declared roots, and fabricated evidence. Elevated-administrator, kernel, and offline privileged compromise remain outside scope. This software CNG design does not claim TPM, HSM, remote-signer, or hostile-administrator protection.

## Repository, host, and operational impact

Repository changes are confined to `.gitattributes`, this AIA, and one draft audit package. No active production-root file is modified. Host changes are confined to the existing dedicated Program Files binary directory and `C:\ProgramData\RandleAI\TerminalAuthority` configuration/evidence roots. The fixed ledger is advanced but never reset, replaced, hidden, or shortened. No Entry Agent, Trade Manager, executor, TradingView, ngrok, broker, capture, or other trading/production process is modified, stopped, or restarted.

The legacy .NET Framework compiler does not emit reproducible PE bytes in this environment. Source-to-binary verification therefore requires both installed/reference raw-hash equality and exact normalized IL equality from a fresh build after removing only runtime-generated MVID and image-base variation. This limitation is explicit evidence, not a claim of deterministic PE output.

## Canonical and authorization impact

No canonical file is amended. The accompanying Canonical Delta describes possible later changes but has no incorporation authority. A successful corrected implementation can only be handed to a separately authorized independent adversarial R7 acceptance review using Codex Ultra.

This correction does not authorize self-review, R7 acceptance, canonical incorporation, merge, capture work, production baseline capture, deployment, trading-service modification or restart, migration, NQ cutover, automated paper trading, live-money trading, Phase 3C2, Phase 3C1-R11 acceptance, Bucket 0 completion, or Bucket 1 work.
