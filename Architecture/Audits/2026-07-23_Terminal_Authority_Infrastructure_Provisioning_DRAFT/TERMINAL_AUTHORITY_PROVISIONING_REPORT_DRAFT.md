# Terminal-Authority Infrastructure Provisioning Report (Draft)

Date: 2026-07-23
Architecture base: `87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94`
Disposition: **PROVISIONED — READY FOR R7 CONTINUATION**

## 1. Primary disposition

The external authority prerequisites are provisioned and independently verifiable within the declared threat model. A restricted Windows virtual service account, compiled service process, nonexportable LocalMachine asymmetric key, authenticated named pipe, fixed signed ledger, public trust root, signed provisioning attestation, offline verifier, and public evidence package now exist.

## 2. Executive summary

The terminal replay blocker was caused by the absence of any authority outside caller-controlled Python objects and caller-owned storage. This task created a separate OS service boundary and proved that the normal filtered interactive caller cannot sign directly, export or open the private key, write the service binary or configuration, append or replace the ledger, select an alternate accepted ledger, or obtain arbitrary signatures. Public verification succeeds after the issuing service exits.

This is infrastructure provisioning only. The service does not implement R7 terminal receipt or candidate/fresh reconciliation semantics, and this report does not accept R7.

## 3. Threat model and administrative boundary

Resisted threats include hostile Python or native user-mode code under the normal filtered `FALCONXTREME\Trader` token; replacement of clients, classes, callbacks, functions, code objects, globals, modules, mappings, caches, and worktrees; caller-selected roots; replay; direct normal-user key/ledger/file access; service restart; and ordinary concurrency.

`Trader` is a member of local Administrators, but the ordinary token is filtered and reported non-administrator. Deliberate UAC elevation, hostile local-administrator takeover, kernel compromise, and offline privileged disk/registry takeover are excluded. The host has no TPM, HSM, or remote signer. A local software-KSP service is accepted only within this boundary and must not be described as resisting an elevated administrator.

## 4. Preflight and active-root preservation

R6, both blocker records, Git locks, writer processes, protected-ref ancestry, and active-root stability were checked before writing. The 10-second recursive writer watch observed zero writes. There were no Git locks and no prohibited governed-commit ancestry into the four protected refs across 64 tests.

The two active-root porcelain-v2 status reads were byte-identical on stdout and stderr. Stdout was 84,230 bytes, 1,022 NUL records, SHA-256 `45dab4e1b8e26a0cd5941e4d0a50aabeeeedde5996e7e5e6a8e854b1d7794b2c`. Stderr was 6,358 bytes, 60 preserved warnings, SHA-256 `6785fe51ed5b0258744cfe310a7a87ad4da103b9a4c15596bdcdb96d309f0ddb`. The active root remained branch `laptop_saved_work`, HEAD `e84774e8b3681ae0aeb8390390dafea8a4b8cfd4`, and was never used as the provisioning worktree.

## 5. Immutable R6 and blocker-authority verification

R6 was independently verified as commit `87d066eb...`, parent `c211870a...`, tree `f9891562...`, subject `docs(recovery): bind fresh execution and boundary authorities`, exactly 65 paths, all modes 100644, and 72 authority roles with zero role/blob mismatch.

The R7 incomplete record was read from commit `06c6805e...`, exact blob `1be3b0b5...`. The blocked continuation was read from commit `8ec5697b...`, exact blob `dfa98a89...`. Each commit had exactly one report-only delta. Neither is an implementation ancestor.

## 6. Selected authority mechanism and rejected alternatives

Selected: a compiled .NET Windows service, restricted virtual service account, LocalMachine Microsoft Software KSP RSA-3072 nonexportable key, pinned self-signed public certificate, authenticated named pipe, and fixed signed NTFS ledger.

Rejected as insufficient: same-user Python authority, cloned Python code objects, HMAC/shared secrets, password-protected key files, CurrentUser keys, repository-contained private material, caller-owned ledger roots, and generic `Sign(bytes)` endpoints. TPM/HSM/remote signing was preferred but unavailable.

## 7. Service principal identity and privileges

Service: `RandleTerminalAuthority`; display name: `Randle AI Terminal Authority`; account: `NT SERVICE\RandleTerminalAuthority`; SID: `S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948`; SID type: `RESTRICTED`; own-process, demand-start.

Required privileges are only `SeChangeNotifyPrivilege` and `SeImpersonatePrivilege`; the latter supports named-pipe client impersonation. Interactive logon failed. The running token is non-administrator and cannot create in `C:\Webhook\RandleSystem`.

## 8. Service installation and measured binary identity

Installed path: `C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthority.exe`. SHA-256: `632afaeeaf15c26ac057b34692ac672e03bc02f60fbb35177c378736b5e316ba`; size: 40,960; NTFS file identity: `70093b3e:001a0000000b3058`. The final service process started at `2026-07-23T14:17:25.6506137Z` and was running at final evidence capture.

The source-to-binary receipt binds four public C# source blobs, Framework64 C# compiler `4.8.4161.0` SHA-256 `adeda78a...af1`, the installed service, narrow client, and public-only verifier. A fresh x64 rebuild using the original `.restricted.exe` assembly names matched all three installed sizes. Normalized IL was byte-identical for service (`ea726ba0...66a1`, 5,190 lines), client (`430360bb...1c29`, 1,627 lines), and verifier (`74804a7a...108b`, 2,742 lines) after excluding only compiler-generated MVID/load-address/output-path fields and the MVID-derived private-implementation type suffix.

## 9. Private-key provisioning and nonexportability

The final key is RSA-3072 in Microsoft Software Key Storage Provider, machine scoped, signing-only, and nonexportable. Container unique name: `1c9681c0b04a3dd4843d8cb457b92413_c5338977-c52f-4ca7-af6f-db9b5e287cca`. Its file is SYSTEM-owned and grants full access only to SYSTEM and read/use only to the service SID.

An initial certificate candidate was future-dated relative to host time and was discarded before acceptance. Thumbprint `069bf59b...f789`, DER identity `b69514...`, and key unique name beginning `96eaa26...` were removed after exact verification. No private export occurred. The final chain was then regenerated and all evidence repeated.

## 10. Public trust identity

Certificate thumbprint: `21961cfc1b10824e539172fd04efa83ad2be9203`; DER/public-key identity: `b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285`; subject/issuer: `CN=Randle AI Terminal Authority Infrastructure v1`; serial: `20488acb14b0028646e123aaf19fd603`; validity: `2026-07-23T13:53:26Z` through `2028-07-23T13:58:26Z`; digital-signature use.

The repository contains DER public bytes only. It contains no private certificate or secret.

## 11. Private-key ACL and caller-isolation results

The key-file SDDL identity is `2d117c23...5e4d`. Public export succeeded. Normal-user private export, direct signing, key-container open, and key-file read failed. Service-authorized attestation signing succeeded. The service source opens only the fixed key unique name; callers cannot choose a key.

## 12. IPC identity and authentication

Pipe: `RandleAI.TerminalAuthority.v1`; protocol `1.0.0`; maximum request 65,536 bytes; pipe ACL identity `51343f0d...ae07`; derived IPC identity `2acddda4...5ba2`. The pipe ACL and impersonated client SID authorize only SYSTEM, the service, and the provisioning operator SID.

Allowed operations are limited to health, ledger status, public trust, one-time provisioning nonce, provisioning attestation, and an authorization self-test. Malformed, unknown, replayed, oversized, caller-payload, caller-ledger-root, and unauthorized-SID requests rejected.

## 13. Fixed durable-ledger identity

Root: `C:\ProgramData\RandleAI\TerminalAuthority\Ledger`; ledger ID `899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52`; fixed by policy and code. The caller cannot pass a root to the service or verifier.

## 14. Ledger ACL and caller-isolation results

The root is SYSTEM-owned. SYSTEM and Administrators have full control, the restricted service SID has service write authority, and `Trader` has read-only evidence access. Normal-user requests for directory add, entry write/append, entry delete, and truncation-capable handles all returned Win32 access denied. This is bounded to the filtered-user threat model; elevated-administrator rollback is out of scope.

## 15. Ledger genesis and checkpoint results

Genesis entry hash: `666e54345c43a8b5d83391f9d37c34537f4291a7839c068aa4734fcb810a91e5`. Final sequence: 5. Final root: `9ee913cfea86b71739b894308bbe48c154c4f6abbf4e949cc2f2172aedb97e6a`. Final checkpoint identity: `f3eeee9f6563428660bb1a3b793e0000cd7207f1059e0095c1ae8140a4994eb8`. All five entry signatures, prior hashes, entry hashes, authority identities, and checkpoint signature verified.

## 16. Signed provisioning-attestation identity

Canonical attestation identity: `63494d8840af241b7916e8ef75e5eae350ea31d8bafbcd0dc1a790f8945e7697`; signature identity: `7199c1790196a0d051663db647a5d8be8a23d3c9af504b349c28978bd84a198b`; RSA-PSS-SHA256. It binds R6, both blocker commits, service/binary/SID/configuration, public key, fixed paths, ACL identities, IPC, ledger genesis/checkpoint, threat model, and a one-time provisioning nonce. Ledger sequence 3 resolves its exact content address.

## 17. Verification after service shutdown

The service was stopped. A fresh public-only verifier process validated the signed attestation and ledger using exported DER bytes only. An elevated public-only `verify-all` also validated actual SCM configuration, executable hash/file identity, policy, trust, ledger, and attestation while the issuer was stopped. The service then restarted, loaded sequence 4, and continued at sequence 5.

## 18. Principal-isolation probes

Six principal probes passed: interactive service-account logon rejected; service token non-admin; repository write absent; normal binary/config/trust writes denied; and service configuration change denied. Exact results are in `negative_probe_results_DRAFT.json` P01–P06.

## 19. Key-isolation probes

Eleven key probes passed: public export, private-export rejection, direct-sign rejection, key-handle rejection, authorized service signing, offline verification, changed/untrusted public-key rejection, payload-signature rejection, nonce replay rejection, and arbitrary-signing rejection. See K01–K11.

## 20. Service-integrity probes

Seven service probes passed. The installed binary/configuration/SID/path matched signed evidence. Altered signed identities rejected. A copied executable outside the SCM path could not use the key or append the ledger and produced no signature. See S01–S07.

## 21. IPC-integrity probes

Eight IPC probes passed. Unauthorized SID, malformed request, unknown operation, nonce replay, oversized input, caller-selected signature payload, and caller-selected ledger root rejected. Valid authenticated health succeeded. See I01–I08.

## 22. Ledger-integrity probes

Eleven ledger probes passed. Public read worked; direct append/modify/delete/truncate access failed; alternate and copied roots rejected; rollback through caller-owned state rejected; altered checkpoint failed signature; restart preserved sequence; and concurrent duplicate nonce submission produced one accepted append and one replay rejection. See L01–L11.

## 23. Secret-scanning results

The package verifier scanned the complete evidence directory for private-key headers, secret-bearing file suffixes, password/credential assignments, HMAC/shared secrets, signing seeds, and access tokens. Findings: zero. Public certificate bytes, consumed nonces, certificate/container identifiers, signatures, and read-only evidence are intentionally public and do not confer signing authority.

## 24. Architecture Impact Assessment

The accompanying assessment introduces the external infrastructure role, principal/key/service/IPC/ledger lifecycle, public trust and threat boundary, and future R7 integration/recovery/revocation obligations. It explicitly distinguishes provisioned prerequisites from the unimplemented R7 terminal workflow.

## 25. Canonical Delta

The delta is draft-only. It identifies possible future canonical roles and lifecycle documents but performs no canonical incorporation. All canonical, operational, deployment, restart, migration, cutover, trading, phase, and bucket permissions remain withheld.

## 26. Bidirectional traceability

Eight forward requirements connect the original infrastructure blockers to the service principal, key, compiled service, IPC, ledger, attestation, negative probes, and governance boundary. Reverse mappings cover the same eight requirements. The package verifier requires forward/reverse set equality.

## 27. Every surviving discrepancy

None within the declared filtered-interactive-user threat model. The preliminary future-dated key and unrestricted service-SID chain were not accepted; both were superseded before final issuance.

## 28. Every blocking finding

None for infrastructure provisioning within the declared threat model. If hostile elevated local administrators or kernel compromise are added to scope, the lack of TPM/HSM/remote signing becomes blocking and this local software-key mechanism is insufficient.

## 29. Every nonblocking finding

1. The trust object is a governance-pinned self-signed certificate, not enterprise PKI.
2. Key rotation, revocation, disaster recovery, and service upgrade procedures remain future governed work.
3. The service is provisioning-only; R7 terminal and reconciliation interfaces remain unimplemented.
4. Fixed-root destructive rollback was not performed with elevated authority; filtered-user access checks denied mutation, copied/alternate roots rejected, and elevated rollback is outside scope.
5. A discarded preliminary unrestricted-SID public chain is retained under a clearly marked nonauthority directory for audit provenance; the final verifier rejects it and the service ignores it.

## 30. Exact host changes

Created the Windows service and restricted virtual-service SID; created fixed Program Files and ProgramData install/config/ledger/trust roots and ACLs; created the final nonexportable LocalMachine KSP key and public certificate; installed measured service/client/verifier binaries; wrote fixed policy; created final five-entry signed ledger/checkpoint and signed attestation; started/stopped/restarted the authority service for verification.

The initial future-dated certificate/key was removed. The initial unrestricted-SID service run was archived under `C:\ProgramData\RandleAI\TerminalAuthority\Discarded\unrestricted_preliminary_20260723` as nonauthority evidence, the service SID was changed to `RESTRICTED`, and a fresh final chain was issued.

No production service, production configuration, production source/test, runtime data, launcher, or deployment file was changed.

## 31. Exact repository paths changed

The final delta contains only this Architecture audit directory, its `durable_ledger_public_snapshot_DRAFT` child, and `Architecture/Impact_Assessments/2026-07-23_Terminal_Authority_Infrastructure_Provisioning_Architecture_Impact_Assessment_DRAFT.md`. The machine-generated final manifest enumerates every nonmanifest path, raw SHA-256, mode, and Git blob; the post-commit handoff reports the complete exact path set including the manifest.

## 32. Commit identity, parent, tree, and subject

The enclosing provenance commit is created only after the final package verifier, staged secret scan, and exact-path audit pass. Its required direct parent is R6 `87d066eb...`; subject is `docs(governance): provision terminal authority infrastructure`. The commit and tree identities are reported in the post-commit handoff because a Git commit cannot include its own cryptographic identity.

## 33. Incomplete/blocker ancestry status

The evidence branch is based directly on R6. Commits `06c6805e...` and `8ec5697b...` are immutable external authority and are not ancestors of the provisioning commit.

## 34. Final branch and worktree status

Branch: `governance/terminal-authority-infrastructure-provisioning-20260723`. The final post-commit audit must report one commit above R6, clean status, and unmerged status. The active production root remains untouched.

## 35. Exact next governed action

Consider a separately authorized R7 continuation branching directly from R6 that consumes both R7 records and this provisioning evidence, implements signed terminal receipts and immutable external reconciliation using the provisioned authority, and undergoes independent review.

## 36. Explicit authorization statement

This result authorizes only consideration of that new R7 continuation. It does not authorize R7 acceptance; operational capture-script or package work; a production baseline capture; merge; canonical incorporation; production implementation; deployment; production-service restart; runtime migration; NQ cutover; automated paper or live-money trading; Phase 3C2; Phase 3C1-R11 acceptance; Bucket 0 completion; or Bucket 1 work.

TERMINAL AUTHORITY INFRASTRUCTURE — PROVISIONED AND READY FOR R7 CONTINUATION
