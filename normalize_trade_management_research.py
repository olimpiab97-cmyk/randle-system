import argparse
import json
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


MODELS = ("fixed_8", "fixed_12", "fixed_16", "structural_dynamic")
DEFAULT_RESEARCH_PATH = Path("Data") / "trade_management_research.jsonl"
DEFAULT_STATE_PATH = Path("Data") / "persistence_state.json"
DEFAULT_EXECUTOR_PATH = Path("Data") / "executor_state.json"
MISSING_BACKFILL_IDS = ("T-ce62f567",)


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
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def coerce_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def round_value(value):
    if value is None:
        return None
    rounded = round(float(value), 8)
    if rounded == int(rounded):
        return float(int(rounded))
    return rounded


def date_from_timestamp(value):
    if not value:
        return None
    return str(value)[:10]


def point_value(symbol):
    root = str(symbol or "").upper()
    if root.startswith("NQ"):
        return 20.0
    if root.startswith("YM"):
        return 5.0
    if root.startswith("RTY"):
        return 50.0
    return None


def actual_result(row, trade=None):
    for source in (row, trade or {}):
        result = source.get("actual_result")
        if result:
            return str(result).lower()
    profit = coerce_float((trade or {}).get("total_profit"))
    if profit is None:
        profit = coerce_float((trade or {}).get("total_pnl"))
    if profit is None:
        return "unknown"
    if profit > 0:
        return "win"
    if profit < 0:
        return "loss"
    return "flat"


def model_result(row, model):
    result = row.get(f"{model}_model_result")
    if result:
        return str(result).lower()
    comparison = row.get("model_comparisons")
    if isinstance(comparison, dict):
        result = (comparison.get(model) or {}).get("model_result")
        if result:
            return str(result).lower()
    return "no_hit"


def classify_model(row, model, baseline):
    helped = row.get("dynamic_helped")
    hurt = row.get("dynamic_hurt")
    same = row.get("dynamic_same")
    if isinstance(helped, dict) or isinstance(hurt, dict) or isinstance(same, dict):
        if isinstance(helped, dict) and helped.get(model):
            return "HELPED"
        if isinstance(hurt, dict) and hurt.get(model):
            return "HURT"
        if isinstance(same, dict) and same.get(model):
            return "SAME"

    result = model_result(row, model)
    if result == "tp1" and baseline in {"flat", "loss", "stop", "unknown"}:
        return "HELPED"
    if result == "stop" and baseline in {"flat", "win", "tp1", "unknown"}:
        return "HURT"
    return "SAME"


def reason_for_classification(row, model, classification, baseline):
    reason_map = row.get("dynamic_help_reason") if classification == "HELPED" else row.get("dynamic_hurt_reason")
    if isinstance(reason_map, dict) and reason_map.get(model):
        return reason_map.get(model)
    result = model_result(row, model)
    if classification == "HELPED":
        return f"{model} reached TP1 while baseline/current result was {baseline}."
    if classification == "HURT":
        return f"{model} hit stop while baseline/current result was {baseline}."
    return f"{model} did not materially improve or worsen the baseline/current result."


def infer_atr(row, trade, audit):
    atr = coerce_float(row.get("atr_value"))
    source = "research_row"
    if atr is None and trade:
        atr = coerce_float(trade.get("atr_value"))
        source = "persistence_state"
    if atr is None:
        entry = coerce_float(row.get("entry_price"))
        stop = coerce_float(row.get("original_stop"))
        if entry is not None and stop is not None:
            atr = abs(entry - stop)
            source = "original_stop_distance_reconstructed"
            audit["missing_inputs"].append("atr_value")
    if atr is None:
        audit["missing_inputs"].append("atr_value")
    return round_value(atr), source


def first_hit_from_trade(trade, model, result):
    if not trade:
        return None, None, None, None
    first_event = trade.get(f"{model}_model_first_hit")
    tp1_at = trade.get(f"{model}_tp1_first_hit_at")
    stop_at = trade.get(f"{model}_stop_first_hit_at")
    if first_event == "tp1":
        return "tp1", tp1_at, tp1_at, stop_at
    if first_event == "stop":
        return "stop", stop_at, tp1_at, stop_at
    if result == "tp1" and tp1_at:
        return "tp1", tp1_at, tp1_at, stop_at
    if result == "stop" and stop_at:
        return "stop", stop_at, tp1_at, stop_at
    return None, None, tp1_at, stop_at


def infer_first_hit(row, trade, model, result, audit):
    first_event, first_at, tp1_at, stop_at = first_hit_from_trade(trade, model, result)
    confidence = "exact"
    if not first_event and result in {"tp1", "stop"}:
        first_event = result
        first_at = row.get("post_be_first_seen_at") if result == "tp1" else row.get("post_be_last_updated_at")
        if result == "tp1":
            tp1_at = tp1_at or first_at
        else:
            stop_at = stop_at or first_at
        confidence = "reconstructed"
        audit["missing_inputs"].append(f"{model}_first_hit_timestamp")
    if result == "no_hit":
        first_event = "no_hit"
    if result in {"tp1", "stop"} and not first_at:
        audit["missing_inputs"].append(f"{model}_first_hit_timestamp")
    return first_event, first_at, tp1_at, stop_at, confidence


def model_field(row, model, field):
    comparison = row.get("model_comparisons")
    if isinstance(comparison, dict) and isinstance(comparison.get(model), dict):
        value = comparison[model].get(field)
        if value is not None:
            return value
    return row.get(f"{model}_{field}")


def build_models(row, trade, audit):
    models = {}
    hit_confidences = []
    for model in MODELS:
        result = model_result(row, model)
        first_event, first_at, tp1_at, stop_at, confidence = infer_first_hit(row, trade, model, result, audit)
        hit_confidences.append(confidence)
        models[model] = {
            "stop_price": model_field(row, model, "stop_price"),
            "tp1_price": model_field(row, model, "tp1_price"),
            "stop_distance_points": model_field(row, model, "stop_distance_points"),
            "result": result,
            "tp1_would_hit": bool(model_field(row, model, "tp1_would_hit")),
            "stop_would_hit": bool(model_field(row, model, "stop_would_hit")),
            "first_hit_event": first_event,
            "first_hit_at": first_at,
            "tp1_first_hit_at": tp1_at,
            "stop_first_hit_at": stop_at,
            "first_hit_confidence": confidence,
        }
    return models, hit_confidences


def overall_classification(by_model):
    values = set(by_model.values())
    if "HURT" in values:
        return "HURT"
    if "HELPED" in values:
        return "HELPED"
    return "SAME"


def build_classification(row, models, baseline):
    by_model = {model: classify_model(row, model, baseline) for model in MODELS}
    reason_by_model = {
        model: reason_for_classification(row, model, by_model[model], baseline)
        for model in MODELS
    }
    overall = overall_classification(by_model)
    if overall == "HELPED":
        reason = "At least one dynamic model reached TP1 while the baseline/current result did not."
    elif overall == "HURT":
        reason = "At least one dynamic model hit stop before producing an offsetting improvement."
    else:
        reason = "Dynamic models did not materially change the baseline/current result."
    return {
        "overall": overall,
        "by_model": by_model,
        "reason": reason,
        "reason_by_model": reason_by_model,
    }


def normalize_row(row, state, source="migration"):
    trade_id = row.get("trade_id")
    trade = (state.get("trades") or {}).get(trade_id) or {}
    audit = {
        "source": source,
        "backfill_confidence": "exact",
        "missing_inputs": [],
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "raw_row": deepcopy(row),
    }
    atr_value, atr_source = infer_atr(row, trade, audit)
    models, hit_confidences = build_models(row, trade, audit)
    baseline = actual_result(row, trade)
    classification = build_classification(row, models, baseline)
    if audit["missing_inputs"]:
        audit["backfill_confidence"] = "partial" if atr_value is None else "reconstructed"
    elif any(confidence == "reconstructed" for confidence in hit_confidences):
        audit["backfill_confidence"] = "reconstructed"
    audit["missing_inputs"] = sorted(set(audit["missing_inputs"]))

    symbol = row.get("symbol") or trade.get("symbol")
    return {
        "schema_version": 2,
        "trade_id": trade_id,
        "date": date_from_timestamp(row.get("closed_at") or trade.get("closed_at")),
        "symbol": symbol,
        "direction": row.get("direction") or trade.get("direction"),
        "entry_price": row.get("entry_price") if row.get("entry_price") is not None else trade.get("entry_price"),
        "original_stop": row.get("original_stop") if row.get("original_stop") is not None else trade.get("original_stop"),
        "original_tp1_price": row.get("original_tp1_price") if row.get("original_tp1_price") is not None else trade.get("tp1_price"),
        "atr_value": atr_value,
        "atr_source": atr_source,
        "atr_bar_timestamp": trade.get("atr_bar_timestamp"),
        "point_value": point_value(symbol),
        "be_trigger": row.get("be_trigger") if row.get("be_trigger") is not None else trade.get("be_trigger"),
        "be_hit_at": row.get("be_hit_at") or trade.get("be_hit_at"),
        "closed_at": row.get("closed_at") or trade.get("closed_at"),
        "actual_exit_price": row.get("actual_exit_price") if row.get("actual_exit_price") is not None else trade.get("exit_price"),
        "actual_exit_reason": row.get("actual_exit_reason") or trade.get("exit_reason"),
        "actual_result": baseline,
        "post_be_best_price": row.get("post_be_best_price"),
        "post_be_worst_price": row.get("post_be_worst_price"),
        "post_be_mfe_points": row.get("post_be_mfe_points"),
        "post_be_mae_points": row.get("post_be_mae_points"),
        "post_be_mfe_ticks": row.get("post_be_mfe_ticks"),
        "post_be_mae_ticks": row.get("post_be_mae_ticks"),
        "post_be_first_seen_at": row.get("post_be_first_seen_at"),
        "post_be_last_updated_at": row.get("post_be_last_updated_at"),
        "entry_leg_high": row.get("entry_leg_high"),
        "entry_leg_low": row.get("entry_leg_low"),
        "models": models,
        "classification": classification,
        "audit": audit,
    }


def row_from_trade(trade):
    row = {
        "trade_id": trade.get("trade_id"),
        "symbol": trade.get("symbol"),
        "direction": trade.get("direction"),
        "entry_price": trade.get("entry_price"),
        "original_stop": trade.get("original_stop"),
        "original_tp1_price": trade.get("original_tp1_price") or trade.get("tp1_price"),
        "be_trigger": trade.get("be_trigger"),
        "be_hit_at": trade.get("be_hit_at"),
        "closed_at": trade.get("closed_at"),
        "actual_exit_price": trade.get("exit_price"),
        "actual_exit_reason": trade.get("exit_reason"),
        "actual_result": "win" if coerce_float(trade.get("total_profit")) and coerce_float(trade.get("total_profit")) > 0 else "flat",
        "post_be_best_price": trade.get("post_be_best_price"),
        "post_be_worst_price": trade.get("post_be_worst_price"),
        "post_be_mfe_points": trade.get("post_be_mfe_points"),
        "post_be_mae_points": trade.get("post_be_mae_points"),
        "post_be_mfe_ticks": trade.get("post_be_mfe_ticks"),
        "post_be_mae_ticks": trade.get("post_be_mae_ticks"),
        "post_be_first_seen_at": trade.get("post_be_first_seen_at"),
        "post_be_last_updated_at": trade.get("post_be_last_updated_at"),
        "entry_leg_high": trade.get("entry_leg_high"),
        "entry_leg_low": trade.get("entry_leg_low"),
    }
    for model in MODELS:
        for field in (
            "stop_price",
            "tp1_price",
            "stop_distance_points",
            "tp1_would_hit",
            "stop_would_hit",
        ):
            row[f"{model}_{field}"] = trade.get(f"{model}_{field}")
        first_hit = trade.get(f"{model}_model_first_hit")
        if first_hit == "tp1":
            result = "tp1"
        elif first_hit == "stop":
            result = "stop"
        elif trade.get(f"{model}_tp1_would_hit"):
            result = "tp1"
        elif trade.get(f"{model}_stop_would_hit"):
            result = "stop"
        else:
            result = "no_hit"
        row[f"{model}_model_result"] = result
    return row


def append_missing_backfills(rows, state):
    existing_ids = {row.get("trade_id") for row in rows}
    added = []
    for trade_id in MISSING_BACKFILL_IDS:
        if trade_id in existing_ids:
            continue
        trade = (state.get("trades") or {}).get(trade_id)
        if not trade:
            continue
        if trade.get("status") != "closed" or not trade.get("moved_to_be"):
            continue
        rows.append(row_from_trade(trade))
        added.append(trade_id)
    return added


def summarize(rows):
    helped = sum(1 for row in rows if row.get("classification", {}).get("overall") == "HELPED")
    hurt = sum(1 for row in rows if row.get("classification", {}).get("overall") == "HURT")
    same = sum(1 for row in rows if row.get("classification", {}).get("overall") == "SAME")
    missing_atr = sum(1 for row in rows if row.get("atr_value") is None)
    missing_first_hit = 0
    for row in rows:
        models = row.get("models") or {}
        if any(
            model.get("result") in {"tp1", "stop"} and not model.get("first_hit_at")
            for model in models.values()
        ):
            missing_first_hit += 1
    return {
        "qualifying_count": len(rows),
        "helped_count": helped,
        "hurt_count": hurt,
        "same_count": same,
        "rows_still_missing_atr": missing_atr,
        "rows_still_missing_first_hit_timestamp": missing_first_hit,
    }


def normalize_file(research_path, state_path, backup_dir=None):
    old_rows = load_jsonl(research_path)
    state = load_json(state_path, {})
    working_rows = deepcopy(old_rows)
    backfilled_trade_ids = append_missing_backfills(working_rows, state)
    normalized = [normalize_row(row, state, "backfill" if row.get("trade_id") in backfilled_trade_ids else "migration") for row in working_rows]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = Path(backup_dir) if backup_dir else research_path.parent
    backup_path = backup_root / f"{research_path.stem}.backup_{timestamp}{research_path.suffix}"
    shutil.copy2(research_path, backup_path)
    write_jsonl(research_path, normalized)

    summary = summarize(normalized)
    summary.update({
        "old_row_count": len(old_rows),
        "new_row_count": len(normalized),
        "backup_path": str(backup_path),
        "backfilled_trade_ids": backfilled_trade_ids,
    })
    return summary


def main():
    parser = argparse.ArgumentParser(description="Normalize Trade Manager research JSONL into canonical audit schema.")
    parser.add_argument("--research-path", default=str(DEFAULT_RESEARCH_PATH))
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--backup-dir", default=None)
    args = parser.parse_args()

    summary = normalize_file(Path(args.research_path), Path(args.state_path), args.backup_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
