# Current Production Baseline Capture Boundary Specification

Status: **REMEDIATED DRAFT — NOT CANONICAL — PENDING NEW INDEPENDENT REVIEW**
Implementation authorization: **None**
Capture authorization: **None**
Independent review status: **Pending**
Normative keywords: **SHALL**, **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are normative.

## 1. Purpose and authority

### 1.1 Purpose

This specification defines how a future Current Production Baseline Capture, initiated only after a distinct governed execution approval, derives, freezes, binds, and verifies its complete repository and external-evidence boundary. A conforming capture proves which disk bytes, Git-cleaned bytes, Git objects, path identities, status bytes, and external dependencies existed and were stable during the capture passes.

### 1.2 Limits of proof

A baseline capture is a disk-state and provenance assertion. It does not prove that captured code is correct, architecturally accepted, safe to deploy, ready to trade, or suitable for canonical incorporation. The following authorities are distinct and SHALL NOT be inferred from one another:

1. disk-state capture authority;
2. architecture approval;
3. implementation approval;
4. merge or canonical-incorporation approval;
5. deployment, restart, migration, or cutover approval; and
6. automated-paper or live-money trading authorization.

### 1.3 Governing authority and status

This draft was requested under the governed Randle AI / Entry Agent recovery workflow after `B5_RECAPTURE_REQUIRED`. It is based for provenance on recapture-requirement report commit `8633a233480a76d76899d7d7e90ab72574f20c52` and remediates the enforcement defects found in independent review of specification commit `a9bc860da0ce4296bb6d93b3e1120489d72a2d3b`. It is not canonical. Independent acceptance would establish only that the document is eligible to be considered as a prerequisite in a later, separately authorized capture-execution task; acceptance grants no execution authority.

## 2. Repository identity

### 2.1 Bound identity set

Before selection and before every pass, the capture SHALL bind:

- the user-supplied repository root and its resolved extended-length Windows path;
- volume GUID, volume serial number, filesystem type, root directory file identifier, and case-sensitivity setting;
- `git rev-parse --git-common-dir`, `git rev-parse --show-toplevel`, and the active worktree path;
- current branch full ref or an explicit detached-HEAD state;
- HEAD object identifier, commit, parent set, and tree;
- raw Git index path, byte size, SHA-256, file identity, and a canonical `git ls-files --stage -z` identity;
- exact raw bytes and SHA-256 of `git status --porcelain=v2 -z --branch --untracked-files=all` plus a separate ignored-path enumeration;
- Git object format, Git version, active attributes sources, and configured line-ending behavior; and
- every linked worktree and its administrative relationship, while excluding other worktree contents from the active production boundary.

An identity command that updates the repository object database or index is forbidden during preflight and selection. Git clean-filter execution MAY use `git hash-object -w --path` only with a newly created disposable `GIT_OBJECT_DIRECTORY`; the implementation SHALL prove that neither the repository object database nor index was written and SHALL remove the disposable directory.

### 2.2 Path and filesystem identity

Repository paths SHALL be NFC-normalized, repository-relative, forward-slash paths encoded in UTF-8. Absolute paths, drive prefixes, empty segments, `.`, `..`, NUL, colons, trailing spaces or dots, backslashes, and alternate Win32 aliases are invalid. Sorting SHALL use unsigned UTF-8 byte order. The verifier SHALL reject exact duplicates, Windows case-fold collisions, and Unicode-normalization collisions.

External paths SHALL use a frozen external-root identifier plus an NFC relative path. Each external root SHALL bind its resolved `\\?\` path, volume and directory file identity, authority, allowed traversal policy, and immutability status. Machine-specific absolute paths appear only in the freeze receipt, attempt ledger, and durable evidence bindings; registries use stable root identifiers.

### 2.3 Long paths, links, streams, modes, endings, and encodings

Enumeration and reads SHALL use extended-length Windows paths and APIs that return explicit errors. Hidden and system entries SHALL be enumerated. Directory junctions, mount points, reparse points, and symlinks SHALL NOT be followed by default. A link may be selected only through an exact reviewed entry that binds the link bytes/metadata, target path, target file identity, allowed root, and target bytes; ambiguity stops the attempt.

Every file SHALL be checked for alternate data streams. A named stream stops the attempt unless an exact reviewed rule captures every stream separately. File type and executable/mode identity SHALL be recorded.

Raw disk bytes are authoritative for disk-state identity. SHA-256 includes every byte, BOM, encoding choice, and line ending. Git-cleaned bytes are a separate identity produced under the frozen `.gitattributes` and Git configuration. Both SHALL be retained; neither may substitute for the other. The applicable Git blob identifier and repository object format SHALL be recorded.

## 3. Capture-boundary classes

### 3.1 Reconciliation and precedence

The semantic class and the Git status state are independent. `tracked`, `modified`, `staged`, `untracked`, `ignored`, `deleted`, and `renamed` are status attributes, never grounds for relevance. Every enumerated path SHALL receive exactly one terminal disposition: `INCLUDE`, `EXCLUDE`, or `SEPARATE_AND_BIND`.

Rules are evaluated in this order: invalid-path/security checks; exact governed inclusions; dependency closure; exact exclusions; narrow pattern exclusions; separate-inventory rules. An include/exclude conflict, dependency-to-exclusion conflict, unknown class, or multiple unreconciled terminal dispositions stops the attempt. No rule silently wins a conflict.

### 3.2 Normative class table

| Class | Disposition | Deterministic rule and evidence | Authority / representation | Failure behavior |
|---|---|---|---|---|
| Production runtime source | INCLUDE | Entrypoint seed plus fixed-point dependency closure | Active production authority; raw bytes and Git object | Stop on missing or unresolved dependency |
| Runtime support modules | INCLUDE | Repository-local import, file-open, route, subprocess, or plugin closure | Derived runtime authority; raw and Git identity | Stop on unresolved relationship |
| Repository-local imports | INCLUDE | Resolved AST import closure from selected modules and tests | Derived dependency | Stop on ambiguous module resolution |
| Launch and startup scripts | INCLUDE | Exact launcher seed and parsed command/reference closure | Startup authority | Stop on unresolved command or target |
| Static runtime dependencies | INCLUDE | Literal asset/resource/config reference from selected runtime | Runtime dependency | Stop on missing or inaccessible target |
| Production configuration | INCLUDE | Active configuration selected by launcher, entrypoint, or explicit registry | Production configuration authority for capture only | Stop on unresolved active configuration or secret exposure policy |
| Production tests | INCLUDE | Section 5 discovery and relevance algorithm | Test evidence, not implementation approval | Stop on unknown test disposition |
| Test support modules | INCLUDE | Import and reference closure of selected tests | Derived test dependency | Stop on unresolved support module |
| Test fixtures | INCLUDE when referenced | Parsed fixture declaration or direct reference from selected test | Test input authority | Stop on missing fixture |
| Replay fixtures | INCLUDE when referenced | Replay/scenario input referenced by a selected test or runner | Recovery input authority | Stop on unresolved or mutable input |
| Architecture-required production evidence | INCLUDE by exact registry | Recovery obligation and evidence reference | Capture evidence authority | Stop if missing, changed, or only described in prose |
| Generated-but-authoritative artifacts | INCLUDE by exact registry | Generator identity, source binding, and authority designation | Generated production authority | Stop if generator/source/authority is missing |
| Untracked files | Status-neutral | Apply the same semantic rules as tracked paths | Raw bytes; future commit creates Git object binding | Stop if omitted because untracked |
| Modified tracked files | Status-neutral | Apply semantic rules and bind parent/index/disk identities | Raw disk and Git-cleaned identities | Stop if status or bytes move |
| Ignored files | Explicitly enumerate and classify | `git ls-files --others --ignored --exclude-standard -z` plus disk scan | Include, exclude, or separately bind | Stop on silent omission |
| Deleted paths | Tombstone; selected deletion stops | Porcelain-v2 deletion plus parent/index object identity | Tombstone, old blob, and absence proof | Stop if selected active bytes are required |
| Renamed paths | Reconcile old and new | Porcelain-v2 rename record plus both identities | Old tombstone and new-path capture | Stop on similarity-only ambiguity |
| External runtime dependencies | SEPARATE_AND_BIND | Exact external-root registry and dependency reference | Path, size, SHA-256, role, authority, immutability | Stop if unresolved, inaccessible, or mutable during passes |
| External evidence dependencies | SEPARATE_AND_BIND | Exact evidence registry | Content-addressed durable evidence | Stop if any recovery-critical evidence is unbound |
| Runtime databases and mutable runtime data | SEPARATE_AND_BIND only with separate authority | Exact mutable-state registry; no read in this task | Runtime authority remains external | Stop rather than access without authorization |
| Backups | EXCLUDE by exact root | Reviewed root rule plus closure-conflict check | No active production authority | Stop if uniquely authoritative or referenced |
| Temporary files | EXCLUDE by narrow rule | Exact root/segment and no dependency conflict | Nonauthoritative | Stop on pattern overreach or conflict |
| Caches | EXCLUDE by narrow rule | Exact cache class and no dependency conflict | Reproducible generated state | Stop if treated as authority |
| Logs | SEPARATE_AND_BIND if recovery-critical; otherwise exclude | Exact evidence binding or narrow `.log` class | Command/test logs can be evidence authority | Stop if required log would be omitted |
| IDE/editor files | EXCLUDE by exact root/suffix | Machine-specific editor class and conflict check | No production authority | Stop if runtime consumes the file |
| Build outputs | EXCLUDE unless generated-authoritative | Exact build root plus reproducibility evidence | Generated state | Stop if active runtime depends on unbound output |
| Browser profiles | EXCLUDE by exact registered profile root | Machine-specific browser state and conflict check | No production authority | Stop if used as required evidence without binding |
| Prior worktrees | EXCLUDE contents; bind relationship | `git worktree list --porcelain` and common-dir identity | Repository provenance only | Stop if confused with active worktree |
| Governance-only documents | SEPARATE_AND_BIND when capture evidence; otherwise separate inventory | Exact evidence role or `Architecture/` class | Governance authority, not production bytes | Stop if freeze/provenance record would be omitted |

## 4. Production relevance derivation

### 4.1 Seed set

The seed set SHALL be the union of exact, reviewed registry entries for production entrypoints, launchers, active configuration selectors, static service entrypoints, and mandatory recovery evidence. The registry is a seed set, not the final inventory. Absence from it never establishes exclusion.

### 4.2 Fixed-point closure

The selection script SHALL construct an NFC module/path map and iterate to a fixed point:

1. Parse Python files with the frozen Python AST version. Resolve absolute and relative imports, packages, namespace decisions, and `__init__.py` effects.
2. Resolve literal `importlib.import_module`, `__import__`, plugin, handler, and factory declarations. A nonliteral or environment-dependent target requires an exact dynamic-dependency registry entry; otherwise stop.
3. Parse frozen launch scripts using a named, frozen parser and bind referenced commands, scripts, working directories, environment-file names, configuration, and assets.
4. Parse supported configuration formats and resolve file/module/plugin references. Unknown formats or computed references stop unless governed.
5. Resolve literal runtime file opens, path joins with frozen constants, static assets, templates, route registration, subprocess invocation, module execution, and plugin loading.
6. Resolve selected test imports, fixtures, replay/scenario inputs, subprocess targets, and direct runtime-path references.
7. Repeat until no new path or unresolved edge remains.

Every edge SHALL record source path, source language or format, parser, source location, edge type, rule identifier, literal or declared target, canonical resolved target, resolution status, evidence, and terminal disposition. A literal target absent from enumeration stops selection. Dynamic observation MAY add dependencies but SHALL NOT erase static ones. A computed target is accepted only when an exact, reviewed dynamic-dependency declaration resolves it completely; otherwise the attempt stops.

## 5. Test-selection algorithm

### 5.1 Discovery universe

The scanner SHALL enumerate every tracked, modified, staged, untracked, and ignored file before test selection. It SHALL identify `test_*.py`, `*_test.py`, `*_tests.py`, replay-test names, scenario runners, and run scripts; Python files using `pytest`, `unittest`, test markers, fixture declarations, subprocess test execution, or governed scenario APIs are also candidates regardless of filename.

### 5.2 Inclusion predicates

A candidate test SHALL be included if any deterministic predicate is true:

- it imports a selected runtime module;
- it directly references a selected runtime path or static dependency;
- it executes a selected entrypoint or launcher, including subprocess execution;
- its exact governed category is production recovery, startup/recovery, watchdog, listener/feed health, trade manager, data pipeline, deployment/startup, replay, pipeline, throughput, or KPI/report verification;
- it provides a fixture, helper, or scenario used by an included test; or
- an exact reviewed include entry supplies evidence-backed recovery relevance.

External-service and integration tests are not excluded merely because their service may be unavailable. They are captured when relevant; execution outcome is preserved separately. Archived and backup tests may be excluded only by an exact root/rule with proof that no selected closure reaches them. Generated tests require generator/source authority. Content-duplicated tests remain separate path identities; duplication alone does not permit omission.

Any discovered test not selected by these predicates SHALL have a deterministic, evidence-backed exclusion entry that applies consistently to comparable tests. Otherwise selection stops with `UNKNOWN_TEST_DISPOSITION`. “Not relevant,” “manual choice,” and absence from an allowlist are invalid rationales.

Parameterized cases and subtests do not create separate file-selection paths, but every executed parameterized, subtest, or child outcome SHALL receive its own outcome identity under section 14.

## 6. Five questioned paths

The normative disposition for the next capture is `INCLUDE` for each path below. No future count is predetermined.

| Path | Rule | Reason |
|---|---|---|
| `test_command_center_listener_watchdog.py` | `PRODUCTION_TEST_CLOSURE` | Modified tracked watchdog test omitted without a deterministic exclusion in the rejected capture |
| `test_offline_replay.py` | `PRODUCTION_TEST_CLOSURE` | Modified tracked offline-replay test omitted without a deterministic exclusion |
| `test_kpi_liquidity_atr_distance_report.py` | `PRODUCTION_TEST_CLOSURE` | Untracked KPI/report test omitted without a deterministic exclusion |
| `test_tick_receiver_pipeline.py` | `PRODUCTION_TEST_CLOSURE` | Untracked data-pipeline test omitted without a deterministic exclusion |
| `test_tick_receiver_throughput.py` | `PRODUCTION_TEST_CLOSURE` | Untracked throughput test omitted without a deterministic exclusion |

An accepted future amendment could exclude one only with a new rule, preserved evidence, comparable-path proof, recovery nonimpact proof, independent reproduction, and independent approval before freeze. Removing one after freeze invalidates the attempt.

## 7. Include and exclusion registries

### 7.1 Include registry

`include_registry_schema_DRAFT.json` is normative for the proposed shape. Each entry SHALL contain a stable ID, canonical repository-relative or external-root-relative path, class, selection-rule ID, evidence references, authority status, required capture form, expected existence state, and specific rationale. External entries also require a frozen external-root ID. Exact entries seed derivation or preserve mandatory evidence; they SHALL NOT form a hand-maintained final allowlist. The selection-rule registry has its own schema; every rule referenced by a registry, dependency edge, or terminal disposition SHALL exist exactly once.

### 7.2 Exclusion registry

`exclusion_registry_schema_DRAFT.json` is normative for the proposed shape. Each entry SHALL contain a canonical exact path or narrowly bounded pattern, match type, rule ID, class, exact rationale, evidence, comparable-path consistency proof, authority, reviewer status, and explicit stop behavior. Pattern `*`, `**`, unanchored recursive globs, undocumented predicates, and exclusions conflicting with dependency closure are invalid.

Duplicate entries, include/exclude overlap, invalid rule IDs, missing evidence, missing rationale, pending review at capture authorization, case collisions, and normalization collisions stop the attempt.

### 7.3 Terminal-disposition inventory

Selection SHALL emit one `terminal_disposition_schema_DRAFT.json` record for every enumerated repository path and governed external artifact. An exclusion or separately bound artifact remains visible in that inventory. The `INCLUDE`, `EXCLUDE`, and `SEPARATE_AND_BIND` sets SHALL be pairwise disjoint and their union SHALL equal the governed enumeration universe. Each separately bound item SHALL identify a complete evidence-binding obligation, and every obligation SHALL point back to exactly one separately bound item. Missing, duplicate, conflicting, or orphan records stop selection.

## 8. Inventory generation

### 8.1 Enumeration inputs

The scanner SHALL enumerate the active worktree root and every frozen external root with native extended-length paths. It SHALL combine full no-follow disk enumeration with NUL-delimited Git tracked/index, status, untracked, ignored, deletion, and rename outputs. Hidden and system files are included in enumeration. Git administrative state is bound separately.

### 8.2 Selection, stability, and identities

For every enumerated item the scanner SHALL:

1. canonicalize and collision-check the path;
2. classify type, reparse status, streams, status attributes, semantic class, rule, and disposition;
3. stat before read, read all raw bytes, and stat after read, comparing volume/file ID, mode, size, and high-resolution modification identity;
4. compute raw SHA-256, raw size, canonical-path SHA-256, and file mode;
5. compute Git-cleaned bytes and Git blob identity under frozen attributes without writing an object;
6. record parent and index blob identities when present;
7. add the item to the canonical ordered inventory; and
8. repeat the stable read during Pass B and final verification.

An inaccessible, unhashable, short-read, changed, vanished, appeared, unsupported, or silently skipped item stops the attempt. A selected file changing between selection and binding invalidates the attempt. Deduplication is by canonical path only; content duplicates remain separate records.

### 8.3 Canonical serialization

`RANDLE-CAPTURE-CJSON-1` permits only null, Boolean, integer, NFC string, array, and object values; floating-point values and surrogate code points are forbidden. Object keys are NFC and sorted by Unicode scalar value (equivalent to UTF-8 byte order for valid scalars). JSON uses UTF-8 without BOM, minimal separators, deterministic escapes, and no insignificant whitespace. Semantic identity hashes those bytes with no terminator. Stored JSON contains the semantic bytes followed by exactly one LF, and file SHA-256 includes that LF. Duplicate parsed keys are rejected.

The inventory records exact item count and byte total. The count emerges only after classification and closure; no historical count is an input.

## 9. Specification freeze before Pass A

### 9.1 Freeze package

Before Pass A, a separately authorized capture SHALL write a content-addressed freeze package containing:

- specification commit, parent, tree, document blob, and document raw SHA-256;
- include-registry, exclusion-registry, selection-rule-registry, and boundary-configuration Git blobs and raw SHA-256 values;
- selection-engine, inventory-generator, boundary-verifier, and operational-capture-script Git blobs and raw SHA-256 values;
- generated ordered inventory identity, item count, byte total, and independent included-, excluded-, and separately-bound-set identities;
- Python/runtime version, Git version, operating-system and filesystem identity;
- capture attempt ID, repository HEAD, branch/detached state, index identity, raw status identity, repository object format, and `.gitattributes` identity;
- required-evidence-set identity, attempt-ledger root, and freeze-receipt schema identity;
- timestamp, timestamp authority, initiating identity, reviewer/authorization identity; and
- a self-hashed freeze receipt conforming to `freeze_receipt_schema_DRAFT.json`.

### 9.2 Pass gate

Pass A SHALL refuse to begin until every frozen field is present, hash-valid, independently recomputed, and equal to current state. It SHALL also require an unused attempt ID and a ledger entry. Any post-freeze change to the specification, commit, tree, script, verifier, registry, configuration, inventory, repository, index, status, environment identity, or external evidence invalidates the attempt. The attempt is terminally recorded, and any retry requires a new attempt ID, evidence directory, and freeze receipt.

## 10. Capture-script identity

The operational capture/selection script does not exist in approved form in this draft package. `selection_engine_DRAFT.py`, `inventory_generator_DRAFT.py`, and `boundary_verifier_DRAFT.py` are specification fixtures only and explicitly refuse production use.

Before a future Pass A, the operational script SHALL be committed or externally content-addressed, versioned, raw-byte hashed, Git-blob hashed where applicable, included in the freeze package, opened read-only during passes, and reverified before Pass A, Pass B, and final. The script SHALL verify its own frozen identity and SHALL NOT modify itself, its verifier, registries, or configuration. Preliminary, final, and invoked helper scripts are all governed inputs. An unbound helper or different preliminary/final algorithm stops the attempt, preventing recurrence of the rejected capture’s unbound-script and hard-coded-final-allowlist defect.

## 11. Attempt ledger

Every initiated attempt SHALL receive an append-only ledger record conforming to `attempt_ledger_schema_DRAFT.json`, including unique attempt ID; monotonic sequence; predecessor identity; start/end times; initiating session; repository, specification, script, and inventory identities; worktree; branch; evidence directory; Pass A and Pass B status; staging state; commits; runtime access; production modification; deployment-attempt and service-restart-attempt facts; stop reason; terminal disposition; manifest path/size/SHA-256; and validated relationships to prior attempts. The ledger SHALL bind an independently frozen expected-attempt universe or append-only authority, entry count, previous root, and current semantic root. Removal, reordering, collapse, cycle, nonexistent relationship, or root substitution stops verification.

The terminal types `NO_ARTIFACT`, `PRE_PASS_A_STOP`, `UNSTABLE`, `ABORTED`, `REJECTED`, `SUCCESSFUL`, `SUPERSEDED`, and `REVIEWED` are distinct. A no-artifact/pre-Pass-A record SHALL state explicit `none` for worktree, branch, evidence directory, staging, commits, and manifest and `NOT_STARTED` for both passes. An unstable or later record SHALL bind its manifest and created artifacts. Truthful incident flags SHALL remain representable; a true runtime, production-modification, deployment-attempt, or restart-attempt flag preserves the incident and separately fails capture authority. Contradictory claims, duplicate IDs, missing evidence, or collapsed attempts stop the workflow.

## 12. Long-path-safe durable manifest

### 12.1 Format and method

The durable manifest SHALL conform to `durable_manifest_schema_DRAFT.json`. Enumeration uses resolved `\\?\` roots, no-follow native directory iteration, explicit hidden/system inclusion, and error-count reconciliation. It SHALL list every repository, durable-evidence, command-log, classification, status, and derived-metadata artifact by canonical root-relative path, role, class, byte size, SHA-256, Git blob if applicable, authority, immutability, and recovery requirement. It SHALL record enumeration roots, path API, item count, byte total, and semantic identity.

Missing, extra, duplicate, inaccessible, unhashable, substituted, or changed artifacts and any silent-skip count greater than zero stop the attempt.

### 12.2 B1 regression sentinels

The regression suite SHALL require these exact durable-root-relative paths whenever the source evidence root is selected:

- `raw_files/Architecture/Impact_Assessments/Evidence/2026-07-16_TradingView_Liquidity_Ladder/Randle_AI_Level_Map_Helper_7-16_Erroneous_Categorical_Exclusion_0543DD45.pine`
- `raw_files/Architecture/Impact_Assessments/Evidence/2026-07-16_TradingView_Liquidity_Ladder/Randle_AI_Level_Map_Helper_7-16_Superseded_2A389A_Revision.pine`

This requirement prevents recurrence of the B1 long-path omission. Historical sizes and hashes are regression evidence, not predicted identities for a new capture.

## 13. Durable evidence binding

The complete required-evidence universe SHALL be defined and frozen before capture by registry identity, canonical entry count, canonical path-set identity, required role set, required artifact-class set, total bytes, semantic root, and registry identity. The eventual committed provenance record SHALL cryptographically bind every original or corrective manifest, status artifact, command result, complete test log, complete failure classification, attempt ledger, include registry, exclusion registry, selection specification, selection/capture script, verification script, freeze receipt, YM patch dependency, external dependency, capture commit, tree, parent, path inventory, Git blob, raw hash, count, and byte total.

Each binding SHALL contain canonical path/root ID, role, artifact class, byte size, SHA-256, Git blob when applicable, authority status, immutability status, recovery requirement, source attempt, capture pass, and semantic purpose. Filename-only or prose-only references are invalid. External mutable locations may be referenced only through a content-addressed immutable snapshot or a binding that explicitly declares the source mutable and separately preserves the bound bytes. Removal of one entry or an entire role/class, duplicate, replacement, count/root mismatch, or mutation of any required field stops verification against the independently frozen registry identity.

## 14. Test-result preservation

The future parser SHALL preserve at least `PASSED`, `FAILED`, `SUBFAILED`, `SKIPPED`, `ERROR`, `XFAIL`, and `XPASS`. Every outcome record SHALL contain normalized original identity, parent identity where applicable, outcome, and source-log location. Every `FAILED`, `SUBFAILED`, `ERROR`, and unexpected `XPASS` SHALL additionally contain nonempty category, rationale, source reference, parser name/version, normalization rule, and classification rule. A `SUBFAILED` record SHALL contain a nonempty parent identity.

The classification SHALL bind full-log path, size, SHA-256, parser name/version, normalization rules, classification rules, exact unique outcome-identity-set SHA-256, per-status counts, per-category counts, source total, and accounted total. Parent failures and child/subtest failures remain distinct. Classification cannot relabel a source failure as pass, skip, xfail, or nonfailure. Empty classification, duplicate, omitted, unsupported, source/log mismatch, or total mismatch causes nonzero exit. Schema and semantic validation SHALL agree.

The historical `156 FAILED + 23 SUBFAILED = 179` is a regression vector demonstrating complete failure retention; it is not an assumed result for a future capture.

## 15. Multi-pass stability

### 15.1 Pass A, Pass B, and final

Pass A, Pass B, and final SHALL independently recompute and compare branch/detached identity; HEAD and capture parent; index; status bytes; specification commit/tree/blob; every registry; configuration; selection engine; inventory generator; verifier; operational script; generated inventory; included/excluded/separately-bound sets; raw, Git-cleaned, mode, and path identities; artifact count and byte total; external and required-evidence identities; attempt-ledger root; freeze receipt; `.gitattributes`; writer count; runtime-operation count; and deployment/restart indicators. Writer scans SHALL be repeated before each pass and after final. Runtime operations are forbidden.

The passes SHALL use identical commands, canonicalization, environment identity, and included/excluded fields. Timestamps are ledger metadata and SHALL NOT enter the governed state-comparison identity. Machine-specific fields enter the environment identity and must match across passes but do not prevent a later reviewer from recomputing content identities from preserved evidence.

### 15.2 Mismatch handling

Any writer activity, selected-file mutation, path appearance/disappearance, status difference, branch movement, index movement, external evidence change, or governed identity mismatch terminates the attempt as `UNSTABLE`. No retry output may overwrite prior artifacts.

## 16. Fail-closed rules

The future capture SHALL stop before or during Pass A for an active repository writer; dirty specification branch; changed specification, capture script, verifier, registry, configuration, or inventory; missing selected path; extra governed path; unknown class; unknown test; unsupported dynamic dependency; inaccessible or invalid path; reparse ambiguity; named stream; long-path enumeration discrepancy; hash mismatch; case or Unicode collision; evidence omission; inconsistent attempt ledger; incomplete classification; status mismatch; branch movement; index movement; reused attempt ID; missing freeze receipt; or production mutation.

During Pass B/final, the same conditions terminate the attempt as unstable. No operator may waive a stop interactively. Resolution requires an evidence-backed specification amendment or a new attempt with a new freeze.

## 17. Authorization boundaries

Independent acceptance of this specification would establish a prerequisite only. It grants no permission to execute a baseline capture. A separately requested and separately approved capture-execution task is mandatory. This draft and its fixture results do not authorize merge, canonical incorporation, implementation, production restart, deployment, runtime migration, NQ cutover, automated paper trading, live-money trading, Bucket 0 completion, Bucket 1, Phase 3C2, or Phase 3C1-R11 acceptance.

No production code or captured code is approved by this document. Bucket 0 remains incomplete and Bucket 1 remains blocked.

## Appendix A — Draft verification package

The governed draft package is under `Architecture/Audits/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT/`. Its schemas, registries, verifier, inventory generator, expectation vectors, mutation vectors, independent expectations, fixture runner, fixture results, and machine-readable traceability are specification evidence only.

The scripts SHALL NOT be represented as production capture implementations. Fixture verification SHALL use disposable synthetic roots and SHALL emit no capture, runtime, deployment, merge, or trading operation.

## 18. Executable conformance and remediation

The remediated draft package SHALL enforce clauses 1–17 through Draft 2020-12 schemas and semantic functions. `schema_validation_DRAFT.py` pins `jsonschema` 4.25.1 and validates every schema and active or complete synthetic instance. `selection_engine_DRAFT.py` emits dependency edges and terminal dispositions. `inventory_generator_DRAFT.py` uses real Windows stream enumeration, extended-length paths, no-follow traversal, stable reads, and isolated Git clean filters. `boundary_verifier_DRAFT.py` validates registries, the five mandatory tests, package Git blobs, dispositions, inventories, freezes, ledgers, evidence universes, outcome classifications, stability, traceability, and authorization language.

`fixture_runner_DRAFT.py` SHALL compare observations to the static `independent_expectations_DRAFT.json`; implementation code SHALL NOT generate that expectation file. It SHALL test real filesystem and Git surfaces where supported, report an explicit unsupported-environment failure otherwise, preserve the historical 571/156/23/3 vector, clean every disposable root, and bind fresh observations by a semantic SHA-256. The traceability matrix SHALL map BR-01 through BR-13 and every normative clause to schemas, rules, enforcing functions, cases, expectations, observations, and future capture obligations. Descriptive identifiers alone do not establish coverage.
