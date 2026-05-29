import argparse
import importlib.util
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
DEFAULT_TRADE_IDS = ["T-b12f8b21", "T-1ec5a9b3"]
LOCAL_ZONE = ZoneInfo("America/Los_Angeles")
UTC_ZONE = ZoneInfo("UTC")


def load_trade_manager():
    spec = importlib.util.spec_from_file_location(
        "trade_manager_research_backfill",
        ROOT / "Engines" / "trade_manager.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path):
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def parse_timestamp(value):
    if not value:
        return datetime.min
    raw_value = str(value)
    if raw_value.endswith("Z"):
        raw_value = raw_value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return datetime.min
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC_ZONE).replace(tzinfo=None)
    return parsed.replace(tzinfo=LOCAL_ZONE).astimezone(UTC_ZONE).replace(tzinfo=None)


def collect_fill_audit_by_trade_id(rows):
    result = {}
    for row in rows:
        trade_id = row.get("trade_id")
        if trade_id:
            result[trade_id] = row
    return result


def collect_orders_by_trade_id(executor_state):
    result = {}
    for order in (executor_state.get("orders") or {}).values():
        trade_id = order.get("trade_id")
        if trade_id:
            result.setdefault(trade_id, []).append(order)
    return result


def add_sample(samples, timestamp, price, source):
    if timestamp is None or price is None:
        return
    try:
        samples.append({
            "timestamp": timestamp,
            "price": float(price),
            "source": source,
        })
    except (TypeError, ValueError):
        return


def collect_post_be_samples(trade, event_log, orders):
    samples = []
    be_hit_at = trade.get("be_hit_at")
    add_sample(samples, be_hit_at, trade.get("be_trigger"), "be_trigger")

    for event in event_log:
        if event.get("trade_id") != trade.get("trade_id"):
            continue
        details = event.get("details") or {}
        price = details.get("price")
        timestamp = event.get("timestamp")
        if price is not None and parse_timestamp(timestamp) >= parse_timestamp(be_hit_at):
            add_sample(samples, timestamp, price, "event_log_price")

    add_sample(samples, trade.get("last_price_at"), trade.get("last_price"), "trade_last_price")

    for order in orders:
        if order.get("type") != "stop":
            continue
        add_sample(
            samples,
            order.get("filled_at") or order.get("closed_at"),
            order.get("fill_trigger_price"),
            "executor_stop_fill_trigger",
        )
        add_sample(
            samples,
            order.get("filled_at") or order.get("closed_at"),
            order.get("filled_price") or order.get("stop_price"),
            "executor_stop_fill",
        )

    add_sample(samples, trade.get("closed_at"), trade.get("exit_price"), "trade_exit")

    deduped = {}
    for sample in samples:
        key = (str(sample["timestamp"]), sample["price"], sample["source"])
        deduped[key] = sample
    return sorted(deduped.values(), key=lambda item: parse_timestamp(item["timestamp"]))


def existing_trade_ids_in_research(path):
    return {
        row.get("trade_id")
        for row in load_jsonl(path)
        if row.get("trade_id")
    }


def remove_trade_ids_from_research(path, trade_ids):
    if not path.exists():
        return 0
    trade_ids = set(trade_ids)
    rows = load_jsonl(path)
    kept_rows = [row for row in rows if row.get("trade_id") not in trade_ids]
    removed_count = len(rows) - len(kept_rows)
    with path.open("w", encoding="utf-8") as f:
        for row in kept_rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    return removed_count


def backfill_trade(manager, trade, fill_audit, event_log, orders):
    replay_trade = deepcopy(trade)
    manager.capture_entry_leg_extremes(replay_trade, fill_audit, replay_trade)

    for sample in collect_post_be_samples(replay_trade, event_log, orders):
        manager.update_post_be_analytics(
            replay_trade,
            sample["price"],
            sample["timestamp"],
        )

    return manager.build_trade_management_research_row(replay_trade)


def main():
    parser = argparse.ArgumentParser(description="Backfill research-only trade management analytics JSONL rows.")
    parser.add_argument("trade_ids", nargs="*", default=DEFAULT_TRADE_IDS)
    parser.add_argument("--force", action="store_true", help="append even if a trade_id already exists in JSONL")
    parser.add_argument("--replace", action="store_true", help="replace existing JSONL rows for the selected trade_ids")
    args = parser.parse_args()

    manager = load_trade_manager()
    state = load_json(ROOT / "Data" / "persistence_state.json", {})
    fill_audit_by_trade_id = collect_fill_audit_by_trade_id(load_jsonl(ROOT / "Data" / "fill_audit_log.jsonl"))
    orders_by_trade_id = collect_orders_by_trade_id(load_json(ROOT / "Data" / "executor_state.json", {}))
    research_path = Path(manager.TRADE_MANAGEMENT_RESEARCH_FILE)
    removed_count = remove_trade_ids_from_research(research_path, args.trade_ids) if args.replace else 0
    existing_trade_ids = existing_trade_ids_in_research(research_path)

    rows = []
    for trade_id in args.trade_ids:
        if trade_id in existing_trade_ids and not args.force:
            continue
        trade = (state.get("trades") or {}).get(trade_id)
        if not trade:
            raise SystemExit(f"trade_not_found: {trade_id}")
        if trade.get("status") != "closed" or not trade.get("moved_to_be"):
            raise SystemExit(f"trade_not_closed_be: {trade_id}")
        rows.append(backfill_trade(
            manager,
            trade,
            fill_audit_by_trade_id.get(trade_id, {}),
            state.get("event_log") or [],
            orders_by_trade_id.get(trade_id, []),
        ))

    research_path.parent.mkdir(parents=True, exist_ok=True)
    with research_path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    print(json.dumps({
        "ok": True,
        "path": str(research_path),
        "written": len(rows),
        "removed": removed_count,
        "trade_ids": [row.get("trade_id") for row in rows],
    }, indent=2))
    for row in rows:
        print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
