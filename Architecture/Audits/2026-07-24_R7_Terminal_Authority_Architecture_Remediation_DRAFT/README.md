# R7 terminal-authority architecture remediation — static proposal package

Status: uninstalled, nonauthoritative remediation source. Every `R7AR-B01` through `R7AR-B16` finding remains **PARTIAL**. This package does not accept R7, amend canonical authority, authorize merge, install a service, create a principal or key, alter trust or a ledger, or authorize production/trading use.

## Exact authority and separated semantics

The package independently reconstructs five exact governing sources without importing the discarded `f0cfbce97e913a133530dd66a70326b1e03a0fb6` diagnostic object. The static graph currently contains 79 governed requirements, 151 independently authored cases, and 151 separately authored expectations:

```text
exact commit/blob/path/range/clause bytes
  -> governed requirements
  -> independently generated cases
  -> separately generated expectations
  -> proposed hostile outer-interface evidence
  -> proposed independent event and observation derivation
  -> comparator
  -> terminal-signer rederivation
  -> transactional receipt and version-aware public verification
  -> candidate/fresh reconciliation
```

Case construction does not read the expectation artifact; expectation construction does not read cases or runtime output. Requests forbid expected status, expected code, desired result, or precomputed observation fields. The proposed installation ACLs deny execution and observation identities access to expectations, but those ACLs have not been applied or probed in this static unit.

`POS-005` and `POS-006` are not synthetic summaries. They are complementary nested submissions through the actual outer terminal operation: candidate runs apply 150 cases and fresh runs apply 150 cases; the runs share 149 ordinary cases and each supplies its own outer-submission meta case. The matrix and its reconciliation remain unexecuted.

## Proposed five-principal boundary

The design uses five distinct virtual service identities: terminal signer, execution, observation, comparator, and upgrade authority. Each proposed service uses a restricted service SID and a `SeChangeNotifyPrivilege` allowlist. `R7ServiceBoundary.cs` proposes LSA-enforced denial of interactive and remote-interactive logon before service start. Non-signer identities are denied terminal/upgrade key access, append stores, receipts, reconciliation, trust, policy, and repository writes. None of these services, rights, SIDs, ACLs, or denials was created or changed in this static unit.

The signer source does not launch semantic children. The proposed named-pipe boundary captures OS caller PID/token/SID/groups/privileges, executable handle identity, raw request/response frames, concurrent connection facts, and durable effects. Child assertions remain evidence only.

## Strict canonical protocol

The proposed protocol uses a 12-byte `R7TA` frame with explicit version, flags, and big-endian length. The complete frame must contain one canonical NFC UTF-8 JSON payload and no trailing bytes. The raw-frame limit is 65,536 bytes and the payload limit is 65,524 bytes. Recursive duplicate keys, invalid UTF-8, non-NFC strings, non-integer numbers, numeric strings, null/absent confusion, unknown fields, partial/multiple frames, and noncanonical payload bytes are rejected before dispatch. The offline 22-case parser suite does not substitute for the still-pending live pipe probes.

## Separate upgrade proposal

The proposed upgrade authority has its own restricted identity, operation-specific nonexportable key, public trust, policy, and append-only ledger; it has no terminal-receipt or generic-signing operation. A transition must bind old/new service, policy, interface, component set, source commit/tree, build receipt, dependency manifest, installer, host/volume/ledger, nonce, activation sequence, rollback, revocation, and anti-downgrade state before installation. No upgrade authority, key, ledger, authorization, activation, or installation exists as a result of this unit.

## Transaction and recovery proposal

Issuance follows `REQUEST_RECEIVED -> RESERVED -> EVIDENCE_VALIDATED -> RECEIPT_PREPARED -> COMMITTED -> RESPONSE_AVAILABLE`, with `ABORTED`, `SUPERSEDED`, and `RECOVERED` classifications. Response bytes are content-addressed before commit and reconstructed from signed state. Signed-chain replay can advance a stale checkpoint without rewriting entries.

`R7RecoveryProbeAuditor.cs` independently reopens each disposable probe's canonical result, public key, signed ledger, object store, transaction state, response/receipt evidence, and recovery intent, then rederives the result code instead of trusting the producer. Static fault tests are confined to marked temporary roots. Installed crash, disk, restart, and checkpoint proof remains outstanding.

## Static script, utility, source, and binary closure

`governed_script_registry.json` is an exact manifest of every top-level PowerShell script that can influence authority derivation, build, package staging, proposed installation/upgrade, matrix construction, evidence, traceability, verification, scanning, or host capture. It records path, raw SHA-256, Git blob identity, mode, size, role, allowed stage, dependency roles, and authority classification.

`external_utility_registry.json` content-binds the absolute Git, PowerShell, compiler, IL, framework/reference, service-control, ACL, filesystem, job, management, utility-module, and PKI inputs. Host-transition utilities are classified as future inputs and are not invoked for mutation. `R7MeasuredUtility.cs` defines held-handle identity checks for future measured invocation. Static measurements do not prove installed runtime dependency closure.

`source_role_registry.json` reverse-routes every current `Source/*.cs` file—including `R7MeasuredUtility.cs`, `R7ServiceBoundary.cs`, and `R7RecoveryProbeAuditor.cs`—to blocker/requirement IDs, architecture role, verification, intended authority, and executable consumers. It declares 12 compile targets with explicit source sets.

`build_static_closure.ps1` creates uninstalled nonauthority binaries only. It verifies registry identities, uses absolute utilities, recursively snapshots build-input roots before and after use, compiles every role twice with fixed x64/.NET 4.8 options and explicit references, records raw PE identities/differences, and requires normalized-IL equality. Precommit commit/tree values are explicit zero placeholders; detached postcommit builds bind the exact commit/tree. No compiled output is installed.

Python and Git are absent from proposed runtime authority. Git remains a content-bound build/verification and future matrix dependency. PowerShell remains a nonauthoritative orchestrator whose executable, modules, scripts, and recursive installation root are measured. Live loaded-module, DLL search, installed file, and running-process closure remains pending.

## Historical proposal and limits

Existing history remains immutable. The static classification registry binds sequence 332 as `INCOMPLETE_ISSUANCE_SUPERSEDED_NONAUTHORITY`, sequence 678 as `ABORTED_CLIENT_REJECTED_ISSUANCE_NONAUTHORITY`, and the ten ambiguous issuance records to exact historical identities with reuse forbidden. No append-only classification has yet been issued on the host.

The threat model excludes kernel compromise, offline/elevated administrator control, physical attack, compromised cryptographic primitives without detectable byte change, and TPM/HSM/remote-signer claims. It does not convert static compilation into OS isolation, host installation, ledger authority, matrix evidence, or independent acceptance.

## Remaining governed work

A separately authorized later unit must provision and verify the upgrade boundary, obtain a pre-install authorization, install only the authorized components, apply and probe the five-principal boundary, run live parser/path/key/dependency/ledger attacks, append governed historical classifications, execute the four candidate/fresh configurations and reconciliations, perform service-stopped and restart verification, and produce host/matrix traceability. This static package cannot approve that work or itself.
