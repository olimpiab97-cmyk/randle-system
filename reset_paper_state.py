import argparse
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Data"
BACKUP_DIR = DATA_DIR / "reset_backups"
EXECUTOR_STATE_FILE = DATA_DIR / "executor_state.json"
TRADE_MANAGER_STATE_FILE = DATA_DIR / "persistence_state.json"


def atomic_write_json(path, payload):
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target_path.parent,
        delete=False,
    ) as tmp_file:
        json.dump(payload, tmp_file, indent=2)
        tmp_file.flush()
        temp_path = Path(tmp_file.name)

    temp_path.replace(target_path)


def read_json(path, default):
    target_path = Path(path)
    if not target_path.exists():
        return default
    try:
        with target_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else default
    except Exception:
        return default


def backup_file(path, timestamp):
    target_path = Path(path)
    if not target_path.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"{target_path.name}.{timestamp}.bak"
    shutil.copy2(target_path, backup_path)
    return backup_path


def clean_executor_state(now):
    return {
        "version": 1,
        "saved_at": now,
        "orders": {},
        "positions": {},
    }


def clean_trade_manager_state(now, preserve_tradingview_atr=False):
    existing = read_json(TRADE_MANAGER_STATE_FILE, {})
    tradingview_atr = existing.get("tradingview_atr", {}) if preserve_tradingview_atr else {}
    if not isinstance(tradingview_atr, dict):
        tradingview_atr = {}

    return {
        "system": {
            "version": "v1",
            "engine_status": "reset",
            "last_update_at": now,
            "paper_reset_at": now,
            "last_noon_runner_flatten_date": None,
            "last_noon_runner_flatten_at": None,
        },
        "trades": {},
        "orders": {},
        "tradingview_atr": tradingview_atr,
        "risk_state": {
            "kill_switch_active": False,
            "kill_switch_reason": None,
            "daily_trade_count": 0,
            "daily_loss_count": 0,
            "max_daily_trades": 2,
            "max_daily_losses": 1,
            "kill_switch_drawdown_pct": 11.0,
            "current_drawdown_pct": 0.0,
            "trading_halted": False,
            "last_reset_date": datetime.now().date().isoformat(),
        },
        "event_log": [],
        "failure_state": {
            "execution_failure_count": 0,
            "qa_critical_count": 0,
            "max_execution_failures": 3,
            "max_qa_critical": 3,
            "last_failure_at": None,
            "halt_reason": None,
        },
    }


def reset_paper_state(preserve_tradingview_atr=False):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    now = datetime.now().isoformat()

    executor_backup = backup_file(EXECUTOR_STATE_FILE, timestamp)
    manager_backup = backup_file(TRADE_MANAGER_STATE_FILE, timestamp)

    atomic_write_json(EXECUTOR_STATE_FILE, clean_executor_state(now))
    atomic_write_json(
        TRADE_MANAGER_STATE_FILE,
        clean_trade_manager_state(now, preserve_tradingview_atr=preserve_tradingview_atr),
    )

    return {
        "ok": True,
        "reset_at": now,
        "executor_state_file": str(EXECUTOR_STATE_FILE),
        "trade_manager_state_file": str(TRADE_MANAGER_STATE_FILE),
        "executor_backup": str(executor_backup) if executor_backup else None,
        "trade_manager_backup": str(manager_backup) if manager_backup else None,
        "preserved_tradingview_atr": bool(preserve_tradingview_atr),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Reset local paper-testing Executor and Trade Manager persisted state."
    )
    parser.add_argument(
        "--preserve-tradingview-atr",
        action="store_true",
        help="Keep latest TradingView ATR relay values while clearing trades, orders, positions, and risk locks.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Explicit full paper reset. This is the default behavior; the flag is accepted for operator clarity.",
    )
    args = parser.parse_args()

    result = reset_paper_state(preserve_tradingview_atr=args.preserve_tradingview_atr)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
