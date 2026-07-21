#!/usr/bin/env python3
"""Long-path/ADS/Git-aware draft inventory generator for synthetic roots only."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from boundary_verifier_DRAFT import (
    BoundaryError,
    canonical_repository_path,
    semantic_identity,
    sha256_bytes,
    stored_json_bytes,
    validate_path_set,
)


DRAFT_SCRIPT_VERSION = "2.0.0-DRAFT"
FORBIDDEN_ROOTS = (
    Path(r"C:\Webhook\RandleSystem"),
    Path(r"C:\Users\Trader\OneDrive\RandleRuntimeData"),
)
FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
ERROR_HANDLE_EOF = 38
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class InventoryError(BoundaryError):
    pass


def extended_length_path(path: Path) -> str:
    absolute = str(path.resolve(strict=False))
    if os.name != "nt" or absolute.startswith("\\\\?\\"):
        return absolute
    if absolute.startswith("\\\\"):
        return "\\\\?\\UNC\\" + absolute[2:]
    return "\\\\?\\" + absolute


def _same_root(root: Path, forbidden: Path) -> bool:
    try:
        return os.path.normcase(str(root.resolve(strict=False))) == os.path.normcase(str(forbidden.resolve(strict=False)))
    except OSError:
        return False


def assert_synthetic_root(root: Path) -> None:
    resolved = root.resolve(strict=True)
    for forbidden in FORBIDDEN_ROOTS:
        if _same_root(resolved, forbidden):
            raise InventoryError("PRODUCTION_ROOT_REFUSED", str(resolved))
    marker = resolved / ".boundary_fixture_root"
    if not marker.is_file():
        raise InventoryError("FIXTURE_MARKER_REQUIRED", str(marker))


def _is_reparse(stat_result: os.stat_result) -> bool:
    return bool(getattr(stat_result, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def alternate_data_streams(path: Path) -> list[str]:
    """Return named NTFS streams using FindFirst/FindNextStreamW."""

    if os.name != "nt":
        raise InventoryError("ADS_UNSUPPORTED_ENVIRONMENT", os.name)

    class WIN32_FIND_STREAM_DATA(ctypes.Structure):
        _fields_ = [("StreamSize", ctypes.c_longlong), ("cStreamName", ctypes.c_wchar * 296)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    find_first = kernel32.FindFirstStreamW
    find_first.argtypes = [ctypes.c_wchar_p, ctypes.c_int, ctypes.POINTER(WIN32_FIND_STREAM_DATA), ctypes.c_uint]
    find_first.restype = ctypes.c_void_p
    find_next = kernel32.FindNextStreamW
    find_next.argtypes = [ctypes.c_void_p, ctypes.POINTER(WIN32_FIND_STREAM_DATA)]
    find_next.restype = ctypes.c_bool
    find_close = kernel32.FindClose
    find_close.argtypes = [ctypes.c_void_p]
    find_close.restype = ctypes.c_bool

    data = WIN32_FIND_STREAM_DATA()
    handle = find_first(extended_length_path(path), 0, ctypes.byref(data), 0)
    if handle == INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()
        if error == ERROR_HANDLE_EOF:
            return []
        raise InventoryError("ADS_ENUMERATION_FAILED", f"{path}:winerror={error}")
    streams: list[str] = []
    try:
        while True:
            name = data.cStreamName
            if name != "::$DATA":
                streams.append(name)
            if not find_next(handle, ctypes.byref(data)):
                error = ctypes.get_last_error()
                if error == ERROR_HANDLE_EOF:
                    break
                raise InventoryError("ADS_ENUMERATION_FAILED", f"{path}:winerror={error}")
    finally:
        if not find_close(handle):
            raise InventoryError("ADS_ENUMERATION_FAILED", f"{path}:FindClose")
    return sorted(streams)


def _stat_identity(value: os.stat_result) -> dict[str, Any]:
    return {
        "device": int(value.st_dev),
        "file_id": int(value.st_ino),
        "mode": int(value.st_mode),
        "size": int(value.st_size),
        "mtime_ns": int(value.st_mtime_ns),
        "filesystem_attributes": int(getattr(value, "st_file_attributes", 0)),
    }


def stable_read(
    path: Path,
    mutation_hook: Callable[[Path], None] | None = None,
    ads_probe: Callable[[Path], list[str]] = alternate_data_streams,
) -> tuple[bytes, os.stat_result, os.stat_result, list[str]]:
    before = os.lstat(extended_length_path(path))
    if stat.S_ISLNK(before.st_mode) or _is_reparse(before):
        raise InventoryError("REPARSE_POINT_AMBIGUITY", str(path))
    if not stat.S_ISREG(before.st_mode):
        raise InventoryError("UNSUPPORTED_FILE_TYPE", str(path))
    streams_before = ads_probe(path)
    try:
        with open(extended_length_path(path), "rb") as handle:
            data = handle.read()
    except PermissionError as exc:
        raise InventoryError("PERMISSION_DENIED", str(path)) from exc
    if mutation_hook is not None:
        mutation_hook(path)
    streams_after = ads_probe(path)
    if streams_before != streams_after:
        raise InventoryError("ADS_MUTATED_DURING_SCAN", f"{path}:{streams_before}->{streams_after}")
    if streams_after:
        raise InventoryError("ALTERNATE_DATA_STREAM", f"{path}:{streams_after}")
    after = os.lstat(extended_length_path(path))
    stable_fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns")
    if any(getattr(before, field, None) != getattr(after, field, None) for field in stable_fields):
        raise InventoryError("FILE_MUTATED_DURING_SCAN", str(path))
    if len(data) != before.st_size:
        raise InventoryError("SHORT_READ", str(path))
    return data, before, after, streams_after


def _walk(root: Path, relative: tuple[str, ...] = ()) -> Iterator[tuple[Path, str]]:
    disk = root.joinpath(*relative)
    try:
        with os.scandir(extended_length_path(disk)) as iterator:
            entries = sorted(list(iterator), key=lambda entry: entry.name.encode("utf-8"))
    except PermissionError as exc:
        raise InventoryError("PERMISSION_DENIED", "/".join(relative) or ".") from exc
    for entry in entries:
        if entry.name in {".", ".."} or (not relative and entry.name == ".git"):
            continue
        next_relative = (*relative, entry.name)
        path = root.joinpath(*next_relative)
        rel = canonical_repository_path("/".join(next_relative))
        try:
            item_stat = entry.stat(follow_symlinks=False)
        except PermissionError as exc:
            raise InventoryError("PERMISSION_DENIED", rel) from exc
        if entry.is_symlink() or _is_reparse(item_stat):
            raise InventoryError("REPARSE_POINT_AMBIGUITY", rel)
        if stat.S_ISDIR(item_stat.st_mode):
            yield from _walk(root, next_relative)
        elif stat.S_ISREG(item_stat.st_mode):
            yield path, rel
        else:
            raise InventoryError("UNSUPPORTED_FILE_TYPE", rel)


def _run_git(root: Path, args: list[str], *, input_bytes: bytes | None = None, env: Mapping[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    command = ["git", "-c", "core.longpaths=true", "-C", str(root), *args]
    merged = os.environ.copy()
    if env:
        merged.update(env)
    process = subprocess.run(command, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=merged, check=False)
    if check and process.returncode != 0:
        raise InventoryError("GIT_IDENTITY_FAILED", f"{' '.join(args)}:{process.stderr.decode('utf-8', 'replace')}")
    return process


def _is_git_worktree(root: Path) -> bool:
    return _run_git(root, ["rev-parse", "--is-inside-work-tree"], check=False).returncode == 0


def _git_attributes(root: Path, relative: str) -> dict[str, str]:
    raw = _run_git(root, ["check-attr", "-z", "--all", "--", relative]).stdout
    parts = raw.split(b"\0")
    result: dict[str, str] = {}
    for index in range(0, len(parts) - 2, 3):
        if not parts[index]:
            continue
        result[parts[index + 1].decode("utf-8")] = parts[index + 2].decode("utf-8")
    return dict(sorted(result.items()))


def _git_status(root: Path, relative: str) -> dict[str, Any]:
    raw = _run_git(root, ["status", "--porcelain=v2", "-z", "--ignored", "--untracked-files=all", "--", relative]).stdout
    tracked = _run_git(root, ["ls-files", "--error-unmatch", "--", relative], check=False).returncode == 0
    text = raw.decode("utf-8", "surrogateescape")
    if not raw:
        state = "TRACKED_UNCHANGED" if tracked else "UNTRACKED_SYNTHETIC"
    elif text.startswith("? "):
        state = "UNTRACKED"
    elif text.startswith("! "):
        state = "IGNORED"
    elif text.startswith("2 "):
        state = "RENAMED"
    else:
        state = "TRACKED_CHANGED"
    return {"porcelain_v2_hex": raw.hex().upper(), "state": state, "tracked": tracked}


def _index_blob(root: Path, relative: str) -> str | None:
    raw = _run_git(root, ["ls-files", "--stage", "--", relative]).stdout.decode("utf-8", "replace").strip()
    return raw.split()[1] if raw else None


def _parent_blob(root: Path, relative: str) -> str | None:
    process = _run_git(root, ["rev-parse", "--verify", f"HEAD:{relative}"], check=False)
    return process.stdout.decode("ascii").strip() if process.returncode == 0 else None


def _clean_git_identity(root: Path, relative: str, raw_bytes: bytes, object_format: str) -> tuple[bytes, str]:
    objects = _run_git(root, ["rev-parse", "--git-path", "objects"]).stdout.decode("utf-8").strip()
    objects_path = Path(objects)
    if not objects_path.is_absolute():
        objects_path = root / objects_path
    with tempfile.TemporaryDirectory(prefix="randle_boundary_git_objects_") as temp:
        isolated = Path(temp) / "objects"
        isolated.mkdir()
        env = {
            "GIT_OBJECT_DIRECTORY": str(isolated),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(objects_path.resolve()),
        }
        oid = _run_git(root, ["hash-object", "-w", f"--path={relative}", "--stdin"], input_bytes=raw_bytes, env=env).stdout.decode("ascii").strip()
        cleaned = _run_git(root, ["cat-file", "blob", oid], env=env).stdout
    expected_length = 40 if object_format == "sha1" else 64
    if len(oid) != expected_length:
        raise InventoryError("GIT_OBJECT_FORMAT_MISMATCH", f"{relative}:{oid}")
    return cleaned, oid


def _raw_blob_identity(data: bytes, object_format: str = "sha1") -> str:
    payload = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    return (hashlib.sha1(payload) if object_format == "sha1" else hashlib.sha256(payload)).hexdigest()


def _line_profile(data: bytes) -> dict[str, int]:
    crlf = data.count(b"\r\n")
    return {"crlf": crlf, "lf": data.count(b"\n") - crlf, "cr": data.count(b"\r") - crlf}


def _encoding_profile(data: bytes) -> dict[str, Any]:
    if data.startswith(b"\xef\xbb\xbf"):
        name, bom = "UTF-8", "UTF-8-BOM"
    elif data.startswith((b"\xff\xfe", b"\xfe\xff")):
        name, bom = "UTF-16", "UTF-16-BOM"
    else:
        bom = "NONE"
        try:
            data.decode("utf-8")
            name = "UTF-8"
        except UnicodeDecodeError:
            name = "BINARY_OR_NON_UTF8"
    return {"bom": bom, "profile": name}


def enumerate_inventory(
    root: Path,
    *,
    require_fixture_marker: bool = True,
    mutation_hooks: Mapping[str, Callable[[Path], None]] | None = None,
    denied_paths: set[str] | None = None,
    ads_probe: Callable[[Path], list[str]] = alternate_data_streams,
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if require_fixture_marker:
        assert_synthetic_root(root)
    hooks = mutation_hooks or {}
    denied = denied_paths or set()
    git_worktree = _is_git_worktree(root)
    object_format = _run_git(root, ["rev-parse", "--show-object-format"]).stdout.decode("ascii").strip() if git_worktree else "sha1"
    attributes_file = root / ".gitattributes"
    attributes_bytes = attributes_file.read_bytes() if attributes_file.is_file() else b""
    attributes_sha256 = sha256_bytes(attributes_bytes)
    artifacts: list[dict[str, Any]] = []
    for path, relative in _walk(root):
        if relative == ".boundary_fixture_root":
            continue
        if relative in denied:
            raise InventoryError("PERMISSION_DENIED", relative)
        data, before, after, streams = stable_read(path, hooks.get(relative), ads_probe)
        if git_worktree:
            cleaned, blob = _clean_git_identity(root, relative, data, object_format)
            status_identity = _git_status(root, relative)
            parent_blob = _parent_blob(root, relative)
            index_blob = _index_blob(root, relative)
            attributes = _git_attributes(root, relative)
        else:
            cleaned, blob = data, _raw_blob_identity(data, object_format)
            status_identity = {"porcelain_v2_hex": "", "state": "UNTRACKED_SYNTHETIC", "tracked": False}
            parent_blob = index_blob = None
            attributes = {}
        artifacts.append(
            {
                "canonical_path": relative,
                "path_sha256": sha256_bytes(relative.encode("utf-8")),
                "raw_byte_size": len(data),
                "raw_sha256": sha256_bytes(data),
                "pre_read_identity": _stat_identity(before),
                "post_read_identity": _stat_identity(after),
                "file_mode": stat.S_IMODE(after.st_mode),
                "filesystem_attributes": int(getattr(after, "st_file_attributes", 0)),
                "git_status": status_identity,
                "parent_git_blob": parent_blob,
                "index_git_blob": index_blob,
                "working_tree_git_cleaned_sha256": sha256_bytes(cleaned),
                "working_tree_git_cleaned_size": len(cleaned),
                "computed_git_blob": blob,
                "repository_object_format": object_format,
                "line_ending_profile": _line_profile(data),
                "encoding_profile": _encoding_profile(data),
                "gitattributes_sha256": attributes_sha256,
                "git_attribute_results": attributes,
                "symlink": False,
                "reparse_point": False,
                "external_root_id": None,
                "alternate_data_streams": streams,
                "accessible": True,
                "stable_read": True,
            }
        )
    ordered = sorted(artifacts, key=lambda item: item["canonical_path"].encode("utf-8"))
    validate_path_set(item["canonical_path"] for item in ordered)
    identity_records = [
        {key: item[key] for key in item if key not in {"pre_read_identity", "post_read_identity"}}
        for item in ordered
    ]
    return {
        "schema_version": "2.0.0-DRAFT",
        "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
        "draft_script_version": DRAFT_SCRIPT_VERSION,
        "enumeration_method": "Python os.scandir over extended-length paths; lstat/no-follow; real FindFirstStreamW/FindNextStreamW; stable pre/post stat and ADS reads",
        "artifacts": ordered,
        "inventory_sha256": semantic_identity(identity_records),
        "artifact_path_set_sha256": semantic_identity([item["canonical_path"] for item in ordered]),
        "total_artifact_count": len(ordered),
        "total_bytes": sum(item["raw_byte_size"] for item in ordered),
        "repository_object_format": object_format,
        "gitattributes_sha256": attributes_sha256,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        inventory = enumerate_inventory(args.fixture_root)
    except (BoundaryError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(stored_json_bytes(inventory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
