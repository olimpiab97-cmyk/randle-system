#!/usr/bin/env python3
"""Governed, long-path-safe reads for the draft R3 authority package.

Only this module may open authority-critical filesystem paths.  Callers choose
whether bytes are worktree evidence or immutable Git-object authority; the
choice is explicit in :class:`ByteObservation` and never inferred from a path.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


_REPARSE_POINT = 0x400
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_GIT_OBJECT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_ERROR_HANDLE_EOF = 38


class GovernedAccessError(OSError):
    """Fail-closed access error with a stable governance code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class FileIdentity:
    canonical_path: str
    byte_size: int
    device: int
    inode: int
    modified_ns: int
    file_attributes: int
    reparse_point: bool


@dataclass(frozen=True)
class ByteObservation:
    source_kind: str
    canonical_path: str
    data: bytes
    sha256: str
    byte_size: int
    git_blob: str | None = None
    file_identity: FileIdentity | None = None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_stream_selector(path: os.PathLike[str] | str) -> str:
    """Reject every NTFS named-stream selector while preserving a drive colon."""

    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise GovernedAccessError("INVALID_AUTHORITY_PATH", repr(raw))
    normalized = raw
    if normalized.startswith("\\\\?\\UNC\\"):
        normalized = "\\\\" + normalized[8:]
    elif normalized.startswith("\\\\?\\"):
        normalized = normalized[4:]
    colon_positions = [index for index, character in enumerate(normalized) if character == ":"]
    permitted = {1} if re.match(r"^[A-Za-z]:", normalized) else set()
    if any(index not in permitted for index in colon_positions):
        raise GovernedAccessError("AUTHORITY_STREAM_SELECTOR_REJECTED", raw)
    if permitted and not re.match(r"^[A-Za-z]:[\\/]", normalized):
        raise GovernedAccessError("AMBIGUOUS_AUTHORITY_COLON", raw)
    return raw


def canonical_absolute_path(path: os.PathLike[str] | str) -> str:
    """Return an absolute, normalized Windows identity without dereferencing."""

    raw = os.fspath(path)
    if raw.startswith("\\\\?\\UNC\\"):
        raw = "\\\\" + raw[8:]
    elif raw.startswith("\\\\?\\"):
        raw = raw[4:]
    absolute = os.path.abspath(raw)
    normalized = os.path.normpath(absolute)
    if os.name == "nt":
        normalized = os.path.normcase(normalized)
    return normalized


def named_streams(path: os.PathLike[str] | str) -> tuple[str, ...]:
    """Enumerate named NTFS streams on the primary file without selecting one."""

    _reject_stream_selector(path)
    if os.name != "nt":
        raise GovernedAccessError("ADS_UNSUPPORTED_ENVIRONMENT", os.name)

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
    if handle == _INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()
        if error == _ERROR_HANDLE_EOF:
            return ()
        raise GovernedAccessError("ADS_ENUMERATION_FAILED", f"{canonical_absolute_path(path)}:winerror={error}")
    result: list[str] = []
    try:
        while True:
            if data.cStreamName != "::$DATA":
                result.append(data.cStreamName)
            if not find_next(handle, ctypes.byref(data)):
                error = ctypes.get_last_error()
                if error == _ERROR_HANDLE_EOF:
                    break
                raise GovernedAccessError("ADS_ENUMERATION_FAILED", f"{canonical_absolute_path(path)}:winerror={error}")
    finally:
        if not find_close(handle):
            raise GovernedAccessError("ADS_ENUMERATION_FAILED", "FindClose")
    return tuple(sorted(result))


def extended_length_path(path: os.PathLike[str] | str) -> str:
    """Return a Windows extended-length path, including governed UNC handling."""

    canonical = canonical_absolute_path(path)
    if os.name != "nt":
        return canonical
    if canonical.startswith("\\\\"):
        return "\\\\?\\UNC\\" + canonical.lstrip("\\")
    if not _DRIVE.match(canonical):
        raise GovernedAccessError("PATH_NOT_ABSOLUTE", canonical)
    return "\\\\?\\" + canonical


def resolve_relative(root: os.PathLike[str] | str, relative: str) -> str:
    """Resolve a slash-delimited path beneath root and reject escape/absolute forms."""

    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise GovernedAccessError("INVALID_RELATIVE_PATH", repr(relative))
    candidate_text = relative.replace("\\", "/")
    if candidate_text.startswith("/") or _DRIVE.match(candidate_text) or candidate_text.startswith("//"):
        raise GovernedAccessError("ABSOLUTE_RELATIVE_PATH", relative)
    parts = candidate_text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise GovernedAccessError("NONCANONICAL_RELATIVE_PATH", relative)
    if any(":" in part for part in parts):
        raise GovernedAccessError("AUTHORITY_STREAM_SELECTOR_REJECTED", relative)
    root_id = canonical_absolute_path(root)
    result = canonical_absolute_path(os.path.join(root_id, *parts))
    prefix = root_id.rstrip(os.sep) + os.sep
    if not result.startswith(prefix):
        raise GovernedAccessError("PATH_ESCAPES_ROOT", relative)
    return result


def _identity_from_stat(path: str, value: os.stat_result) -> FileIdentity:
    attributes = int(getattr(value, "st_file_attributes", 0))
    return FileIdentity(
        canonical_path=canonical_absolute_path(path),
        byte_size=int(value.st_size),
        device=int(value.st_dev),
        inode=int(value.st_ino),
        modified_ns=int(value.st_mtime_ns),
        file_attributes=attributes,
        reparse_point=bool(attributes & _REPARSE_POINT),
    )


def _reparse_component(path: os.PathLike[str] | str) -> str | None:
    """Return the first reparse component in an absolute path, including parents."""

    canonical = canonical_absolute_path(path)
    candidates = [Path(canonical), *Path(canonical).parents]
    for candidate in reversed(candidates[:-1]):  # skip the drive/UNC anchor itself
        try:
            value = os.lstat(extended_length_path(candidate))
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if int(getattr(value, "st_file_attributes", 0)) & _REPARSE_POINT:
            return canonical_absolute_path(candidate)
    return None


def stat_regular_file(
    path: os.PathLike[str] | str,
    *,
    allow_reparse: bool = False,
) -> FileIdentity:
    _reject_stream_selector(path)
    reparse_component = None if allow_reparse else _reparse_component(path)
    if reparse_component is not None:
        raise GovernedAccessError("REPARSE_POINT_REJECTED", reparse_component)
    governed = extended_length_path(path)
    try:
        value = os.lstat(governed)
    except FileNotFoundError as exc:
        raise GovernedAccessError("FILE_MISSING", canonical_absolute_path(path)) from exc
    except PermissionError as exc:
        raise GovernedAccessError("FILE_INACCESSIBLE", canonical_absolute_path(path)) from exc
    except OSError as exc:
        raise GovernedAccessError("FILE_STAT_FAILED", f"{canonical_absolute_path(path)}:{exc}") from exc
    identity = _identity_from_stat(path, value)
    if not stat.S_ISREG(value.st_mode):
        raise GovernedAccessError("NOT_REGULAR_FILE", identity.canonical_path)
    if identity.reparse_point and not allow_reparse:
        raise GovernedAccessError("REPARSE_POINT_REJECTED", identity.canonical_path)
    return identity


def resolve_primary_file_authority(
    path: os.PathLike[str] | str,
    *,
    allow_reparse: bool = False,
    forbid_named_streams: bool = True,
) -> FileIdentity:
    """Resolve exactly one primary unnamed regular-file stream for authority use."""

    _reject_stream_selector(path)
    identity = stat_regular_file(path, allow_reparse=allow_reparse)
    streams = named_streams(path)
    if forbid_named_streams and streams:
        raise GovernedAccessError("AUTHORITY_FILE_HAS_NAMED_STREAMS", f"{identity.canonical_path}:{streams}")
    return identity


def read_binary(
    path: os.PathLike[str] | str,
    *,
    allow_reparse: bool = False,
) -> ByteObservation:
    """Read one regular file with long-path, reparse, and mutation enforcement."""

    before = resolve_primary_file_authority(path, allow_reparse=allow_reparse)
    governed = extended_length_path(path)
    descriptor: int | None = None
    try:
        descriptor = os.open(governed, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        opened = os.fstat(descriptor)
        opened_identity = _identity_from_stat(path, opened)
        if (opened_identity.device, opened_identity.inode) != (before.device, before.inode):
            raise GovernedAccessError("FILE_IDENTITY_CHANGED", before.canonical_path)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = _identity_from_stat(path, os.fstat(descriptor))
    except PermissionError as exc:
        raise GovernedAccessError("FILE_INACCESSIBLE", before.canonical_path) from exc
    except GovernedAccessError:
        raise
    except OSError as exc:
        raise GovernedAccessError("FILE_READ_FAILED", f"{before.canonical_path}:{exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if before != after:
        raise GovernedAccessError("FILE_CHANGED_DURING_READ", before.canonical_path)
    data = b"".join(chunks)
    if len(data) != before.byte_size:
        raise GovernedAccessError("FILE_SIZE_MISMATCH", before.canonical_path)
    return ByteObservation(
        source_kind="WORKTREE_BYTES",
        canonical_path=before.canonical_path,
        data=data,
        sha256=sha256_bytes(data),
        byte_size=len(data),
        file_identity=before,
    )


def read_text(
    path: os.PathLike[str] | str,
    *,
    encoding: str = "utf-8",
    allow_reparse: bool = False,
) -> str:
    observation = read_binary(path, allow_reparse=allow_reparse)
    try:
        return observation.data.decode(encoding, "strict")
    except UnicodeDecodeError as exc:
        raise GovernedAccessError("TEXT_DECODE_FAILED", observation.canonical_path) from exc


def write_disposable_binary(path: os.PathLike[str] | str, data: bytes, *, exclusive: bool = True) -> FileIdentity:
    """Write a disposable fixture file; this operation never confers authority."""
    canonical = canonical_absolute_path(path)
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0)
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    descriptor = os.open(extended_length_path(canonical), flags, 0o600)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
    finally:
        os.close(descriptor)
    return stat_regular_file(canonical, allow_reparse=False)


def read_named_stream(path: os.PathLike[str] | str, stream_name: str) -> bytes:
    """Read one enumerated NTFS named stream through the governed handle path."""

    if os.name != "nt":
        raise GovernedAccessError("ADS_UNSUPPORTED_ENVIRONMENT")
    if not re.fullmatch(r":[^:\\/:*?\"<>|]+(?::\$DATA)?", stream_name):
        raise GovernedAccessError("INVALID_STREAM_NAME", stream_name)
    _reject_stream_selector(path)
    stat_regular_file(path)
    governed = extended_length_path(path) + stream_name
    descriptor: int | None = None
    try:
        descriptor = os.open(governed, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    except PermissionError as exc:
        raise GovernedAccessError("STREAM_INACCESSIBLE", f"{canonical_absolute_path(path)}:{stream_name}") from exc
    except OSError as exc:
        raise GovernedAccessError("STREAM_READ_FAILED", f"{canonical_absolute_path(path)}:{stream_name}:{exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def read_relative_binary(
    root: os.PathLike[str] | str,
    relative: str,
    *,
    allow_reparse: bool = False,
) -> ByteObservation:
    return read_binary(resolve_relative(root, relative), allow_reparse=allow_reparse)


def read_relative_text(
    root: os.PathLike[str] | str,
    relative: str,
    *,
    encoding: str = "utf-8",
    allow_reparse: bool = False,
) -> str:
    return read_text(resolve_relative(root, relative), encoding=encoding, allow_reparse=allow_reparse)


def enumerate_directory(
    directory: os.PathLike[str] | str,
    *,
    allow_reparse_entries: bool = False,
) -> tuple[str, ...]:
    """Return canonical child identities using a long-path-safe directory handle."""

    _reject_stream_selector(directory)
    governed = extended_length_path(directory)
    try:
        with os.scandir(governed) as iterator:
            results: list[str] = []
            for entry in iterator:
                try:
                    value = entry.stat(follow_symlinks=False)
                except PermissionError as exc:
                    raise GovernedAccessError("DIRECTORY_ENTRY_INACCESSIBLE", entry.path) from exc
                attributes = int(getattr(value, "st_file_attributes", 0))
                if attributes & _REPARSE_POINT and not allow_reparse_entries:
                    raise GovernedAccessError("REPARSE_POINT_REJECTED", entry.path)
                results.append(canonical_absolute_path(entry.path))
            return tuple(sorted(results, key=lambda value: value.casefold()))
    except FileNotFoundError as exc:
        raise GovernedAccessError("DIRECTORY_MISSING", canonical_absolute_path(directory)) from exc
    except PermissionError as exc:
        raise GovernedAccessError("DIRECTORY_INACCESSIBLE", canonical_absolute_path(directory)) from exc


def enumerate_regular_files(root: os.PathLike[str] | str) -> Iterator[FileIdentity]:
    pending = [canonical_absolute_path(root)]
    while pending:
        directory = pending.pop()
        for child in reversed(enumerate_directory(directory)):
            governed = extended_length_path(child)
            value = os.lstat(governed)
            attributes = int(getattr(value, "st_file_attributes", 0))
            if attributes & _REPARSE_POINT:
                raise GovernedAccessError("REPARSE_POINT_REJECTED", child)
            if stat.S_ISDIR(value.st_mode):
                pending.append(child)
            elif stat.S_ISREG(value.st_mode):
                yield _identity_from_stat(child, value)


def _run_git(repository: os.PathLike[str] | str, *args: str) -> bytes:
    repository_id = canonical_absolute_path(repository)
    command = [
        "git",
        "-c",
        "core.longpaths=true",
        "-c",
        f"safe.directory={Path(repository_id).as_posix()}",
        "-C",
        repository_id,
        *args,
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise GovernedAccessError("GIT_OBJECT_READ_FAILED", result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def git_object_bytes(
    repository: os.PathLike[str] | str,
    authority_ref: str,
    repository_path: str,
) -> ByteObservation:
    """Read authoritative bytes from a commit/tree or the explicitly staged index."""

    if authority_ref != ":" and not _GIT_OBJECT.fullmatch(authority_ref):
        raise GovernedAccessError("AUTHORITY_REF_NOT_IMMUTABLE", authority_ref)
    normalized = repository_path.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/") or not normalized or ":" in normalized:
        raise GovernedAccessError("NONCANONICAL_REPOSITORY_PATH", repository_path)
    object_spec = f":{normalized}" if authority_ref == ":" else f"{authority_ref}:{normalized}"
    blob = _run_git(repository, "rev-parse", object_spec).decode("ascii", "strict").strip()
    if not _GIT_OBJECT.fullmatch(blob):
        raise GovernedAccessError("INVALID_GIT_BLOB", blob)
    data = _run_git(repository, "cat-file", "blob", blob)
    return ByteObservation(
        source_kind="STAGED_GIT_BLOB" if authority_ref == ":" else "COMMITTED_GIT_BLOB",
        canonical_path=normalized,
        data=data,
        sha256=sha256_bytes(data),
        byte_size=len(data),
        git_blob=blob,
    )


def git_tree_entries(repository: os.PathLike[str] | str, authority_ref: str, prefix: str = "") -> tuple[str, ...]:
    if ":" in prefix:
        raise GovernedAccessError("AUTHORITY_STREAM_SELECTOR_REJECTED", prefix)
    if authority_ref == ":":
        output = _run_git(repository, "ls-files", "--stage")
        paths = [line.split(b"\t", 1)[1].decode("utf-8", "strict") for line in output.splitlines() if b"\t" in line]
    else:
        if not _GIT_OBJECT.fullmatch(authority_ref):
            raise GovernedAccessError("AUTHORITY_REF_NOT_IMMUTABLE", authority_ref)
        arguments = ("ls-tree", "-r", "--name-only", authority_ref) if not prefix else ("ls-tree", "-r", "--name-only", authority_ref, "--", prefix)
        output = _run_git(repository, *arguments)
        paths = [line.decode("utf-8", "strict") for line in output.splitlines()]
    if prefix:
        governed_prefix = prefix.replace("\\", "/").rstrip("/")
        paths = [path for path in paths if path == governed_prefix or path.startswith(governed_prefix + "/")]
    return tuple(sorted(paths))


def git_revision_identity(repository: os.PathLike[str] | str, commit: str) -> dict[str, str]:
    if not _GIT_OBJECT.fullmatch(commit):
        raise GovernedAccessError("AUTHORITY_REF_NOT_IMMUTABLE", commit)
    resolved = _run_git(repository, "rev-parse", f"{commit}^{{commit}}").decode("ascii", "strict").strip()
    tree = _run_git(repository, "rev-parse", f"{commit}^{{tree}}").decode("ascii", "strict").strip()
    parents = _run_git(repository, "show", "-s", "--format=%P", commit).decode("ascii", "strict").strip().split()
    if len(parents) != 1:
        raise GovernedAccessError("GIT_SINGLE_PARENT_REQUIRED", commit)
    return {"commit": resolved, "tree": tree, "parent": parents[0]}
