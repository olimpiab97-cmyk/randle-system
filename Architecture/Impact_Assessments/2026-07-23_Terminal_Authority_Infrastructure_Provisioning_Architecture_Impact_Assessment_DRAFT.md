# Terminal Authority Infrastructure Provisioning — Architecture Impact Assessment (Draft)

Date: 2026-07-23
Repository base: `87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94`
Scope: host authority infrastructure and public governance evidence only

## Decision summary

The host now has a separately executed provisioning authority boundary suitable for consumption by a later, separately governed R7 continuation. The boundary is a compiled Windows service running as the restricted virtual service account `NT SERVICE\RandleTerminalAuthority`. It owns access to a LocalMachine Microsoft Software KSP RSA-3072 nonexportable key, a fixed authenticated named-pipe protocol, and a fixed signed append-only ledger.

This assessment does not claim that the R7 terminal supervisor, terminal receipt workflow, or immutable candidate/fresh reconciliation has been implemented. It establishes only the prerequisite host facilities and their public trust evidence.

## Governing drivers

The R7 incomplete record (`06c6805e...`) showed that a caller-replaceable Python client could replay a complete successful result and that dictionary reconciliation could self-authorize `MATCHED`. The blocked continuation (`8ec5697b...`) established that no TPM, usable signing certificate, configured signer, separate supervisor service, HSM/remote signer, or fixed authenticated ledger then existed.

The root architectural defect was the absence of an authority outside the hostile caller's Python object graph and caller-owned storage roots.

## New external authority role

The draft architecture adds `TERMINAL_AUTHORITY_INFRASTRUCTURE` as a host role. Its current interface is intentionally restricted to health, public-trust retrieval, ledger status, one-time provisioning-nonce issuance, provisioning-attestation issuance, and an authorization self-test. It is not a generic signer and is not yet the complete R7 terminal supervisor.

The service is bound to:

- fixed executable path and measured binary identity;
- restricted service SID and non-administrator service token;
- fixed policy, state, trust, and ledger paths;
- exact certificate/public-key identity;
- explicit named-pipe ACL and request schema;
- closed provisioning operation allowlist;
- fixed ledger identity and signed checkpoint chain.

## Principal and privilege impact

The virtual service account has no reusable password and failed interactive logon. The service runs as an own-process, demand-start Windows service with only `SeChangeNotifyPrivilege` and `SeImpersonatePrivilege`; impersonation is used to authenticate the named-pipe client SID. The service SID type is `RESTRICTED`, which prevents inherited `Authenticated Users` repository permissions from becoming service authority. The running service reports `is_administrator=false` and `repository_write_access=false`.

## Key lifecycle impact

The signing key is LocalMachine scoped, RSA-3072, nonexportable, and backed by Microsoft Software Key Storage Provider. Its key-file ACL grants full access to SYSTEM and read/use access only to the restricted service SID. The filtered interactive user could export the public certificate but could not open the key container, read the key file, sign directly, or export private key material.

The public trust root is a pinned self-signed certificate, not an enterprise code-signing PKI assertion. Rotation, revocation, expiry, backup/recovery, and service re-provisioning require future governed procedures before the key validity interval ends. No private key, PFX, shared secret, seed, or credential is present in Git.

## IPC lifecycle impact

The fixed pipe `RandleAI.TerminalAuthority.v1` has explicit SID ACLs, a 65,536-byte request bound, strict canonical JSON requests, a closed operation set, and request-nonce replay rejection. The operator may request only predefined provisioning actions; the caller cannot submit a signature payload, ledger root, receipt status, or arbitrary signing operation.

The later R7 continuation must define a new terminal-supervisor protocol version and schemas. It must not broaden the provisioning interface into an arbitrary signing oracle.

## Ledger lifecycle impact

The ledger root is fixed at `C:\ProgramData\RandleAI\TerminalAuthority\Ledger`. Only SYSTEM and the service principal have write authority; the interactive user has read-only evidence access. Entries are canonical, signed, sequential, prior-hash bound, write-through flushed, and paired with a signed checkpoint. The final provisioning chain is sequence 5 with root `9ee913cf...97e6a` and checkpoint identity `f3eeee9f...4eb8`.

Rollback resistance is defined against the filtered interactive-user threat: that caller cannot replace, delete, append, or truncate fixed-root state, and caller-owned alternate or copied roots reject. Deliberate elevated-administrator or offline rollback is outside the accepted local-software-key threat model and must not be represented as resisted.

## Service lifecycle impact

The service implementation, configuration, binary, service SID, policy, and public trust are measured in a signed attestation. Public verification succeeded while the issuer was stopped and from a fresh process using only public trust bytes. Restart loaded the existing chain and continued monotonically from sequence 4 to sequence 5.

Operational monitoring, automatic startup policy, disaster recovery, key rotation, revocation, and service upgrades remain future governed work. The installed service is infrastructure, not a production trading service, and its restart did not restart or change any production process.

## Evidence and traceability impact

The provisioning audit package carries:

- source and source-to-binary measurements;
- pinned public certificate bytes and identities;
- signed attestation and public ledger snapshot;
- principal, ACL, service, IPC, key, and ledger evidence;
- 43 direct positive/negative probe results;
- closed Draft 2020-12 schemas for core authority artifacts;
- bidirectional traceability to the R7 blocker requirements.

The separately installed public-only verifier remains the decisive host signature/ledger verifier. The repository verifier checks that committed canonical receipt content reconstructs the exact host receipt identities and contains no secret material.

## Threat-model boundary

The implemented boundary resists hostile user-mode code under the normal filtered `Trader` token, including Python-object replacement, direct key use, direct ledger writes, caller-owned roots, replay, restart, and ordinary concurrency.

The interactive account is a member of local Administrators, but its ordinary token is filtered. Deliberate UAC elevation, hostile local-administrator takeover, kernel compromise, and offline disk/registry takeover are explicitly outside scope. Because the host has no TPM, HSM, or remote signer, this boundary is mandatory and must remain prominent in all downstream authorization.

## Future R7 integration obligations

A new R7 continuation must branch directly from R6 and consume the incomplete record, blocker record, and final provisioning-evidence commit. It must extend the external service through a separately reviewed terminal protocol that signs immutable terminal and reconciliation receipts, ledger-binds every acceptance, resolves child evidence, rejects Python dictionaries and replay, and undergoes independent review.

The continuation must also prove that the private authority remains unavailable, all R7 service controls are terminally mandatory, and candidate/fresh reconciliation is performed by the external boundary rather than Python convenience logic.

## Canonical impact

No canonical document is changed by this draft. Future accepted incorporation would need to update the architecture authority model, recovery governance, key/service/ledger lifecycle, evidence resolution, trust rotation/revocation, and R7 terminal verification specifications. Those changes remain proposed and withheld.

## Authorization boundary

This assessment supports only consideration of a new governed R7 continuation. It does not authorize R7 acceptance, operational capture work, a production baseline capture, merge, canonical incorporation, production implementation, deployment, production restart, runtime migration, NQ cutover, trading, Phase 3C2, Phase 3C1-R11 acceptance, Bucket 0 completion, or Bucket 1 work.
