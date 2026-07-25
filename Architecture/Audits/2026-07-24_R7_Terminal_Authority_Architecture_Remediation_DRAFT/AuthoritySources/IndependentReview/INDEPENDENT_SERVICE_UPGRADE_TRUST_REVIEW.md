# Independent service-upgrade and trust-authority review

The signed provisioning attestation SHA-256 `63494d8840af241b7916e8ef75e5eae350ea31d8bafbcd0dc1a790f8945e7697` binds:

- service binary `632afaeeaf15c26ac057b34692ac672e03bc02f60fbb35177c378736b5e316ba`;
- policy `675a9fa9c761b2738e6b7115366eaf8bb001f6f9ff1f3fb598db2f68ad57fc19`;
- interface `1.0.0`;
- original IPC identity beginning `2acddd...`.

The reviewed live authority is service `9ea829...`, policy `76eb2900...`, interface `3.0.0-DRAFT`, updated IPC identity beginning `3a2c...`, plus new worker/launcher/Python/fixture dependencies. No governing R6/R7 object or separate signed host-upgrade receipt authorizes that transition. Provisioning explicitly left upgrade governance as future work.

At startup, the new service opens the preserved key and appends `R7_SERVICE_UPGRADE_ACTIVATED` if it has not seen its own computed subject. This is circular self-authorization. The ledger's 11 upgrade entries have valid signatures but unresolved child content. The constant for the v1 provisioning-attestation identity is not used to validate an authorized transition.

The preserved key provides cryptographic continuity only. It does not bind the authority role of a replacement binary/policy/interface, prevent downgrade, identify a current canonical version, revoke older clients, constrain operation classes, or establish why a DRAFT interface may issue acceptance authority. The old v1 client was correctly rejected by the current service, but that one direction does not establish downgrade/upgrade lifecycle control.

This failure is independently blocking even if all functional tests were otherwise correct. Required remediation is a separately governed, signed, durable and publicly resolvable upgrade transition binding old/new service, policy, interface, IPC, workers, dependencies, trust/key/ledger, authorization window and anti-rollback state. It must be verified before the new binary can use terminal authority; self-signing after installation is insufficient.
