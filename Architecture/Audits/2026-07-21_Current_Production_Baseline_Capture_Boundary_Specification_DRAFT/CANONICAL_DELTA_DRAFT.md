# Canonical Delta — Current Production Baseline Capture Boundary

Status: **REMEDIATED DRAFT — NOT CANONICAL — PENDING NEW INDEPENDENT REVIEW**

## Proposed new normative concepts

1. A capture boundary is a deterministic fixed point over entrypoints, imports, runtime references, launch references, tests, fixtures, governed registries, and external dependencies.
2. Git status state is orthogonal to production relevance; tracked, modified, untracked, and ignored paths use the same relevance rules.
3. Every enumerated path receives exactly one terminal disposition, with conflicts and unknowns stopping the attempt.
4. The specification, scripts, registries, environment, repository state, generated inventory, and external evidence are frozen before Pass A.
5. Raw disk identity and Git-cleaned/blob identity are distinct and both are preserved.
6. Attempt history is append-only and distinguishes no-artifact, pre-Pass-A, unstable, aborted, rejected, successful, superseded, and reviewed attempts.
7. Durable evidence is enumerated with extended-length Windows paths and bound by complete content identities.
8. Every test outcome—including `SUBFAILED`, `XFAIL`, and `XPASS`—is individually preserved and source-reconciled.
9. Every enumerated artifact remains visible in a terminal-disposition inventory whose three disjoint sets reconcile to the enumeration universe.
10. Package authority derives registries, configuration, selector, inventory generator, and verifier identities from committed Git objects plus current raw bytes.
11. Attempt and evidence completeness depend on independently frozen universes, not self-reported mutable counts.
12. Positive or ambiguous authority language anywhere in the governed package is a semantic verification failure.

## Machine-enforced controls in this remediation

- Python AST, PowerShell, batch/shell, JSON, YAML, TOML, and INI parser fixtures emit resolved dependency edges or fail closed.
- Pytest fixtures, markers, parameterization, unittest discovery, route/handler/factory/plugin loading, subprocess targets, static resources, replay/scenario data, and configuration targets are exercised.
- All paths receive `INCLUDE`, `EXCLUDE`, or `SEPARATE_AND_BIND`; exclusions and separate bindings cannot disappear.
- The five questioned tests remain exact normative inclusions even when relevance signals, registry entries, path case, names, or proposed exclusions are mutated.
- Real NTFS stream enumeration, extended-length paths, long-path sentinels, reparse points, inaccessible paths, and stable reads are tested on disposable roots.
- Draft 2020-12 schemas and complete instances are independently validated with pinned `jsonschema` 4.25.1 and then semantically validated.
- Every freeze and multi-pass field is mutation-tested; the historical 753-outcome classification is complete and source-bound.
- Static independent expectations and observation roots detect expectation, observation, and enforcing-code drift.

## Clarified existing concepts

- A capture proves disk state and provenance, not implementation quality or deployment/trading readiness.
- Tests and failures are evidence; classification never converts a failure to a pass.
- External runtime/evidence dependencies remain external authority but must be content-bound when required for recovery.
- Governance documents are not production implementation; capture-critical governance records are separately bound.
- Multi-pass stability includes specification, scripts, status, index, branch, external evidence, raw bytes, and clean bytes.

## Rejected prior practices

- Hard-coded final allowlists as the sole proof of capture completeness.
- Undocumented manual removal of paths selected by preliminary discovery.
- Predetermining an inventory count and selecting toward it.
- Omitting untracked or ignored files solely because of Git status.
- Unbound preliminary/final scripts or helper logic.
- Filename-only references to durable evidence.
- Non-long-path-aware enumeration that silently skips artifacts.
- Recording only ordinary `FAILED` nodes while omitting `SUBFAILED` outcomes.
- Collapsing a no-artifact attempt into an unstable artifact-producing attempt.
- Reusing attempt IDs or overwriting evidence after instability.

## Future incorporation set

If independently accepted, a later governed task must incorporate the accepted specification into `Architecture/README.md`, `Architecture/06_Randle_AI_Modernization_Charter.md`, `Architecture/07_Randle_AI_Modernization_Roadmap.md`, `CODEX_TASK_TEMPLATE.md`, and the accepted successor of `Architecture/14_Randle_AI_Runtime_Recovery_Verification_Specification_DRAFT.md`. That task must preserve the independent review identity and must not retroactively accept the rejected capture.

## Remaining draft matters

The specification text, schemas, registries, rule registry, parser expectations, fixture scripts, and verification results remain draft pending new independent review. The fixture scripts are enforcement evidence, not the future operational capture script; that operational script remains intentionally absent and must later be separately committed or content-addressed and frozen. No repository-specific future inventory exists, no capture has run, and no architecture, merge, deployment, restart, migration, cutover, trading, Bucket, Phase 3C2, or R11 acceptance authority is created.
