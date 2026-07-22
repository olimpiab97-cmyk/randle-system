# R2 Package Index

Status: governed draft; pending independent review.

## Accepted-specification input roles

`package_role_authority_DRAFT.json` is the only role-to-path authority. Its entries are read from the accepted Git commit, and every named blob is independently derived. The accepted input root deliberately excludes `fixture_results_DRAFT.json` and `REMEDIATION_REPORT_DRAFT.md`; those are derived review evidence whose contents cannot define the input identity they report. The final commit still preserves both files.

### Normative and assessment documents

- `Architecture/15_Randle_AI_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT.md`
- `CANONICAL_DELTA_DRAFT.md`
- this package index
- the Architecture Impact Assessment
- the Architecture traceability narrative

### Immutable authority artifacts

- `package_role_authority_DRAFT.json`
- `governed_authority_universe_DRAFT.json`
- `.gitattributes`
- `authorization_state_DRAFT.json`
- `attempt_prefix_authority_DRAFT.json`
- `required_evidence_policy_DRAFT.json`
- `operational_package_interface_DRAFT.json`
- include, exclusion, selection-rule, and boundary-configuration registries

### Schemas

- capture boundary
- include registry
- exclusion registry
- selection-rule registry
- terminal disposition
- freeze receipt
- attempt ledger
- attempt-prefix authority
- durable manifest
- durable-evidence binding
- required-evidence policy
- test classification
- authorization state
- operational-package interface
- case definition
- independent expectations
- semantic traceability

Every schema file ends in `_schema_DRAFT.json` and is included in the independently derived schema-set identity.

### Draft enforcing code

- `selection_engine_DRAFT.py`
- `inventory_generator_DRAFT.py`
- `boundary_verifier_DRAFT.py`
- `historical_log_parser_DRAFT.py`
- `schema_validation_DRAFT.py`
- `fixture_runner_DRAFT.py`

These are review fixtures and interfaces. They are not an operational capture script.

### Static cases, expectations, and traceability

- `case_definitions_DRAFT.json`
- `independent_expectations_DRAFT.json`
- `expected_case_vectors_DRAFT.json`
- `mutation_case_vectors_DRAFT.json`
- `historical_classification_DRAFT.json`
- `semantic_traceability_DRAFT.json`
- `traceability_matrix_DRAFT.json`, retained only as an explicit disposition of the rejected v2 trace artifact

### Derived review evidence

- `fixture_results_DRAFT.json`
- `REMEDIATION_REPORT_DRAFT.md`

## External immutable evidence

The historical classification binds the external log at SHA-256 `6F1B876C814B25D27F5EF8B4CFE3A66C4B0E847263FEC784C56896DC8FF3194A`. The log is not copied into the repository.

## Serialization

All committed JSON uses `RANDLE-CAPTURE-CJSON-1`: UTF-8, no BOM, NFC strings, sorted keys, compact separators, no duplicate keys, no CR, and exactly one terminal LF. Canonical verification reads committed Git blob bytes.

## Boundary

No production source, production test, launcher, deployment file, production configuration, runtime data, runtime database, cache, operational capture script, or temporary fixture artifact belongs in this package.
