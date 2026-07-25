from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent


def row(i: int, category: str, attack: str, classification: str, evidence: str, mutates_host: bool = False):
    return {
        "attack": attack,
        "category": category,
        "classification": classification,
        "evidence": evidence,
        "id": f"IAP-{i:03d}",
        "host_mutation_required_for_live_exploit": mutates_host,
    }


ROWS = [
    row(1, "semantic_graph", "Missing child evidence hidden behind a signed parent", "CONFIRMED_STATIC_BYPASS", "Service checks child-reported inner hashes/receipt IDs but does not resolve inner receipt body/signature/token/subject-ledger membership."),
    row(2, "semantic_graph", "Valid evidence attached to the wrong case", "STATIC_REJECTION_PRESENT", "Outer request, response and event case_id equality is checked; no live mutation was needed."),
    row(3, "semantic_graph", "Valid event attached to the wrong expectation", "STATIC_REJECTION_PRESENT", "case_id-indexed expectation comparison rejects direct cross-attachment."),
    row(4, "semantic_graph", "Two cases share one process invocation when isolation is required", "CONFIRMED_DESIGN_BYPASS", "All 178 execute_case exchanges intentionally share one Python subject process; case definitions' isolation rules are not consumed."),
    row(5, "semantic_graph", "Correct response with wrong side effects", "CONFIRMED_STATIC_BYPASS", "Required/forbidden side-effect fields have zero verifier references; outer delta is hard-constrained to zero and subject delta only to >=1."),
    row(6, "semantic_graph", "Correct side effects with wrong response", "STATIC_REJECTION_PRESENT", "Expected status/classification comparison rejects a directly wrong response."),
    row(7, "semantic_graph", "Unknown extra child evidence ignored", "CONFIRMED_STATIC_BYPASS", "Raw-evidence locator content and unreferenced files are not closed against semantic extras; only selected locators are resolved."),
    row(8, "semantic_graph", "Conflicting duplicate event with favorable ordering", "STATIC_REJECTION_PRESENT", "Duplicate case IDs and required count are checked in current source."),
    row(9, "semantic_graph", "Reordered events change semantics", "UNRESOLVED_STATIC_GAP", "Hash-chain integrity is checked, but no independently governed per-case ordering semantics is enforced."),
    row(10, "semantic_graph", "Stale but later-signed observation", "CONFIRMED_AUTHORITY_BYPASS", "Same-SID hostile child can use the signing key and stores; observation semantics are copied from events."),
    row(11, "semantic_graph", "Correct individual cases with invalid aggregate terminal conclusion", "CONFIRMED_STATIC_BYPASS", "Aggregate accepts expectation-conditioned case rows and does not independently prove declared side-effect/evidence obligations."),
    row(12, "semantic_graph", "Circular trace mappings", "CONFIRMED_STATIC_BYPASS", "Service checks selected trace fields but no complete reverse resolution or acyclic mapping."),

    row(13, "parser", "Duplicate JSON keys", "CONFIRMED_LIVE_BYPASS", "Live duplicate operation UNKNOWN then GET_HEALTH returned COMPLETE; JavaScriptSerializer collapses to last value; checkpoint unchanged."),
    row(14, "parser", "Differing canonical JSON representation", "CONFIRMED_STATIC_BYPASS", "Outer IPC parser does not canonical-roundtrip request bytes; whitespace/noncanonical outer JSON is accepted before semantic extraction."),
    row(15, "parser", "Unicode-normalized identifiers", "UNRESOLVED_STATIC_GAP", "Outer parser applies no NFC normalization/equality guard."),
    row(16, "parser", "Case-folded path collisions", "CONFIRMED_PATH_CONTROL_GAP", "Windows-insensitive lexical path checks lack final handle/path identity."),
    row(17, "parser", "Integer/string coercion", "CONFIRMED_LOCAL_AND_STATIC_BYPASS", "Independent .NET reproduction converted string \"1\" with the exact Convert.ToInt64 pattern used by RequireLong."),
    row(18, "parser", "Null versus absent fields", "MIXED_STATIC_RESULT", "Exact top-level keys reject many forms; nested schema/default semantics are not uniformly runtime enforced."),
    row(19, "parser", "Unknown-field smuggling", "MIXED_STATIC_RESULT", "Top-level request key sets are generally exact, while committed schemas and nested exact-key rules are not uniformly loaded/enforced."),
    row(20, "parser", "Oversized nested object below frame limit", "NOT_EXECUTED_AUTHORIZATION_LIMIT", "Would consume live service parser resources; authored result was not treated as independent evidence."),
    row(21, "parser", "Truncated multibyte data", "STATIC_REJECTION_PRESENT", "Strict UTF-8 decoder is configured; no live state was changed."),
    row(22, "parser", "Multiple objects in one frame", "CONFIRMED_STATIC_FRAMING_GAP", "ReadRequest stops at first LF and does not require end-of-frame/pipe completion; live compound attempt broke the pipe and was not counted as acceptance."),
    row(23, "parser", "Trailing data after first object", "CONFIRMED_STATIC_FRAMING_GAP", "Bytes following the first LF are not bound to the parsed request."),
    row(24, "parser", "Line-ending transformation", "UNRESOLVED_STATIC_GAP", "Outer requests are not bound to canonical LF-only representation."),
    row(25, "parser", "Locale-dependent parsing", "STATIC_REJECTION_PRESENT", "GUID and invariant numeric conversions avoid the identified locale path."),

    row(26, "filesystem_identity", "Junction or symlink substitution", "CONFIRMED_CONTROL_GAP_NOT_LIVE_EXPLOITED", "Path-based lexical prefix/read/hash lacks final no-follow handle validation; one retained junction exists.", True),
    row(27, "filesystem_identity", "Hard-link substitution", "CONFIRMED_CONTROL_GAP_NOT_LIVE_EXPLOITED", "No link-count/file-ID enforcement; current critical paths have link count one.", True),
    row(28, "filesystem_identity", "Alternate data streams", "CONFIRMED_CONTROL_GAP_NOT_LIVE_EXPLOITED", "No stream enumeration/rejection; current scan found zero ADS.", True),
    row(29, "filesystem_identity", "8.3 path alias", "CONFIRMED_CONTROL_GAP_NOT_LIVE_EXPLOITED", "8.3 creation is enabled and aliases exist; no final-path alias rejection.", True),
    row(30, "filesystem_identity", "Rename race", "CONFIRMED_TOCTOU_GAP_NOT_LIVE_EXPLOITED", "Hash/check and later path use are not protected by an immutable held handle.", True),
    row(31, "filesystem_identity", "Read-after-hash replacement", "CONFIRMED_TOCTOU_GAP_NOT_LIVE_EXPLOITED", "No before/after file ID or held handle across governed use.", True),
    row(32, "filesystem_identity", "Mutable ProgramData case or expectation copy", "HOST_CLEAN_BUT_ARCHITECTURE_BROKEN", "Current hashes match; same-SID hostile children have authority in service-owned roots and path reader lacks handle closure.", True),
    row(33, "filesystem_identity", "Evidence-root copy with valid internal hashes", "UNRESOLVED_STATIC_GAP", "Content identity survives copying and service does not independently derive all semantic freshness."),
    row(34, "filesystem_identity", "Worker replacement between measurement and launch", "CONFIRMED_TOCTOU_GAP_NOT_LIVE_EXPLOITED", "Worker is fully measured at startup; launch later uses a path and trusts child self-report.", True),
    row(35, "filesystem_identity", "Comparator replacement between measurement and launch", "CONFIRMED_TOCTOU_AND_SAME_ROLE_GAP", "Comparator is a mode of the same worker and has the same path/token/authority exposure.", True),
    row(36, "filesystem_identity", "Dependency or Python import substitution", "CONFIRMED_DEPENDENCY_GAP_NOT_LIVE_EXPLOITED", "Git is unbound; full Python runtime checked only at service start; user-site is appended.", True),
    row(37, "filesystem_identity", "Wrong executable with copied version metadata", "STATIC_HASH_REJECTION_WITH_SELF_REPORT_GAP", "Pinned image hashes reject simple copying; process/token evidence is partly child-reported and same-SID authority remains."),

    row(38, "service_protocol", "Old client against new service", "REJECTED_LIVE", "Retained v1 client returned INTERFACE_VERSION_REJECTED; checkpoint unchanged."),
    row(39, "service_protocol", "New client against old interface", "NOT_EXECUTED_AUTHORIZATION_LIMIT", "Would require replacing/stopping current service, not authorized.", True),
    row(40, "service_protocol", "Operation downgrade", "CONFIRMED_LIVE_DUPLICATE_KEY_BYPASS", "Duplicate operation keys select last value and bypass first operation semantics."),
    row(41, "service_protocol", "Policy downgrade", "CONFIRMED_GOVERNANCE_GAP_NOT_LIVE_EXPLOITED", "No externally authorized active-version/anti-rollback state.", True),
    row(42, "service_protocol", "Valid signature for wrong operation", "CONFIRMED_SAME_PRINCIPAL_CAPABILITY", "Hostile children can open the same key and modify stores; no per-operation key capability."),
    row(43, "service_protocol", "Valid receipt from superseded binary or policy", "CONFIRMED_TRUST_LIFECYCLE_BYPASS", "v1 attestation does not govern v3 and no supersession/anti-downgrade receipt exists."),
    row(44, "service_protocol", "Nonce reuse across operation types", "STATIC_REJECTION_PRESENT", "Stored request identity conflict is intended to reject cross-operation reuse; no independent concurrency live test."),
    row(45, "service_protocol", "Concurrent conflicting candidate/fresh requests", "NOT_EXECUTED_AUTHORIZATION_LIMIT", "State-changing concurrent live requests were not authorized.", True),
    row(46, "service_protocol", "Reconciliation before both inputs durably committed", "STATIC_REJECTION_PRESENT", "Current reconciler resolves terminal ledger membership before commit."),
    row(47, "service_protocol", "Reconciliation against superseded receipt", "CONFIRMED_LIFECYCLE_GAP", "There is no governed supersession/terminal-state model."),
    row(48, "service_protocol", "Response replay after service restart", "NOT_EXECUTED_AUTHORIZATION_LIMIT", "Service restart was not authorized; response durability defect is independently established."),
    row(49, "service_protocol", "Disconnect immediately after commit", "CONFIRMED_EXISTING_EVIDENCE", "Seq 678 appended usable attempt, response store failed and client saw REQUEST_REJECTED."),
    row(50, "service_protocol", "Exact 65,536-byte frame", "NOT_EXECUTED_INDEPENDENTLY", "Static limit is 65,536; authored boundary result was not promoted to independent PASS."),
    row(51, "service_protocol", "65,537-byte frame", "NOT_EXECUTED_INDEPENDENTLY", "Static code intends rejection; no independent live request was made."),

    row(52, "ledger_reconciliation", "Stale checkpoint with later entries", "CONFIRMED_FATAL_RECOVERY_GAP", "Restart verifier requires checkpoint == final entry and has no forward recovery."),
    row(53, "ledger_reconciliation", "Later checkpoint with missing entries", "STATIC_REJECTION_PRESENT", "Strict checkpoint/chain equality rejects this state."),
    row(54, "ledger_reconciliation", "Detached valid receipt", "STATIC_REJECTION_PRESENT", "Public/service verifier checks authoritative ledger membership for terminal/reconciliation receipts."),
    row(55, "ledger_reconciliation", "Correct receipt under copied ledger", "STATIC_FIXED_ROOT_REJECTION_PRESENT", "Runtime paths are fixed, though a public offline copied-root threat was not exhaustively executed."),
    row(56, "ledger_reconciliation", "Candidate/fresh semantic equality with partial evidence inequality", "CONFIRMED_SEMANTIC_GAP", "Unconsumed required/forbidden evidence can differ while compared summaries remain equal."),
    row(57, "ledger_reconciliation", "Candidate/fresh share one child process", "STATIC_REJECTION_PRESENT", "Current runs launch distinct process IDs and reconciliation checks selected provenance fields."),
    row(58, "ledger_reconciliation", "Candidate/fresh share one event subtree", "STATIC_REJECTION_PRESENT", "Run IDs/event roots and current locators are compared for disjointness."),
    row(59, "ledger_reconciliation", "Two invalid graphs reconcile to same summary", "CONFIRMED_ARCHITECTURE_BYPASS", "Both expectation-conditioned graphs can pass the same shallow terminal verifier and reconcile."),
    row(60, "ledger_reconciliation", "Valid old reconciliation replayed against new terminal receipts", "STATIC_REJECTION_PRESENT", "Reconciliation receipt binds exact terminal locators/claims."),
    row(61, "ledger_reconciliation", "Conflicting later terminal state", "CONFIRMED_LIFECYCLE_GAP", "No supersession/conflict state machine defines authoritative latest terminality."),
    row(62, "ledger_reconciliation", "Reservation without completion", "NOT_LIVE_PRESENT_BUT_CRASH_WINDOW_UNVERIFIED", "Current ledger pairs 64/64 terminal and 31/31 reconciliation; crash injection was not authorized."),
    row(63, "ledger_reconciliation", "Duplicate completion", "STATIC_SERVICE_REJECTION_BUT_SAME_SID_DIRECT_CAPABILITY", "Normal idempotency should reject; same-SID hostile child can sign/append directly.", True),
]


def main() -> None:
    definitions = {
        "artifact_type": "R7_INDEPENDENT_ADVERSARIAL_PROBE_DEFINITIONS",
        "candidate_commit": "35add65e8900ce9a48c3a7175e5e61e5e0868a84",
        "count": len(ROWS),
        "probes": [{k: v for k, v in item.items() if k not in {"classification", "evidence"}} for item in ROWS],
        "schema_version": "1.0.0",
    }
    results = {
        "artifact_type": "R7_INDEPENDENT_ADVERSARIAL_PROBE_RESULTS",
        "candidate_commit": "35add65e8900ce9a48c3a7175e5e61e5e0868a84",
        "count": len(ROWS),
        "disposition": "FAIL_BLOCKING_BYPASSES_SURVIVE",
        "results": ROWS,
        "schema_version": "1.0.0",
        "summary": {
            key: sum(item["classification"].startswith(key) for item in ROWS)
            for key in ("CONFIRMED", "REJECTED", "STATIC", "NOT", "UNRESOLVED", "MIXED", "HOST")
        },
    }
    (ROOT / "INDEPENDENT_ADVERSARIAL_PROBE_DEFINITIONS.json").write_text(
        json.dumps(definitions, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (ROOT / "INDEPENDENT_ADVERSARIAL_PROBE_RESULTS.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"count": len(ROWS), "status": results["disposition"]}, sort_keys=True))


if __name__ == "__main__":
    main()
