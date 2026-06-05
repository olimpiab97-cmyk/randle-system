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
    models = row.get("models")
    if isinstance(models, dict) and isinstance(models.get(model), dict):
        result = str(models[model].get("result") or "").lower()
    else:
        result = str(row.get(f"{model}_model_result") or "").lower()
    if result == "tp1":
        return "TP1"
    if result == "stop":
        return "STOP"
    return "SAME"


def model_flag(row, field, model):
    classification = row.get("classification")
    if isinstance(classification, dict):
        by_model = classification.get("by_model")
        if isinstance(by_model, dict):
            value = str(by_model.get(model) or "").upper()
            if field == "dynamic_helped":
                return value == "HELPED"
            if field == "dynamic_hurt":
                return value == "HURT"
            if field == "dynamic_same":
                return value == "SAME"
    values = row.get(field)
    if isinstance(values, dict):
        return bool(values.get(model))
    return False


def model_classification(row, model):
    classification = row.get("classification")
    if isinstance(classification, dict):
        by_model = classification.get("by_model")
        if isinstance(by_model, dict):
            value = str(by_model.get(model) or "").upper()
            if value in {"HELPED", "HURT", "SAME"}:
                return value
    if model_flag(row, "dynamic_helped", model):
        return "HELPED"
    if model_flag(row, "dynamic_hurt", model):
        return "HURT"
    return "SAME"


def trade_level_classification(row):
    classification = row.get("classification")
    if isinstance(classification, dict):
        value = str(classification.get("overall") or "").upper()
        if value in {"HELPED", "HURT", "SAME"}:
            return value

    values = {model_classification(row, model) for model in MODELS}
    if "HURT" in values:
        return "HURT"
    if "HELPED" in values:
        return "HELPED"
    return "SAME"


def trade_label(row):
    return (
        f"{row.get('symbol')} {row.get('trade_id')} "
        f"{row.get('direction')} entry={row.get('entry_price')}"
    )


def print_counter(title, counter, keys):
    print(title)
    for key in keys:
        print(f"  {key}: {counter.get(key, 0)}")


def print_per_trade_classification(rows):
    headers = (
        "trade_id",
        "date",
        "symbol",
        "direction",
        "trade_level_classification",
        "fixed_8",
        "fixed_12",
        "fixed_16",
        "structural_dynamic",
    )
    table = []
    for row in rows:
        table.append({
            "trade_id": str(row.get("trade_id") or ""),
            "date": str(row.get("date") or str(row.get("closed_at") or "")[:10]),
            "symbol": str(row.get("symbol") or ""),
            "direction": str(row.get("direction") or ""),
            "trade_level_classification": trade_level_classification(row),
            "fixed_8": model_classification(row, "fixed_8"),
            "fixed_12": model_classification(row, "fixed_12"),
            "fixed_16": model_classification(row, "fixed_16"),
            "structural_dynamic": model_classification(row, "structural_dynamic"),
        })

    widths = {
        header: max(len(header), *(len(item[header]) for item in table)) if table else len(header)
        for header in headers
    }
    print("Per-trade model classification table")
    print("  " + "  ".join(header.ljust(widths[header]) for header in headers))
    print("  " + "  ".join("-" * widths[header] for header in headers))
    for item in table:
        print("  " + "  ".join(item[header].ljust(widths[header]) for header in headers))


def main():
    parser = argparse.ArgumentParser(description="Summarize observational Trade Manager research rows.")
    parser.add_argument("--path", default=str(DEFAULT_PATH), help="JSONL research file path")
    args = parser.parse_args()

    path = Path(args.path)
    rows = load_rows(path)

    baseline_counts = Counter(baseline_bucket(row) for row in rows)
    dynamic_counts = {model: Counter(dynamic_bucket(row, model) for row in rows) for model in MODELS}
    trade_level_counts = Counter(trade_level_classification(row) for row in rows)
    model_level_counts = {
        model: Counter(model_classification(row, model) for row in rows)
        for model in MODELS
    }

    print(f"Research file: {path}")
    print(f"Total observed trades: {len(rows)}")
    print_counter("Baseline counts", baseline_counts, ("TP1", "BE", "STOP", "FLAT"))

    print("Trade-level rollup")
    print("  rule: HURT if any model hurt; HELPED if any model helped and none hurt; SAME only if all models same")
    print(f"  trade_level_helped={trade_level_counts.get('HELPED', 0)}")
    print(f"  trade_level_hurt={trade_level_counts.get('HURT', 0)}")
    print(f"  trade_level_same={trade_level_counts.get('SAME', 0)}")

    print("Dynamic model counts")
    for model in MODELS:
        counts = dynamic_counts[model]
        print(f"  {model}: TP1={counts.get('TP1', 0)} STOP={counts.get('STOP', 0)} SAME={counts.get('SAME', 0)}")

    print("Model-level classification counts")
    for model in MODELS:
        counts = model_level_counts[model]
        print(
            f"  {model}: "
            f"model_level_helped_by_model={counts.get('HELPED', 0)} "
            f"model_level_hurt_by_model={counts.get('HURT', 0)} "
            f"model_level_same_by_model={counts.get('SAME', 0)}"
        )

    print("Per-symbol breakdown")
    by_symbol = defaultdict(list)
    for row in rows:
        by_symbol[row.get("symbol")].append(row)
    for symbol in SYMBOLS:
        symbol_rows = by_symbol.get(symbol, [])
        baseline = Counter(baseline_bucket(row) for row in symbol_rows)
        print(f"  {symbol}: trades={len(symbol_rows)} baseline={dict(baseline)}")
        for model in MODELS:
            classifications = Counter(model_classification(row, model) for row in symbol_rows)
            counts = Counter(dynamic_bucket(row, model) for row in symbol_rows)
            print(
                f"    {model}: TP1={counts.get('TP1', 0)} "
                f"STOP={counts.get('STOP', 0)} SAME={counts.get('SAME', 0)} "
                f"helped={classifications.get('HELPED', 0)} "
                f"hurt={classifications.get('HURT', 0)} "
                f"same={classifications.get('SAME', 0)}"
            )

    print_per_trade_classification(rows)

    print("Helped trades")
    helped_any = False
    for row in rows:
        models = [model for model in MODELS if model_classification(row, model) == "HELPED"]
        if models:
            helped_any = True
            print(f"  {trade_label(row)} models={','.join(models)}")
    if not helped_any:
        print("  none")

    print("Hurt trades")
    hurt_any = False
    for row in rows:
        models = [model for model in MODELS if model_classification(row, model) == "HURT"]
        if models:
            hurt_any = True
            print(f"  {trade_label(row)} models={','.join(models)}")
    if not hurt_any:
        print("  none")


if __name__ == "__main__":
    main()
