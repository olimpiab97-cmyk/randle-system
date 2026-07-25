from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import sys

REVIEW = pathlib.Path(__file__).resolve().parent
ROOT = REVIEW.parents[2]
IMPL = ROOT / "Architecture/Audits/2026-07-23_Current_Production_Baseline_Boundary_R7_Terminal_Authority_Implementation_DRAFT"
RUNTIME = pathlib.Path(r"C:\Program Files\RandleAI\TerminalAuthority\PythonRuntime")
STATE = pathlib.Path(r"C:\ProgramData\RandleAI\TerminalAuthority")
MANIFEST = IMPL / "r7_python_runtime_manifest_DRAFT.json"

PATTERNS = {
    "PRIVATE_KEY_TEXT": re.compile(rb"PRIVATE KEY", re.I),
    "OPENAI_STYLE_TOKEN": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "GITHUB_TOKEN": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "AWS_ACCESS_KEY": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "JWT": re.compile(rb"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify(path: pathlib.Path, pattern: str) -> str:
    text = str(path).replace("/", "\\").lower()
    if "pythonruntime\\lib\\test\\certdata" in text:
        return "PUBLIC_CPYTHON_STANDARD_LIBRARY_TEST_FIXTURE"
    if text.endswith(("pythonruntime\\dlls\\libcrypto-3.dll", "pythonruntime\\dlls\\libssl-3.dll")):
        return "PUBLIC_CRYPTO_LIBRARY_DIAGNOSTIC_STRING"
    if text.endswith("pythonruntime\\news.txt"):
        return "PUBLIC_CPYTHON_CHANGELOG_SECURITY_VOCABULARY"
    if "independent_secret_contamination_scan.py" in text:
        return "REVIEW_SCANNER_PATTERN_LITERAL"
    if text.endswith((".cs", ".py", ".ps1", ".md", ".json")) and pattern == "PRIVATE_KEY_TEXT":
        return "SOURCE_OR_REPORT_SECURITY_VOCABULARY"
    return "UNCLASSIFIED_POTENTIAL_SECRET"


def scan_file(path: pathlib.Path, scope: str, hits: list[dict], errors: list[dict]) -> None:
    try:
        data = path.read_bytes()
    except Exception as exc:
        errors.append({"path": str(path), "scope": scope, "error": f"{type(exc).__name__}: {exc}"})
        return
    for name, regex in PATTERNS.items():
        count = len(regex.findall(data))
        if count:
            hits.append(
                {
                    "classification": classify(path, name),
                    "count": count,
                    "file_sha256": sha(data),
                    "path": str(path),
                    "pattern": name,
                    "scope": scope,
                }
            )
    if path.suffix.lower() in {".pfx", ".p12", ".pkcs12"}:
        hits.append(
            {
                "classification": "UNCLASSIFIED_POTENTIAL_SECRET",
                "count": 1,
                "file_sha256": sha(data),
                "path": str(path),
                "pattern": "PKCS12_EXTENSION",
                "scope": scope,
            }
        )


def candidate_paths() -> list[pathlib.Path]:
    safe = ROOT.as_posix()
    output = subprocess.run(
        ["git", "-c", f"safe.directory={safe}", "diff", "--name-only", "bb04ac54fb328516d0c785f4e6551e6a20d73759..35add65e8900ce9a48c3a7175e5e61e5e0868a84"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    return [ROOT / line for line in output.splitlines() if line and (ROOT / line).is_file()]


def main() -> int:
    hits: list[dict] = []
    errors: list[dict] = []
    candidate = candidate_paths()
    review_files = [p for p in REVIEW.rglob("*") if p.is_file() and p.name != "INDEPENDENT_SECRET_AND_CONTAMINATION_SCAN.json"]
    for path in candidate:
        scan_file(path, "CANDIDATE_50_PATH_DELTA", hits, errors)
    for path in review_files:
        scan_file(path, "REVIEW_PACKAGE", hits, errors)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    runtime_mismatches = []
    for item in manifest["files"]:
        path = RUNTIME / pathlib.PurePosixPath(item["path"])
        try:
            data = path.read_bytes()
            actual = sha(data)
            if len(data) != item["size"] or actual != item["sha256"]:
                runtime_mismatches.append({"path": str(path), "expected": item, "actual_sha256": actual, "actual_size": len(data)})
            for name, regex in PATTERNS.items():
                count = len(regex.findall(data))
                if count:
                    hits.append({"classification": classify(path, name), "count": count, "file_sha256": actual, "path": str(path), "pattern": name, "scope": "PINNED_PYTHON_RUNTIME"})
        except Exception as exc:
            errors.append({"path": str(path), "scope": "PINNED_PYTHON_RUNTIME", "error": f"{type(exc).__name__}: {exc}"})

    state_files = [p for p in STATE.rglob("*") if p.is_file()]
    for path in state_files:
        scan_file(path, "DEDICATED_PROGRAMDATA_STATE", hits, errors)

    unclassified = [item for item in hits if item["classification"] == "UNCLASSIFIED_POTENTIAL_SECRET"]
    result = {
        "artifact_type": "R7_INDEPENDENT_SECRET_AND_CONTAMINATION_SCAN",
        "candidate_file_count": len(candidate),
        "errors": errors,
        "hit_count": len(hits),
        "hits": sorted(hits, key=lambda x: (x["scope"], x["path"], x["pattern"])),
        "python_runtime": {
            "expected_file_count": manifest["file_count"],
            "manifest_sha256": sha(MANIFEST.read_bytes()),
            "mismatch_count": len(runtime_mismatches),
            "mismatches": runtime_mismatches,
            "root_identity_claim": manifest["runtime_root_identity"],
        },
        "review_file_count": len(review_files),
        "schema_version": "1.0.0",
        "state_file_count": len(state_files),
        "status": "PASS_NO_UNCLASSIFIED_SECRET" if not unclassified and not errors and not runtime_mismatches else "FAIL_REVIEW_REQUIRED",
        "unclassified_potential_secret_count": len(unclassified),
    }
    output = REVIEW / "INDEPENDENT_SECRET_AND_CONTAMINATION_SCAN.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"errors": len(errors), "hits": len(hits), "runtime_mismatches": len(runtime_mismatches), "status": result["status"], "unclassified": len(unclassified)}, sort_keys=True))
    return 0 if result["status"] == "PASS_NO_UNCLASSIFIED_SECRET" else 1


if __name__ == "__main__":
    raise SystemExit(main())
