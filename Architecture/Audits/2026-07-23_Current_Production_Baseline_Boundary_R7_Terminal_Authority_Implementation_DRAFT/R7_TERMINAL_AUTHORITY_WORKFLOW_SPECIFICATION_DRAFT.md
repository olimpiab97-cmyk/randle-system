# R7 real-execution terminal-authority workflow specification (draft)

Status: corrected implementation contract and review input only. It does not accept R7, amend canonical authority, authorize a merge, or authorize operational or trading use.

## 1. Immutable authority

The workflow is derived from R6 commit `87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94`, the two complete R7 record commits `06c6805ed52a0d539a73088c097c60dec335462a` and `8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6`, and provisioning commit `bb04ac54fb328516d0c785f4e6551e6a20d73759`. The record commits are read through immutable Git objects but never enter implementation ancestry.

The execution authorities are finalized before execution:

- case definitions: SHA-256 `58d6c043b857b6950d375724ef1f05b695028a3778ee47067284148c477b9214`, Git blob `dae357d801cabdde7ca8a314c83380984161e687`, 995804 bytes, 178 cases;
- independent expectations: SHA-256 `7563a8b8af74f15ad226d61015d0946867fa1d18495143e8206600f1c3c81005`, Git blob `c21ea8f5ab4b54fc0d0638e9bb20df83c8a88f1d`, 285399 bytes, 178 expectations;
- R7I-B01 attacks: SHA-256 `f5e4d9ac5c68a9190921bdec0b5fee88d11957d47a9d68dd2f95f02eef30ba9d`, Git blob `4694125882526d5bd9abb14b394d17d463d32564`, 6777 bytes, 25 probes;
- correction requirements: SHA-256 `cfeae6afaa86a851b6b44a5bec65922879114d641ffcc24e37d69d328cbe5756`, Git blob `b781cb5cfed4c2ccc7c91c55ca22f73fb01051a7`, 3788 bytes.

The service resolves those exact fixed files and identities. Requests cannot contain alternate case, expectation, policy, trust, evidence, receipt, reconciliation, or ledger roots.

## 2. Authority separation

The pipe client is only a requester. It cannot provide a status, observation, event, discrepancy count, ledger sequence, prior hash, signing payload, or reconciliation result. The measured execution subject is explicitly nonauthoritative: it exposes the actual R7 public controls and returns raw outcomes, but it cannot issue an outer terminal receipt.

Only `RandleTerminalAuthority`, running with the restricted virtual-service SID, may validate the complete graph, use the nonexportable LocalMachine CNG RSA-3072 key, append the fixed ledger, and return an immutable locator. The public verifier has no private-key access and accepts only fixed-root content-addressed objects.

The stages are deliberately separate:

```text
R6/R7 requirement
  -> immutable case definition
  -> separately authored immutable expectation
  -> measured real public-interface invocation
  -> current raw request/response/process/ledger evidence
  -> observation derived from that evidence
  -> independent comparator with explicit discrepancies
  -> service terminal verification
  -> durable reservation, receipt storage, commit, checkpoint
  -> public-only verification
  -> distinct candidate and fresh execution
  -> measured external reconciliation
```

No text status such as `PASS`, `OK`, or `MATCHED` is accepted as evidence of a prior stage.

## 3. Closed outer interface

Interface `3.0.0-DRAFT` permits exactly these operations:

- `GET_HEALTH`, `GET_PUBLIC_TRUST`, and `GET_LEDGER_STATUS` for diagnostics;
- `ISSUE_R7_ATTEMPT` to create a service-owned attempt for one governed matrix configuration;
- `EXECUTE_R7_RUN` to execute one candidate or fresh phase;
- `GET_R7_RECEIPT` and `GET_R7_RECONCILIATION` for immutable-locator retrieval;
- `RECONCILE_R7_TERMINAL_RECEIPTS` for the service-issued candidate/fresh pair.

There is no generic signing or ledger-append endpoint. Strict JSON keys, request size, complete-frame reading, authenticated pipe ACL, caller SID, canonical nonce, operation-specific shape, phase, and state are checked before authority-changing work.

## 4. Case and expectation construction

The 178 cases are requirement-derived rather than count-preserving placeholders. They comprise 20 expected acceptances and 158 expected rejections across R7-01 through R7-15. Every case has a stable semantic identifier such as `R7-01-P001` or `R7-01-M001`, exact governing objects and paths, public interface, operation, initial state, prerequisites, request-construction rule, caller class, isolation, response semantics, required and forbidden effects, ledger delta, receipt behavior, retry/replay behavior, raw-evidence obligations, observation derivation, comparator rule, and bidirectional trace.

The expectation artifact is produced separately before execution and binds each case ID to expected outcome, classification, enforcing authority and function, effects, forbidden effects, ledger behavior, and evidence obligations. It contains no event, observation, receipt, comparator result, or precomputed current-run value. Worker modes resolve fixed SHA-256 and Git-blob identities and reject caller-provided authority files or inline objects.

## 5. Measured public-interface execution

Each terminal run launches one fresh measured subject process through `RandleTerminalAuthorityR7SubjectLauncher.exe`. The launcher receipt binds launcher, Python runtime, subject service source, process IDs, parent ID, start time, command, environment, inherited token/SID evidence, and readiness response. The subject repository, commit, tree, source identities, Python runtime manifest, and interface files are fixed in policy.

For every case, the service constructs canonical request bytes from the case definition and a one-shot current-run case token, sends them to the named public interface, captures exact response bytes, and stores both content-addressed. It records outer ledger state before and after, inner recorder event and subject ledger evidence, subject process and service identity, and required side-effect evidence. Physical-filename cases use the measured fixture helper; its signed process receipt, PID, file identity, exit code, junction/reparse bytes, and filesystem snapshot must reconcile before the case event is accepted.

The suite process receipt is issued only after all current invocations complete. It binds the launcher/subject process, file and binary identities, start/end/exit evidence, current run, subject run, case count, fixture count, raw case index, and all raw locators. Prior-run locators, copied process receipts, wrong binaries, wrong callers, missing requests or responses, and unresolvable evidence fail validation.

## 6. Events and observations

An event is constructed from a completed current case invocation. It binds run and case IDs, case and expectation identities, interface, invoking and target process evidence, request and response hashes and locators, pre/post outer ledger state, subject execution receipt and recorder event, fixture receipt where required, observed effects and forbidden-effect checks, event-construction component, schema version, and governed time fields. Event construction never receives or emits terminal conformity authority.

The event source contains exactly the immutable case set once each and no extras. Its root is calculated from actual canonical event bytes and a current chain; it cannot be supplied by the caller.

`R7MeasuredWorker.derive-observations` runs as a separately measured fresh process. It loads only the event source plus the fixed authority files and derives actual outcome, response classification, enforcing function and authority, process identity, interface invocation, subject and outer ledger deltas, fixture effects, receipt evidence, and forbidden-effect results from cited raw locators. It rejects any desired status field or observation copied from expectation text.

## 7. Independent comparison

`R7MeasuredWorker.compare` runs as another measured fresh process. It independently resolves the case definitions, expectations, event source, observations, process receipts, raw request and response bytes, subject ledger evidence, outer ledger boundaries, and bidirectional trace. For every expected case it checks uniqueness, current execution, correct interface and caller, evidence resolution, expected outcome and classification, required effects, forbidden-effect absence, and correct producer identity. It also rejects unknown, duplicate, stale, conflicting, or extra evidence.

The comparator emits one explicit row per case and a discrepancy list. A zero discrepancy count is accepted only when all independently loaded inputs support it; a caller-provided count or matching pair of text fields is rejected.

## 8. Terminal verification and durable order

Before signing, the service resolves and revalidates every child object. It verifies the exact immutable authority bytes, a complete 178-case bijection, current run binding, real invocation corroboration, suite/observation/comparator process receipts, request and response content, inner and outer ledger evidence, derived observations, comparator inputs and rows, zero blocking discrepancies, and forward/reverse traceability. It rejects synthetic all-conforming evidence even if internally hashed or signed.

For a conforming run, the service appends `R7_TERMINAL_RESERVED`, creates and signs the canonical receipt, stores the receipt under its SHA-256 locator, appends `R7_TERMINAL_RECEIPT_COMMITTED`, and flushes a signed checkpoint before returning success. Failure after reservation but before response produces no success response and never deletes the retained reservation or prior history.

## 9. Reconciliation

Candidate and fresh phases are distinct executions with unique run IDs, nonces, subject processes, event roots, evidence objects, process receipts, terminal receipts, and provenance roots. The service launches a separate measured reconciliation worker. That worker resolves both terminal locators and ledger memberships, then independently revalidates both complete graphs and trace rows. It requires equivalent governed semantics but disjoint execution provenance and rejects any shared synthetic class, copied evidence, same receipt, same run, stale child, or detached ledger membership.

Only after this validation does the service reserve, sign, store, commit, and checkpoint a reconciliation receipt with result `SEMANTICALLY_EQUIVALENT_REAL_EXECUTIONS`. The public verifier repeats the immutable graph, signature, ledger, and provenance checks without invoking the service or using private material.

## 10. Replay, restart, concurrency, and failure

Request nonces are canonical UUIDs. An identical retry resolves to the service-owned response; changed bytes under the same nonce reject. Attempt/phase and candidate/fresh pair subjects are one-time. Concurrent duplicates serialize under the fixed ledger lock and can add at most one authority transition.

Startup verifies service path and hash, policy, worker and helper identities, trust, key access, fixed roots, ledger chain, and checkpoint before opening the pipe. Service absence, incomplete requests, evidence resolution failure, signature failure, wrong authority, substituted trust, or durable response failure is fail-closed. Restart resumes from the retained ledger and checkpoint. Public verification remains available while the service is stopped.

## 11. Trust and authorization limits

The corrected executable preserves the provisioned restricted SID, LocalMachine CNG RSA-3072 nonexportable key, certificate thumbprint `21961cfc1b10824e539172fd04efa83ad2be9203`, public trust SHA-256 `b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285`, ledger identity `899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52`, and fixed roots.

Key rotation, trust substitution, revocation, recovery, policy upgrade, and later binary upgrade remain separately governed. Elevated-administrator, kernel, and offline privileged compromise are outside the declared threat model. The implementation makes no TPM, HSM, or remote-signer claim.

The only next action enabled by a successful corrected implementation is a separately authorized independent adversarial R7 acceptance review using Codex Ultra. Canonical incorporation, merge, capture work, deployment, trading-service changes, runtime migration, NQ cutover, paper or live trading, Phase 3C2, Phase 3C1-R11 acceptance, Bucket 0 completion, and Bucket 1 work remain outside this authority.
