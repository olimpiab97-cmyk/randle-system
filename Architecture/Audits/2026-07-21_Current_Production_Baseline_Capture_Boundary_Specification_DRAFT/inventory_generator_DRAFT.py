#!/usr/bin/env python3
"""Long-path/ADS/Git-aware draft inventory for fixtures and accepted read-only worktrees."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import re
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
    require,
    sha256_bytes,
    stored_json_bytes,
    validate_path_set,
)
from governed_file_access_DRAFT import GovernedAccessError
from governed_file_access_DRAFT import extended_length_path as governed_extended_length_path
from governed_file_access_DRAFT import read_binary as governed_read_binary
from governed_file_access_DRAFT import read_named_stream


DRAFT_SCRIPT_VERSION = "3.0.0-DRAFT"
FORBIDDEN_ROOTS = (
    Path(r"C:\Webhook\RandleSystem"),
    Path(r"C:\Users\Trader\OneDrive\RandleRuntimeData"),
)
FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
ERROR_HANDLE_EOF = 38
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
FILE_READ_EA = 0x0008
FILE_READ_ATTRIBUTES = 0x0080
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000


class InventoryError(BoundaryError):
    pass


def extended_length_path(path: Path) -> str:
    return governed_extended_length_path(path)


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


def assert_governed_read_only_root(root: Path, accepted_commit: str) -> None:
    """Permit an exact, clean, non-production worktree for read-only derivation."""

    resolved = root.resolve(strict=True)
    for forbidden in FORBIDDEN_ROOTS:
        if _same_root(resolved, forbidden):
            raise InventoryError("PRODUCTION_ROOT_REFUSED", str(resolved))
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", accepted_commit or ""):
        raise InventoryError("GOVERNED_REPOSITORY_COMMIT", accepted_commit)
    if not _is_git_worktree(resolved):
        raise InventoryError("GOVERNED_REPOSITORY_REQUIRED", str(resolved))
    head = _run_git(resolved, ["rev-parse", "HEAD"]).stdout.decode("ascii").strip().lower()
    if head != accepted_commit:
        raise InventoryError("GOVERNED_REPOSITORY_HEAD", f"{head}!={accepted_commit}")
    status = _run_git(resolved, ["status", "--porcelain=v2", "-z", "--untracked-files=all"]).stdout
    if status:
        raise InventoryError("GOVERNED_REPOSITORY_DIRTY", status.hex().upper())


def _is_reparse(stat_result: os.stat_result) -> bool:
    return bool(getattr(stat_result, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def alternate_data_streams(path: Path) -> list[str]:
    """Return named NTFS streams using FindFirst/FindNextStreamW."""

    if os.name != "nt":
        raise InventoryError("ADS_UNSUPPORTED_ENVIRONMENT", os.name)

    class WIN32_FIND_STREAM_DATA(ctypes.Structure):
        _fields_ = [("StreamSize", ctypes.c_longlong), ("cStreamName", ctypes.c_wchar * 296)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
    create_file.restype = ctypes.c_void_p
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_bool
    find_first = kernel32.FindFirstStreamW
    find_first.argtypes = [ctypes.c_wchar_p, ctypes.c_int, ctypes.POINTER(WIN32_FIND_STREAM_DATA), ctypes.c_uint]
    find_first.restype = ctypes.c_void_p
    find_next = kernel32.FindNextStreamW
    find_next.argtypes = [ctypes.c_void_p, ctypes.POINTER(WIN32_FIND_STREAM_DATA)]
    find_next.restype = ctypes.c_bool
    find_close = kernel32.FindClose
    find_close.argtypes = [ctypes.c_void_p]
    find_close.restype = ctypes.c_bool

    governed_path = extended_length_path(path)
    access_handle = create_file(
        governed_path,
        FILE_READ_EA | FILE_READ_ATTRIBUTES,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if access_handle == INVALID_HANDLE_VALUE:
        raise InventoryError("ADS_ENUMERATION_FAILED", f"{path}:access-not-proven:winerror={ctypes.get_last_error()}")
    if not close_handle(access_handle):
        raise InventoryError("ADS_ENUMERATION_FAILED", f"{path}:access-handle-close:winerror={ctypes.get_last_error()}")

    data = WIN32_FIND_STREAM_DATA()
    handle = find_first(governed_path, 0, ctypes.byref(data), 0)
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


def _ads_content_identities(path: Path, stream_names: list[str]) -> list[dict[str, Any]]:
    identities: list[dict[str, Any]] = []
    for stream_name in stream_names:
        suffix = stream_name[:-6] if stream_name.endswith(":$DATA") else stream_name
        try:
            payload = read_named_stream(path, suffix)
        except (GovernedAccessError, OSError, PermissionError) as exc:
            raise InventoryError("ADS_ENUMERATION_FAILED", f"{path}:{stream_name}:{exc}") from exc
        identities.append({"stream_name": stream_name, "byte_size": len(payload), "sha256": sha256_bytes(payload)})
    return identities


def stable_read(
    path: Path,
    mutation_hook: Callable[[Path], None] | None = None,
    ads_probe: Callable[[Path], list[str]] = alternate_data_streams,
) -> dict[str, Any]:
    before = os.lstat(extended_length_path(path))
    if stat.S_ISLNK(before.st_mode) or _is_reparse(before):
        raise InventoryError("REPARSE_POINT_AMBIGUITY", str(path))
    if not stat.S_ISREG(before.st_mode):
        raise InventoryError("UNSUPPORTED_FILE_TYPE", str(path))
    streams_before = ads_probe(path)
    stream_identities_before = _ads_content_identities(path, streams_before)
    try:
        first_data = governed_read_binary(path).data
    except (PermissionError, GovernedAccessError) as exc:
        raise InventoryError("PERMISSION_DENIED", str(path)) from exc
    if mutation_hook is not None:
        mutation_hook(path)
    streams_after = ads_probe(path)
    stream_identities_after = _ads_content_identities(path, streams_after)
    try:
        second_data = governed_read_binary(path).data
    except (PermissionError, GovernedAccessError) as exc:
        raise InventoryError("PERMISSION_DENIED", str(path)) from exc
    if streams_before != streams_after or stream_identities_before != stream_identities_after:
        raise InventoryError("ADS_MUTATED_DURING_SCAN", f"{path}:{streams_before}->{streams_after}")
    if streams_after:
        raise InventoryError("ALTERNATE_DATA_STREAM", f"{path}:{streams_after}")
    after = os.lstat(extended_length_path(path))
    stable_fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns")
    if any(getattr(before, field, None) != getattr(after, field, None) for field in stable_fields):
        raise InventoryError("FILE_MUTATED_DURING_SCAN", str(path))
    if len(first_data) != before.st_size or len(second_data) != after.st_size:
        raise InventoryError("SHORT_READ", str(path))
    if sha256_bytes(first_data) != sha256_bytes(second_data):
        raise InventoryError("FILE_CONTENT_MUTATED_DURING_SCAN", str(path))
    return {
        "first_data": first_data,
        "second_data": second_data,
        "first_stat": before,
        "second_stat": after,
        "streams_first": streams_before,
        "streams_second": streams_after,
        "stream_identities_first": stream_identities_before,
        "stream_identities_second": stream_identities_after,
    }


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
    command = ["git", "-c", "core.longpaths=true", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args]
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


def _index_entry(root: Path, relative: str) -> tuple[str | None, str | None]:
    raw = _run_git(root, ["ls-files", "--stage", "--", relative]).stdout.decode("utf-8", "replace").strip()
    return (raw.split()[0], raw.split()[1]) if raw else (None, None)


def _parent_entry(root: Path, relative: str) -> tuple[str | None, str | None]:
    process = _run_git(root, ["ls-tree", "HEAD", "--", relative], check=False)
    raw = process.stdout.decode("utf-8", "replace").strip()
    if process.returncode != 0 or not raw:
        return None, None
    header = raw.split("\t", 1)[0].split()
    return header[0], header[2]


def _git_tree_entries(root: Path) -> dict[str, tuple[str, str]]:
    process = _run_git(root, ["ls-tree", "-rz", "--full-tree", "HEAD"], check=False)
    if process.returncode != 0:
        return {}
    result: dict[str, tuple[str, str]] = {}
    for record in process.stdout.split(b"\0"):
        if not record:
            continue
        header, raw_path = record.split(b"\t", 1)
        mode, kind, oid = header.decode("ascii").split()
        if kind == "blob":
            result[raw_path.decode("utf-8", "surrogateescape")] = (mode, oid)
    return result


def _effective_clean_filter_identity(root: Path, attributes: Mapping[str, str]) -> dict[str, Any]:
    """Bind every repository configuration value capable of changing clean bytes."""
    keys = ["core.autocrlf", "core.eol", "core.safecrlf"]
    driver = attributes.get("filter")
    if driver and driver not in {"set", "unset", "unspecified"}:
        keys.extend(
            [
                f"filter.{driver}.clean",
                f"filter.{driver}.process",
                f"filter.{driver}.required",
            ]
        )
    values: dict[str, str | None] = {}
    for key in keys:
        process = _run_git(root, ["config", "--get", key], check=False)
        values[key] = process.stdout.decode("utf-8", errors="strict").rstrip("\r\n") if process.returncode == 0 else None
    material = {
        "attributes": {key: attributes[key] for key in sorted(attributes) if key in {"text", "eol", "working-tree-encoding", "filter"}},
        "configuration": values,
    }
    return {"material": material, "sha256": semantic_identity(material)}


def _git_index_entries(root: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for record in _run_git(root, ["ls-files", "-s", "-z"]).stdout.split(b"\0"):
        if not record:
            continue
        header, raw_path = record.split(b"\t", 1)
        mode, oid, stage = header.decode("ascii").split()
        if stage == "0":
            result[raw_path.decode("utf-8", "surrogateescape")] = (mode, oid)
    return result


def _git_rename_pairs(root: Path) -> dict[str, str]:
    raw = _run_git(root, ["diff", "HEAD", "--name-status", "-z", "-M"], check=False).stdout
    parts = [item for item in raw.split(b"\0") if item]
    result: dict[str, str] = {}
    index = 0
    while index < len(parts):
        status = parts[index].decode("ascii", "replace")
        index += 1
        if status.startswith("R") or status.startswith("C"):
            require(index + 1 < len(parts), "GIT_RENAME_PARSE", status)
            source = parts[index].decode("utf-8", "surrogateescape")
            destination = parts[index + 1].decode("utf-8", "surrogateescape")
            result[source] = destination
            index += 2
        else:
            index += 1
    return result


def _tombstone_record(
    relative: str,
    object_format: str,
    attributes_sha256: str,
    parent: tuple[str, str] | None,
    index: tuple[str, str] | None,
    rename_destination: str | None,
) -> dict[str, Any]:
    staged_deleted = parent is not None and index is None
    unstaged_deleted = index is not None
    state = "RENAME_SOURCE_TOMBSTONE" if rename_destination else "STAGED_DELETION_TOMBSTONE" if staged_deleted else "UNSTAGED_DELETION_TOMBSTONE"
    return {
        "canonical_path": relative,
        "path_sha256": sha256_bytes(relative.encode("utf-8")),
        "raw_byte_size": None,
        "raw_sha256": None,
        "first_raw_byte_size": None,
        "first_raw_sha256": None,
        "second_raw_byte_size": None,
        "second_raw_sha256": None,
        "pre_read_identity": None,
        "post_read_identity": None,
        "file_mode": int((index or parent or ("0", ""))[0], 8),
        "filesystem_attributes": None,
        "git_status": {"porcelain_v2_hex": "", "state": state, "tracked": True, "staged_deleted": staged_deleted, "unstaged_deleted": unstaged_deleted},
        "parent_git_blob": parent[1] if parent else None,
        "parent_git_mode": parent[0] if parent else None,
        "index_git_blob": index[1] if index else None,
        "index_git_mode": index[0] if index else None,
        "working_tree_git_cleaned_sha256": None,
        "working_tree_git_cleaned_size": None,
        "computed_git_blob": None,
        "repository_object_format": object_format,
        "line_ending_profile": None,
        "encoding_profile": None,
        "gitattributes_sha256": attributes_sha256,
        "git_attribute_results": {},
        "symlink": False,
        "reparse_point": False,
        "external_root_id": None,
        "alternate_data_streams": [],
        "alternate_data_stream_identities_first": [],
        "alternate_data_stream_identities_second": [],
        "accessible": True,
        "stable_read": True,
        "existence_state": "TOMBSTONE",
        "rename_destination": rename_destination,
    }


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
    try:
        attributes_bytes = governed_read_binary(attributes_file).data
    except GovernedAccessError as exc:
        if exc.code != "FILE_MISSING":
            raise InventoryError("GIT_ATTRIBUTES_ACCESS", str(exc)) from exc
        attributes_bytes = b""
    attributes_sha256 = sha256_bytes(attributes_bytes)
    attributes_parent_blob = _parent_entry(root, ".gitattributes")[1] if git_worktree else None
    attributes_computed_blob = _raw_blob_identity(attributes_bytes, object_format) if attributes_bytes else None
    clean_filter_cache: dict[tuple[tuple[str, str], ...], dict[str, Any]] = {}
    artifacts: list[dict[str, Any]] = []
    for path, relative in _walk(root):
        if relative == ".boundary_fixture_root":
            continue
        if relative in denied:
            raise InventoryError("PERMISSION_DENIED", relative)
        stable = stable_read(path, hooks.get(relative), ads_probe)
        data = stable["second_data"]
        before = stable["first_stat"]
        after = stable["second_stat"]
        streams = stable["streams_second"]
        if git_worktree:
            cleaned, blob = _clean_git_identity(root, relative, data, object_format)
            status_identity = _git_status(root, relative)
            parent_mode, parent_blob = _parent_entry(root, relative)
            index_mode, index_blob = _index_entry(root, relative)
            attributes = _git_attributes(root, relative)
            clean_key = tuple(sorted((key, value) for key, value in attributes.items() if key in {"text", "eol", "working-tree-encoding", "filter"}))
            if clean_key not in clean_filter_cache:
                clean_filter_cache[clean_key] = _effective_clean_filter_identity(root, attributes)
            clean_filter_identity = clean_filter_cache[clean_key]
        else:
            cleaned, blob = data, _raw_blob_identity(data, object_format)
            status_identity = {"porcelain_v2_hex": "", "state": "UNTRACKED_SYNTHETIC", "tracked": False}
            parent_mode = index_mode = parent_blob = index_blob = None
            attributes = {}
            clean_filter_identity = {"material": {"attributes": {}, "configuration": {}}, "sha256": semantic_identity({"attributes": {}, "configuration": {}})}
        artifacts.append(
            {
                "canonical_path": relative,
                "path_sha256": sha256_bytes(relative.encode("utf-8")),
                "raw_byte_size": len(data),
                "raw_sha256": sha256_bytes(data),
                "first_raw_byte_size": len(stable["first_data"]),
                "first_raw_sha256": sha256_bytes(stable["first_data"]),
                "second_raw_byte_size": len(stable["second_data"]),
                "second_raw_sha256": sha256_bytes(stable["second_data"]),
                "pre_read_identity": _stat_identity(before),
                "post_read_identity": _stat_identity(after),
                "file_mode": stat.S_IMODE(after.st_mode),
                "filesystem_attributes": int(getattr(after, "st_file_attributes", 0)),
                "git_status": status_identity,
                "parent_git_blob": parent_blob,
                "parent_git_mode": parent_mode,
                "index_git_blob": index_blob,
                "index_git_mode": index_mode,
                "working_tree_git_cleaned_sha256": sha256_bytes(cleaned),
                "working_tree_git_cleaned_size": len(cleaned),
                "computed_git_blob": blob,
                "repository_object_format": object_format,
                "line_ending_profile": _line_profile(data),
                "encoding_profile": _encoding_profile(data),
                "gitattributes_sha256": attributes_sha256,
                "gitattributes_git_blob": attributes_parent_blob,
                "gitattributes_computed_git_blob": attributes_computed_blob,
                "git_attribute_results": attributes,
                "effective_clean_filter_identity": clean_filter_identity,
                "symlink": False,
                "reparse_point": False,
                "external_root_id": None,
                "alternate_data_streams": streams,
                "alternate_data_stream_identities_first": stable["stream_identities_first"],
                "alternate_data_stream_identities_second": stable["stream_identities_second"],
                "accessible": True,
                "stable_read": True,
                "existence_state": "PRESENT",
                "rename_destination": None,
            }
        )
    if git_worktree:
        parent_entries = _git_tree_entries(root)
        index_entries = _git_index_entries(root)
        rename_pairs = _git_rename_pairs(root)
        present = {item["canonical_path"] for item in artifacts}
        governed_missing = sorted((set(parent_entries) | set(index_entries) | set(rename_pairs)) - present, key=lambda item: item.encode("utf-8"))
        for relative in governed_missing:
            canonical_repository_path(relative)
            artifacts.append(_tombstone_record(relative, object_format, attributes_sha256, parent_entries.get(relative), index_entries.get(relative), rename_pairs.get(relative)))
    ordered = sorted(artifacts, key=lambda item: item["canonical_path"].encode("utf-8"))
    validate_path_set(item["canonical_path"] for item in ordered)
    identity_records = [
        {key: item[key] for key in item if key not in {"pre_read_identity", "post_read_identity"}}
        for item in ordered
    ]
    return {
        "schema_version": "3.0.0-DRAFT",
        "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
        "draft_script_version": DRAFT_SCRIPT_VERSION,
        "enumeration_method": "Python os.scandir over extended-length paths; lstat/no-follow; real FindFirstStreamW/FindNextStreamW; two raw content reads and two ADS name/content scans",
        "artifacts": ordered,
        "inventory_sha256": semantic_identity(identity_records),
        "artifact_path_set_sha256": semantic_identity([item["canonical_path"] for item in ordered]),
        "total_artifact_count": len(ordered),
        "total_bytes": sum(item["raw_byte_size"] or 0 for item in ordered),
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
