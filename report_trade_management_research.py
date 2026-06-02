import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


MODELS = ("fixed_8", "fixed_12", "fixed_16", "structural_dynamic")
SYMBOLS = ("NQM6", "YMM6", "RTYM6")
DEFAULT_PATH = Path("Data") / "trade_management_research.jsonl"


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
