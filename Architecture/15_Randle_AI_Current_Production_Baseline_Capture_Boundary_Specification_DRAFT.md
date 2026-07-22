# Current Production Baseline Capture Boundary Specification

Status: REMEDIATED DRAFT; not canonical; pending independent review.

Authority status: none. Baseline capture, operational capture-script work, merge, canonical incorporation, production implementation, deployment, service restart, runtime migration, NQ cutover, automated paper trading, live-money trading, Phase 3C2, Phase 3C1-R11 acceptance, Bucket 0 completion, and Bucket 1 work remain withheld.

## 1. Scope and authority separation

This draft defines a deterministic boundary and verification interface for a possible future Current Production Baseline Capture. It does not perform that capture. It contains no operational capture script. Acceptance of this draft would establish only an accepted-specification identity suitable for a separately governed operational-package proposal.

The following authorities are separate and MUST NOT be inferred from this document: specification acceptance, operational-package review, freeze acceptance, capture execution, canonical incorporation, production implementation, deployment, restart, migration, cutover, and trading.

The immutable external review authority is commit `7b60e890b7d426fd1331ab5876004b1b68ee6444`, whose Section 33 corrections are represented by R2-01 through R2-16 below. This remediation descends directly from `50bc58afc8861631f253f787d88dbd0f28c2d328`; it does not rewrite that commit or its parent.

## 2. R2-01: checkout-independent bytes and Git authority

Committed Git blob bytes are the authoritative bytes for every governed package artifact. Canonical JSON validation MUST read those bytes through `git show <accepted-commit>:<path>` or an equivalent object operation. A worktree read is a separate observation. Its Git-cleaned bytes, produced by the actual frozen attributes and clean-filter behavior, MUST reproduce the committed blob. Raw worktree bytes need not equal blob bytes when a governed checkout transformation applies.

The package-local `.gitattributes` pins JSON, Python, Markdown, and the attribute file itself to LF. A fresh checkout with either `core.autocrlf=true` or `core.autocrlf=false` MUST reconcile to the same package Git-object identity. Unexpected transformation, changed worktree with unchanged blob, changed blob with unchanged worktree, changed attribute policy, or failure to pass command-scoped `core.longpaths=true` MUST stop verification.

Every package Git command MUST be long-path-safe and use only command-scoped `safe.directory` when necessary. Global and repository Git configuration are outside this specification's mutation authority.

## 3. R2-02: parser-backed dependency closure

Selection starts from governed include entries, enumerates the complete governed repository root, and reaches a fixed point over dependency edges. A synthetic root requires its fixture marker. A non-fixture root is permitted only as an exact, clean, non-production Git worktree whose `HEAD` equals the independently validated accepted-specification commit; this mode is read-only and refuses the active production root. Every edge MUST preserve source path, source language, parser name and version, source location, edge type, rule ID, literal or declared target, target expression, resolved canonical target, resolution state, evidence, and disposition obligation.

Python MUST use the Python AST and cover absolute and relative imports; `importlib.import_module`; `__import__`; literal `open`; `pathlib.Path`; `read_text`; `read_bytes`; path open/write operations; subprocess targets; route decorators; handler, factory, and plugin registration; pytest fixtures; unittest relationships; replay and scenario relationships; and static-resource APIs. Literal path candidates include extensionless names, slash-free names, relative paths, simple constant concatenation, and values propagated through `pathlib`.

PowerShell MUST use its parser AST for script invocation, dot sourcing, call operator, `Start-Process`, `Import-Module`, `Get-Content`, `Set-Content`, `Test-Path`, configuration, and launcher references. JSON MUST use a strict JSON parser; YAML MUST use pinned PyYAML; TOML MUST use `tomllib`; INI MUST use `configparser`. Batch and POSIX shell use an explicitly bounded lexical grammar and MUST fail on constructs outside that grammar. They are not represented as full-language parsers.

A missing literal target MUST fail even if absent from the enumerated path set. A malformed configuration MUST fail. An unresolved dynamic dependency MUST fail unless an independently frozen declaration resolves it exactly.

## 4. R2-03: complete terminal dispositions

Every enumerated repository or governed external artifact MUST receive exactly one terminal disposition: `INCLUDE`, `EXCLUDE`, or `SEPARATE_AND_BIND`. Their sets MUST be pairwise disjoint and their union MUST equal the independently enumerated universe.

Each record MUST bind canonical path, class, disposition, rule ID, exact rule-registry blob, authority object and identity, rationale, evidence and evidence identities, capture form, expected existence, external root when applicable, exclusion-review identity when applicable, and complete separate-binding obligations when applicable.

`INCLUDE` MUST NOT carry exclusion or separate-binding metadata. `EXCLUDE` MUST remain visible and MUST NOT carry include or separate-binding obligations. `SEPARATE_AND_BIND` MUST remain visible and MUST carry complete evidence obligations. The verifier MUST independently regenerate records from the frozen enumeration and registries; a caller-provided record is only a claim. Rebuilding a self-root after an omission or substitution does not establish authority.

The freeze binds the ordered disposition set, count, include-set identity, exclude-set identity, separate-set identity, complete semantic root, and the registry blobs responsible for every record.

## 5. R2-04: mandatory five-test authority

The following exact paths are mandatory `INCLUDE` entries:

- `test_command_center_listener_watchdog.py`
- `test_offline_replay.py`
- `test_kpi_liquidity_atr_distance_report.py`
- `test_tick_receiver_pipeline.py`
- `test_tick_receiver_throughput.py`

The old 234-path count has no authority. The verifier MUST derive the include, exclusion, rule, configuration, selection-engine, inventory-generator, and verifier blobs from the accepted specification commit. It MUST verify each path's complete authority tuple, evidence tuple, physical existence, source relevance signal, raw SHA-256, computed Git blob, mode, and rule binding.

Real-commit verification MUST reconstruct specification policy from an isolated, clean worktree at the exact accepted commit. The physical inventory root is a separate parameter: during specification verification it is a marker-bound governed fixture; a future authorized inventory may instead use an exact clean non-production worktree under separately frozen authority. The synthetic root cannot substitute for the real accepted-commit Git-object derivation, and the accepted-specification worktree cannot substitute for physical inventory evidence. A missing accepted commit, dirty specification worktree, moved specification `HEAD`, active production-root use without future authority, transformed accepted enforcing blob, or caller-provided replacement authority MUST terminate before selection.

Removal, rename, case change, relevance removal, registry replacement, pending capture-mode exclusion, unbound approved-looking exclusion, configuration change, enforcing-code change, forged authority, forged evidence, or changed committed blob MUST fail through the actual accepted-package verification path.

## 6. R2-05: one validation pipeline

Every governed JSON artifact passes, in order: strict duplicate-key and canonical JSON loading; Draft 2020-12 schema validation; semantic validation; cross-artifact validation; and immutable-authority validation. A schema failure cannot be converted into semantic acceptance.

Schemas MUST enforce nonempty parser policy; long-path, ADS, and stability policies; capture-mode exclusion restrictions; conditional external-root requirements; known rule references; complete terminal dispositions, freeze receipt, attempt ledger, evidence registry, and classification; and Git object identifiers conditioned on object format. SHA-1 values are exactly 40 lowercase hexadecimal characters. SHA-256 object values are exactly 64 lowercase hexadecimal characters. Matching invalid claims MUST fail.

The pinned independent validator is `jsonschema==4.25.1` with `Draft202012Validator`. Metaschema checks and all active and synthetic instances MUST pass with zero schema/semantic disagreements.

## 7. R2-06 and R2-07: filesystem streams and two-read identity

On Windows, every filesystem-backed scan MUST invoke `FindFirstStreamW` and `FindNextStreamW`. Named, zero-byte, and multiple alternate streams are governed failures. Stream appearance, disappearance, or content change between scans is instability. A filesystem-backed case MUST NOT replace the enumerator with a callback. If an access-failure reproduction cannot be created on the running Windows identity, the result MUST explicitly state `ADS_ACCESS_FAILURE_UNSUPPORTED`; it cannot report success. Colon-like file content is not an alternate stream.

Every selected file MUST be opened and content-read at least twice across the governed interval. The record binds first and second raw SHA-256, size, file identity, stat metadata, attributes, mode, ADS names and content identities, parent blob, index blob, actual Git-cleaned bytes and identity, computed Git blob, object format, effective clean-filter identity, `.gitattributes` blob, effective attributes, encoding, BOM, line-ending profile, and reparse or symlink state.

Same-size replacement with restored modification time or attributes MUST fail because content identity differs. Raw-only checkout transformation is acceptable only when frozen attributes explain it and the actual clean-filter result reconciles. Clean-filter, BOM, encoding, mode, parent, index, attributes, or between-read content mutation MUST fail.

## 8. R2-08: independently reconstructed freeze

A freeze receipt is a claim. The verifier MUST reconstruct its authority from the accepted specification repository, a distinct later operational-package repository or immutable content address, the committed role map, committed schemas and registries, current Git state, generated inventory and dispositions, evidence policy, preserved attempt prefix, authorization state, and observed environment.

The reconstructed set binds accepted specification commit, parent, tree, document blob, complete schema-set identity, all registry and executable blobs, package byte identities, object format, HEAD, parent, branch or detached state, index, status bytes, `.gitattributes`, inventory, dispositions and set roots, evidence-policy identity, attempt-prefix authority, environment identity, later operational-package identity, future script identity, attempt ID, timestamp authority, and authorization identity.

Matching invalid values, caller-supplied inventory, caller-supplied dispositions, caller-supplied evidence roots, caller-supplied attempt universe, changed package blob, changed registry, changed configuration, or changed environment identity MUST fail. Pass A remains blocked without a complete accepted freeze receipt.

## 9. R2-09: preserved-prefix attempt ledger

The attempt ledger MUST be checked against a committed immutable genesis or previously accepted prefix authority external to the ledger instance. That authority binds preserved attempt IDs, count, genesis entry hash, and preserved ledger root.

Each current entry binds unique attempt ID, monotonic sequence, predecessor, prior-entry hash, prior-ledger root, entry hash, current root, chronology, worktree, branch, evidence directory, pass states, staging, commits, manifest, terminal disposition, relationships, and truthful incident fields. The verifier MUST check prefix preservation, full count, expected historical IDs from the external authority, hash ancestry, cycles, relationships, manifests, and chronology.

Truthful `runtime_access`, `production_modification`, `deployment_attempted`, or `service_restart_attempted` values remain representable and preserved. A true value disqualifies capture authority; it MUST NOT erase the incident record.

## 10. R2-10: preexisting required-evidence policy

`required_evidence_policy_DRAFT.json` is independent of evidence instances. It freezes required roles, classes, cardinality, conditional rules, semantic purposes, source-attempt and capture-pass relationships, immutability, and recovery requirements.

An evidence instance MUST reconcile to that policy and to the accepted attempt ledger. It binds policy blob and raw hash, expected role and class sets, count, path-set identity, entry-set identity, semantic root, total bytes, and registry identity. Changing a recovery flag or other semantic and rebuilding all instance roots MUST fail because the preexisting policy remains unchanged.

## 11. R2-11: actual historical classification authority

The source is the actual immutable historical log at `C:/Users/Trader/OneDrive/RandleRuntimeData/provenance/current_production_baseline_capture_20260720_retry1/command_results/18_broad_captured_entry_agent_pytest.log`, size 2,226,181 bytes, SHA-256 `6F1B876C814B25D27F5EF8B4CFE3A66C4B0E847263FEC784C56896DC8FF3194A`.

The versioned parser MUST derive 571 PASSED, 156 FAILED, 23 SUBFAILED, 3 SKIPPED, 0 ERROR, 753 accounted outcomes, and 179 individually classified failed outcomes from those bytes. Every outcome binds its actual parser-event identity, parent when applicable, deterministic line and byte location, parser and version, normalization rule, classification rule, category, rationale, and source evidence. The quiet progress events in the source log use deterministic event identities; named failures and subfailures retain their actual node text. The verifier reparses the bound bytes and rejects nonexistent or wrong source locations, changed log bytes, removed subfailures, duplicates, changed parent, changed classification, parser-version drift, or rule drift.

## 12. R2-12: actual observed multi-pass stability

Pass A, Pass B, and final state MUST be observed from a controlled repository rather than supplied as integers or identity strings. The observer reads HEAD, parent, branch or detached state, index, raw status, object format, attributes, inventory, disposition and package roles, registries, configuration, script and verifier identities, artifact count, byte total, evidence set, ledger root, freeze receipt, and environment.

Writer, runtime-operation, deployment-attempt, and restart-attempt counts MUST come from a separately rooted append-only event source. Branch, HEAD, index, status, file, registry, configuration, count, byte-total, evidence, or observer-event changes between the three observations MUST terminate as unstable. Three equal syntactically invalid HEAD claims MUST fail before equality comparison.

## 13. R2-13: independent fixture architecture

Case definitions and immutable expectations are separate committed artifacts. Every expectation binds case ID, normative requirement, authoritative-input identity, expected status, terminal disposition, exact code, exact enforcing surface, evidence obligations, and authority result. The expectation artifact is static and MUST NOT be generated from observations.

Enforcing functions produce raw observations containing actual status, disposition, code, enforcing surface, evidence, authority result, and input identity. A comparison-only layer compares the two artifacts. It cannot create expected truth. A terminal comparison receipt is mandatory.

There is no negative-assertion helper. Forcing one or all enforcing functions to success changes observations and creates discrepancies. Disabling comparison terminates verification. Replacing observations with expectations fails provenance. Removing expectations fails. Expectation-only and observation-only changes create discrepancies. A descriptive-label change does not redefine enforcement truth. Observation-semantic identity includes actual status, disposition, code, surface, evidence, authority, and identities.

## 14. R2-14: structured authorization policy

`authorization_state_DRAFT.json` lists every protected domain and permits only `WITHHELD`, `NOT_AUTHORIZED`, or `PENDING_INDEPENDENT_REVIEW`. No positive state is valid in this draft.

The free-text verifier scans every governed package role, including Markdown structure and JSON values. Authority verbs combined with protected objects fail unless a narrow withholding grammar applies. Ambiguous, conditional-positive, contradictory, mixed-case, punctuation, table, heading, list, blockquote, and structured JSON variants MUST fail closed. Required mutation phrases are constructed from inert fragments inside enforcing fixtures so the governed package itself contains no positive free-text grant.

## 15. R2-15: semantic traceability

`semantic_traceability_DRAFT.json` maps every R2 requirement to its normative clause, every schema property and conditional pointer, each rule-registry entry, implementing source file and symbol, invoked positive and mutation cases, immutable expectation, fresh observation, and future operational obligation.

The verifier enumerates schema fields directly, parses source symbols with the Python AST, checks every referenced function exists, verifies every mapped function is invoked by a case that expects that exact surface, checks every selection-rule ID, and compares actual observations when supplied. Identifier-set placeholders are invalid. Missing field mapping, nonexistent function, wrong function, unused mapped function, missing rule, identifier-only substitution, or altered expected surface MUST fail.

## 16. R2-16: separate accepted specification and later operational package

Accepted specification authority binds its commit, tree, document blob, complete schema set, registries, rules, verifier interface, package roles, byte policy, and authorization state.

A future operational package is a separate authority. It binds a later commit or immutable external content address, future script blob and raw SHA-256, supporting modules, package tree and parent, manifest, independent-review receipt, compatibility declaration, independent-review decision, and freeze-package identity. The later commit can descend from another commit without changing the accepted specification identity.

Compatibility verification binds the accepted specification interface version, accepted-specification identity, later-package identity, review decision, future script content, and freeze receipt. Wrong or modified specification identity, unreviewed package, wrong script blob, wrong package tree, incompatible interface, unbound external content, or self-referential use of one identity for both authorities MUST fail.

No operational capture script is included here. Operational capture-script work remains withheld. A later proposal would require separate governance and independent review before any freeze or capture request.

## 17. Canonical serialization and package reconciliation

`RANDLE-CAPTURE-CJSON-1` permits null, Boolean, integer, NFC string, array, and object. Floating point, surrogate code points, duplicate keys, BOM, CR, and non-UTF-8 are forbidden. Object keys sort deterministically; separators are compact. Stored JSON is canonical semantic bytes plus exactly one LF. Semantic hashes exclude the stored LF; raw hashes include it.

The case count emerges from coverage. The package records positive, mutation, real-surface, and meta-verification counts; passed, failed, and discrepancy counts; case, expectation, observation, enforcing-code, schema-set, package-object, and external-evidence identities; committed/fresh reconciliation; cleanup; wall time; validator, Python, Git, OS, and filesystem identities.

## 18. Continuing state

This document is a draft boundary specification only. Baseline capture is not authorized. Operational capture-script work is not authorized. Merge and canonical incorporation are not authorized. Production implementation, deployment, service restart, runtime migration, NQ cutover, automated paper trading, live-money trading, Phase 3C2, and Phase 3C1-R11 acceptance are not authorized. Bucket 0 remains incomplete. Bucket 1 remains blocked.

## 19. R3 independent-authority clauses

The following explicit clause IDs are the stable normative anchors consumed from this specification's immutable Git blob. The R2 controls remain historical draft context and are not acceptance authority where an R3 clause supersedes them.

Clause ID: CPB-R3-01

Every authority-package, schema, policy, fixture, expectation, observation, traceability, report, role-map, and reconciliation read shall pass through the governed extended-length access layer. The layer shall canonicalize absolute, UNC, and relative-to-root paths; reject unauthorized reparses and non-regular files; distinguish binary and strict text reads; expose stable file identity; and fail closed on inaccessible, missing, renamed, or mutated paths.

Clause ID: CPB-R3-02

Every accepted specification artifact shall derive authoritative bytes from the immutable Git object selected by external review authority. Worktree bytes are environmental evidence only; expected line-ending transformation shall not change the observation-semantic identity, while a changed authoritative Git blob shall change it.

Clause ID: CPB-R3-03

Review mode shall succeed only for the terminal reconciliation value MATCHED. NOT_YET_RECORDED, MISMATCH, MISSING_COMMITTED_RESULT, INVALID_COMMITTED_RESULT, COMPARATOR_NOT_AUTHORIZED, incomplete cases, invalid receipts, changed enforcement, changed schemas, or failed cleanup shall terminate verification.

Clause ID: CPB-R3-04

The bounded batch grammar shall derive dependency edges for start, call, direct invocation, cmd, PowerShell, pwsh, and Python launcher forms, including quoted, relative, variable-expanded, and extensionless literal targets. Missing literals, unresolved variables, malformed quoting, and unsupported compound grammar shall fail closed.

Clause ID: CPB-R3-05

A SEPARATE_AND_BIND disposition shall be derived from an immutable committed policy and role map defining authorized classes, authorities, evidence roles and classes, cardinality, immutability, recovery, external roots, capture forms, review, and semantic purpose. Rebuilt instance roots shall not authorize changed obligations.

Clause ID: CPB-R3-06

Draft 2020-12 validation shall use the pinned validator lock and FormatChecker, including independently pinned RFC 3339 and URI dependencies. Attempt, freeze, authorization, review, evidence, and ledger timestamps shall also pass semantic RFC 3339 and chronology validation against frozen timestamp authority, with zero schema/semantic disagreement.

Clause ID: CPB-R3-07

Freeze verification shall compare receipt claims with separately bound attempt authorization, issuance timestamp, sequence, specification, inventory, observer, evidence-policy, and prefix authority. Receipt fields and a rebuilt receipt hash shall never select their own authority.

Clause ID: CPB-R3-08

Attempt-prefix validation shall load immutable authority bytes and reconcile raw SHA-256, Git blob, canonical semantic identity, role-map binding, schema identity, accepted prefix count, attempt IDs, prior ledger root, and authority ID before accepting any ledger claim.

Clause ID: CPB-R3-09

Required-evidence validation shall load immutable policy bytes and reconcile raw SHA-256, Git blob, semantic identity, policy ID, roles, classes, cardinality, conditions, purpose, recovery, source-attempt, capture-pass, and immutability rules. Evidence instances shall not redefine policy.

Clause ID: CPB-R3-10

Historical evidence shall be governed by an external binding of logical ID, exact physical path, normalization, size, hash, provenance root, capture attempt, evidence role, and external root. The parser shall read that exact file and reconcile parser events and source locations; a classification path claim shall not select the file.

Clause ID: CPB-R3-11

Observer events shall come from an independently frozen source binding its ID, exact path, type, schema, initial and append-only roots, sequence, source and reader implementation, attempt, and freeze role. Caller substitution, removal, reordering, truncation, or rebuilt roots shall terminate verification.

Clause ID: CPB-R3-12

Comparison authority shall be external to the comparator receipt and bind comparator code, raw hash, interface, expectations, observations, result schema, policy, issuer, and terminal rules. Disabled, replaced, self-generated, discrepant, or unauthorized comparison shall terminate verification.

Clause ID: CPB-R3-13

Authorization shall combine complete structured state with conservative fail-closed free-text grammar. Every protected domain shall resolve only to unambiguous withholding; positive, unknown, conditional-positive, double-negative, contradictory, or structurally hidden authorization statements shall fail.

Clause ID: CPB-R3-14

Traceability shall resolve clause IDs and semantic clause hashes from immutable specification bytes and shall verify schema pointers, rules, existing and invoked functions, positive and mutation cases, expectations, fresh observations, observed code and surface, reverse mappings, and future obligations.

Clause ID: CPB-R3-15

A future operational-package interface shall load actual immutable manifest and review-receipt bytes and verify their hashes, schemas, package commit, tree and parent, script and support blobs, reviewer authority, decision, reviewed package, issue time, compatibility, accepted specification, and interface version. Hash strings without authorized bytes are insufficient.

Clause ID: CPB-R3-16

The Architecture Impact Assessment and Canonical Delta shall distinguish demonstrated R3 enforcement, rejected R2 claims, remaining draft controls, later operational-package work, later capture authorization, and continuing prohibitions. This remediation does not perform canonical incorporation or grant operational authority.
