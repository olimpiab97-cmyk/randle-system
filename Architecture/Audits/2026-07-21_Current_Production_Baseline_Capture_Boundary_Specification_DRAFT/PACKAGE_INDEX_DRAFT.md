# R3 Package Index

Status: governed draft pending independent review.

## Byte authority

`r3_authority_bindings_DRAFT.json` binds every enforcement authority to a repository-relative path, raw SHA-256, and Git blob. JSON authorities also bind canonical semantic identity and schema bytes. The binding document is loaded directly from the immutable review commit or, only during candidate preparation, from the staged index. No authority-critical object authenticates itself.

The specification, Architecture Impact Assessment, traceability narrative, Canonical Delta, this index, remediation report, schemas, registries, scripts, fixtures, expectations, authorization state and policy, evidence policy, attempt-prefix authority, and operational-package interface are authoritative only as committed Git-object bytes. Worktree bytes are environmental evidence and cannot alter the deterministic observation identity.

## R3 authority artifacts

- `r3_authority_bindings_DRAFT.json` and its schema
- `separate_binding_policy_DRAFT.json`
- `authority_role_map_DRAFT.json`
- `attempt_authorization_R3_DRAFT.json`
- `timestamp_authority_R3_DRAFT.json`
- `attempt_prefix_authority_R3_DRAFT.json`
- `required_evidence_policy_R3_DRAFT.json`
- `historical_evidence_authority_R3_DRAFT.json`
- `observer_source_authority_R3_DRAFT.json`
- `observer_event_source_R3_DRAFT.jsonl`
- `comparison_authority_R3_DRAFT.json`
- `comparison_policy_R3_DRAFT.json`
- `authorization_policy_R3_DRAFT.json`
- `operational_package_interface_R3_DRAFT.json`

## R3 enforcing fixtures

- `governed_file_access_DRAFT.py`
- `r3_authority_verifier_DRAFT.py`
- `comparison_engine_DRAFT.py`
- `fixture_runner_R3_DRAFT.py`
- remediated `boundary_verifier_DRAFT.py`, `inventory_generator_DRAFT.py`, `selection_engine_DRAFT.py`, `schema_validation_DRAFT.py`, `historical_log_parser_DRAFT.py`, and legacy `fixture_runner_DRAFT.py`

These files are specification fixtures, not an operational capture script.

## Cases, expectations, observations, and traceability

- `case_definitions_R3_DRAFT.json` binds immutable inputs and coverage-derived case IDs.
- `independent_expectations_R3_DRAFT.json` independently binds expected status, code, enforcing function, authority source, and evidence obligation.
- `semantic_traceability_R3_DRAFT.json` binds explicit specification clauses to schema pointers, rules, source functions, positive and mutation cases, and future obligations.
- `fixture_results_R3_DRAFT.json` preserves the reconciled observations and external-comparator receipt.
- every R3 schema file ending `_schema_DRAFT.json` participates in the derived schema-set identity.
- `validator_requirements_DRAFT.lock` identifies the pinned validation environment.

Earlier R2 artifacts remain only where needed for provenance or remediated compatibility. They do not override an R3 authority object.

## External immutable evidence

The historical authority binds the external 2,226,181-byte log at SHA-256 `6f1b876c814b25d27f5ef8b4cfe3a66c4b0e847263fec784c56896dc8ff3194a`. The log is read from its separately authorized physical path and is not copied into Git.

## Serialization and boundary

Governed JSON is canonical UTF-8 with no BOM, sorted keys, compact separators, and one terminal LF. No production source, production test, launcher, deployment file, production configuration, runtime data, runtime database, cache, operational capture script, or temporary fixture artifact belongs in this package.
