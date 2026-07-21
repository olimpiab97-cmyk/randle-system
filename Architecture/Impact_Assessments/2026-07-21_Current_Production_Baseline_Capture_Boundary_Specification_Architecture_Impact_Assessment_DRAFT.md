# Architecture Impact Assessment — Current Production Baseline Capture Boundary Specification

Status: **REMEDIATED DRAFT — NOT CANONICAL — PENDING NEW INDEPENDENT REVIEW**
Assessment date: 2026-07-21
Implementation, capture, deployment, restart, and trading authority: **None**

## Decision summary

The proposed specification replaces operator-selected capture scope with a frozen, rule-derived, bidirectionally verified boundary. Its architectural effect is governance and provenance only: it defines what a later authorized capture must bind and how ambiguity stops that attempt. It does not change runtime architecture, production behavior, service topology, test authority, or deployment authority.

## Impact by authority domain

| Domain | Proposed impact | Authority effect | Principal risk and control |
|---|---|---|---|
| Governance | Introduces a draft boundary specification, governed registries, freeze gate, semantic authorization scanner, and attempt ledger | Draft only; new independent review required | False elevation to approval; machine scanning rejects positive or ambiguous authority language |
| Repository provenance | Represents root, common directory, worktree, HEAD, index, status, raw bytes, real Git-clean-filter bytes, trees, modes, attributes, and blobs | Makes later capture claims reproducible | Identity gaps; schemas and full-field equality mutations stop on omission or change |
| Production recovery | Makes the selected file/dependency set reproducible and prevents silent omitted active bytes | Improves future recovery evidence, not recovery authorization | Over- or under-capture; controlled by closure plus unknown-class stop |
| Test authority | Parser-backed rules select production-relevant tests and preserve every governed outcome kind | Tests remain evidence, not approval | Manual test omission; exact five-test authority, content discovery, fixture ownership, and unknown-test stops are executable |
| Runtime authority | Separates repository bytes from mutable runtime databases/data and external runtime dependencies | No runtime read or mutation authority is created | Accidental runtime access; controlled by separate authorization and stop behavior |
| Deployment authority | Captures launcher/config dependencies when relevant but grants no deployment right | No deployment, restart, migration, or cutover authority | Conflating captured launcher with approval; controlled by purpose/authorization clauses |
| Evidence durability | Requires long-path-safe manifests and a frozen complete evidence universe | Evidence becomes independently auditable in a later separately authorized capture | Real extended-path, sentinel, entry/class deletion, count, and semantic-root mutations are enforced |
| Traceability | Links B1–B5 and BR-01–BR-13 to clauses, schemas, functions, independent expectations, observations, and future obligations | Enables independent review | Prose-only claims; reverse coverage rejects orphan clauses, fields, functions, and cases |
| Operational safety | Requires writer-free, stable, isolated, multi-pass operation with zero runtime/deployment/restart indicators | No present operational authority | Full-field freeze and multi-pass mutation matrices, truthful incident facts, and authority failure are executable |
| Future reproducibility | Defines canonical paths, serialization, inventories, environments, and mutation detection | Enables later exact reconstruction of capture decisions | Environment drift; controlled by frozen versions and identities |

## Data and control-flow impact

The proposed future flow is:

`independently accepted specification prerequisite → separately authorized attempt ledger entry → complete disk/Git enumeration → relevance fixed point → exact classification → frozen inventory and receipt → Pass A → Pass B → final reconciliation → durable manifest → provenance commit → independent capture review`

Every transition is gated by immutable identities. A failed gate records a terminal attempt and does not reuse its artifact directory.

## Compatibility and migration

No production migration is required. Existing rejected capture commits `28a4faa8e6abf3c8b4e642c20ca6dc31c4991fc6` and `37c30269ce8fdc9cb0e62fe879058d8279e74799` remain historical evidence only. Recapture-report commit `8633a233480a76d76899d7d7e90ab72574f20c52` remains the provenance base for this draft branch. A future accepted specification can be bound by object identity from a separately based capture branch; it need not make the rejected capture canonical.

## Security and privacy

The boundary scanner can encounter secrets, browser profiles, runtime databases, and machine-specific paths. The specification therefore requires classification before content preservation, exact external-root authority, no runtime-data access without separate authorization, and evidence records that bind machine-specific locations only where necessary. A future implementation must define secret-redaction policy without weakening raw-byte identity; if raw bytes cannot be durably preserved under policy, capture stops.

## Canonical documents requiring future amendment if accepted

No canonical document is amended in this task. If the draft is independently accepted, the minimum future governed incorporation set is:

1. `Architecture/README.md` — add the accepted specification to the authority/status index and point to its review record.
2. `Architecture/06_Randle_AI_Modernization_Charter.md` — incorporate the frozen-boundary, complete-external-binding, and fail-closed evidence requirements into the charter’s evidence standard.
3. `CODEX_TASK_TEMPLATE.md` — add the mandatory boundary-freeze, writer scan, attempt ledger, and independent-review gates for future baseline captures.
4. The accepted successor of `Architecture/14_Randle_AI_Runtime_Recovery_Verification_Specification_DRAFT.md` — cross-reference complete outcome preservation and clarify that verification evidence does not approve captured implementation.
5. `Architecture/07_Randle_AI_Modernization_Roadmap.md` — insert the independently accepted pre-capture boundary specification and freeze gate into recovery sequencing before any new baseline capture.

The Constitution, lifecycle, interface, decision, observability, and state-boundary specifications do not require semantic amendment because this proposal does not change runtime behavior or authority. They may receive nonnormative cross-references only if a later architecture owner finds them useful. The Roadmap is an incorporation target because the prerequisite and freeze gate change governed recovery sequencing, not runtime design.

## Remediation enforcement status

The earlier draft overstated fixture enforcement. This remediation limits the assessment to controls exercised by the package: parser-backed Python, launcher, configuration, fixture, route, plugin, subprocess, resource, and test closure; explicit three-way dispositions; exact Git-blob/raw-byte package authority; real NTFS stream detection; full raw/Git identity records; complete freezes; independently frozen attempt/evidence universes; source-bound nonempty classification; full multi-pass equality; independent expectations; and semantic governance scanning. The draft scripts still refuse production roots and are not an operational capture implementation.

## Assessment conclusion

The draft has a positive governance and provenance impact and no authorized runtime impact. Its material cost is stricter stop behavior and broader evidence enumeration; that cost is intentional because a baseline that cannot prove its boundary is not recoverable governance evidence. Independent review remains mandatory before incorporation or use.
