#!/usr/bin/env python3
"""Draft inventory generator used only by the specification fixture package.

The command-line interface requires an explicitly named synthetic fixture root.
It refuses the production repository and runtime-data roots. A future capture
implementation must be separately reviewed, committed, frozen, and authorized.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Callable, Iterator

from boundary_verifier_DRAFT import (
    BoundaryError,
    canonical_repository_path,
    semantic_identity,
    sha256_bytes,
    stored_json_bytes,
    validate_path_set,
)


DRAFT_SCRIPT_VERSION = "0.1.0-DRAFT"
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


def _same_forbidden_root(root: Path, forbidden: Path) -> bool:
    try:
        return os.path.normcase(str(root.resolve(strict=False))) == os.path.normcase(str(forbidden.resolve(strict=False)))
    except OSError:
        return False


def assert_synthetic_root(root: Path) -> None:
    resolved = root.resolve(strict=True)
    for forbidden in FORBIDDEN_ROOTS:
        if _same_forbidden_root(resolved, forbidden):
            raise InventoryError("PRODUCTION_ROOT_REFUSED", str(resolved))
    marker = resolved / ".boundary_fixture_root"
    if not marker.is_file():
        raise InventoryError("FIXTURE_MARKER_REQUIRED", str(marker))


def _is_reparse(stat_result: os.stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def alternate_data_streams(path: Path) -> list[str]:
    """Return named NTFS data streams; fail closed if enumeration fails."""

    if os.name != "nt":
        return []

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
        raise InventoryError("ADS_ENUMERATION_FAILED", f"{path}: winerror={error}")
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
                raise InventoryError("ADS_ENUMERATION_FAILED", f"{path}: winerror={error}")
    finally:
        find_close(handle)
    return streams


def stable_read(
    path: Path,
    mutation_hook: Callable[[Path], None] | None = None,
    ads_probe: Callable[[Path], list[str]] = alternate_data_streams,
) -> tuple[bytes, os.stat_result]:
    before = os.lstat(extended_length_path(path))
    if stat.S_ISLNK(before.st_mode) or _is_reparse(before):
        raise InventoryError("REPARSE_POINT_AMBIGUITY", str(path))
    if not stat.S_ISREG(before.st_mode):
        raise InventoryError("UNSUPPORTED_FILE_TYPE", str(path))
    streams = ads_probe(path)
    if streams:
        raise InventoryError("ALTERNATE_DATA_STREAM", f"{path}: {streams}")
    try:
        with open(extended_length_path(path), "rb") as handle:
            data = handle.read()
    except PermissionError as exc:
        raise InventoryError("PERMISSION_DENIED", str(path)) from exc
    if mutation_hook is not None:
        mutation_hook(path)
    after = os.lstat(extended_length_path(path))
    stable_fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns")
    if any(getattr(before, field, None) != getattr(after, field, None) for field in stable_fields):
        raise InventoryError("FILE_MUTATED_DURING_SCAN", str(path))
    if len(data) != before.st_size:
        raise InventoryError("SHORT_READ", str(path))
    return data, after


def _walk(root: Path, relative: tuple[str, ...] = ()) -> Iterator[tuple[Path, str]]:
    disk = root.joinpath(*relative)
    try:
        with os.scandir(extended_length_path(disk)) as iterator:
            entries = sorted(list(iterator), key=lambda entry: entry.name.encode("utf-8"))
    except PermissionError as exc:
        rel = "/".join(relative) or "."
        raise InventoryError("PERMISSION_DENIED", rel) from exc
    for entry in entries:
        if entry.name in {".", ".."}:
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


def enumerate_inventory(
    root: Path,
    *,
    require_fixture_marker: bool = True,
    mutation_hooks: dict[str, Callable[[Path], None]] | None = None,
    denied_paths: set[str] | None = None,
    ads_paths: set[str] | None = None,
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if require_fixture_marker:
        assert_synthetic_root(root)
    hooks = mutation_hooks or {}
    denied = denied_paths or set()
    ads = ads_paths or set()
    artifacts: list[dict[str, Any]] = []
    for path, relative in _walk(root):
        if relative == ".boundary_fixture_root":
            continue
        if relative in denied:
            raise InventoryError("PERMISSION_DENIED", relative)
        probe = (lambda _path, rel=relative: [":fixture:$DATA"] if rel in ads else [])
        data, file_stat = stable_read(path, hooks.get(relative), probe)
        artifacts.append(
            {
                "canonical_path": relative,
                "file_mode": stat.S_IMODE(file_stat.st_mode),
                "git_blob": None,
                "mtime_ns": file_stat.st_mtime_ns,
                "raw_git_blob_sha1": hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\x00" + data).hexdigest(),
                "sha256": sha256_bytes(data),
                "size": len(data),
            }
        )
    ordered = sorted(artifacts, key=lambda item: item["canonical_path"].encode("utf-8"))
    validate_path_set(item["canonical_path"] for item in ordered)
    identity_payload = [
        {key: item[key] for key in ("canonical_path", "file_mode", "git_blob", "raw_git_blob_sha1", "sha256", "size")}
        for item in ordered
    ]
    return {
        "canonical_serialization": "RANDLE-CAPTURE-CJSON-1",
        "draft_script_version": DRAFT_SCRIPT_VERSION,
        "enumeration_method": "Python os.scandir over extended-length paths; lstat/no-follow; stable pre/post read",
        "artifacts": ordered,
        "inventory_sha256": semantic_identity(identity_payload),
        "total_artifact_count": len(ordered),
        "total_bytes": sum(item["size"] for item in ordered),
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
