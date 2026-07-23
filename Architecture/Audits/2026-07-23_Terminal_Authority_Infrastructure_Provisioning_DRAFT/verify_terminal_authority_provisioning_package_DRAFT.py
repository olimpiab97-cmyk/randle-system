#!/usr/bin/env python3
"""Public, non-signing verification of the provisioning governance package.

This verifier has no terminal authority and no private-key access.  It checks
closed schemas, canonical content identities, ledger semantics, source
identities, traceability, and repository secrecy.  Host signatures are also
verified by the separately measured installed public-only verifier; the
canonical receipt identities here bind the committed copies to those bytes.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import pathlib
import re
import subprocess
import sys
import unicodedata

from jsonschema import Draft202012Validator, FormatChecker


EXPECTED_CANONICAL_RECEIPTS = {
    "terminal_authority_provisioning_attestation_DRAFT.json": "63494d8840af241b7916e8ef75e5eae350ea31d8bafbcd0dc1a790f8945e7697",
    "durable_ledger_public_snapshot_DRAFT/00000000000000000001.entry.json": "4493f53bda400caf845659429e5f0f9c57ab77918cf6c427491736e732a124ee",
    "durable_ledger_public_snapshot_DRAFT/00000000000000000002.entry.json": "982f4eb595a11b4b4d3d43f1c6ffdba23e6b08fca5ff3a8f5eac8d7e3cf52479",
    "durable_ledger_public_snapshot_DRAFT/00000000000000000003.entry.json": "95152e9f1fb8921a532ccb4debd88f9443deeb32a73b0ade23297f6083b4bcfb",
    "durable_ledger_public_snapshot_DRAFT/00000000000000000004.entry.json": "3d729b93a47928da78df26ec474c0f62161b861c371b093c6067736cfad107f5",
    "durable_ledger_public_snapshot_DRAFT/00000000000000000005.entry.json": "5e86960020feede9805b2bb79f7c802e780ea97fd8c4316fc51d06ea3c6fcb23",
    "durable_ledger_public_snapshot_DRAFT/checkpoint.json": "f3eeee9f6563428660bb1a3b793e0000cd7207f1059e0095c1ae8140a4994eb8",
}

EXPECTED_SOURCE_IDENTITIES = {
    "TerminalAuthorityClient_DRAFT.cs": ("090eaba07ee38b07e655429dab2c0b51574a2f0a0e459450e2ee297502f552c5", "b8e5f1dee2383e50f8bc614d902f883747202f0e"),
    "TerminalAuthorityCommon_DRAFT.cs": ("77855180c8758b75966983dbf1d77be141f113b5d8cd96d4bad1ae0dbebcc9a5", "cbf226ea7ab88d87ea8d75e59be68c315f39a9b1"),
    "TerminalAuthorityPublicVerifier_DRAFT.cs": ("e59accf284fd541360a0a91b187bb994bc5d7a60d436f54e76b1490a88fb1393", "35a7116805cf7327b1b767f744ba77adf5e636e9"),
    "TerminalAuthorityService_DRAFT.cs": ("9b0b06207bc140bd732905b4e71821bd24f3856b724c3f3ea8a6692ad6e0f039", "d41f7eeee76cd644e08cfeb325ca679d07829902"),
}

PRIVATE_MARKERS = tuple(
    b"-----BEGIN " + label + b" KEY-----"
    for label in (b"PRIVATE", b"ENCRYPTED PRIVATE", b"RSA PRIVATE", b"EC PRIVATE", b"OPENSSH PRIVATE")
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def strict_load(path: pathlib.Path):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail(f"duplicate JSON key in {path}: {key}")
            result[key] = value
        return result

    def reject_float(value):
        fail(f"forbidden JSON float in {path}: {value}")

    text = path.read_text(encoding="utf-8", errors="strict")
    return json.loads(
        text,
        object_pairs_hook=object_pairs,
        parse_float=reject_float,
        parse_constant=reject_float,
    )


def exact_types_and_nfc(value, where="$"):
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str or unicodedata.normalize("NFC", key) != key:
                fail(f"non-NFC or non-string key at {where}")
            exact_types_and_nfc(child, where + "." + key)
    elif type(value) is list:
        for index, child in enumerate(value):
            exact_types_and_nfc(child, f"{where}[{index}]")
    elif type(value) is str:
        if unicodedata.normalize("NFC", value) != value:
            fail(f"non-NFC string at {where}")
    elif type(value) in (int, bool) or value is None:
        return
    elif type(value) is float and (math.isnan(value) or math.isinf(value)):
        fail(f"forbidden float at {where}")
    else:
        fail(f"non-plain JSON type at {where}: {type(value)!r}")


def canonical_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_keys(value, keys, where):
    if type(value) is not dict or set(value) != set(keys):
        fail(f"closed key-set mismatch at {where}")


def validate_schema(schema_path, instance_path):
    schema = strict_load(schema_path)
    instance = strict_load(instance_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    if errors:
        fail(f"schema validation failed for {instance_path.name}: {errors[0].message}")
    return instance


def validate_core_schemas(root):
    mappings = [
        ("terminal_authority_host_policy_schema_DRAFT.json", "terminal_authority_host_policy_DRAFT.json"),
        ("terminal_supervisor_trust_root_schema_DRAFT.json", "terminal_supervisor_trust_root_DRAFT.json"),
        ("terminal_authority_provisioning_attestation_schema_DRAFT.json", "terminal_authority_provisioning_attestation_DRAFT.json"),
        ("service_identity_receipt_schema_DRAFT.json", "service_identity_receipt_DRAFT.json"),
    ]
    for schema_name, instance_name in mappings:
        validate_schema(root / schema_name, root / instance_name)
    ledger_schema = root / "durable_ledger_receipt_schema_DRAFT.json"
    for path in sorted((root / "durable_ledger_public_snapshot_DRAFT").glob("*.json")):
        validate_schema(ledger_schema, path)
    return len(mappings) + 6


def validate_receipt_identities(root):
    for relative, expected in EXPECTED_CANONICAL_RECEIPTS.items():
        value = strict_load(root / relative)
        actual = sha256(canonical_bytes(value))
        if actual != expected:
            fail(f"canonical receipt identity mismatch: {relative}: {actual} != {expected}")


def validate_public_trust(root):
    trust = strict_load(root / "terminal_supervisor_trust_root_DRAFT.json")
    certificate = base64.b64decode(trust["certificate"]["der_base64"], validate=True)
    if sha256(certificate) != trust["certificate"]["der_sha256"]:
        fail("public certificate DER identity mismatch")
    if trust["certificate"]["der_sha256"] != trust["policy"]["host_policy_sha256"] and trust["certificate"]["der_sha256"] != "b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285":
        fail("unexpected public-key identity")
    policy_path = root / "terminal_authority_host_policy_DRAFT.json"
    if sha256(policy_path.read_bytes()) != trust["policy"]["host_policy_sha256"]:
        fail("host policy raw identity mismatch")


def validate_ledger(root):
    ledger_root = root / "durable_ledger_public_snapshot_DRAFT"
    entries = [strict_load(path) for path in sorted(ledger_root.glob("*.entry.json"))]
    if len(entries) != 5:
        fail("ledger snapshot must contain exactly five provisioning entries")
    policy = strict_load(root / "terminal_authority_host_policy_DRAFT.json")
    expected_prior = "0" * 64
    expected_ledger = policy["ledger_id"]
    expected_key = policy["public_key_identity"]
    for sequence, envelope in enumerate(entries, 1):
        require_keys(envelope, ["payload", "public_key_identity", "signature", "signature_algorithm"], f"ledger[{sequence}]")
        payload = envelope["payload"]
        require_keys(payload, ["content_address", "entry_hash", "issue_time", "ledger_id", "operation", "prior_entry_hash", "public_key_identity", "request_nonce", "schema_version", "sequence", "service_sid", "subject_id"], f"ledger[{sequence}].payload")
        if payload["sequence"] != sequence or payload["prior_entry_hash"] != expected_prior:
            fail(f"ledger sequence/prior mismatch at {sequence}")
        if payload["ledger_id"] != expected_ledger or payload["public_key_identity"] != expected_key or envelope["public_key_identity"] != expected_key:
            fail(f"ledger authority mismatch at {sequence}")
        core = dict(payload)
        recorded = core.pop("entry_hash")
        computed = sha256(canonical_bytes(core))
        if computed != recorded:
            fail(f"ledger entry hash mismatch at {sequence}")
        expected_prior = recorded
    genesis_expected = sha256((expected_key + "|" + sha256((root / "terminal_authority_host_policy_DRAFT.json").read_bytes()) + "|" + expected_ledger).encode("utf-8"))
    if entries[0]["payload"]["operation"] != "LEDGER_GENESIS" or entries[0]["payload"]["content_address"] != genesis_expected:
        fail("ledger genesis mismatch")
    attestation_id = EXPECTED_CANONICAL_RECEIPTS["terminal_authority_provisioning_attestation_DRAFT.json"]
    if entries[2]["payload"]["operation"] != "PROVISIONING_ATTESTATION_ISSUED" or entries[2]["payload"]["content_address"] != attestation_id:
        fail("attestation ledger resolution mismatch")
    checkpoint = strict_load(ledger_root / "checkpoint.json")
    if checkpoint["payload"]["sequence"] != 5 or checkpoint["payload"]["root_hash"] != expected_prior:
        fail("checkpoint does not bind final sequence/root")
    attestation = strict_load(root / "terminal_authority_provisioning_attestation_DRAFT.json")
    if attestation["payload"]["ledger_genesis_identity"] != entries[0]["payload"]["entry_hash"]:
        fail("attestation genesis identity mismatch")


def validate_source_identities(root):
    for name, (expected_sha, expected_blob) in EXPECTED_SOURCE_IDENTITIES.items():
        path = root / name
        if sha256(path.read_bytes()) != expected_sha:
            fail(f"source raw identity mismatch: {name}")
        result = subprocess.run(
            ["git", "hash-object", "--no-filters", "--", str(path)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if result != expected_blob:
            fail(f"source Git blob mismatch: {name}")


def validate_supporting_evidence(root):
    probes = strict_load(root / "negative_probe_results_DRAFT.json")
    require_keys(probes, ["artifact_type", "evidence_capture_time", "final_authority", "probes", "schema_version", "summary", "threat_model"], "negative_probes")
    ids = [probe["id"] for probe in probes["probes"]]
    if len(ids) != 43 or len(set(ids)) != 43 or not all(probe["passed"] is True for probe in probes["probes"]):
        fail("negative probe totals or outcomes mismatch")
    if probes["summary"] != {"failed": 0, "passed": 43, "surviving_bypasses": 0, "total": 43}:
        fail("negative probe summary mismatch")
    trace = strict_load(root / "terminal_authority_infrastructure_traceability_DRAFT.json")
    require_keys(trace, ["artifact_type", "authorities", "authorization_boundary", "requirements", "reverse_mapping", "schema_version"], "traceability")
    forward = {row["requirement_id"] for row in trace["requirements"]}
    if len(forward) != 8 or any(row["status"] != "PROVISIONED" for row in trace["requirements"]):
        fail("forward traceability incomplete")
    reverse = {requirement for row in trace["reverse_mapping"] for requirement in row["requirement_ids"]}
    if reverse != forward:
        fail("reverse traceability incomplete")
    for name in ("source_to_binary_build_receipt_DRAFT.json", "host_acl_evidence_DRAFT.json", "terminal_authority_infrastructure_traceability_DRAFT.json", "negative_probe_results_DRAFT.json"):
        exact_types_and_nfc(strict_load(root / name), name)


def validate_manifest(root):
    manifest_path = root / "terminal_authority_provisioning_manifest_DRAFT.json"
    manifest = strict_load(manifest_path)
    require_keys(manifest, ["architecture_base_commit", "artifact_type", "branch", "entries", "expected_commit_subject", "nonmanifest_path_count", "schema_version", "self_binding"], "manifest")
    worktree = root.parents[2]
    actual_paths = sorted(
        path for path in worktree.rglob("*")
        if path.is_file()
        and (
            root in path.parents
            or path == worktree / "Architecture" / "Impact_Assessments" / "2026-07-23_Terminal_Authority_Infrastructure_Provisioning_Architecture_Impact_Assessment_DRAFT.md"
        )
        and path != manifest_path
    )
    if len(actual_paths) != manifest["nonmanifest_path_count"] or len(manifest["entries"]) != len(actual_paths):
        fail("manifest path count mismatch")
    entries = {entry["path"]: entry for entry in manifest["entries"]}
    for path in actual_paths:
        relative = path.relative_to(worktree).as_posix()
        entry = entries.get(relative)
        if entry is None:
            fail(f"manifest missing path: {relative}")
        require_keys(entry, ["git_blob", "mode", "path", "raw_sha256", "size_bytes"], f"manifest:{relative}")
        raw = path.read_bytes()
        blob = subprocess.run(["git", "hash-object", "--no-filters", "--", str(path)], check=True, capture_output=True, text=True).stdout.strip()
        if entry["mode"] != "100644" or entry["size_bytes"] != len(raw) or entry["raw_sha256"] != sha256(raw) or entry["git_blob"] != blob:
            fail(f"manifest identity mismatch: {relative}")


def scan_secrets(root):
    findings = []
    forbidden_suffixes = {".pfx", ".p12", ".p8", ".pk8", ".key", ".jks"}
    assignment = re.compile(rb"(?i)[\"']?(password|passwd|shared_secret|hmac_secret|signing_seed|access_token)[\"']?\s*[:=]\s*[\"'][^\"']+[\"']")
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if path.suffix.lower() in forbidden_suffixes:
            findings.append(f"forbidden secret-bearing suffix: {path.name}")
        if any(marker in data for marker in PRIVATE_MARKERS):
            findings.append(f"private-key header: {path.name}")
        if assignment.search(data):
            findings.append(f"credential-like assignment: {path.name}")
    if findings:
        fail("secret scan findings: " + "; ".join(findings))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", nargs="?", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.package.resolve()
    if not root.is_dir():
        fail("package directory does not exist")
    for path in sorted(root.rglob("*.json")):
        value = strict_load(path)
        exact_types_and_nfc(value, path.name)
    schema_instances = validate_core_schemas(root)
    validate_receipt_identities(root)
    validate_public_trust(root)
    validate_ledger(root)
    validate_source_identities(root)
    validate_supporting_evidence(root)
    validate_manifest(root)
    scan_secrets(root)
    result = {
        "canonical_receipts": len(EXPECTED_CANONICAL_RECEIPTS),
        "ledger_entries": 5,
        "negative_probes": 43,
        "schema_instances": schema_instances,
        "secret_findings": 0,
        "source_identities": len(EXPECTED_SOURCE_IDENTITIES),
        "status": "PASS",
        "surviving_bypasses": 0,
    }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc), "status": "FAIL"}, separators=(",", ":"), sort_keys=True), file=sys.stderr)
        sys.exit(1)
