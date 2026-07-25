# Independent matrix and public-only verification review

## New review matrix

No new eight-run/four-reconciliation matrix was executed. Each terminal run and reconciliation durably appends to the live authority ledger and creates persistent authority evidence. This acceptance prompt explicitly authorized only read-only inspection and nonpersistent, non-destructive requests; it did not pre-authorize those persistent writes. A service stop/restart was also not authorized. No authored matrix result was converted into an independent PASS.

This missing matrix does not make the review indeterminate because independently proved blockers already require rejection. It remains an unverified mandatory condition that must be rerun after separate remediation and authorization.

## Existing authored matrix evidence

The retained chain shows the claimed final matrix region at sequences 612–675 and contains eight final terminal commits plus four reconciliation commits. The final candidate/fresh/reconciliation locators are distinct and their signatures and ledger membership are cryptographically valid. This is implementation-authored historical evidence only; the review did not treat it as a new independent matrix or semantic proof of all 178 cases.

## Public-only checks

Using only the installed public certificate and public verifier, with the service left running but not consulted for private authority:

- terminal `01d3f127509ae36579b2356ef452c9ada8b42a62f10ccebc2bfe550666d1c563`: VERIFIED;
- terminal `d935400395d5710ef296dcb0d1aeea5dc4654f0bbf696c062cb833b245164832`: VERIFIED;
- reconciliation `3bb2ef071095be927e5480d4b916478c70696244c97c64fff892d679d3b6778c`: VERIFIED;
- independent ledger/checkpoint verification: 678/678 valid using `independent_ledger_verifier.cs`.

The service-stopped public-verification test was not run because stopping/restarting the dedicated service requires fresh authorization. The verification paths above read files directly and need no private key, but process-independent behavior after an actual stop remains authorization-limited.

## Historical public-verification incompatibility

The installed verifier's read-only `verify-all` failed with `InvalidDataException: terminal fixed authority rejected`. The oldest retained terminal receipt `8a06b2c2e851cc45f13ee9a618b6f34b1064945b63905c616cb6fd1893be6418` reproduces the same failure individually, while the final v3 pair verifies. The current verifier hard-binds current service/policy/binary authority and cannot verify all retained receipts across the preserved upgrade history.

This violates durable post-exit public verification and demonstrates the missing governed upgrade/version-verifier lifecycle. Ledger continuity without a version-aware public verification chain is insufficient.
