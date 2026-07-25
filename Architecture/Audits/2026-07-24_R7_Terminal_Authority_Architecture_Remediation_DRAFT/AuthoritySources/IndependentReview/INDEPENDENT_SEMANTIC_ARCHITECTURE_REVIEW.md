# Independent execution, comparator, terminal-verifier and reconciliation review

## Real-execution claim

The implementation launches measured processes and stores real request/response bytes. That fact does not establish governed semantic execution. For every one of the 178 cases, the outer request is only `{"case_id":"...","operation":"execute_case"}`. The f0 subject looks up the case, expected output and mutation internally and calls test-only case handlers. All callers are trusted same-SID service children and all 158 negative cases are marked meta-verification. A fixture exercising an internally selected simulation stands in for the hostile external interface required by R6/R7.

The service copies child-reported `outcome`, `inner_event.event_hash` and `execution_receipt.receipt_identity` into current rows. It supplies the case definition's public-interface label and derives outer ledger snapshots around the exchange. It does not independently resolve the inner execution receipt signature/body/token/subject-ledger membership. The later event builder hardcodes `interface_invoked=true`; observations copy event fields. The evidence therefore proves that a measured child returned bytes, not that the claimed governed operation and side effects occurred.

## Comparator independence

Separation into a worker executable is not substantive independence:

- the same builder consumes discarded f0 cases and expected outputs to create both final cases and expectations;
- the subject recorder receives expected status/code/evidence and will not record a differing result;
- the observer copies event status/classification/authority;
- the comparator compares those values against the same expectation source;
- declared required/forbidden side effects and evidence obligations are not consumed;
- no independent raw-evidence semantic oracle exists for the 178 case handlers.

An internally consistent false graph can therefore be built by the measured same-SID child. Because that child also has signing-key and ledger/store authority, process measurement cannot contain the attack.

## Terminal verifier

The service does verify many structural relationships: content locators, outer request/response hashes, case cardinality, current run IDs, event hash chain, process index, comparator locator, terminal receipt signature and ledger membership. The blocking gap is semantic derivation. It accepts child status/code/function/authority plus arbitrary 64-hex inner identities so long as they match expectation-conditioned data. It never establishes that the inner interface action produced those values, independently proves the claimed process token from the target process, or semantically checks the case artifact's required/forbidden effects.

Consequently a measured hostile child below the service can fabricate a complete graph the service accepts. The exact same principal can also bypass the service and sign/mutate stores directly. The service is neither a semantic oracle nor an isolated terminal authority.

## Reconciliation

The reconciler resolves two signed terminal locators and compares substantial graph fields. However, both terminal graphs can originate from the same expectation-conditioned synthetic class. Candidate/fresh receipts can therefore be distinct in run IDs, nonces, process IDs and event roots yet share the same invalid proof method. Reconciliation proves structural equality/disjoint identifiers over service-accepted graphs; it does not independently establish the correctness of each governed case from raw side effects. Two semantically invalid graphs can reconcile.

## IPC parser

The service reads through the first LF, deserializes with `JavaScriptSerializer`, and enforces only the collapsed top-level dictionary. It does not reject duplicate keys before parsing. `RequireLong` uses `Convert.ToInt64`, accepting numeric strings. Runtime does not load the committed JSON schemas for requests/evidence, and nested unknown-field/key-set semantics are inconsistent.

The independent live probe sent one object containing duplicate `operation` keys: first `UNKNOWN_OPERATION`, last `GET_HEALTH`. The service accepted the collapsed last value and returned `COMPLETE`; checkpoint identity remained unchanged. Local reproduction showed duplicate `{"a":1,"a":2}` collapses to one key/value 2 and numeric string `"1"` coerces to integer 1. This is a confirmed canonical/parser bypass, not a theoretical concern.

## Conclusion

The required chain from immutable case through independent expectation, hostile public execution, raw current evidence, independent observation/comparison and full service semantic proof is not present. Measured execution, valid signatures and a consistent graph do not rescue this architecture.
