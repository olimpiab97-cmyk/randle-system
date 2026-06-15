import argparse
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path


MODELS = ("fixed_8", "fixed_12", "fixed_16", "structural_dynamic")
HALF_ATR_MODEL = "half_atr_dynamic"
SYMBOLS = ("NQM6", "YMM6", "RTYM6")
DEFAULT_PATH = Path("Data") / "trade_management_research.jsonl"
ROOT = Path(__file__).resolve().parent


def load_trade_manager():
    spec = importlib.util.spec_from_file_location(
        "trade_manager_research_report",
        ROOT / "Engines" / "trade_manager.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_rows(path):
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON on line {line_number}: {exc}") from exc
    return rows


def baseline_bucket(row):
    result = str(row.get("actual_result") or row.get("actual_exit_reason") or "flat").lower()
    if result == "tp1":
        return "TP1"
    if result in {"be", "break_even", "breakeven"}:
        return "BE"
    if result in {"stop", "stopped", "loss"}:
        return "STOP"
    return "FLAT"


def dynamic_bucket(row, model):
    result = str(row.get(f"{model}_model_result") or "").lower()
    if result == "tp1":
        return "TP1"
    if result == "stop":
        return "STOP"
    return "SAME"


def model_flag(row, field, model):
    values = row.get(field)
    if isinstance(values, dict):
        return bool(values.get(model))
    return False


def half_atr_fields(row, manager):
    if "half_atr_dynamic_enabled" in row:
        return row
    return {**row, **manager.half_atr_dynamic_research_row_fields(dict(row))}


def numeric(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def average(values):
    values = [value for value in values if value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def format_number(value):
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def trade_label(row):
    return (
        f"{row.get('symbol')} {row.get('trade_id')} "
        f"{row.get('direction')} entry={row.get('entry_price')}"
    )


def print_counter(title, counter, keys):
    print(title)
    for key in keys:
        print(f"  {key}: {counter.get(key, 0)}")


def main():
    parser = argparse.ArgumentParser(description="Summarize observational Trade Manager research rows.")
    parser.add_argument("--path", default=str(DEFAULT_PATH), help="JSONL research file path")
    args = parser.parse_args()

    path = Path(args.path)
    rows = load_rows(path)
    manager = load_trade_manager()
    half_rows = [half_atr_fields(row, manager) for row in rows]

    baseline_counts = Counter(baseline_bucket(row) for row in rows)
    dynamic_counts = {model: Counter(dynamic_bucket(row, model) for row in rows) for model in MODELS}
    helped_counts = {model: sum(1 for row in rows if model_flag(row, "dynamic_helped", model)) for model in MODELS}
    hurt_counts = {model: sum(1 for row in rows if model_flag(row, "dynamic_hurt", model)) for model in MODELS}
    net = {model: helped_counts[model] - hurt_counts[model] for model in MODELS}

    print(f"Research file: {path}")
    print(f"Total observed trades: {len(rows)}")
    print_counter("Baseline counts", baseline_counts, ("TP1", "BE", "STOP", "FLAT"))

    print("Dynamic model counts")
    for model in MODELS:
        counts = dynamic_counts[model]
        print(f"  {model}: TP1={counts.get('TP1', 0)} STOP={counts.get('STOP', 0)} SAME={counts.get('SAME', 0)}")

    print("Help / hurt / net")
    for model in MODELS:
        print(f"  {model}: helped={helped_counts[model]} hurt={hurt_counts[model]} net={net[model]}")

    half_evaluable = [row for row in half_rows if row.get("half_atr_dynamic_enabled")]
    half_triggered = [row for row in half_evaluable if row.get("half_atr_dynamic_trigger_reached")]
    half_improved_risk = [
        row for row in half_triggered
        if row.get("half_atr_dynamic_used_original_stop") is False
    ]
    half_retained_original = [
        row for row in half_triggered
        if row.get("half_atr_dynamic_used_original_stop") is True
    ]
    half_classification = Counter(row.get("half_atr_dynamic_helped_hurt_same") or "unable_to_evaluate" for row in half_rows)
    half_unable_reasons = Counter(
        row.get("half_atr_dynamic_unable_to_evaluate_reason") or "unspecified"
        for row in half_rows
        if row.get("half_atr_dynamic_helped_hurt_same") == "unable_to_evaluate"
    )
    half_r_values = [numeric(row.get("half_atr_dynamic_result_r")) for row in half_rows]
    half_winner_r_values = [
        numeric(row.get("half_atr_dynamic_result_r"))
        for row in half_rows
        if numeric(row.get("half_atr_dynamic_result_r")) is not None and numeric(row.get("half_atr_dynamic_result_r")) > 0
    ]
    baseline_r_values = [
        manager.actual_result_r(row)
        for row in rows
        if manager.actual_result_r(row) is not None
    ]

    print("HALF_ATR_DYNAMIC_RISK_RESET")
    print(f"  Total trades evaluated: {len(rows)}")
    print(f"  Trades reaching 0.5 ATR favorable trigger: {len(half_triggered)}")
    print(f"  Trades where dynamic stop improved risk: {len(half_improved_risk)}")
    print(f"  Trades where original stop/TP1 were retained because adjustment was worse: {len(half_retained_original)}")
    print(
        "  Helped / hurt / same totals: "
        f"helped={half_classification.get('helped', 0)} "
        f"hurt={half_classification.get('hurt', 0)} "
        f"same={half_classification.get('same', 0)} "
        f"unable_to_evaluate={half_classification.get('unable_to_evaluate', 0)}"
    )
    print(f"  Average R of all trades: {format_number(average(half_r_values))}")
    print(f"  Average R of winners: {format_number(average(half_winner_r_values))}")
    print(f"  Baseline average R: {format_number(average(baseline_r_values))}")
    print(f"  Comparison versus actual baseline: avg_delta_r={format_number((average(half_r_values) - average(baseline_r_values)) if average(half_r_values) is not None and average(baseline_r_values) is not None else None)}")
    print(f"  Unable to evaluate reasons: {dict(half_unable_reasons)}")

    print("Per-symbol breakdown")
    by_symbol = defaultdict(list)
    for row in rows:
        by_symbol[row.get("symbol")].append(row)
    for symbol in SYMBOLS:
        symbol_rows = by_symbol.get(symbol, [])
        baseline = Counter(baseline_bucket(row) for row in symbol_rows)
        print(f"  {symbol}: trades={len(symbol_rows)} baseline={dict(baseline)}")
        for model in MODELS:
            helped = sum(1 for row in symbol_rows if model_flag(row, "dynamic_helped", model))
            hurt = sum(1 for row in symbol_rows if model_flag(row, "dynamic_hurt", model))
            counts = Counter(dynamic_bucket(row, model) for row in symbol_rows)
            print(
                f"    {model}: TP1={counts.get('TP1', 0)} "
                f"STOP={counts.get('STOP', 0)} SAME={counts.get('SAME', 0)} "
                f"helped={helped} hurt={hurt} net={helped - hurt}"
            )

    print("Helped trades")
    helped_any = False
    for row in rows:
        models = [model for model in MODELS if model_flag(row, "dynamic_helped", model)]
        if models:
            helped_any = True
            print(f"  {trade_label(row)} models={','.join(models)}")
    if not helped_any:
        print("  none")

    print("Hurt trades")
    hurt_any = False
    for row in rows:
        models = [model for model in MODELS if model_flag(row, "dynamic_hurt", model)]
        if models:
            hurt_any = True
            print(f"  {trade_label(row)} models={','.join(models)}")
    if not hurt_any:
        print("  none")


if __name__ == "__main__":
    main()
