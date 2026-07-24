# R7 real-execution terminal-authority requirement matrix (draft)

Status: corrected implementation traceability and review input only. It is not an R7 acceptance record or canonical incorporation.

## Immutable governing objects

| Authority | Identity | Use |
|---|---|---|
| R6 | commit `87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94`; parent `c211870a8183e8f3e9ea9bf17fa34288b2c3000e`; tree `f9891562ea09d011d4d9803d9cf64b88ff1f2dbf` | R7-01…R7-15 normative requirements |
| Complete R7 record 1 | commit `06c6805ed52a0d539a73088c097c60dec335462a`; report blob `1be3b0b5f15ac8e68b88202e0e9d3787b69d1856` | incomplete-control and replay findings; immutable input only |
| Complete R7 record 2 | commit `8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6`; report blob `dfa98a89049b9596387143c002252d91d608fbfc` | external terminal-authority requirement; immutable input only |
| Provisioning | commit `bb04ac54fb328516d0c785f4e6551e6a20d73759`; parent R6; tree `b25b41d9cfb5a0dbfdb271e4519734f60a11ad80` | service SID, isolated key, trust, fixed ledger, public verifier |
| Case set | SHA-256 `58d6c043b857b6950d375724ef1f05b695028a3778ee47067284148c477b9214`; blob `dae357d801cabdde7ca8a314c83380984161e687`; 995804 bytes | 178 immutable real cases |
| Expectations | SHA-256 `7563a8b8af74f15ad226d61015d0946867fa1d18495143e8206600f1c3c81005`; blob `c21ea8f5ab4b54fc0d0638e9bb20df83c8a88f1d`; 285399 bytes | independently authored expected semantics |
| R7I-B01 probes | SHA-256 `f5e4d9ac5c68a9190921bdec0b5fee88d11957d47a9d68dd2f95f02eef30ba9d`; blob `4694125882526d5bd9abb14b394d17d463d32564`; 6777 bytes | 25 prohibited synthetic-evidence constructions |
| Correction requirements | SHA-256 `cfeae6afaa86a851b6b44a5bec65922879114d641ffcc24e37d69d328cbe5756`; blob `b781cb5cfed4c2ccc7c91c55ca22f73fb01051a7`; 3788 bytes | correction-specific terminal semantics |

The two R7 record commits are prohibited ancestors. The case and expectation blobs are read as content-addressed inputs without adding either record commit to branch ancestry.

## Requirement-derived case coverage

| Requirement | Cases | Expected accept | Expected reject | Public control families |
|---|---:|---:|---:|---|
| R7-01 | 11 | 1 | 10 | `access_capability` |
| R7-02 | 8 | 1 | 7 | `external_issuance` |
| R7-03 | 11 | 1 | 10 | `external_launch` |
| R7-04 | 11 | 1 | 10 | `durable_ledger` |
| R7-05 | 12 | 1 | 11 | `recorder_session` |
| R7-06 | 11 | 1 | 10 | `observation_evidence` |
| R7-07 | 8 | 1 | 7 | `immutable_dispatch` |
| R7-08 | 8 | 1 | 7 | `internal_repository` |
| R7-09 | 26 | 2 | 24 | `complete_trace`, `internal_repository` |
| R7-10 | 9 | 1 | 8 | `review_resolution` |
| R7-11 | 10 | 1 | 9 | `compatibility_resolution` |
| R7-12 | 20 | 1 | 19 | `physical_filename` |
| R7-13 | 23 | 2 | 21 | `closed_authorization` |
| R7-14 | 8 | 4 | 4 | `real_classification`, `retained_controls` |
| R7-15 | 2 | 1 | 1 | `closed_authorization` |
| Total | 178 | 20 | 158 | 15 measured public-control families |

The count is the result of the immutable case construction, not a requested terminal count and not evidence of execution by itself.

## Forward implementation matrix

| ID | Governing requirement | Implemented enforcement | Positive evidence | Bypass evidence |
|---|---|---|---|---|
| R7I-01 | Case definitions resolve to exact immutable bytes. | `R7Support.ReadPinnedBytes`, `ReadCaseAuthority`, fixed policy identity; service `ValidateAuthoritySets`. | All 8 matrix runs resolve blob `dae357…` and SHA-256 `58d6…`. | A06 unresolved identity, A07 post-hash mutation, A08 alternate case input reject. |
| R7I-02 | Expectations are independent and immutable. | Separate expectation builder/artifact; `ReadExpectationAuthority`; comparator loads it separately. | 178-case ID-order bijection and expected semantics independently compared in every run. | A03 expectation-copy observation and A09 alternate expectations reject. |
| R7I-03 | Actual public controls run under measured isolation. | Service `ExecuteRealSuite`, `SendSubject`, `ValidateSubjectInstallation`, `ValidatePythonRuntime`; measured subject launcher and fixture helper. | 1424 current case executions across 8 terminal runs, each with canonical requests/responses and current subject process. | A01/A02 synthetic loop and identity echo, A14/A16 process-without-invocation, A17 wrong binary/caller reject. |
| R7I-04 | Request, response, process, service, token, and ledger evidence is current and resolvable. | `IssueSuiteProcessReceipt`, raw content-addressed stores, token/file/reparse native identity, inner recorder and ledger evidence. | 8 unique suite process receipts plus observer/comparator receipts; conditional fixture receipts resolve per case. | A13 prior event, A14 prior process, A15 fabricated request/response, A25 copied root reject. |
| R7I-05 | Events derive from real evidence and carry no final authority. | Service `BuildCurrentEvents` only after current invocation; event root from canonical bytes. | Each run has exactly one event per governed case and unique current event root. | A01 predetermined conforming events, A10 skipped case, A11 duplicate, A12 extra case reject. |
| R7I-06 | Observations derive from current events. | Fresh worker mode `DeriveObservations`; citations to raw event locators; no desired-status input. | 8 unique observation locators and per-case citations resolve. | A03 copied expectations and prior-run substitutions reject. |
| R7I-07 | Comparator independently resolves complete inputs and emits discrepancies. | Fresh worker `Compare`, `VerifyCase`, `VerifyFixtureProcessEvidence`, `Index`, `RejectUnknown`; explicit discrepancy rows. | Every matrix comparison resolves 178 cases and zero blocking discrepancies from evidence. | A04 constructed equal text, A05 no case load, A10–A19 missing/wrong/forbidden evidence reject. |
| R7I-08 | Terminal verifier rejects semantic fabrication before signing. | Service `VerifyCurrentRunSemantics`, `VerifyStoredFixtureEvidence`, process-index and trace checks, durable `StoreSigned`. | Eight distinct signed terminal receipts publicly verify with ledger membership. | All A01–A19, A22–A25 reject before terminal authority; A23 proves valid signature cannot cover unresolved children. |
| R7I-09 | Candidate/fresh reconciliation resolves both full executions. | Worker `Reconcile`, `VerifyWorkerTerminal`, `VerifyWorkerEvents`, `VerifyWorkerProcesses`; service `ValidateReconciliationEvaluator`; public `VerifyReconciliation`. | Four distinct reconciliation receipts report `SEMANTICALLY_EQUIVALENT_REAL_EXECUTIONS`. | A20 shared evidence, A21 two synthetic receipts, same-receipt structural probe, prior-pair replay reject. |
| R7I-10 | Receipt and ledger ordering is durable and publicly verifiable. | `DurableCreate`, `StoreContentAddressed`, fixed-ledger reserve/commit/checkpoint; public `VerifyLedger` and `FindLedgerEntry`. | Reservation precedes commit; public verification works with service stopped; restart retains checkpoint. | A18 rejection with unauthorized append, A19 success without subject append, A24 detached receipt, durable-response blocker reject. |
| R7I-11 | IPC and caller authority are closed. | `ValidateRequestShape`, caller SID check, strict JSON, 64 KiB limit, complete request reader, restricted pipe ACL. | Diagnostic and governed operations succeed for allowed caller. | 20 IPC negatives cover malformed, oversized, partial, disconnect, unknown/generic-sign, extra fields, roots/status/payload, replay objects, and dictionary reconciliation. |
| R7I-12 | Principal, key, trust, and repository remain isolated. | Restricted service SID; fixed certificate/key; public-only verifier; repository denial; policy-bound binaries. | SID restriction, caller key-open/export denial, public trust identity, repository denial. | Copied executable and altered trust reject without ledger authority. |
| R7I-13 | Replay, retry, idempotency, and concurrency are service-owned. | `LoadIdempotentResponse`, `StoreIdempotentResponse`, ledger lock, attempt/phase state. | Sequential and concurrent exact duplicates produce one transition and identical response. | Changed bytes with reused nonce, same candidate/fresh receipt, repeated pair, and stale run evidence reject. |
| R7I-14 | Required checkout and line-ending matrix uses real executions. | Matrix driver creates isolated clean short/long clones with `autocrlf=true/false`; real service calls and public verification. | 8 terminal runs and 4 reconciliations pass; all required provenance classes are distinct. | Initial long-path diagnostic failed closed before completion; corrected driver uses pre-clone `core.longpaths` and completed all four rows. |
| R7I-15 | Source-to-binary and package identity are reviewable. | Exact build script, normalized IL semantic verifier, package manifest/schema/secret verifier. | Installed/reference hashes match; seven fresh builds have exact normalized IL; sources have SHA-256 and Git blobs. | Package verifier rejects path drift, ancestry drift, blob drift, schema violations, stale synthetic identities, secrets, and forbidden authorization claims. |

## Stage-to-source reverse map

| Stage or field class | Producing/validating source | Immutable or durable sink | Reverse resolution |
|---|---|---|---|
| Case definition | `build_r7_real_case_authorities_DRAFT.py` | `r7_real_case_definitions_DRAFT.json`; fixed ProgramData authority file | case ID → R7 requirement → exact governing commit/blob/path → source case |
| Independent expectation | same builder's separate pre-execution output path | `r7_independent_expectations_DRAFT.json`; fixed ProgramData authority file | expectation ID → case ID → expected outcome/effects/evidence obligations |
| Public invocation | `TerminalAuthorityR7Service_DRAFT.cs::ExecuteRealSuite/SendSubject` | canonical request/response raw evidence | event locator → exact bytes → subject execution receipt → case token |
| Subject process | `TerminalAuthorityR7SubjectLauncher_DRAFT.cs`; service `IssueSuiteProcessReceipt` | signed process receipt and process index | event → suite receipt → launcher/subject PID, parent, token, binary/file identity |
| Fixture process | `TerminalAuthorityR7FixtureHost_DRAFT.cs`; service `ResolveFixtureEvidence` | signed fixture receipt, reparse and filesystem snapshots | physical case → fixture locator → PID/file/exit/reparse identity |
| Event | service `BuildCurrentEvents` | event source locator and event root | event → raw locators, current run/case, process receipt, ledger boundaries |
| Observation | worker `DeriveObservations` | observation locator | observation field → evidence citation → event/raw bytes |
| Comparator | worker `Compare/VerifyCase` | comparator locator with rows and discrepancies | row → expectation + observation + event + process/ledger/trace inputs |
| Bidirectional trace | service `BuildTraceability`; verifier checks | trace locator | requirement/case → invocation/event/observation/comparison; reverse case lookup |
| Terminal receipt | service `VerifyCurrentRunSemantics/StoreSigned` | terminal locator plus reserve/commit ledger entries | receipt field → exact child locator/identity and committed ledger membership |
| Reconciliation | worker `Reconcile`; service `ValidateReconciliationEvaluator` | reconciliation result, process receipt, signed reconciliation locator, ledger entries | reconciliation field → both complete terminals + disjoint provenance checks |
| Public verification | `TerminalAuthorityR7PublicVerifier_DRAFT.cs` | stdout result only; no new authority | locator → signature/trust → children → fixed ledger/checkpoint |
| Host policy | `build_r7_service_policy_DRAFT.py`; installer | fixed policy/authority files and ACLs | policy element → repository source/blob/hash → installed bytes/binary |

## Attack-to-failure reverse map

| Probe range | Attack class | Required rejection evidence |
|---|---|---|
| A01–A05 | predetermined results, identity echo, expectation copy, constructed equal values, comparator without case load | explicit classification/outcome/authority/strict-input discrepancies; no outer ledger delta |
| A06–A09 | unresolved, mutated, or caller-selected case/expectation authority | pinned-byte or strict-input rejection; no receipt |
| A10–A12 | missing, duplicate, or extra cases | structural discrepancy; no terminal receipt |
| A13–A17 | prior or fabricated event/process/request/response evidence; process without interface; wrong binary/caller | run/process/launch/interface/target identity discrepancy |
| A18–A19 | rejection with forbidden append; success without required durable effect | forbidden/outer or subject-ledger discrepancy |
| A20–A21 | shared synthetic pair; two structurally reconcilable synthetic receipts | provenance reuse or terminal rejection before reconciliation authority |
| A22–A25 | false trace, valid signature with unresolved child, detached receipt, copied evidence root | trace or public-verifier/strict-input rejection |

## Matrix and authorization boundary

The pre-commit result comprises four clean checkout variants, eight current terminal runs, 1424 case invocations, and four externally evaluated reconciliations. Run ID, run nonce, subject run, event root/source, observation, comparator, process index, trace, terminal receipt, all 24 outer process receipts/nonces, and four reconciliation process receipts are unique at their required cardinalities.

These mappings describe the implementation; they do not establish R7 acceptance. The next governed action after a successful immutable post-commit audit is a separately authorized independent adversarial R7 acceptance review using Codex Ultra. Merge, canonical incorporation, capture work, deployment, and any trading-system action remain excluded.
