# Independent R7 requirement reconstruction

This inventory was reconstructed before evaluating the implementation-authored 178-case artifact. The source is the immutable R6 specification blob `343622743668d7ddc524513307e726f20d1db9fc`, the imported R6 rejection record blob `851a2aadef9e121e11b5b43837dd37c0a7c2dc96`, and both complete R7 report blobs `1be3b0b5f15ac8e68b88202e0e9d3787b69d1856` and `dfa98a89049b9596387143c002252d91d608fbfc`.

## R6 clauses retained as R7 authority

| ID | Immutable location | Required positive authority | Required rejection/evidence/durability | Acceptance significance |
|---|---|---|---|---|
| CPB-R6-01 | R6 spec lines 129–131 | Authority access from exact committed bytes and measured call origin | Reject constant-folded/unknown dynamic/mutable-label access; bind raw hash, Git blob, code object, role, commit and process origin | Blocking |
| CPB-R6-02 | lines 133–135 | Parser, comparator, recorder and access probes run behind a fresh measured process boundary | Reject caller launchers; receipt binds nonce, PID/parent, times, image, flags, environment, command, inputs/outputs/streams and issuance | Blocking |
| CPB-R6-03 | lines 137–139 | Externally issued unique one-use run authority | Reject deterministic case IDs, replay, expiry and wrong spec/case/expectation/code/schema/recorder/comparator/mandatory authority | Blocking |
| CPB-R6-04 | lines 141–143 | Recorder derives every current event and a monotonic finalized chain | Caller may not supply observed function/status/code/authority/evidence/time/process receipt/event hash | Blocking |
| CPB-R6-05 | lines 145–147 | Observations reconstructed from current finalized external event bytes | Reject prior/committed events and invalid run/recorder/chain/freshness/cardinality/code/authority/evidence | Blocking |
| CPB-R6-06 | lines 149–151 | Surface derives from executing function code object, symbol, span, module blob, process and recorder | Reject expected labels, wrapper text and replay adapters as observed authority | Blocking |
| CPB-R6-07 | lines 153–155 | Every decision reparses immutable/content-addressed bytes, checks raw/object identity, canonical form, schema and semantics, then freezes | Reject mutable caches, duplicate/canonical ambiguity and unresolved bytes | Blocking |
| CPB-R6-08 | lines 157–159 | Complete independently resolving forward/reverse trace | Reject orphan, circular or source-only mappings; bind clause, schema, rule, symbol, code, invocation, cases, expectations, events, observations, comparison and future obligation | Blocking |
| CPB-R6-09 | lines 161–163 | Reviewer/issuer authority resolves from separate immutable trust and issuance bytes | Receipt cannot redefine persona, capability, independence, decision, issue time, package or boundary authority | Blocking |
| CPB-R6-10 | lines 165–167 | Compatibility proven by immutable evidence from an authorized issuer | Reject unresolved hashes and self-claims; bind all package/interface/schema/verifier/finding/attachment/state details | Blocking |
| CPB-R6-11 | lines 169–171 | Exact validator distribution and all named FormatChecker capabilities | Missing/mismatched package or date-time, time, URI, hostname, IDN, IP, email, regex or UUID capability terminates | Blocking |
| CPB-R6-12 | lines 173–175 | Real path loads immutable include/exclusion/rule/universe/mandatory/evidence/physical inventory; all five named tests execute | Reject missing, altered, excluded, wrong-rule or wrong-root named tests and fixture substitution | Blocking |
| CPB-R6-13 | lines 177–179 | Candidate/fresh runs have distinct provenance and semantic reconciliation | Reject replayed authority/events/process receipts, caller event fields, observation copying, skipped preflight, mutable cache and comparison replay | Blocking |
| CPB-R6-14 | lines 181–183 | Closed proof vocabulary backed by clause, implementation, positive/mutation, expectation, current event/observation, comparison and trace | Reject unsupported completion/proof claims | Blocking |
| CPB-R6-15 | lines 185–187 | AIA/Canonical Delta accurately separate retained, rejected, corrected, draft, deferred and restricted work | Reject overstatement or canonical/operational incorporation | Blocking |

The earlier R4/R5 clauses remain incorporated by R6. Material retained properties include canonical parsing (CPB-R4-03), expectation/actual provenance separation (CPB-R4-07), bidirectional traceability (CPB-R4-09), future-receipt resolution (CPB-R4-10), isolated execution and event/observation derivation (CPB-R5 series), trusted future issuance and evidence-bound claims.

## Complete R7 record requirements

| ID | Immutable location | Requirement | Required tests/evidence | Acceptance significance |
|---|---|---|---|---|
| R7-B01 | first R7 report lines 54–70 | A complete prior result with zero current processes/events must never obtain terminal acceptance | Direct replaceable-client/supervisor, complete replay and zero-event attacks | Blocking |
| R7-B02 | first R7 report lines 72–88 | Reconciliation resolves full immutable signed evidence; it never trusts caller dictionaries or two matching summaries | Fabricated dictionaries, detached receipts, copied roots and two-invalid-graph attacks | Blocking |
| R7-T01 | first R7 report lines 94–105(1–2) | Final execution, terminal issuance and reconciliation reside behind a noncaller-replaceable measured boundary | Hostile launcher/worker/client/supervisor substitutions | Blocking |
| R7-T02 | lines 99–101 and second report lines 96–100 | Durable public asymmetric trust whose private authority is unavailable to runner/caller; governed role, domain, validity, rotation and revocation | Principal/key isolation, direct-sign denial, trust substitution/downgrade and public-only verification | Blocking |
| R7-T03 | first report line 101 | Parser/comparator/recorder/event/observation/terminal/reconciliation receipts remain publicly verifiable after issuer exit | Public-only receipt and child-graph verification | Blocking |
| R7-T04 | first report line 102 | Locator-only reconciliation internally loads bytes, validates closed schemas/signatures/ledger/process/event graph and rejects arbitrary objects | Parser/canonicalization, unresolved child and summary-only attacks | Blocking |
| R7-T05 | first report line 103 | Terminal/reconciliation success is durably ledger-bound and caller cannot append authority | Direct append, detached/copy ledger, append-before-response and crash tests | Blocking |
| R7-T06 | first report line 104 | Direct public tests replace client/supervisor, replay complete prior result, submit zero events/fabricated dictionaries and attempt direct append | Every direct regression must block terminal/reconciliation authority | Blocking |
| R7-T07 | first report lines 105–106 | New complete eight-execution matrix and corrected AIA/Canonical Delta after bypass closure | Four checkout/line-ending variants, candidate+fresh and reconciliation with distinct provenance | Blocking |
| R7-T08 | second report lines 98–103 | Separate OS principal/nonexportable key, measured supervisor, fixed authenticated ledger and approved submit/retrieve/verify/reconcile interfaces | Host identity, upgrade authority, authenticated IPC and lifecycle evidence | Blocking |
| R7-T09 | second report lines 103–105 | Explicit authorization for the eight runs/four reconciliations and later independent review | New evidence, not reused authored evidence | Blocking |

## Independently required semantic chain

Approval requires every normative behavior to resolve through:

`authority object → requirement → immutable case → separately authored expectation → hostile-capable real public invocation → current raw process/request/response/side-effect evidence → event derived without expectation authority → observation derived from event → independent comparison → service-side full-graph verification → durable signed receipt and ledger → public-only verification → full external candidate/fresh reconciliation`.

The governing objects prescribe properties, not a count of 178. No independent authority fixes 15 groups, 178 cases, 20 acceptances or 158 rejections.
