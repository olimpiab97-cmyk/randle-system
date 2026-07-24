#!/usr/bin/env python3
"""Build the closed R7 terminal-authority service policy."""

from __future__ import annotations

import json
from pathlib import Path


PACKAGE = Path(__file__).resolve().parent


def main() -> int:
    value = {
        "adversarial_probe_authority": {"count": 25, "git_blob": "4694125882526d5bd9abb14b394d17d463d32564", "path": "C:/ProgramData/RandleAI/TerminalAuthority/Config/R7Authorities/r7i_b01_adversarial_probes.json", "raw_sha256": "f5e4d9ac5c68a9190921bdec0b5fee88d11957d47a9d68dd2f95f02eef30ba9d", "size": 6777},
        "allowed_configurations": ["SHORT_AUTOCRLF_TRUE", "SHORT_AUTOCRLF_FALSE", "LONG_AUTOCRLF_TRUE", "LONG_AUTOCRLF_FALSE"],
        "allowed_operations": ["EXECUTE_R7_RUN", "GET_HEALTH", "GET_LEDGER_STATUS", "GET_PUBLIC_TRUST", "GET_R7_RECEIPT", "GET_R7_RECONCILIATION", "ISSUE_R7_ATTEMPT", "RECONCILE_R7_TERMINAL_RECEIPTS"],
        "artifact_type": "R7_REAL_EXECUTION_TERMINAL_AUTHORITY_POLICY",
        "case_authority": {"count": 178, "git_blob": "dae357d801cabdde7ca8a314c83380984161e687", "path": "C:/ProgramData/RandleAI/TerminalAuthority/Config/R7Authorities/r7_real_case_definitions.json", "raw_sha256": "58d6c043b857b6950d375724ef1f05b695028a3778ee47067284148c477b9214", "size": 995804},
        "correction_requirements": {"git_blob": "b781cb5cfed4c2ccc7c91c55ca22f73fb01051a7", "path": "C:/ProgramData/RandleAI/TerminalAuthority/Config/R7Authorities/R7I_B01_CORRECTION_REQUIREMENTS.md", "raw_sha256": "cfeae6afaa86a851b6b44a5bec65922879114d641ffcc24e37d69d328cbe5756", "size": 3788},
        "expectation_authority": {"count": 178, "git_blob": "c21ea8f5ab4b54fc0d0638e9bb20df83c8a88f1d", "path": "C:/ProgramData/RandleAI/TerminalAuthority/Config/R7Authorities/r7_independent_expectations.json", "raw_sha256": "7563a8b8af74f15ad226d61015d0946867fa1d18495143e8206600f1c3c81005", "size": 285399},
        "fixed_roots": {"evidence": "C:/ProgramData/RandleAI/TerminalAuthority/Evidence", "fixture_process_receipts": "C:/ProgramData/RandleAI/TerminalAuthority/Evidence/R7FixtureProcessReceipts", "ledger": "C:/ProgramData/RandleAI/TerminalAuthority/Ledger", "receipts": "C:/ProgramData/RandleAI/TerminalAuthority/Receipts", "reconciliations": "C:/ProgramData/RandleAI/TerminalAuthority/Reconciliations", "responses": "C:/ProgramData/RandleAI/TerminalAuthority/Responses", "sessions": "C:/ProgramData/RandleAI/TerminalAuthority/Sessions"},
        "interface_version": "3.0.0-DRAFT",
        "ledger_id": "899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52",
        "provisioning_commit": "bb04ac54fb328516d0c785f4e6551e6a20d73759",
        "public_key_identity": "b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285",
        "python_runtime_manifest": {"file_count": 3209, "git_blob": "950b69e03584f60202eeab494bab11ab9704d114", "raw_sha256": "35140cb03dad5984572fbccbb99fbfc20a5496440411c5ad21a690656a7471f2", "runtime_root_identity": "1e545dc3e7a1e63563674d5b0774329ab63d54bf61d44bcce7ea7dc5d26d1bc0", "size": 439239},
        "r6_commit": "87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94",
        "r7_records": [{"commit": "06c6805ed52a0d539a73088c097c60dec335462a", "report_git_blob": "1be3b0b5f15ac8e68b88202e0e9d3787b69d1856"}, {"commit": "8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6", "report_git_blob": "dfa98a89049b9596387143c002252d91d608fbfc"}],
        "schema_version": "7.1.0-DRAFT",
        "service_sid": "S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948",
        "subject": {"commit": "f0cfbce97e913a133530dd66a70326b1e03a0fb6", "direct_interface_sha256": "69e18f2cb7273c09db0479aa5318c69a3f1e2104476f1b166e38db7f75a38877", "fixture_host_sha256": "7a82bab5acfa36555d0e3b9cf29084101f8276b4ceba93cd48cc1e85fadf1454", "governed_access_sha256": "716c4168dfd6ea37ac9d01d811f3e687e9136b38dc2fff5cb06f1159979e9fdc", "launcher_sha256": "3445e5effd6398b648afa6898391f4e2b5de34f696dd91bfedc2dc29be4e3877", "ledger_sha256": "ea58dea2c9385f20c2d0761b3fd75670980d4214a168e6be2ab9fb1486313cf7", "python_sha256": "624bbc0586d8855633b875e911883bbef8a0e8b8711e11126df480dd86f54181", "repository": "C:/ProgramData/RandleAI/TerminalAuthority/Config/R7ExecutionSubjectRepository", "service_sha256": "12fcf7209567e565b1314dd7ac0389bbb42da794fc08810ac0fe7d70f407cb57", "tree": "02324c2b2dc3415fa2dbe21144e12ab667bf40d9", "verifier_sha256": "75ca67e6fb7e1d39805cf1be46a36a7b3f550cd877044f8ea350549503ab5461"},
        "synthetic_authority_prohibitions": ["CALLER_RESULT_AUTHORITY", "CONSTRUCTED_ZERO_DISCREPANCIES", "EXPECTATION_TO_OBSERVATION_COPY", "POLICY_IDENTITY_ECHO", "PREDETERMINED_PASS_EVENTS", "PRIOR_RUN_SUBSTITUTION", "UNRESOLVED_CHILD_EVIDENCE"],
        "threat_model": "FILTERED_INTERACTIVE_USER_HOSTILE_ELEVATED_ADMIN_AND_KERNEL_OUT_OF_SCOPE",
        "worker_sha256": "b2971b85de73d999bfa801d047b22c2ec6fc3d6bc5cb5923ea4a9ab240ed4401",
    }
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    (PACKAGE / "r7_terminal_authority_policy_DRAFT.json").write_bytes(raw)
    print(json.dumps({"bytes": len(raw)}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
