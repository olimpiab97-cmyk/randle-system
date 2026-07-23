# R6 remediation coverage

Immutable review authority: commit `7dfe3c1ba61db800d4cfb27cf68b631abb3cf472`, record blob `3f6eaa5e3e93013a08c5c03a79d00fee20de2ddb`, Sections 30-34.

| R5 rejection area | R6 clauses | Enforcing surface | Bound evidence |
|---|---|---|---|
| Computed access and forged module origin | CPB-R6-01 | `enforce_access` and runtime audit-hook probes | access-origin authority, static and runtime receipts |
| Replaceable parser/comparator launch | CPB-R6-02, CPB-R6-03 | measured external launcher and fresh-run issuer | process/run receipts with unique nonces |
| Replayed or caller-authored events | CPB-R6-04 through CPB-R6-06, CPB-R6-13 | external recorder worker and observation derivation | finalized current-run event chain |
| Mutable post-validation authority | CPB-R6-07, CPB-R6-09, CPB-R6-10 | immutable reparse/deep-freeze boundary | Git-object bindings and resolved issuance/evidence bytes |
| Incomplete or stale trace semantics | CPB-R6-08 | `validate_trace` | current-run event and observation identities |
| Unenforced validator environment | CPB-R6-11 | `verify_validator_environment` | installed-distribution and FormatChecker receipt |
| Unused mandatory-test registry | CPB-R6-12 | `verify_mandatory_five_tests` | registry, physical inventory, and content receipt |
| Unsupported architecture claims | CPB-R6-14, CPB-R6-15 | `validate_documents` | claim vocabulary and current evidence map |

The package remains draft. This mapping grants no operational, capture, merge, deployment, or trading authority.
