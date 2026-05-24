import json
import math
import os
import stat
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SNAPSHOT_PATH = BASE_DIR / "Data" / "paper_account_snapshot.json"
TM_BASE_URL = os.getenv("TRADE_MANAGER_BASE_URL", "http://127.0.0.1:7001").strip() or "http://127.0.0.1:7001"
EX_BASE_URL = os.getenv("EXECUTOR_BASE_URL", "http://127.0.0.1:6001").strip() or "http://127.0.0.1:6001"
HTTP_TIMEOUT_SECONDS = float(os.getenv("SYNTHETIC_EQUITY_HTTP_TIMEOUT_SECONDS", "2.0") or "2.0")
DEFAULT_STARTING_BALANCE = 50000.0
RESET_AT_RAW = os.getenv("SYNTHETIC_EQUITY_RESET_AT", "").strip()

TICK_SPECS = {
    "NQ": {"tick_size": 0.25, "tick_value": 20.0},
    "MNQ": {"tick_size": 0.25, "tick_value": 2.0},
    "YM": {"tick_size": 1.0, "tick_value": 5.0},
    "MYM": {"tick_size": 1.0, "tick_value": 0.5},
    "RTY": {"tick_size": 0.10, "tick_value": 5.0},
    "M2K": {"tick_size": 0.10, "tick_value": 0.5},
    "ES": {"tick_size": 0.25, "tick_value": 12.5},
    "MES": {"tick_size": 0.25, "tick_value": 1.25},
    "GC": {"tick_size": 0.10, "tick_value": 10.0},
    "MGC": {"tick_size": 0.10, "tick_value": 1.0},
}


def utc_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def finite_float(value):
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def get_starting_balance():
    configured = finite_float(os.getenv("PAPER_STARTING_BALANCE"))
    return configured if configured is not None else DEFAULT_STARTING_BALANCE


def parse_iso_datetime(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"invalid_reset_at value={value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_reset_at():
    return parse_iso_datetime(RESET_AT_RAW)


def snapshot_reset_value(reset_at):
    return reset_at.isoformat().replace("+00:00", "Z") if reset_at else None


def normalize_symbol_root(symbol):
    raw = str(symbol or "").strip().upper()
    if not raw:
        return ""
    cleaned = "".join(ch for ch in raw.replace("!", "") if ch.isalnum())
    if not cleaned:
        return ""
    for root in sorted(TICK_SPECS, key=len, reverse=True):
        if cleaned.startswith(root):
            return root
    if len(cleaned) >= 2 and cleaned[:2].isalpha():
        return cleaned[:2]
    return cleaned


def fetch_json(url):
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"fetch_failed url={url} error={exc}") from exc


def safe_snapshot(reason):
    reset_at = get_reset_at()
    return {
        "ok": False,
        "source": "synthetic_paper_equity",
        "balance": None,
        "cash_balance": None,
        "net_liq": None,
        "unrealized_pnl": None,
        "realized_pnl": None,
        "updated_at": utc_iso(),
        "reset_at": snapshot_reset_value(reset_at),
        "reason": reason,
    }


def realized_value_for_trade(trade):
    if not isinstance(trade, dict):
        return 0.0
    for key in ("realized_pnl", "total_pnl", "total_profit"):
        numeric = finite_float(trade.get(key))
        if numeric is not None:
            return numeric
    return 0.0


def trade_closed_at(trade):
    if not isinstance(trade, dict):
        return None
    for key in ("closed_at", "exit_at", "exited_at", "updated_at", "timestamp"):
        try:
            parsed = parse_iso_datetime(trade.get(key))
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed
    return None


def trade_is_after_reset(trade, reset_at):
    if reset_at is None:
        return True
    closed_at = trade_closed_at(trade)
    return closed_at is not None and closed_at >= reset_at


def calculate_realized_pnl(trades_payload, reset_at=None):
    trades = trades_payload.get("trades") if isinstance(trades_payload, dict) else None
    if not isinstance(trades, dict):
        return 0.0

    total = 0.0
    for trade in trades.values():
        if not isinstance(trade, dict):
            continue
        if str(trade.get("status") or "").strip().lower() != "closed":
            continue
        if not trade_is_after_reset(trade, reset_at):
            continue
        total += realized_value_for_trade(trade)
    return round(total, 2)


def get_positions(positions_payload):
    positions = positions_payload.get("positions") if isinstance(positions_payload, dict) else None
    return positions if isinstance(positions, dict) else {}


def get_last_prices(live_prices_payload):
    if not isinstance(live_prices_payload, dict):
        return {}
    prices = live_prices_payload.get("last_prices")
    return prices if isinstance(prices, dict) else {}


def find_price_for_symbol(symbol, prices):
    direct = finite_float(prices.get(symbol))
    if direct is not None:
        return direct

    root = normalize_symbol_root(symbol)
    for candidate, value in prices.items():
        if normalize_symbol_root(candidate) == root:
            numeric = finite_float(value)
            if numeric is not None:
                return numeric
    return None


def calculate_unrealized_pnl(positions_payload, live_prices_payload):
    positions = get_positions(positions_payload)
    prices = get_last_prices(live_prices_payload)
    total = 0.0

    for symbol, position in positions.items():
        if not isinstance(position, dict):
            continue
        qty = finite_float(position.get("qty"))
        avg_entry = finite_float(position.get("avg_entry_price"))
        if qty is None or avg_entry is None or abs(qty) <= 0:
            continue

        last_price = find_price_for_symbol(str(symbol or "").strip().upper(), prices)
        if last_price is None:
            raise RuntimeError(f"missing_live_price symbol={symbol}")

        root = normalize_symbol_root(symbol)
        spec = TICK_SPECS.get(root)
        if not spec:
            raise RuntimeError(f"missing_tick_spec symbol={symbol} root={root}")

        ticks = (last_price - avg_entry) / spec["tick_size"]
        total += ticks * spec["tick_value"] * qty

    return round(total, 2)


def build_snapshot():
    starting_balance = get_starting_balance()
    reset_at = get_reset_at()

    try:
        trades_payload = fetch_json(f"{TM_BASE_URL}/trades")
        positions_payload = fetch_json(f"{EX_BASE_URL}/positions")
        live_prices_payload = fetch_json(f"{EX_BASE_URL}/debug/live_prices")
        realized_pnl = calculate_realized_pnl(trades_payload, reset_at=reset_at)
        unrealized_pnl = calculate_unrealized_pnl(positions_payload, live_prices_payload)
    except Exception as exc:
        return safe_snapshot(str(exc))

    cash_balance = round(starting_balance + realized_pnl, 2)
    equity = round(cash_balance + unrealized_pnl, 2)
    return {
        "ok": True,
        "source": "synthetic_paper_equity",
        "balance": equity,
        "cash_balance": cash_balance,
        "net_liq": equity,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
        "updated_at": utc_iso(),
        "reset_at": snapshot_reset_value(reset_at),
        "reason": None,
    }


def atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)

        try:
            replace_path(temp_path, path)
        except PermissionError:
            try:
                os.chmod(path, stat.S_IWRITE)
                replace_path(temp_path, path)
            except PermissionError as exc:
                raise PermissionError(f"atomic_replace_failed path={path} error={exc}") from exc
    except Exception:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise


def replace_path(source, target):
    source = Path(source)
    target = Path(target)
    try:
        os.replace(source, target)
        return
    except PermissionError:
        if not sys.platform.startswith("win"):
            raise

    import ctypes

    replace_file = ctypes.windll.kernel32.ReplaceFileW
    replace_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    replace_file.restype = ctypes.c_int
    result = replace_file(
        str(target),
        str(source),
        None,
        0,
        None,
        None,
    )
    if not result:
        error_code = ctypes.windll.kernel32.GetLastError()
        raise PermissionError(error_code, "ReplaceFileW failed", str(source), str(target))


def main():
    snapshot = build_snapshot()
    try:
        atomic_write_json(SNAPSHOT_PATH, snapshot)
    except Exception as exc:
        failed_snapshot = safe_snapshot(str(exc))
        print(json.dumps(failed_snapshot, indent=2))
        return 1
    print(json.dumps(snapshot, indent=2))
    return 0 if snapshot.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
