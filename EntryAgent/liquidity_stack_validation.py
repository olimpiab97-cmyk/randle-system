"""Canonical Liquidity Level stack validation shared by Entry Agent paths."""

from __future__ import annotations

import math
import re
from typing import Any


RECOGNIZED_LIQUIDITY_LEVELS = ("YH", "YL", "ONH", "ONL", "LH", "LL", "PMH", "PML")
RECOGNIZED_LIQUIDITY_LEVEL_SET = set(RECOGNIZED_LIQUIDITY_LEVELS)
ACTIVE_LEVEL_STATUSES = {"ACTIVE", "REACTIVATED"}
STACK_GROUP_PATTERN = re.compile(r"^(HIGH|LOW)\s+([1-9][0-9]*)$", re.IGNORECASE)
CONVENTIONAL_HIGH_LEVELS = {"ONH", "LH", "PMH"}
CONVENTIONAL_LOW_LEVELS = {"ONL", "LL", "PML"}
STACK_THRESHOLD_PERCENT_FALLBACK = 10.0


def optional_number(value: Any) -> float | None:
    """Return a finite float or None."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return None
    return parsed


def normalize_stack_group_label(value: Any) -> str | None:
    """Return NONE or a canonical HIGH/LOW ordinal label."""
    text = str(value or "NONE").strip()
    if not text or text.upper() == "NONE":
        return "NONE"
    match = STACK_GROUP_PATTERN.fullmatch(text)
    if match is None:
        return None
    return f"{match.group(1).upper()} {int(match.group(2))}"


def stack_group_side(label: str) -> str | None:
    """Return high/low for one canonical group label."""
    if label.startswith("HIGH "):
        return "high"
    if label.startswith("LOW "):
        return "low"
    return None


def stack_threshold_from_context(context: dict[str, Any] | None) -> float | None:
    """Resolve the frozen stack threshold, including the governed 10% legacy fallback."""
    if not isinstance(context, dict):
        return None
    candidates = [context]
    for field in ("locked_liquidity_context", "tv_context"):
        nested = context.get(field)
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        for field in ("stack_threshold", "frozen_stack_threshold"):
            value = optional_number(candidate.get(field))
            if value is not None and value >= 0:
                return value
    raw_symbol = str(context.get("normalized_symbol") or context.get("symbol") or "").upper()
    tick_size = 0.25 if "NQ" in raw_symbol else 1.0 if "YM" in raw_symbol else None
    for candidate in candidates:
        for field in ("daily_atr14", "daily_atr_14", "daily_atr", "atr_daily_14", "atr_daily"):
            daily_atr = optional_number(candidate.get(field))
            if daily_atr is not None and daily_atr >= 0:
                raw_threshold = daily_atr * (STACK_THRESHOLD_PERCENT_FALLBACK / 100.0)
                if tick_size is None:
                    return raw_threshold
                return math.floor((raw_threshold / tick_size) + 0.5) * tick_size
    return None


def stack_reference_price_from_context(context: dict[str, Any] | None) -> float | None:
    """Resolve the frozen price used to determine a Liquidity Level's market side."""
    if not isinstance(context, dict):
        return None
    candidates = [context]
    for field in ("locked_liquidity_context", "tv_context"):
        nested = context.get(field)
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        for field in ("session_lock_price", "stack_reference_price", "frozen_market_reference_price"):
            value = optional_number(candidate.get(field))
            if value is not None:
                return value
    return None


def _error(code: str, message: str, **details: Any) -> dict[str, Any]:
    result = {"error": message, "code": code}
    result.update(details)
    return result


def _explicit_members(stack: dict[str, Any]) -> list[Any] | None:
    members = stack.get("members")
    if isinstance(members, list):
        return members
    components = stack.get("components")
    return components if isinstance(components, list) else None


def validate_liquidity_stack_structure(
    levels: Any,
    explicit_stacks: Any = None,
    *,
    stack_threshold: Any = None,
    session_reference_price: Any = None,
) -> dict[str, Any] | None:
    """Validate complete-span membership, side, numbering, and explicit parity."""
    if not isinstance(levels, dict):
        return _error("STACK_LEVELS_INVALID", "levels must be an object")

    row_groups: dict[str, list[dict[str, Any]]] = {}
    level_records: dict[str, dict[str, Any]] = {}
    for raw_name, details in levels.items():
        if not isinstance(details, dict):
            continue
        name = str(raw_name).strip().upper()
        raw_group = details.get("stack_group")
        status = str(details.get("status") or "").strip().upper()
        price = optional_number(details.get("price"))
        if name in RECOGNIZED_LIQUIDITY_LEVEL_SET:
            level_records[name] = {"status": status, "price": price}

        raw_memberships = details.get("stack_groups")
        if raw_memberships is not None and not isinstance(raw_memberships, list):
            return _error(
                "STACK_GROUPS_INVALID",
                f"{name}.stack_groups must be an array when supplied",
                level=name,
            )

        normalized_single = normalize_stack_group_label(raw_group)
        if normalized_single is None:
            return _error(
                "STACK_GROUP_LABEL_INVALID",
                f"{name}.stack_group is not a canonical HIGH/LOW ordinal",
                level=name,
                stack_group=raw_group,
            )

        memberships: list[str] = []
        if isinstance(raw_memberships, list):
            for raw_membership in raw_memberships:
                label = normalize_stack_group_label(raw_membership)
                if label in {None, "NONE"}:
                    return _error(
                        "STACK_GROUP_LABEL_INVALID",
                        f"{name}.stack_groups contains a noncanonical stack owner",
                        level=name,
                        stack_group=raw_membership,
                    )
                if label in memberships:
                    return _error(
                        "STACK_MEMBER_DUPLICATE",
                        f"{name} repeats {label} in stack_groups",
                        level=name,
                        stack_group=label,
                    )
                memberships.append(label)

            raw_single_supplied = raw_group is not None and str(raw_group).strip() != ""
            if raw_single_supplied and normalized_single == "NONE" and memberships:
                return _error(
                    "STACK_MEMBERSHIP_MISMATCH",
                    f"{name}.stack_group contradicts stack_groups",
                    level=name,
                    stack_group=raw_group,
                    stack_groups=memberships,
                )
            if normalized_single != "NONE" and normalized_single not in memberships:
                return _error(
                    "STACK_MEMBERSHIP_MISMATCH",
                    f"{name}.stack_group contradicts stack_groups",
                    level=name,
                    stack_group=normalized_single,
                    stack_groups=memberships,
                )
        elif normalized_single != "NONE":
            memberships.append(normalized_single)

        if not memberships:
            continue
        if name not in RECOGNIZED_LIQUIDITY_LEVEL_SET:
            return _error("STACK_MEMBER_UNKNOWN", f"{name} is not a recognized Liquidity Level", level=name)
        if status not in ACTIVE_LEVEL_STATUSES:
            return _error(
                "STACK_MEMBER_INACTIVE",
                f"{name} cannot be stacked with status {status or 'MISSING'}",
                level=name,
                stack_groups=memberships,
            )
        if price is None:
            return _error(
                "STACK_MEMBER_PRICE_INVALID",
                f"{name}.price must be numeric for stack validation",
                level=name,
                stack_groups=memberships,
            )
        for label in memberships:
            row_groups.setdefault(label, []).append({"name": name, "price": price})

    explicit_present = explicit_stacks is not None
    explicit_groups: dict[str, set[str]] = {}
    if explicit_present:
        if not isinstance(explicit_stacks, list):
            return _error("STACK_DEFINITIONS_INVALID", "liquidity_map.stacks must be an array")
        for index, stack in enumerate(explicit_stacks):
            if not isinstance(stack, dict):
                return _error(
                    "STACK_DEFINITION_INVALID",
                    f"liquidity_map.stacks[{index}] must be an object",
                    stack_index=index,
                )
            members = _explicit_members(stack)
            if members is None:
                return _error(
                    "STACK_MEMBERS_INVALID",
                    f"liquidity_map.stacks[{index}] requires members or components",
                    stack_index=index,
                )
            normalized_members: list[str] = []
            for member in members:
                name = str(member).strip().upper()
                if name not in RECOGNIZED_LIQUIDITY_LEVEL_SET:
                    return _error(
                        "STACK_MEMBER_UNKNOWN",
                        f"{name} is not a recognized Liquidity Level",
                        stack_index=index,
                        level=name,
                    )
                if name in normalized_members:
                    return _error(
                        "STACK_MEMBER_DUPLICATE",
                        f"{name} appears more than once in liquidity_map.stacks[{index}]",
                        stack_index=index,
                        level=name,
                    )
                normalized_members.append(name)

            raw_label = (
                stack.get("stack_group")
                if stack.get("stack_group") is not None
                else stack.get("id")
                if stack.get("id") is not None
                else stack.get("name")
            )
            label = normalize_stack_group_label(raw_label)
            if label in {None, "NONE"}:
                member_row_labels = {
                    normalize_stack_group_label((levels.get(name) or {}).get("stack_group"))
                    for name in normalized_members
                    if isinstance(levels.get(name), dict)
                }
                member_row_labels.discard(None)
                member_row_labels.discard("NONE")
                label = next(iter(member_row_labels)) if len(member_row_labels) == 1 else None
            if label is None:
                return _error(
                    "STACK_GROUP_LABEL_INVALID",
                    f"liquidity_map.stacks[{index}] requires a canonical stack_group or unambiguous row labels",
                    stack_index=index,
                    stack_group=raw_label,
                )
            if label in explicit_groups:
                return _error(
                    "STACK_DEFINITION_DUPLICATE",
                    f"explicit stack {label} is defined more than once",
                    stack_index=index,
                    stack_group=label,
                )

            declared_side = str(stack.get("side") or "").strip().lower()
            expected_side = stack_group_side(label)
            if declared_side and declared_side not in {
                expected_side,
                "upper" if expected_side == "high" else "lower",
            }:
                return _error(
                    "STACK_SIDE_CONTRADICTION",
                    f"explicit stack {label} declares contradictory side {declared_side}",
                    stack_index=index,
                    stack_group=label,
                )
            explicit_groups[label] = set(normalized_members)

    row_sets = {label: {member["name"] for member in members} for label, members in row_groups.items()}
    validation_groups = explicit_groups if explicit_present else row_sets
    if explicit_present and row_sets != explicit_groups:
        return _error(
            "STACK_MEMBERSHIP_MISMATCH",
            "row stack_group labels do not match explicit membership",
            row_groups={key: sorted(value) for key, value in row_sets.items()},
            explicit_groups={key: sorted(value) for key, value in explicit_groups.items()},
        )
    if not validation_groups:
        return None

    threshold = optional_number(stack_threshold)
    if threshold is None or threshold < 0:
        return _error("STACK_THRESHOLD_MISSING", "a frozen stack threshold is required")
    reference = optional_number(session_reference_price)

    group_metrics: dict[str, dict[str, Any]] = {}
    for label, member_names in validation_groups.items():
        if len(member_names) < 2:
            return _error(
                "STACK_MEMBER_COUNT_INVALID",
                f"{label} must contain at least two Liquidity Levels",
                stack_group=label,
                member_count=len(member_names),
            )
        members: list[dict[str, Any]] = []
        for name in sorted(member_names):
            record = level_records.get(name)
            if record is None:
                return _error(
                    "STACK_MEMBERSHIP_MISMATCH",
                    f"{name} is defined in {label} but missing from levels",
                    stack_group=label,
                    level=name,
                )
            if record["status"] not in ACTIVE_LEVEL_STATUSES:
                return _error(
                    "STACK_MEMBER_INACTIVE",
                    f"{name} cannot be stacked with status {record['status'] or 'MISSING'}",
                    level=name,
                    stack_group=label,
                )
            if record["price"] is None:
                return _error(
                    "STACK_MEMBER_PRICE_INVALID",
                    f"{name}.price must be numeric for stack validation",
                    level=name,
                    stack_group=label,
                )
            members.append({"name": name, "price": record["price"]})
        prices = [member["price"] for member in members]
        lowest = min(prices)
        highest = max(prices)
        span = highest - lowest
        if span > threshold + 1e-9:
            return _error(
                "STACK_FULL_SPAN_EXCEEDED",
                f"{label} complete Liquidity Level span {span} exceeds threshold {threshold}",
                stack_group=label,
                lowest_liquidity_level=lowest,
                highest_liquidity_level=highest,
                span=span,
                stack_threshold=threshold,
            )
        side = stack_group_side(label)
        if reference is not None:
            invalid_side = [
                member["name"]
                for member in members
                if not (member["price"] > reference if side == "high" else member["price"] < reference)
            ]
            if invalid_side:
                return _error(
                    "STACK_MEMBER_SIDE_MISMATCH",
                    f"{label} contains Liquidity Levels outside its frozen market side",
                    stack_group=label,
                    levels=sorted(invalid_side),
                    session_reference_price=reference,
                )
        else:
            for member in members:
                name = member["name"]
                conventional_side = (
                    "high" if name in CONVENTIONAL_HIGH_LEVELS else "low" if name in CONVENTIONAL_LOW_LEVELS else None
                )
                if conventional_side is None:
                    return _error(
                        "STACK_REFERENCE_PRICE_MISSING",
                        f"a frozen market reference is required to validate {name} in {label}",
                        stack_group=label,
                        level=name,
                    )
                if conventional_side != side:
                    return _error(
                        "STACK_MEMBER_SIDE_MISMATCH",
                        f"{name} does not belong to the declared side of {label}",
                        stack_group=label,
                        level=name,
                    )
        group_metrics[label] = {
            "side": side,
            "innermost": lowest if side == "high" else highest,
            "outermost": highest if side == "high" else lowest,
        }

    for side in ("high", "low"):
        side_labels = [label for label, metric in group_metrics.items() if metric["side"] == side]
        side_labels.sort(
            key=lambda label: (group_metrics[label]["innermost"], label),
            reverse=side == "low",
        )
        for ordinal, label in enumerate(side_labels, start=1):
            expected = f"{side.upper()} {ordinal}"
            if label != expected:
                return _error(
                    "STACK_NUMBERING_INVALID",
                    f"expected {expected} but received {label}",
                    stack_group=label,
                    expected_stack_group=expected,
                )

    labels = sorted(validation_groups, key=lambda label: (stack_group_side(label) or "", int(label.split()[1])))
    for left_index, left_label in enumerate(labels):
        for right_label in labels[left_index + 1 :]:
            shared_members = validation_groups[left_label] & validation_groups[right_label]
            left_metric = group_metrics[left_label]
            right_metric = group_metrics[right_label]
            if left_metric["side"] != right_metric["side"]:
                if shared_members:
                    return _error(
                        "STACK_MEMBER_OVERLAP",
                        f"{left_label} and {right_label} overlap across different sides",
                        stack_group=right_label,
                        other_stack_group=left_label,
                        levels=sorted(shared_members),
                    )
                continue

            left_ordinal = int(left_label.split()[1])
            right_ordinal = int(right_label.split()[1])
            consecutive = right_ordinal == left_ordinal + 1
            boundaries_touch = abs(left_metric["outermost"] - right_metric["innermost"]) <= 1e-9

            if shared_members:
                shared_prices = {
                    level_records[name]["price"]
                    for name in shared_members
                    if name in level_records and level_records[name]["price"] is not None
                }
                if len(shared_prices) != 1 or not consecutive or not boundaries_touch:
                    return _error(
                        "STACK_MEMBER_OVERLAP",
                        f"{left_label} and {right_label} do not share one canonical boundary price",
                        stack_group=right_label,
                        other_stack_group=left_label,
                        levels=sorted(shared_members),
                        shared_prices=sorted(shared_prices),
                        earlier_outermost_price=left_metric["outermost"],
                        next_innermost_price=right_metric["innermost"],
                    )
                shared_price = next(iter(shared_prices))
                if abs(shared_price - left_metric["outermost"]) > 1e-9:
                    return _error(
                        "STACK_MEMBER_OVERLAP",
                        f"{left_label} and {right_label} overlap in the interior of a stack",
                        stack_group=right_label,
                        other_stack_group=left_label,
                        levels=sorted(shared_members),
                        shared_price=shared_price,
                    )
            elif not (consecutive and boundaries_touch):
                continue
            else:
                shared_price = left_metric["outermost"]

            boundary_members = {
                name
                for name, record in level_records.items()
                if record["status"] in ACTIVE_LEVEL_STATUSES
                and record["price"] is not None
                and abs(record["price"] - shared_price) <= 1e-9
            }
            missing_left = boundary_members - validation_groups[left_label]
            missing_right = boundary_members - validation_groups[right_label]
            if missing_left or missing_right:
                return _error(
                    "STACK_BOUNDARY_RECIPROCAL_MEMBERS_MISSING",
                    f"every active Liquidity Level at {shared_price} must belong to both {left_label} and {right_label}",
                    stack_group=right_label,
                    other_stack_group=left_label,
                    shared_price=shared_price,
                    missing_from_earlier=sorted(missing_left),
                    missing_from_next=sorted(missing_right),
                )

    return None


def format_stack_validation_error(error: dict[str, Any] | None, prefix: str = "") -> str | None:
    """Return a stable diagnostic string for persisted session-lock state."""
    if error is None:
        return None
    code = str(error.get("code") or "STACK_VALIDATION_FAILED")
    message = str(error.get("error") or "Liquidity Level stack validation failed")
    return f"{prefix}{code} {message}".strip()
