#!/usr/bin/env python3
"""Measured R5 subprocess worker. Reads one canonical envelope from stdin."""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import sys
import unicodedata
from types import MappingProxyType
from typing import Any


def fail(code: str, detail: str = "") -> None:
    raise ValueError(f"{code}:{detail}" if detail else code)


def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            fail("JSON_DUPLICATE_KEY", key)
        result[key] = value
    return result


def plain(value: Any) -> None:
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str or unicodedata.normalize("NFC", key) != key:
                fail("NON_PLAIN_OR_NFC_KEY")
            plain(child)
        return
    if type(value) is list:
        for child in value:
            plain(child)
        return
    if type(value) is str:
        if unicodedata.normalize("NFC", value) != value:
            fail("NON_NFC_VALUE")
        return
    if type(value) in {int, bool, type(None)}:
        return
    fail("NON_PLAIN_VALUE", type(value).__name__)


def canonical(value: Any) -> bytes:
    plain(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def load(data: bytes) -> Any:
    value = json.loads(
        data.decode("utf-8", "strict"),
        object_pairs_hook=pairs,
        parse_float=lambda token: fail("JSON_FLOAT_FORBIDDEN", token),
        parse_constant=lambda token: fail("JSON_CONSTANT_FORBIDDEN", token),
    )
    plain(value)
    if canonical(value) != data:
        fail("JSON_NOT_CANONICAL")
    return value


def source_namespace(source: bytes, name: str) -> dict[str, Any]:
    namespace: dict[str, Any] = {
        "__name__": name,
        "__file__": f"<measured:{name}>",
        "__builtins__": builtins.__dict__,
    }
    code = compile(source, f"<measured:{name}>", "exec", dont_inherit=True, optimize=0)
    exec(code, namespace, namespace)
    return namespace


def runtime_guard(payload: dict[str, Any]) -> dict[str, Any]:
    authority_prefix = payload["authority_prefix"].casefold()
    module_name = payload["module_name"]
    source = bytes.fromhex(payload["source_hex"])
    blocked: list[str] = []
    guarded_events = {"open", "os.listdir", "os.scandir", "os.walk", "os.stat", "os.lstat"}

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event not in guarded_events:
            return
        target = str(args[0]) if args else ""
        if authority_prefix not in target.casefold():
            return
        frame = sys._getframe(1)
        approved = False
        while frame is not None:
            if frame.f_globals.get("__name__") in {"governed_file_access_DRAFT", "inventory_generator_DRAFT"}:
                approved = True
                break
            frame = frame.f_back
        if not approved:
            blocked.append(event)
            raise PermissionError("R5_RUNTIME_AUTHORITY_ACCESS_DENIED")

    sys.addaudithook(hook)
    namespace = {"__name__": module_name, "__builtins__": builtins.__dict__}
    try:
        exec(compile(source, "<runtime-access-case>", "exec", dont_inherit=True), namespace, namespace)
    except PermissionError as exc:
        return {"status": "REJECTED", "code": str(exc), "blocked_events": blocked}
    return {"status": "ACCEPTED", "code": "OK", "blocked_events": blocked}


def historical_parser(envelope: dict[str, Any]) -> dict[str, Any]:
    source = bytes.fromhex(envelope["source_bytes_hex"])
    if hashlib.sha256(source).hexdigest() != envelope["source_raw_sha256"]:
        fail("MEASURED_SOURCE_HASH")
    namespace = source_namespace(source, "historical_parser_core_R5_DRAFT")
    symbol = envelope["payload"]["parser_symbol"]
    function = namespace.get(symbol)
    if type(function).__name__ != "function":
        fail("PARSER_SYMBOL")
    result = function(
        bytes.fromhex(envelope["payload"]["log_bytes_hex"]),
        envelope["payload"]["logical_path"],
        envelope["payload"]["expected_log_sha256"],
    )
    plain(result)
    return result


def comparator(envelope: dict[str, Any]) -> dict[str, Any]:
    source = bytes.fromhex(envelope["source_bytes_hex"])
    if hashlib.sha256(source).hexdigest() != envelope["source_raw_sha256"]:
        fail("MEASURED_SOURCE_HASH")
    namespace = source_namespace(source, "comparison_engine_R5_DRAFT")
    function = namespace.get("compare")
    if type(function).__name__ != "function":
        fail("COMPARATOR_SYMBOL")
    payload = envelope["payload"]
    result = function(payload["expectations"], payload["observations"], payload["context"])
    plain(result)
    return result


def main() -> int:
    try:
        envelope = load(sys.stdin.buffer.read())
        mode = envelope["mode"]
        if mode == "runtime_guard":
            result = runtime_guard(envelope["payload"])
        elif mode == "historical_parser":
            result = historical_parser(envelope)
        elif mode == "comparator":
            result = comparator(envelope)
        else:
            fail("WORKER_MODE", str(mode))
        sys.stdout.buffer.write(canonical(result))
        return 0
    except BaseException as exc:
        sys.stderr.write(f"{type(exc).__name__}:{exc}\n")
        return 71


if __name__ == "__main__":
    raise SystemExit(main())
