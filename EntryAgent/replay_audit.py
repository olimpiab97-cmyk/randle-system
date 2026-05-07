"""Replay/audit Entry Agent status from existing logs.

This tool is intentionally read-only against strategy logic. It compares the
published Entry Agent reasoning log with completed 1-minute bars, TradingView
level snapshots, and submitted trade records, then emits an audit report and
regression-case JSON.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from blueprint_rules import LOWER_LIQUIDITY_LEVELS, UPPER_LIQUIDITY_LEVELS, optional_float
from levels import root_symbol

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DATA_DIR = ROOT_DIR / "Data"
SYMBOLS = ("NQ", "YM", "RTY")
STEP_RANK = {
    "Step 1": 1,
    "Step 2": 2,
    "Step 2.5": 2.5,
    "Step 3": 3,
    "Step 4": 4,
    "Step 5": 5,
    "Step 6": 6,
    "Step 7": 7,
}
ACTIVE_PRIORITY = {"YH": 0, "YL": 0, "ONH": 1, "ONL": 1, "LH": 2, "LL": 2, "PMH": 3, "PML": 3}


def read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def minute_key(value: Any) -> str | None:
    parsed = parse_time(value)
    if not parsed:
        return None
    return parsed.replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z")


def is_exact_minute_timestamp(value: Any) -> bool:
    parsed = parse_time(value)
    return bool(parsed and parsed.second == 0 and parsed.microsecond == 0)


def step_at_least(step: Any, minimum: str) -> bool:
    return STEP_RANK.get(str(step), 0) >= STEP_RANK[minimum]


def active_levels(tv_context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    levels = tv_context.get("levels") if isinstance(tv_context.get("levels"), dict) else {}
    active: dict[str, dict[str, Any]] = {}
    for name, details in levels.items():
        if name not in ACTIVE_PRIORITY or not isinstance(details, dict):
            continue
        if str(details.get("status") or "").upper() != "ACTIVE":
            continue
        price = optional_float(details.get("price"))
        if price is None:
            continue
        active[name] = {**details, "price": price}
    return active


def level_side(name: str) -> str | None:
    if name in UPPER_LIQUIDITY_LEVELS:
        return "upper"
    if name in LOWER_LIQUIDITY_LEVELS:
        return "lower"
    return None


def expected_active_liquidity(record: dict[str, Any], tv_context: dict[str, Any] | None) -> str | None:
    """Expected active level from close-confirmed candle close and current TV levels."""
    if not isinstance(tv_context, dict):
        return None
    close = optional_float(record.get("candle_close"))
    if close is None:
        return None
    candidates = []
    for name, details in active_levels(tv_context).items():
        price = optional_float(details.get("price"))
        if price is None:
            continue
        side = level_side(name)
        if side == "upper" and close >= price:
            candidates.append((abs(close - price), ACTIVE_PRIORITY[name], name))
        elif side == "lower" and close <= price:
            candidates.append((abs(close - price), ACTIVE_PRIORITY[name], name))
    if not candidates:
        return None
    return min(candidates)[2]


def load_bars(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    payload = read_json(path)
    output: dict[str, dict[str, dict[str, Any]]] = {symbol: {} for symbol in SYMBOLS}
    for raw_symbol, bars in (payload.get("symbols") or {}).items():
        symbol = root_symbol(str(raw_symbol))
        if symbol not in output or not isinstance(bars, list):
            continue
        for bar in bars:
            if not isinstance(bar, dict):
                continue
            key = minute_key(bar.get("timestamp"))
            if key:
                output[symbol][key] = bar
    return output


def load_tv_contexts(path: Path) -> dict[str, dict[str, Any]]:
    payload = read_json(path)
    contexts = payload.get("symbols") if isinstance(payload, dict) else {}
    if not isinstance(contexts, dict):
        return {}
    return {root_symbol(symbol): context for symbol, context in contexts.items() if isinstance(context, dict)}


def load_submitted_trades(persistence_path: Path, executor_path: Path, fill_audit_path: Path) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    persistence = read_json(persistence_path)
    for trade in (persistence.get("trades") or {}).values():
        if not isinstance(trade, dict):
            continue
        trades.append(
            {
                "source": str(persistence_path),
                "trade_id": trade.get("trade_id"),
                "symbol": root_symbol(str(trade.get("requested_symbol") or trade.get("symbol") or "")),
                "execution_symbol": trade.get("execution_symbol") or trade.get("symbol"),
                "direction": trade.get("direction"),
                "created_at": trade.get("created_at"),
                "entry_price": trade.get("entry_price"),
                "status": trade.get("status"),
            }
        )

    executor = read_json(executor_path)
    for order in (executor.get("orders") or {}).values():
        if not isinstance(order, dict) or order.get("type") != "entry":
            continue
        trades.append(
            {
                "source": str(executor_path),
                "trade_id": order.get("trade_id"),
                "order_id": order.get("order_id"),
                "symbol": root_symbol(str(order.get("symbol") or order.get("resolved_symbol") or "")),
                "execution_symbol": order.get("resolved_symbol") or order.get("symbol"),
                "direction": order.get("direction"),
                "created_at": order.get("filled_at") or order.get("created_at"),
                "entry_price": order.get("filled_price"),
                "status": order.get("status"),
            }
        )

    for audit in read_jsonl(fill_audit_path):
        if audit.get("reject_reason"):
            continue
        trades.append(
            {
                "source": str(fill_audit_path),
                "trade_id": audit.get("trade_id"),
                "order_id": audit.get("order_id"),
                "symbol": root_symbol(str(audit.get("requested_symbol") or audit.get("execution_symbol") or "")),
                "execution_symbol": audit.get("execution_symbol"),
                "direction": audit.get("direction"),
                "created_at": audit.get("timestamp"),
                "entry_price": audit.get("selected_fill_price"),
                "status": "submitted",
            }
        )
    return [trade for trade in trades if trade.get("symbol") in SYMBOLS]


def trades_by_minute(trades: list[dict[str, Any]], date_text: str) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        created_at = parse_time(trade.get("created_at"))
        if not created_at or created_at.date().isoformat() != date_text:
            continue
        key = created_at.replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z")
        grouped[(str(trade["symbol"]), key)].append(trade)
    return grouped


def add_case(cases: list[dict[str, Any]], case_type: str, record: dict[str, Any], message: str, expected: Any, actual: Any) -> None:
    cases.append(
        {
            "case_type": case_type,
            "symbol": record.get("symbol"),
            "timestamp": record.get("timestamp"),
            "candle_time": record.get("candle_time"),
            "candle_minute": minute_key(record.get("candle_time")),
            "message": message,
            "expected": expected,
            "actual": actual,
            "record": {
                "step": record.get("step"),
                "active_liquidity_name": record.get("active_liquidity_name"),
                "liquidity_price": record.get("liquidity_price"),
                "setup_direction": record.get("setup_direction"),
                "leg1_state": record.get("leg1_state"),
                "leg1_completed_at": record.get("leg1_completed_at"),
                "leg2_state": record.get("leg2_state"),
                "entry_status": record.get("entry_status"),
                "wait_reason": record.get("wait_reason"),
                "last_decision": record.get("last_decision"),
            },
        }
    )


def audit_records(
    records: list[dict[str, Any]],
    bars: dict[str, dict[str, dict[str, Any]]],
    contexts: dict[str, dict[str, Any]],
    trades_for_minute: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    last_leg1_complete_minute: dict[str, str] = {}
    seen_trade_keys_by_symbol: dict[str, set[str]] = defaultdict(set)

    for record in records:
        symbol = root_symbol(str(record.get("symbol") or ""))
        if symbol not in SYMBOLS:
            continue
        candle_minute = minute_key(record.get("candle_time"))
        bar = bars.get(symbol, {}).get(candle_minute or "")
        close_confirmed = bool(candle_minute and bar)
        expected_active = expected_active_liquidity(record, contexts.get(symbol))
        flags: list[str] = []

        if record.get("leg1_state") == "COMPLETE":
            completed_minute = minute_key(record.get("leg1_completed_at"))
            if not completed_minute or completed_minute not in bars.get(symbol, {}):
                flags.append("leg1_complete_without_completed_bar")
                add_case(
                    cases,
                    "leg1_marked_complete_before_participation_or_close",
                    record,
                    "Leg 1 COMPLETE is published without a matching completed 1-minute bar.",
                    "WAIT until participation candle close is confirmed",
                    "Leg 1 COMPLETE",
                )
            if not record.get("setup_direction") or not record.get("rejection_mode_entered"):
                flags.append("leg1_complete_without_visible_participation_context")
                add_case(
                    cases,
                    "leg1_marked_complete_before_participation",
                    record,
                    "Leg 1 COMPLETE is visible while setup/rejection participation context is not confirmed.",
                    "WAIT / monitoring participation",
                    {"leg1_state": record.get("leg1_state"), "setup_direction": record.get("setup_direction")},
                )
            if completed_minute:
                last_leg1_complete_minute[symbol] = completed_minute

        if step_at_least(record.get("step"), "Step 5"):
            leg1_minute = minute_key(record.get("leg1_completed_at")) or last_leg1_complete_minute.get(symbol)
            if not leg1_minute or (candle_minute and leg1_minute >= candle_minute):
                flags.append("step5_before_prior_confirmed_leg1")
                add_case(
                    cases,
                    "step_jumped_to_step5_too_early",
                    record,
                    "Step 5 is visible before a prior candle has a close-confirmed Leg 1.",
                    "Step 4 / WAIT until next closed candle",
                    record.get("step"),
                )

        actual_active = record.get("active_liquidity_name")
        if expected_active and actual_active and actual_active != expected_active:
            flags.append("active_liquidity_mismatch")
            add_case(
                cases,
                "active_liquidity_expected_mismatch",
                record,
                f"Expected active liquidity {expected_active} from the logged candle close and TV levels, but status published {actual_active}.",
                expected_active,
                actual_active,
            )

        if not is_exact_minute_timestamp(record.get("candle_time")) and step_at_least(record.get("step"), "Step 5"):
            flags.append("advanced_state_on_non_close_timestamp")
            add_case(
                cases,
                "status_not_close_confirmed",
                record,
                "Advanced state was published from a non-minute candle timestamp.",
                "WAIT until close-confirmed minute bar",
                record.get("step"),
            )

        minute_trades = trades_for_minute.get((symbol, candle_minute or ""), [])
        for trade in minute_trades:
            trade_key = str(trade.get("trade_id") or trade.get("order_id") or "")
            if trade_key:
                seen_trade_keys_by_symbol[symbol].add(trade_key)

        rows.append(
            {
                "symbol": symbol,
                "timestamp": record.get("timestamp"),
                "candle_time": record.get("candle_time"),
                "candle_minute": candle_minute,
                "close_confirmed": close_confirmed,
                "expected_step": "Step 4/WAIT" if flags and "step5_before_prior_confirmed_leg1" in flags else record.get("step"),
                "actual_step": record.get("step"),
                "expected_active_liquidity": expected_active,
                "actual_active_liquidity": actual_active,
                "leg1_state": record.get("leg1_state"),
                "leg2_state": record.get("leg2_state"),
                "entry_status": record.get("entry_status"),
                "trades": minute_trades,
                "flags": flags,
            }
        )

    for symbol, trade_keys in seen_trade_keys_by_symbol.items():
        if symbol == "NQ" and len(trade_keys) > 1:
            synthetic_record = {"symbol": symbol, "timestamp": None, "candle_time": None}
            add_case(
                cases,
                "nq_rearmed_overfired_multiple_entries",
                synthetic_record,
                "NQ has multiple submitted/filled entries in today's audited window.",
                "At most one armed Entry Agent fire per setup",
                sorted(trade_keys),
            )
    return rows, cases


def write_report(path: Path, date_text: str, rows: list[dict[str, Any]], cases: list[dict[str, Any]], source_paths: dict[str, Path]) -> None:
    counts_by_type = defaultdict(int)
    for case in cases:
        counts_by_type[case["case_type"]] += 1

    lines = [
        f"# Entry Agent Replay Audit - {date_text}",
        "",
        "## Sources",
    ]
    for name, source_path in source_paths.items():
        lines.append(f"- {name}: `{source_path}`")
    lines.extend(["", "## Summary"])
    lines.append(f"- Audited rows: {len(rows)}")
    lines.append(f"- Regression cases: {len(cases)}")
    for case_type, count in sorted(counts_by_type.items()):
        lines.append(f"- {case_type}: {count}")

    lines.extend(["", "## Candle-by-Candle Findings"])
    flagged_rows = [row for row in rows if row["flags"]]
    for row in flagged_rows[:200]:
        trade_text = ", ".join(str(trade.get("trade_id") or trade.get("order_id")) for trade in row["trades"]) or "-"
        lines.append(
            "| {symbol} | {candle} | close_confirmed={confirmed} | expected_step={expected_step} | "
            "actual_step={actual_step} | expected_liq={expected_liq} | actual_liq={actual_liq} | "
            "leg1={leg1} | leg2={leg2} | trades={trades} | flags={flags} |".format(
                symbol=row["symbol"],
                candle=row["candle_time"],
                confirmed=row["close_confirmed"],
                expected_step=row["expected_step"],
                actual_step=row["actual_step"],
                expected_liq=row["expected_active_liquidity"],
                actual_liq=row["actual_active_liquidity"],
                leg1=row["leg1_state"],
                leg2=row["leg2_state"],
                trades=trade_text,
                flags=",".join(row["flags"]),
            )
        )

    lines.extend(["", "## Regression Cases"])
    for case in cases[:200]:
        lines.append(
            f"- `{case['case_type']}` {case.get('symbol')} {case.get('candle_time')}: "
            f"{case['message']} expected={case['expected']} actual={case['actual']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_audit(date_text: str) -> dict[str, Any]:
    source_paths = {
        "reasoning": DATA_DIR / f"entry_reasoning_{date_text}.jsonl",
        "recent_bars": DATA_DIR / "rithmic_recent_bars.json",
        "tv_context_by_symbol": BASE_DIR / "tv_context_by_symbol.json",
        "tv_context_events": BASE_DIR / "tv_context_events.jsonl",
        "persistence_state": DATA_DIR / "persistence_state.json",
        "executor_state": DATA_DIR / "executor_state.json",
        "fill_audit": DATA_DIR / "fill_audit_log.jsonl",
    }
    records = read_jsonl(source_paths["reasoning"])
    bars = load_bars(source_paths["recent_bars"])
    contexts = load_tv_contexts(source_paths["tv_context_by_symbol"])
    trades = load_submitted_trades(source_paths["persistence_state"], source_paths["executor_state"], source_paths["fill_audit"])
    rows, cases = audit_records(records, bars, contexts, trades_by_minute(trades, date_text))
    return {
        "date": date_text,
        "source_paths": {name: str(path) for name, path in source_paths.items()},
        "rows": rows,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Entry Agent replay/audit report from existing logs.")
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--report", default=None)
    parser.add_argument("--cases", default=None)
    args = parser.parse_args()

    audit = build_audit(args.date)
    report_path = Path(args.report) if args.report else DATA_DIR / f"entry_replay_audit_{args.date}.md"
    cases_path = Path(args.cases) if args.cases else DATA_DIR / f"entry_replay_regression_cases_{args.date}.json"
    write_report(
        report_path,
        args.date,
        audit["rows"],
        audit["cases"],
        {name: Path(path) for name, path in audit["source_paths"].items()},
    )
    cases_path.write_text(json.dumps(audit["cases"], indent=2) + "\n", encoding="utf-8")
    print(f"report={report_path}")
    print(f"cases={cases_path}")
    print(f"rows={len(audit['rows'])}")
    print(f"cases_count={len(audit['cases'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
