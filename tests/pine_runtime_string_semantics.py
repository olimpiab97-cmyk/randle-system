"""Bounded source-semantic model for Pine JSON string serialization.

This module deliberately models Pine string-literal behavior rather than
borrowing Python's escape semantics. TradingView remains the Pine compiler.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def pine_literal_body_value(body: str) -> str:
    """Decode the Pine literal body rules relevant to the governed serializer."""

    supported = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'"}
    result: list[str] = []
    index = 0
    while index < len(body):
        if body[index] != "\\" or index + 1 == len(body):
            result.append(body[index])
            index += 1
            continue
        following = body[index + 1]
        result.append(supported.get(following, following))
        index += 2
    return "".join(result)


def legacy_unsafe_pine_json_string(value: str) -> str:
    """Project the removed R2 serializer, including its unsafe ``\r`` step."""

    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n")
    # In Pine, the unsupported literal body \r denotes ordinary ``r`` while
    # the replacement body \\r denotes the two JSON characters backslash+r.
    escaped = escaped.replace(pine_literal_body_value(r"\r"), pine_literal_body_value(r"\\r"))
    escaped = escaped.replace("\t", "\\t")
    return '"' + escaped + '"'


def assert_corrected_serializer_source(pine_source: str) -> None:
    unsafe = 'str.replace_all(escaped, "\\r", "\\\\r")'
    assert unsafe not in pine_source
    assert 'str.match(x, "\\\\x0D") != ""' in pine_source
    assert 'runtime.error("CANONICAL_JSON_STRING_U000D_REJECTED")' in pine_source
    assert 'str.replace_all(x, "\\\\", "\\\\\\\\")' in pine_source
    assert 'str.replace_all(escaped, "\\\"", "\\\\\\\"")' in pine_source
    assert 'str.replace_all(escaped, "\\n", "\\\\n")' in pine_source
    assert 'str.replace_all(escaped, "\\t", "\\\\t")' in pine_source


def production_pine_json_string(value: str, pine_source: str) -> str:
    """Project the corrected production f_json_str transformation order."""

    assert_corrected_serializer_source(pine_source)
    if "\r" in value:
        raise ValueError("CANONICAL_JSON_STRING_U000D_REJECTED")
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n")
    escaped = escaped.replace("\t", "\\t")
    return '"' + escaped + '"'


def production_pine_json_dumps(value: Any, pine_source: str) -> str:
    """Encode JSON while routing every string through production f_json_str."""

    if isinstance(value, str):
        return production_pine_json_string(value, pine_source)
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        return json.dumps(value, allow_nan=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(production_pine_json_dumps(item, pine_source) for item in value) + "]"
    if isinstance(value, dict):
        members = (
            production_pine_json_string(str(key), pine_source)
            + ":"
            + production_pine_json_dumps(item, pine_source)
            for key, item in value.items()
        )
        return "{" + ",".join(members) + "}"
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def load_pine(path: Path) -> str:
    return path.read_text(encoding="utf-8")
