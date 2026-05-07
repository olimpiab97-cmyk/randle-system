from flask import Flask, request, jsonify, redirect, url_for
from datetime import datetime
import math
import requests
import uuid

from database import (
    init_db,
    save_trade,
    load_trade,
    save_system_state,
    load_system_state,
    load_trade_log,
    load_active_trades,
    load_all_trades,
    delete_trade,
    clear_all_trades
)

app = Flask(__name__)
init_db()

# =========================
# RISK ENGINE (SHADOW MODE)
# =========================
MODEL_ACCOUNT_SIZE = 100000

USE_DYNAMIC_SIZING = False  # KEEP FALSE

RISK_PROFILES = {
    "aggressive": 0.10,
    "standard": 0.025,
    "conservative": 0.01
}

TICK_VALUES = {
    "MNQ": 2,
    "M2K": 5,
    "MES": 5,
    "NQ": 20,
    "RTY": 50,
    "BTC": 5
}

# Webhook app runs on 5000
APP_PORT = 5000

# Executor runs on 6001
EXECUTOR_BASE_URL = "http://127.0.0.1:6001"
EXECUTOR_URL = f"{EXECUTOR_BASE_URL}/execute"

DEFAULT_SYSTEM_STATE = {
    "trade_count": 0,
    "loss_count": 0,
    "daily_pnl": 0.0,
    "trading_locked": False,
    "start_equity": 10000.0,
    "current_equity": 10000.0,
    "kill_switch_triggered": False,
    "last_reset_date": None
}


def get_system_state():
    state = load_system_state()
    if not state:
        save_system_state(DEFAULT_SYSTEM_STATE)
        return DEFAULT_SYSTEM_STATE.copy()
    return state


def is_form_request() -> bool:
    content_type = request.content_type or ""
    return (
        "application/x-www-form-urlencoded" in content_type
        or "multipart/form-data" in content_type
    )


def normalize_symbol(value):
    return str(value or "").strip().upper()


def current_state_payload():
    return {
        "ok": True,
        "trades": load_active_trades(),
        "system": get_system_state(),
        "trade_log": load_trade_log()
    }


def post_executor(payload: dict):
    return requests.post(EXECUTOR_URL, json=payload, timeout=5)


def calculate_position_size(atr, symbol, profile):
    tick_value = TICK_VALUES.get(symbol, 5)
    risk_percent = RISK_PROFILES.get(profile, 0.025)

    model_risk = MODEL_ACCOUNT_SIZE * risk_percent
    contracts = model_risk / (atr * tick_value)

    return round(contracts, 2)


def get_next_slot_id(active_trades):
    used_slots = {t.get("slot_id") for t in active_trades}
    if 1 not in used_slots:
        return 1
    if 2 not in used_slots:
        return 2
    return None


def close_trade_locally(trade: dict, reason: str, exit_price=None):
    trade["status"] = "closed"
    trade["exit_reason"] = reason
    trade["exit_price"] = exit_price
    trade["closed_at"] = datetime.now().isoformat()
    trade["remaining_size"] = 0
    trade["stop_state"] = "flat"
    save_trade(trade)


def process_single_trade_price_update(trade: dict, price: float):
    if not trade:
        return None

    if trade.get("status") != "active":
        return None

    trade["last_price"] = price
    trade["last_price_at"] = datetime.now().isoformat()

    # Backfill fields for older saved trades
    if "be_was_hit" not in trade:
        trade["be_was_hit"] = False
    if "be_hit_at" not in trade:
        trade["be_hit_at"] = None
    if "tp1_hit_at" not in trade:
        trade["tp1_hit_at"] = None
    if "be_then_tp1_same_update" not in trade:
        trade["be_then_tp1_same_update"] = False
    if "stop_state" not in trade:
        trade["stop_state"] = "original"

    # =========================
    # STOP HIT CHECK
    # =========================
    stop_hit = (
        (trade["direction"] == "long" and price <= trade["current_stop"]) or
        (trade["direction"] == "short" and price >= trade["current_stop"])
    )

    if stop_hit:
        print(f"🛑 STOP HIT [{trade['trade_id']}] at {trade['current_stop']}")

        try:
            if trade.get("stop_order_id"):
                post_executor({
                    "action": "cancel_order",
                    "trade_id": trade["trade_id"],
                    "broker_order_id": trade.get("stop_order_id")
                })

            if trade.get("tp1_order_id") and not trade.get("tp1_hit", False):
                post_executor({
                    "action": "cancel_order",
                    "trade_id": trade["trade_id"],
                    "broker_order_id": trade.get("tp1_order_id")
                })

            post_executor({
                "action": "flatten_symbol",
                "trade_id": trade["trade_id"],
                "symbol": trade["symbol"]
            })

        except Exception as e:
            print("❌ Stop execution error:", str(e))

        close_trade_locally(
            trade=trade,
            reason="stop_hit",
            exit_price=trade["current_stop"]
        )
        return {
            "trade_id": trade["trade_id"],
            "slot_id": trade.get("slot_id"),
            "message": "Stopped out",
            "trade": trade
        }

    # =========================
    # BREAK EVEN
    # =========================
    be_action_taken = False

    if not trade.get("moved_to_be", False) and not trade.get("tp1_hit", False):
        be_hit = (
            (trade["direction"] == "long" and price >= trade["be_trigger"]) or
            (trade["direction"] == "short" and price <= trade["be_trigger"])
        )

        if be_hit:
            print(f"✅ BE CONDITION HIT [{trade['trade_id']}]")

            trade["current_stop"] = trade["entry_price"]
            trade["moved_to_be"] = True
            trade["be_was_hit"] = True
            trade["be_hit_at"] = datetime.now().isoformat()
            trade["stop_state"] = "breakeven"
            be_action_taken = True

            save_trade(trade)

            try:
                if trade.get("stop_order_id"):
                    post_executor({
                        "action": "cancel_order",
                        "trade_id": trade["trade_id"],
                        "broker_order_id": trade.get("stop_order_id")
                    })

                be_stop = post_executor({
                    "action": "submit_stop",
                    "trade_id": trade["trade_id"],
                    "symbol": trade["symbol"],
                    "stop_price": trade["entry_price"],
                    "qty": trade["remaining_size"]
                }).json()

                trade["stop_order_id"] = be_stop.get("broker_order_id")
                print("🔁 BE STOP RESET:", be_stop)

                save_trade(trade)

            except Exception as e:
                print("❌ BE executor error:", str(e))
                print("⚠️ BE state saved anyway")

    # =========================
    # TP1 LOGIC
    # =========================
    if not trade.get("tp1_hit", False):
        tp1_hit = (
            (trade["direction"] == "long" and price >= trade["tp1_price"]) or
            (trade["direction"] == "short" and price <= trade["tp1_price"])
        )

        if tp1_hit:
            tp1_qty = int(trade.get("tp1_qty", math.ceil(trade["position_size"] / 2)))
            runner_qty = max(trade["position_size"] - tp1_qty, 0)

            trade["tp1_hit"] = True
            trade["tp1_hit_at"] = datetime.now().isoformat()
            trade["tp1_qty"] = tp1_qty
            trade["remaining_size"] = runner_qty

            if be_action_taken:
                trade["be_then_tp1_same_update"] = True

            if runner_qty > 0:
                trade["current_stop"] = trade["original_stop"]
                trade["stop_state"] = "runner_original"
                trade["moved_to_be"] = False
            else:
                trade["current_stop"] = None
                trade["stop_state"] = "flat"
                trade["stop_order_id"] = None
                trade["moved_to_be"] = False
                trade["status"] = "closed"
                trade["closed_at"] = datetime.now().isoformat()
                trade["exit_reason"] = "tp1_full_exit"

            print(f"🎯 TP1 HIT [{trade['trade_id']}]: exited {tp1_qty}, runner {runner_qty}")

            save_trade(trade)

            try:
                if trade.get("stop_order_id"):
                    post_executor({
                        "action": "cancel_order",
                        "trade_id": trade["trade_id"],
                        "broker_order_id": trade.get("stop_order_id")
                    })

                if runner_qty > 0:
                    new_stop = post_executor({
                        "action": "submit_stop",
                        "trade_id": trade["trade_id"],
                        "symbol": trade["symbol"],
                        "stop_price": trade["original_stop"],
                        "qty": runner_qty
                    }).json()

                    trade["stop_order_id"] = new_stop.get("broker_order_id")
                    print("🔁 STOP RESET:", new_stop)
                else:
                    trade["stop_order_id"] = None

                save_trade(trade)

            except Exception as e:
                print("❌ TP1 executor error:", str(e))
                print("⚠️ TP1 state saved anyway")

    save_trade(trade)
    return {
        "trade_id": trade["trade_id"],
        "slot_id": trade.get("slot_id"),
        "trade": trade
    }


def process_price_update(price: float, incoming_symbol: str | None = None):
    active_trades = load_active_trades()

    if not active_trades:
        return {"ok": False, "message": "No active trades"}, 400

    incoming_symbol = normalize_symbol(incoming_symbol)
    matched_trades = []

    for trade in active_trades:
        active_symbol = normalize_symbol(trade.get("symbol"))

        if incoming_symbol and incoming_symbol != active_symbol:
            continue

        result = process_single_trade_price_update(trade, price)
        if result:
            matched_trades.append(result)

    if incoming_symbol and not matched_trades:
        return {
            "ok": True,
            "message": f"No active trades matched symbol {incoming_symbol}",
            "trades": active_trades
        }, 200

    return {
        "ok": True,
        "updated_trades": matched_trades,
        "trades": load_active_trades()
    }, 200

    return list(ORDERS.values())


@app.route("/", methods=["GET"])
def dashboard():
    trades = load_active_trades()
    system = get_system_state()

    return f"""
    <html>
    <head>
        <title>Randle Command Center</title>
        <style>
            body {{ font-family: Arial; background:#111; color:#eee; padding:20px; }}
            h2 {{ color:#00ffcc; }}
            .box {{ background:#1a1a1a; padding:15px; margin-bottom:20px; border-radius:8px; }}
            input {{ margin:3px; padding:5px; }}
            button {{ padding:8px 12px; margin-top:5px; cursor:pointer; }}
        </style>
    </head>
    <body>

    <h2>🔥 Randle Command Center</h2>

    <div class="box">
        <h3>🚀 Enter Trade</h3>
        <form method="post" action="/webhook">
            <input type="hidden" name="event" value="enter_trade">

            Symbol: <input name="symbol" value="BTC"><br>
            Direction: <input name="direction" value="long"><br>
            Entry: <input name="entry_price" value="100"><br>
            Stop: <input name="stop_price" value="90"><br>
            TP1: <input name="tp1_price" value="110"><br>
            BE Trigger: <input name="be_trigger_price" value="105"><br>
            Size: <input name="position_size" value="2"><br>

            <button type="submit">ENTER</button>
        </form>
    </div>

    <div class="box">
        <h3>📈 Send Price Update</h3>
        <form method="post" action="/webhook">
            <input type="hidden" name="event" value="price_update">
            Symbol: <input name="symbol"><br>
            Price: <input name="price">
            <button type="submit">Update Price</button>
        </form>
    </div>

    <div class="box">
        <h3>⚡ Actions</h3>

        <form method="get" action="/state">
            <button type="submit">Refresh State</button>
        </form>

        <form method="post" action="/reset_trade">
            <button type="submit" style="background:orange;color:black;">CLEAR ALL TRADES</button>
        </form>

        <form method="post" action="/webhook">
            <input type="hidden" name="event" value="flatten">
            <button type="submit" style="background:red;color:white;">FLATTEN ALL ACTIVE</button>
        </form>
    </div>

    <div class="box">
        <h3>📊 Active Trades</h3>
        <pre>{trades}</pre>
    </div>

    <div class="box">
        <h3>🧠 System State</h3>
        <pre>{system}</pre>
    </div>

    </body>
    </html>
    """


@app.route("/state", methods=["GET"])
def state_get():
    return jsonify(current_state_payload())


@app.route("/reset_trade", methods=["POST"])
def reset_trade():
    clear_all_trades()
    return jsonify({
        "ok": True,
        "message": "All trades cleared"
    })

@app.route("/all_trades", methods=["GET"])
def all_trades():
    return jsonify({
        "ok": True,
        "trades": load_all_trades()
    })


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or request.form

    print("RAW:", request.get_data(as_text=True))
    print("PARSED:", data)

    if not data:
        result = jsonify({"ok": False, "message": "No data received"})
        return redirect(url_for("dashboard")) if is_form_request() else (result, 400)

    event = data.get("event")
    trades = load_active_trades()
    system = get_system_state()

    if event == "enter_trade":
        try:
            position_size = float(data["position_size"])

            atr = data.get("atr")
            symbol = normalize_symbol(data.get("symbol"))
            profile = data.get("profile", "standard")

            shadow_qty = None

            if atr:
                try:
                    atr_val = float(atr)
                    shadow_qty = calculate_position_size(atr_val, symbol, profile)
                except Exception:
                    shadow_qty = None

            print(
                f"📊 SHADOW SIZING | Profile: {profile} | ATR: {atr} | "
                f"Shadow Contracts: {shadow_qty} | Live Contracts: {position_size}"
            )

            if len(trades) >= 2:
                result = jsonify({"ok": False, "message": "Max 2 active trades reached"})
                return redirect(url_for("dashboard")) if is_form_request() else (result, 400)

            slot_id = get_next_slot_id(trades)
            if slot_id is None:
                result = jsonify({"ok": False, "message": "No open trade slot available"})
                return redirect(url_for("dashboard")) if is_form_request() else (result, 400)

            tp1_qty = math.ceil(position_size / 2)
            trade_id = f"T-{uuid.uuid4().hex[:8]}"

            trade = {
                "trade_id": trade_id,
                "slot_id": slot_id,
                "symbol": normalize_symbol(data["symbol"]),
                "direction": data["direction"],
                "entry_price": float(data["entry_price"]),
                "original_stop": float(data["stop_price"]),
                "current_stop": float(data["stop_price"]),
                "tp1_price": float(data["tp1_price"]),
                "be_trigger": float(data["be_trigger_price"]),
                "position_size": position_size,
                "remaining_size": position_size,
                "tp1_qty": tp1_qty,
                "tp1_hit": False,
                "tp1_hit_at": None,
                "moved_to_be": False,
                "be_was_hit": False,
                "be_hit_at": None,
                "be_then_tp1_same_update": False,
                "stop_state": "original",
                "status": "active",
                "created_at": datetime.now().isoformat(),
                "closed_at": None,
                "exit_reason": None,
                "exit_price": None,
                "last_price": None,
                "last_price_at": None,
                "stop_order_id": None,
                "tp1_order_id": None
            }
        except (KeyError, TypeError, ValueError) as e:
            result = jsonify({"ok": False, "message": f"Invalid enter_trade payload: {str(e)}"})
            return redirect(url_for("dashboard")) if is_form_request() else (result, 400)

        save_trade(trade)

        try:
            entry = post_executor({
                "action": "submit_entry",
                "trade_id": trade["trade_id"],
                "symbol": trade["symbol"],
                "direction": trade["direction"],
                "qty": trade["position_size"]
            }).json()

            stop = post_executor({
                "action": "submit_stop",
                "trade_id": trade["trade_id"],
                "symbol": trade["symbol"],
                "stop_price": trade["original_stop"],
                "qty": trade["position_size"]
            }).json()

            trade["stop_order_id"] = stop.get("broker_order_id")

            tp1 = post_executor({
                "action": "submit_limit",
                "trade_id": trade["trade_id"],
                "symbol": trade["symbol"],
                "limit_price": trade["tp1_price"],
                "qty": tp1_qty,
                "tag": "tp1"
            }).json()

            trade["tp1_order_id"] = tp1.get("broker_order_id")

            print("🔥 ENTRY:", entry)
            print("🛑 STOP:", stop)
            print("🎯 TP1:", tp1)

            save_trade(trade)

        except Exception as e:
            print("❌ Executor error:", str(e))

        if is_form_request():
            return redirect(url_for("dashboard"))
        return jsonify({"ok": True, "trade": trade})

    elif event == "price_update":
        try:
            price = float(data["price"])
            incoming_symbol = data.get("symbol")
        except (KeyError, TypeError, ValueError):
            result = jsonify({"ok": False, "message": "Invalid or missing price"})
            return redirect(url_for("dashboard")) if is_form_request() else (result, 400)

        response_body, status_code = process_price_update(price, incoming_symbol)

        if is_form_request():
            return redirect(url_for("dashboard"))
        return jsonify(response_body), status_code

    elif event == "state":
        payload = {
            "ok": True,
            "trades": load_active_trades(),
            "system": system,
            "trade_log": load_trade_log()
        }
        if is_form_request():
            return redirect(url_for("dashboard"))
        return jsonify(payload)

    elif event == "flatten":
        active_trades = load_active_trades()

        for trade in active_trades:
            if trade.get("status") == "active":
                try:
                    post_executor({
                        "action": "flatten_symbol",
                        "trade_id": trade["trade_id"],
                        "symbol": trade["symbol"]
                    })
                except Exception as e:
                    print(f"❌ Flatten error [{trade['trade_id']}]:", str(e))

                close_trade_locally(trade, "manual_flatten", trade.get("last_price"))

        if is_form_request():
            return redirect(url_for("dashboard"))
        return jsonify({"ok": True, "trades": load_active_trades()})

    result = jsonify({"ok": False, "message": f"Unknown event: {event}"})
    return redirect(url_for("dashboard")) if is_form_request() else (result, 400)


if __name__ == "__main__":
    print(f"🚀 Trade Manager Running on http://127.0.0.1:{APP_PORT}")
    app.run(host="0.0.0.0", port=APP_PORT, debug=True, use_reloader=False)
