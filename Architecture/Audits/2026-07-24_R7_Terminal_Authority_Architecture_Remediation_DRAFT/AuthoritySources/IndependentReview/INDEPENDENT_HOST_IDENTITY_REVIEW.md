# Independent host identity and attack-surface review

All host checks were read-only. The dedicated service remained running throughout.

## Current identity

- service: `RandleTerminalAuthority`, Running, Manual, PID 21308, account `NT SERVICE\RandleTerminalAuthority`;
- restricted SID: `S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948`;
- service image: 123,392 bytes, SHA-256 `9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526`;
- worker: 79,360 bytes, SHA-256 `b2971b85de73d999bfa801d047b22c2ec6fc3d6bc5cb5923ea4a9ab240ed4401`;
- policy: 4,297 bytes, SHA-256 `76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b`;
- interface: `3.0.0-DRAFT`; pipe frame limit: 65,536 bytes;
- trust certificate: 1,073 bytes, SHA-256 `b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285`, thumbprint `21961cfc1b10824e539172fd04efa83ad2be9203`;
- key: LocalMachine CNG RSA-3072, export policy None, unique name `1c9681c0b04a3dd4843d8cb457b92413_c5338977-c52f-4ca7-af6f-db9b5e287cca`;
- ledger: fixed identity `899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52`, sequence 678, root `87fdc1bb...`.

Filtered interactive-user ACLs are read-only on public/config/evidence/ledger/trust; Responses and Sessions are not user-readable. An ordinary caller could not open the CNG key. The key is nonexportable. These are positive user-isolation facts.

## Blocking principal-isolation failure

Service source launches the subject launcher and worker with the default caller token and explicitly requires `CREATEPROCESS_DEFAULT_CALLER_TOKEN` plus the exact service SID. The launcher then starts Python the same way. A retained live process receipt corroborates that inheritance.

That SID can use/read the CNG key and has Modify authority over Evidence, Ledger, Receipts, Reconciliations and Trust. The key name is public. Consequently a hostile measured launcher, Python subject, worker, comparator or fixture has the same signing and durable-store authority as the supposed terminal service. Nonexportability prevents export, not signing by a same-principal process. The service is not the sole terminal authority under the prompt's hostile-child hypothesis.

## Inventory and path surface

- Program Files root: 3,220 files / 78,492,790 bytes;
- ProgramData root: 11,251 files / 389,659,649 bytes;
- total: 14,471 files / 468,152,439 bytes;
- canonical inventory identity: `dc03b7ec598bb9278a1bb677d3d452939cc32ba148d744ed71ce50e3b2c3cb87`;
- inventory JSON SHA-256: `fa113667da1633e5af64de6022c99a66952493a19785970adbdbc88633e338a3` at `C:\Users\Trader\AppData\Local\Temp\r7_independent_acceptance_review_20260723_preflight\authority_host_inventory.json`.

Across 3,228 critical binary/pinned/trust/checkpoint paths: zero multi-hardlinks, alternate data streams or reparse points. Across both full roots: zero alternate streams and exactly one reparse point—the retained seq-332 test junction under `Evidence\R7ExecutionSubjectTemp\randle-r7-authority-session-31u0gxpw\...\reparse-parent`. C: has 8.3 name creation enabled and critical paths have short aliases.

`ReadPinnedBytes` and `ReadContentAddressed` perform lexical `Path.GetFullPath` prefix checks followed by path-based read/hash. They do not prove final NT path, reject reparse tags/link count/ADS/short aliases, hold immutable file handles, or close rename/read-after-hash races. Current critical files are clean, but the same-SID hostile children can mutate evidence roots, so the design does not enforce the required filesystem property.

The Trust directory retains five stale clients/verifiers/probes plus diagnostic/fault files. Current service source does not load those executables, but verifier/version selection and provenance are not fully governed. The one old-v1 client test correctly returned `INTERFACE_VERSION_REJECTED` and did not alter the checkpoint.
