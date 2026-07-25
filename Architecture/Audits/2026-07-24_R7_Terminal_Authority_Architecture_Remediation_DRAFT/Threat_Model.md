# Threat model and assurance boundary

## Intended protected boundary

The proposed boundary covers exact governing bytes; independent cases and expectations; canonical framed IPC; five distinct service identities; held executable/policy/authority/dependency handles; separate terminal and upgrade keys/trust/ledgers; append-only transaction/recovery state; content-addressed raw evidence, receipts, responses, and reconciliation; and version-aware offline public verification.

The attacker model treats execution, observation, comparator, fixtures, request builders, and every child-emitted field as hostile. It also includes malformed/ambiguous frames; invalid callers; replay and conflicting retry; signer impersonation; path reparse/link/ADS/alias/case/race/substitution; build/runtime path and DLL/import substitution; self-authorized upgrade/downgrade/replay; response loss; partial writes; stale/partial checkpoints; process restart; inconsistent historical evidence; and two matching but invalid graphs.

## Proposed OS and semantic controls

Terminal signer, execution, observation, comparator, and upgrade authority use distinct restricted virtual-service SIDs. The installation design applies `SeDenyInteractiveLogonRight` and `SeDenyRemoteInteractiveLogonRight`, a `SeChangeNotifyPrivilege` allowlist, narrow pipe ACLs/operations, and disjoint filesystem/key rights. The signer does not spawn semantic children and must derive disposition from OS-captured caller/process/token/frame/file/ledger/effect facts.

The protocol accepts only one complete canonical NFC UTF-8 JSON payload in an exact frame. Expected semantics are inaccessible to execution and observation under the proposed ACLs. Recovery-producer results are not trusted: the auditor reopens canonical evidence and independently derives the public result code from signed ledger/transaction state.

Fixed files and external utilities are intended to be opened no-follow, measured by canonical handle identity, and held through use. Static package construction uses absolute utility paths and records recursive closure before and after compilation. Git and PowerShell remain measured nonauthoritative build/verification inputs. Unit 2 limits measured SCM, ACL, management, and PKI use to the new upgrade authority. The one measured `takeown.exe` invocation occurred at commit `22ce0e7`, was nonrecursive and restricted to the exact public certificate file, and is preserved as nonauthority recovery evidence; the current resume may only validate that result. Terminal-service mutation is prohibited. Python and runtime Git are prohibited.

The Unit 2 authority has one signing operation: construction of the fixed `AUTHORIZE_TERMINAL_TRANSITION` envelope. Provisioning attestation signing is bootstrap evidence, not terminal-transition authority. No generic signing, arbitrary hash signing, terminal receipt, reconciliation, install, activation, or revocation IPC operation is exposed. The service captures and enforces its effective SID, groups, and one-privilege token before opening its key.

The existing terminal ACLs are not changed and do not grant the upgrade SID direct read access to the terminal binary or policy. Unit 2 therefore binds the exact elevated preflight capture and marks direct current-state remeasurement as mandatory when a later installer attempts consumption. This protects the existing terminal boundary but means Unit 2 authorization is not, by itself, proof that future current state remains unchanged.

## Pre-provision Unit 2 source assurance

Before host provisioning, this source boundary establishes source/package identities, exact script/utility/source routing, fixed compiler/reference/options, successful compile probes, offline strict-parser behavior, disposable transaction/recovery behavior, static retained-history classification, and the bounded Unit 2 implementation. Exact postcommit builds, installed identities, live pipe/key/principal/ledger proof, stopped-service verification, and restart continuity must still occur before the Unit 2 evidence commit.

Bootstrap failure is not authority. The preserved exit-1639 attempt stopped before service/key/certificate creation; the preserved CNG-compatibility attempt left only a stopped restricted service entry and created no certificate or key file. A third attempt used CNG `KeySpec None` and created one nonexportable key and public certificate but failed before bootstrap completion when the public certificate file acquired an empty protected DACL. A fourth attempt restored that public ACL and replaced the key-file Administrator grant with metadata-only rights, then failed on a redundant owner reassertion while SYSTEM ownership remained intact. No attempt installed a binary, policy, ledger, or authorization or started the service. The corrected bootstrap requires and propagates all four exact failed-attempt identities, verifies the stopped post-recovery state without reading private bytes, and performs no further ACL mutation. None of the interruptions can be omitted or reinterpreted as provisioning success.

It does **not** establish that any proposed service, principal, LSA right, ACL, key, trust file, policy, ledger transition, runtime module hold, pipe caller check, hostile path denial, upgrade authorization, historical classification append, matrix graph, service-stop behavior, or restart behavior exists on the live host. All `R7AR-B01` through `R7AR-B16` findings therefore remain partial.

## Trusted computing base and exclusions

The future design depends on measured Windows kernel/SCM/LSA, NTFS handle and durability semantics, CNG/RSA-PSS/SHA-256, CLR/.NET framework/native modules, and exact public trust. Byte changes in manifested components are intended to be detected, but compromise without detectable identity change is outside the claim.

Explicit exclusions are kernel compromise, offline/elevated administrator control, physical attack, firmware/hardware compromise, compromised cryptographic primitives without detectable byte change, and TPM/HSM/remote-signer protection. Administrator take-ownership ability is not misrepresented as cryptographic isolation. No production, trading, deployment, acceptance, or canonical claim follows from this package.
