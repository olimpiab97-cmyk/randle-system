from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

PACKAGE = pathlib.Path(__file__).resolve().parent
ROOT = PACKAGE.parents[2]
OUTPUT = PACKAGE / "review_manifest.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def is_ancestor(commit: str) -> bool:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    return result.returncode == 0


def main() -> None:
    files = []
    for path in sorted(PACKAGE.rglob("*"), key=lambda value: value.as_posix()):
        if not path.is_file() or path == OUTPUT:
            continue
        data = path.read_bytes()
        files.append(
            {
                "git_blob": git_blob(data),
                "mode": "100644",
                "path": path.relative_to(ROOT).as_posix(),
                "raw_sha256": sha256(data),
                "size": len(data),
            }
        )
    result = {
        "artifact_type": "R7_INDEPENDENT_ACCEPTANCE_REVIEW_MANIFEST",
        "base_candidate_commit": "35add65e8900ce9a48c3a7175e5e61e5e0868a84",
        "disposition": "REJECT — R7 REMEDIATION REQUIRED",
        "file_count_excluding_manifest": len(files),
        "files": files,
        "manifest_self_exclusion": "review_manifest.json is the only excluded file because a file cannot contain its own stable raw/Git identity; its identity is reported after commit.",
        "prohibited_r7_ancestors": {
            "06c6805ed52a0d539a73088c097c60dec335462a": is_ancestor("06c6805ed52a0d539a73088c097c60dec335462a"),
            "8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6": is_ancestor("8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6"),
        },
        "review_branch": git("branch", "--show-current"),
        "schema_version": "1.0.0",
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"file_count_excluding_manifest": len(files), "manifest_sha256": sha256(OUTPUT.read_bytes()), "manifest_git_blob": git_blob(OUTPUT.read_bytes())}, sort_keys=True))


if __name__ == "__main__":
    main()
