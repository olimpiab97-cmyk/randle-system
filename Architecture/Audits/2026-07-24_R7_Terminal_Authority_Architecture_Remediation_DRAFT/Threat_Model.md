# Threat model and assurance boundary

## Intended protected boundary

The proposed boundary covers exact governing bytes; independent cases and expectations; canonical framed IPC; five distinct service identities; held executable/policy/authority/dependency handles; separate terminal and upgrade keys/trust/ledgers; append-only transaction/recovery state; content-addressed raw evidence, receipts, responses, and reconciliation; and version-aware offline public verification.

The attacker model treats execution, observation, comparator, fixtures, request builders, and every child-emitted field as hostile. It also includes malformed/ambiguous frames; invalid callers; replay and conflicting retry; signer impersonation; path reparse/link/ADS/alias/case/race/substitution; build/runtime path and DLL/import substitution; self-authorized upgrade/downgrade/replay; response loss; partial writes; stale/partial checkpoints; process restart; inconsistent historical evidence; and two matching but invalid graphs.

## Proposed OS and semantic controls

Terminal signer, execution, observation, comparator, and upgrade authority use distinct restricted virtual-service SIDs. The installation design applies `SeDenyInteractiveLogonRight` and `SeDenyRemoteInteractiveLogonRight`, a `SeChangeNotifyPrivilege` allowlist, narrow pipe ACLs/operations, and disjoint filesystem/key rights. The signer does not spawn semantic children and must derive disposition from OS-captured caller/process/token/frame/file/ledger/effect facts.

The protocol accepts only one complete canonical NFC UTF-8 JSON payload in an exact frame. Expected semantics are inaccessible to execution and observation under the proposed ACLs. Recovery-producer results are not trusted: the auditor reopens canonical evidence and independently derives the public result code from signed ledger/transaction state.

Fixed files and external utilities are intended to be opened no-follow, measured by canonical handle identity, and held through use. Static package construction uses absolute utility paths and records recursive closure before and after compilation. Git and PowerShell remain measured nonauthoritative build/verification inputs; service-control, ACL, filesystem, job, and PKI tools are future transition/matrix inputs only. Python and runtime Git are prohibited.

## Static-unit assurance actually established

This unit can establish only source/package identities, exact script/utility/source routing, fixed compiler/reference/options, successful two-pass compilation, normalized-IL equality, offline strict-parser behavior, disposable temporary transaction/recovery behavior, static retained-history classification, trace completeness, and secret/contamination scan results. The compiled binaries and generated identities are explicitly uninstalled and nonauthoritative.

It does **not** establish that any proposed service, principal, LSA right, ACL, key, trust file, policy, ledger transition, runtime module hold, pipe caller check, hostile path denial, upgrade authorization, historical classification append, matrix graph, service-stop behavior, or restart behavior exists on the live host. All `R7AR-B01` through `R7AR-B16` findings therefore remain partial.

## Trusted computing base and exclusions

The future design depends on measured Windows kernel/SCM/LSA, NTFS handle and durability semantics, CNG/RSA-PSS/SHA-256, CLR/.NET framework/native modules, and exact public trust. Byte changes in manifested components are intended to be detected, but compromise without detectable identity change is outside the claim.

Explicit exclusions are kernel compromise, offline/elevated administrator control, physical attack, firmware/hardware compromise, compromised cryptographic primitives without detectable byte change, and TPM/HSM/remote-signer protection. Administrator take-ownership ability is not misrepresented as cryptographic isolation. No production, trading, deployment, acceptance, or canonical claim follows from this package.
