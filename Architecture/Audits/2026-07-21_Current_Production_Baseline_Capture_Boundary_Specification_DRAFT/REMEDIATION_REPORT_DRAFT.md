# R4 remediation report - baseline capture remains withheld

## Scope and immutable authorities

R4 is a draft, provenance-only remediation directly above `f04105fdbffbad1fe58779a8ac3bb809a99ee2a5`. It consumes the R3 rejection at `119bff0e09cb49e70884d6ca038deab12c9fc739` as immutable external review authority and does not incorporate that review commit into its ancestry.

Preflight preserved the dirty active production root without modification. Its two command-scoped long-path status reads were byte-identical: stdout was 84,230 bytes, 1,022 records, SHA-256 `53db7b5c3820f743ea97746bd813871c02bf2f924a546426db186701fda6c764`; stderr was 6,358 bytes, 60 warnings, SHA-256 `6785fe51ed5b0258744cfe310a7a87ad4da103b9a4c15596bdcdb96d309f0ddb`. The branch was `laptop_saved_work`, HEAD was `e84774e8b3681ae0aeb8390390dafea8a4b8cfd4`, no Git lock was present, and a 10-second recursive watch observed zero writes.

## R4 correction surfaces

The candidate package provides machine-enforced surfaces for all R3 blocking findings:

- primary unnamed-stream authority resolution rejects ADS selectors and prohibited named streams, while package enumeration is centrally audited;
- SEPARATE_AND_BIND review requirements derive from immutable policy and prohibit self-review;
- family-specific Draft 2020-12 schemas are closed and canonical JSON rejects duplicate keys, floats, and non-NFC keys or values;
- timestamp issuer, role, capability, trust root, chronology, attempt, and cutoff are independently bound;
- historical parsing loads the authorized parser implementation from committed Git bytes and binds the actual historical log;
- observer authority binds the accepted freeze receipt, freeze authority, attempt, source window, implementation, and append-only event root;
- terminal comparison receipts bind interface, completion, case set and counts, authority set, code, schemas, cleanup, issuance, and committed/fresh identities;
- expectation and observation provenance are independent and copying in either direction is rejected;
- protected-domain governance prose accepts only unambiguous withholding or pending-independent-review states and rejects unknown verbs;
- traceability loads the committed matrix and binds authoritative clauses plus current-run observations;
- future manifests, compatibility declarations, and independent review receipts use distinct closed schemas and require exact compatible and independently accepted states;
- the Architecture Impact Assessment and Canonical Delta distinguish retained R3 evidence, corrected R4 controls, draft status, and future authorization.

## Verification design

Coverage, rather than a target count, yields 254 cases: 43 positive and 211 mutation cases; 97 exercise real surfaces and 157 are synthetic; 157 are meta-verification cases. Static committed expectations bind exact status, error code, enforcing function, authority source, and evidence obligation. Fresh observations bind actual execution provenance and have no expectation dependency. The external comparison engine independently recomputes discrepancies.

The schema package uses Python 3.12.2, jsonschema 4.25.1, referencing 0.36.2, rfc3339-validator 0.1.4, PyYAML 6.0.2, Unicode NFC normalization, and a content-bound validator lock. Candidate verification requires all schemas and active instances to validate, all 17 invalid synthetic instances to reject, the valid synthetic instance to pass, and zero canonical/schema/semantic disagreement.

The terminal result cannot succeed without an immutable committed result. Candidate generation is deliberately non-successful; review mode requires exact committed/fresh equality, `MATCHED`, complete cases and comparison, valid comparator authority and terminal receipt, and cleanup `PASS`. `NOT_YET_RECORDED` is never a successful state.

## Evidence lifecycle

Durable evidence consists only of this draft package's specification, schemas, policies, verifier code, fixture definitions, independent expectations, governed result, traceability, impact assessment, Canonical Delta, and this report. Disposable preflight, candidate, checkout, and validation evidence is kept outside the repository and removed after the final audit where governance does not require retention. No production source, production test, runtime data, configuration, launcher, deployment file, or operational capture script is changed.

Final commit identity and four-way checkout receipts are intentionally reported by the post-commit audit rather than embedded self-referentially in this commit.

## Continuing authorization

A baseline capture is not authorized. Operational capture-script work is not authorized. Merge is not authorized. Canonical incorporation is not authorized. Production implementation is not authorized. Deployment is not authorized. Production restart is not authorized. Runtime migration is not authorized. NQ cutover is not authorized. Automated paper trading is not authorized. Live-money trading is not authorized. Phase 3C2 is not authorized. Phase 3C1-R11 acceptance is not authorized during this task. Bucket 0 remains incomplete. Bucket 1 remains blocked. Any successful R4 remediation still requires independent review before any separately governed next step.
