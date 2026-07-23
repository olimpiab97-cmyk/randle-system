#!/usr/bin/env python3
"""Measured R6 runtime audit-hook origin for primary authority access probes."""

from __future__ import annotations

import builtins
import hashlib
import inspect
import marshal
import os
import sys
from typing import Any


GUARDED_EVENTS = {"open", "os.scandir", "os.listdir", "os.walk", "os.stat"}


def _fingerprint(code: Any) -> str:
    normalized = code.replace(co_filename="<R6-AUTHORITY>", co_firstlineno=1)
    return hashlib.sha256(marshal.dumps(normalized)).hexdigest()


def _approved_read(path: str) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        return os.read(descriptor, 64)
    finally:
        os.close(descriptor)


def _unauthorized_computed_open(path: str) -> bytes:
    function = getattr(builtins, "op" + "en")
    with function(path, "rb") as stream:
        return stream.read(64)


def _unauthorized_computed_scandir(path: str) -> int:
    function = getattr(os, "scan" + "dir")
    with function(path) as iterator:
        return sum(1 for _ in iterator)


def run_access_probe(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {_fingerprint(_approved_read.__code__)}

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event not in GUARDED_EVENTS:
            return
        frame = inspect.currentframe()
        permitted = False
        while frame is not None:
            if _fingerprint(frame.f_code) in allowed:
                permitted = True
                break
            frame = frame.f_back
        if not permitted:
            raise PermissionError("R6_RUNTIME_ACCESS_ORIGIN_UNAUTHORIZED")

    sys.addaudithook(hook)
    vector = payload["vector"]
    try:
        if vector == "permitted_measured_origin":
            data = _approved_read(payload["path"])
            return {"status": "PASS", "code": "OK", "byte_count": len(data), "origin_fingerprint": next(iter(allowed))}
        if vector in {"computed_open", "forged_name", "forged_module", "runtime_wrapper"}:
            globals()["__name__"] = "governed_file_access_DRAFT" if vector == "forged_name" else globals()["__name__"]
            data = _unauthorized_computed_open(payload["path"])
            return {"status": "BYPASS", "code": "OK", "byte_count": len(data)}
        if vector == "computed_scandir":
            count = _unauthorized_computed_scandir(payload["directory"])
            return {"status": "BYPASS", "code": "OK", "entry_count": count}
        raise ValueError("ACCESS_PROBE_VECTOR")
    except PermissionError:
        return {"status": "BLOCKED", "code": "RUNTIME_ACCESS_ORIGIN_UNAUTHORIZED"}

