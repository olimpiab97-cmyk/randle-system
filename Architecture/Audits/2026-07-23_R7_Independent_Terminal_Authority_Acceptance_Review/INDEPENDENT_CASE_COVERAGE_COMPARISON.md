# Independent case and expectation coverage comparison

The committed case and expectation bytes have the claimed hashes, blobs, sizes and modes. They parse as canonical JSON with 178 unique, bijective case IDs and an internal 20-accept/158-reject split. Those are consistency facts, not governing completeness.

## Disposition-determinative results

1. **Zero valid exact authority mappings.** All 178 rows cite R6 spec blob `343622743668d7ddc524513307e726f20d1db9fc` for `R7-01` through `R7-15` and embed `CPB-R7-01` through `CPB-R7-15`. The cited immutable blob contains 15 `CPB-R6-*` clauses and zero `CPB-R7-*` clauses. The claimed CPB-R7 text exists only in discarded sibling commit `f0cfbce...`, blob `c4180efa...`.
2. **Discarded source is normative in substance.** Every one of the 178 `source_case` objects is byte-for-object identical to discarded f0 case blob `e7919987dc0518f6eb5978bb9bf57989898a2c51`; all 178 expectation semantics are copied from discarded expectation blob `da11fc852e63e7f30a6265d04d8978d93aa359fd`.
3. **Expectations are not independent.** One builder loads the discarded cases and expectations together and emits both final artifacts. Case and expectation status/classification/function/authority/evidence agree in all 178 rows. Every authority identity is `sha256("R7-INTERNAL-AUTHORITY-REPOSITORY")`; evidence identities use the implementation formula `sha256("R7-EVIDENCE-" + interface)`.
4. **Expectation values construct actuals.** The f0 recorder is initialized with expected status/code/evidence, rejects deviations, and writes expected evidence identity into `actual_evidence_identity`.
5. **Declared obligations are inert.** Runtime verifier source contains zero uses of `expected_evidence_obligation`, `expected_ledger_delta`, `forbidden_outcomes`, `forbidden_side_effects`, `required_evidence` and `required_side_effects`. Restart/retry/replay/comparator/observation rules are likewise not semantically executed.
6. **Fixture/meta execution replaces hostile public interfaces.** All 178 operations are `execute_case`; all callers are the service child; all 158 negative rows are `meta_verification:true`. The wire request is only `{case_id, operation}` and the trusted f0 subject selects and simulates the mutation internally.
7. **Outer R7 authority is absent from the case set.** Zero cases invoke attempt issuance, run execution, terminal receipt retrieval, reconciliation or reconciliation retrieval. Zero case IDs directly test required outer client/supervisor replacement, zero-event replay, arbitrary reconciliation dictionaries, direct ledger append, public verification, key/trust lifecycle or service/policy downgrade.
8. **Material R6 coverage is collapsed or missing.** Canonicalization ambiguities, complete process receipt roles, run-authority bindings, all FormatChecker capabilities, the five real governed-root tests, complete replay categories, proof grammar and AIA/Canonical distinctions are not adequately tested.

## Independent count conclusion

- authored structural count: 178;
- authored internal split: 20 accept / 158 reject;
- valid exact governing mappings: **0 / 178**;
- cases exercising the outer terminal/reconciliation protocol: **0 / 178**;
- independently established complete count: **not established**;
- approval consequence: **blocking failure**.

Machine-reproduced details are in `independent_case_expectation_audit_result.json`; the reproducer is `independent_case_expectation_audit.py`.
