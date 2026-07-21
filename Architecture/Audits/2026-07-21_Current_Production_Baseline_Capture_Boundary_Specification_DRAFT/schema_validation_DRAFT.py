#!/usr/bin/env python3
"""Pinned independent Draft 2020-12 validation adapter for draft fixtures."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
from typing import Any, Mapping

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
    return json.loads(path.read_bytes().decode("utf-8"))


def validate_named_instances(package: Path, instances: Mapping[str, tuple[str, Any]]) -> dict[str, Any]:
    identity = validator_identity()
    validated: list[dict[str, str]] = []
    for label, (schema_name, instance) in sorted(instances.items()):
        schema = load_json(package / schema_name)
        validate_schema_and_instance(schema, instance, label)
        validated.append({"label": label, "schema": schema_name})
    return {"validator": identity, "validated": validated, "errors": [], "warnings": []}
