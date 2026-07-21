# Traceability Matrix — Current Production Baseline Capture Boundary Specification

Status: **REMEDIATED DRAFT — NOT CANONICAL — PENDING NEW INDEPENDENT REVIEW**

The machine-readable authority is `Architecture/Audits/2026-07-21_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT/traceability_matrix_DRAFT.json`. It maps B1–B5, BR-01–BR-13, clauses 1–18, schemas, machine rules, enforcing functions, static expectations, fresh observations, and future capture obligations. Prefix routing is deterministic: the verifier expands every declared case prefix against the exact fixture case set and rejects missing or orphan cases.

## Historical finding prevention

| Finding | Normative prevention | Executable evidence | Future obligation |
|---|---|---|---|
| B1 — incomplete durable manifest | Clauses 8 and 12; real extended-path enumeration and two exact Pine sentinels | `POS-INVENTORY-LONG-*`, `MUT-LONG-*`, inaccessible and changed-file cases | Select the evidence root only with complete sentinel and manifest reconciliation |
| B2 — missing immutable evidence binding | Clauses 9, 10, and 13; complete frozen evidence universe and package Git-blob authority | `POS-EVIDENCE-*`, `MUT-EVIDENCE-*`, `POS-PACKAGE-*`, `MUT-PACKAGE-*` | Freeze every recovery dependency and bind it in committed provenance |
| B3 — incomplete failure classification | Clause 14; nonempty source-bound classification for all governed failure kinds | `POS-CLASSIFICATION-571-156-23-3`, `MUT-CLASSIFICATION-*` | Preserve the actual future outcomes, including every `SUBFAILED` |
| B4 — unreconciled attempt provenance | Clause 11; independently frozen append-only attempt universe | `POS-ATTEMPT-*`, `MUT-ATTEMPT-*` | Append every initiated attempt and retain truthful incident facts |
| B5 — nonreproducible boundary | Clauses 3–10; parser closure, exact dispositions, five-test authority, package binding, and freeze | `POS-SELECTION-*`, `POS-CLOSURE-*`, `MUT-CLOSURE-*`, `POS-FIVE-*`, `MUT-FIVE-*` | Derive the future count from the accepted frozen rules and disk state |

## Independent-review remediation

| Finding | Clause(s) | Enforcing surface | Principal cases |
|---|---:|---|---|
| BR-01 closure incomplete | 4–5 | parser-backed selection fixed point | `POS-CLOSURE-*`, `POS-PARSER-*`, `POS-TEST-RELATION-*`, `MUT-CLOSURE-*` |
| BR-02 dispositions absent | 3, 7 | terminal-disposition reconciliation | `POS-TERMINAL-*`, `MUT-DISPOSITION-*` |
| BR-03 five-test bypass | 6, 7, 9 | exact registry authority plus committed package bindings | `POS-FIVE-*`, `MUT-FIVE-*`, `MUT-PACKAGE-*` |
| BR-04 shallow schemas | 7, 9, 18 | pinned Draft 2020-12 plus semantic validation | `POS-SCHEMA-*`, `MUT-SCHEMA-*`, `MUT-REGISTRY-*` |
| BR-05 ADS disabled | 2, 8, 12 | real `FindFirstStreamW`/`FindNextStreamW` | `MUT-ADS-*` |
| BR-06 identity incomplete | 2, 8, 12 | full inventory/Git clean-filter model | `POS-INVENTORY-GIT-*`, `MUT-IDENTITY-*` |
| BR-07 freeze incomplete | 9–10 | complete derived freeze receipt | `POS-FREEZE`, `MUT-FREEZE-*` |
| BR-08 attempt completeness | 11 | frozen universe, predecessor chain, incident authority | `POS-ATTEMPT-*`, `MUT-ATTEMPT-*` |
| BR-09 evidence omission | 13 | frozen path/role/class/count/root registry | `POS-EVIDENCE-*`, `MUT-EVIDENCE-*` |
| BR-10 empty classification | 14, 18 | schema plus source/log semantic reconciliation | `POS-CLASSIFICATION-*`, `MUT-CLASSIFICATION-*` |
| BR-11 stability incomplete | 15–16 | equality over every governed field | `POS-MULTIPASS`, `MUT-MULTIPASS-*` |
| BR-12 overclaimed fixtures | 18 | static expectations, observation root, function/schema/case reverse trace | `POS-INDEPENDENCE-*`, `POS-TRACEABILITY-*`, code-binding mutations |
| BR-13 authority leakage | 1, 17, 18 | semantic package-language scanner | `POS-GOVERNANCE-*`, `MUT-GOVERNANCE-*` |

## Reverse coverage

The verifier independently requires:

1. exactly findings BR-01 through BR-13;
2. exactly normative clauses 1 through 18;
3. expansion of requirement case IDs and prefixes to the complete fixture case set;
4. equality between traced enforcing functions and the callable enforcement catalog;
5. governance of every field in every one of the ten schema files through an `ALL_DECLARED_FIELDS` schema mapping;
6. nonempty machine rules, expected result, observed result, and future obligation for every clause and finding; and
7. no descriptive-only claim presented as enforcement.

The static expectation file enumerates each case individually. The positive and mutation vector files route those cases independently by explicit ID or bounded prefix. The result file binds the case set, expectation bytes, and observation semantics by SHA-256. Any missing reverse edge, altered expectation, altered observation, missing function, schema orphan, or untraced case is a blocking discrepancy.

## Authority boundary

This traceability record supplies draft review evidence only. It grants no permission for a baseline capture, merge, canonical incorporation, production implementation, deployment, service restart, runtime migration, NQ cutover, paper or live-money trading, Phase 3C2, Phase 3C1-R11 acceptance, Bucket 0 completion, or Bucket 1 work.
