# Independent bidirectional traceability review

The implementation claims 1,424 rows (178 cases × eight mappings). Count and internal hash consistency are not sufficient.

## Forward-trace result

The first edge fails for every case: the recorded governing object is the R6 spec blob, but the recorded `R7-*`/`CPB-R7-*` clauses do not exist in that blob. The true source is discarded f0 material. Thus **0/178 cases have a valid exact authority-to-case edge**.

Subsequent edges are also not authoritative:

- expectations are copied from the same discarded implementation model;
- actual events are expectation-conditioned;
- observations copy event values;
- case-declared required/forbidden evidence and effects are not runtime-resolved;
- source process receipts do not prove the interface or side effect;
- terminal verifier accepts child-reported inner identities;
- outer terminal/reconciliation interfaces are absent from the case set;
- upgrade entries have unresolved content addresses;
- host files and dependencies lack complete governed provenance.

## Reverse-trace result

Reverse mappings are incomplete or circular for the discarded f0 subject, Python runtime/import graph, Git executable/dependencies, framework references, installed/stale binaries, host policy/ACL elements, service upgrades, response gaps, incomplete seq-332 state and version-specific public verifiers. Trace rows point back into implementation-authored case/expectation/event summaries rather than independent governing clauses and raw behavior.

## Claimed row verification

All 1,424 claimed rows were structurally accounted for through their 178 case groups, but none can satisfy the complete forward chain because the governing-clause edge is false. This is not a sampling conclusion. The machine audit also confirmed no runtime references to six material obligation fields.

Traceability status: **FAIL — false normative roots, circular provenance, missing semantic and host reverse edges**.
