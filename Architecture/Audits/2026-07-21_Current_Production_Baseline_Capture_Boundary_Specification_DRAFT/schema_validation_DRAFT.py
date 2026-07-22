#!/usr/bin/env python3
"""Pinned independent Draft 2020-12 validation adapter for draft fixtures."""

from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

PINNED_VALIDATOR = "jsonschema"
PINNED_VERSION = "4.25.1"
SUPPORTED_DRAFT = "2020-12"


class SchemaValidationError(ValueError):
    pass


def validator_identity() -> dict[str, str]:
    try:
        installed = importlib.metadata.version(PINNED_VALIDATOR)
    except importlib.metadata.PackageNotFoundError as exc:
        raise SchemaValidationError("PINNED_VALIDATOR_UNAVAILABLE") from exc
    if installed != PINNED_VERSION:
        raise SchemaValidationError(f"PINNED_VALIDATOR_VERSION_MISMATCH:{installed}")
    return {"name": PINNED_VALIDATOR, "version": installed, "draft": SUPPORTED_DRAFT}


def validate_schema_and_instance(schema: Mapping[str, Any], instance: Any, label: str) -> None:
    validator_identity()
    from jsonschema import Draft202012Validator, FormatChecker

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # validator exception types are deliberately reported verbatim
        raise SchemaValidationError(f"SCHEMA_INVALID:{label}:{exc}") from exc
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    if errors:
        rendered = [f"/{'/'.join(map(str, e.absolute_path))}:{e.message}" for e in errors]
        raise SchemaValidationError(f"INSTANCE_INVALID:{label}:{rendered}")


def load_json(path: Path) -> Any:
    resolved = os.path.abspath(os.fspath(path))
    governed = "\\\\?\\" + resolved if os.name == "nt" and not resolved.startswith("\\\\?\\") else resolved
    with open(governed, "rb") as handle:
        return strict_canonical_json_loads(handle.read())


def strict_canonical_json_loads(raw: bytes) -> Any:
    if raw.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        raise SchemaValidationError("JSON_BOM_OR_UTF16_FORBIDDEN")
    if b"\r" in raw or not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise SchemaValidationError("JSON_LINE_ENDING_POLICY")
    try:
        text = raw[:-1].decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SchemaValidationError("JSON_UTF8_REQUIRED") from exc
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise SchemaValidationError(f"JSON_DUPLICATE_KEY:{key}")
            result[key] = value
        return result
    value = json.loads(
        text,
        object_pairs_hook=pairs,
        parse_constant=lambda token: (_ for _ in ()).throw(SchemaValidationError(f"JSON_NONFINITE:{token}")),
        parse_float=lambda token: (_ for _ in ()).throw(SchemaValidationError(f"JSON_FLOAT_FORBIDDEN:{token}")),
    )
    reproduced = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if reproduced != raw:
        raise SchemaValidationError("JSON_NONCANONICAL")
    return value


def validate_governed_artifact(
    raw: bytes,
    schema: Mapping[str, Any],
    semantic_validator: Callable[[Any], None],
    cross_artifact_validator: Callable[[Any], None],
    immutable_authority_validator: Callable[[Any], None],
    label: str,
) -> dict[str, Any]:
    """The only valid artifact pipeline: bytes, schema, semantic, cross, authority."""
    value = strict_canonical_json_loads(raw)
    validate_schema_and_instance(schema, value, label)
    semantic_validator(value)
    cross_artifact_validator(value)
    immutable_authority_validator(value)
    return {
        "label": label,
        "stages": [
            "STRICT_CANONICAL_JSON",
            "DRAFT_2020_12_SCHEMA",
            "SEMANTIC",
            "CROSS_ARTIFACT",
            "IMMUTABLE_AUTHORITY",
        ],
        "status": "VALID",
    }


def validate_named_instances(package: Path, instances: Mapping[str, tuple[str, Any]]) -> dict[str, Any]:
    identity = validator_identity()
    validated: list[dict[str, str]] = []
    for label, (schema_name, instance) in sorted(instances.items()):
        schema = load_json(package / schema_name)
        validate_schema_and_instance(schema, instance, label)
        validated.append({"label": label, "schema": schema_name})
    return {"validator": identity, "validated": validated, "errors": [], "warnings": []}
