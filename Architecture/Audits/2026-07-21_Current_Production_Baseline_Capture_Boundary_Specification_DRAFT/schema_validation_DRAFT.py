#!/usr/bin/env python3
"""Pinned independent Draft 2020-12 validation adapter for draft fixtures."""

from __future__ import annotations

import importlib.metadata
import json
import unicodedata
from pathlib import Path
from typing import Any, Callable, Mapping

from governed_file_access_DRAFT import read_binary, sha256_bytes


PINNED_DISTRIBUTIONS = {
    "attrs": "25.3.0",
    "fqdn": "1.5.1",
    "idna": "3.11",
    "jsonschema": "4.25.1",
    "jsonschema-specifications": "2025.4.1",
    "lark": "1.2.2",
    "PyYAML": "6.0.2",
    "referencing": "0.36.2",
    "rfc3339-validator": "0.1.4",
    "rfc3986-validator": "0.1.1",
    "rfc3987-syntax": "1.1.0",
    "rpds-py": "0.27.1",
    "six": "1.17.0",
    "typing_extensions": "4.16.0",
}
SUPPORTED_DRAFT = "2020-12"
REQUIRED_FORMATS = ("date-time", "hostname", "idn-hostname", "ipv4", "ipv6", "uri")


class SchemaValidationError(ValueError):
    pass


def _require_nfc(value: Any, pointer: str = "") -> None:
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise SchemaValidationError(f"JSON_NON_NFC:{pointer or '/'}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _require_nfc(item, f"{pointer}/{index}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if unicodedata.normalize("NFC", key) != key:
                raise SchemaValidationError(f"JSON_NON_NFC_KEY:{pointer}/{key}")
            _require_nfc(item, f"{pointer}/{key}")


def validator_identity(lock_authority_bytes: bytes | None = None) -> dict[str, Any]:
    installed_versions: dict[str, str] = {}
    for distribution, expected in PINNED_DISTRIBUTIONS.items():
        try:
            installed = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError as exc:
            raise SchemaValidationError(f"PINNED_VALIDATOR_UNAVAILABLE:{distribution}") from exc
        if installed != expected:
            raise SchemaValidationError(
                f"PINNED_VALIDATOR_VERSION_MISMATCH:{distribution}:{installed}:{expected}"
            )
        installed_versions[distribution] = installed
    from jsonschema import FormatChecker

    available = set(FormatChecker().checkers)
    missing = sorted(set(REQUIRED_FORMATS) - available)
    if missing:
        raise SchemaValidationError(f"FORMAT_CHECKER_INCOMPLETE:{missing}")
    lock_bytes = (
        lock_authority_bytes
        if lock_authority_bytes is not None
        else read_binary(Path(__file__).resolve().parent / "validator_requirements_DRAFT.lock").data
    )
    return {
        "name": "jsonschema",
        "version": installed_versions["jsonschema"],
        "draft": SUPPORTED_DRAFT,
        "distributions": installed_versions,
        "format_checker": "jsonschema.FormatChecker",
        "required_formats": list(REQUIRED_FORMATS),
        "lock_sha256": sha256_bytes(lock_bytes),
    }


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


def validate_format_checker_configuration(format_checker: Any) -> None:
    if format_checker is None:
        raise SchemaValidationError("FORMAT_CHECKER_REQUIRED")
    available = set(getattr(format_checker, "checkers", {}))
    missing = sorted(set(REQUIRED_FORMATS) - available)
    if missing:
        raise SchemaValidationError(f"FORMAT_CHECKER_INCOMPLETE:{missing}")


def validate_validator_environment_claim(
    claimed: Mapping[str, Any], lock_authority_bytes: bytes | None = None
) -> None:
    actual = validator_identity(lock_authority_bytes)
    if claimed != actual:
        raise SchemaValidationError("VALIDATOR_ENVIRONMENT_IDENTITY")


def load_json(path: Path) -> Any:
    return strict_canonical_json_loads(read_binary(path).data)


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
    _require_nfc(value)
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
