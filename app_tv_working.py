from flask import Flask, request, jsonify, redirect, url_for
from datetime import datetime
import pytz
import requests

from database import (
    init_db,
    save_trade,
    load_trade,
    save_system_state,
    load_system_state,
    load_trade_log
)

app = Flask(__name__)
init_db()

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


# =========================
# DASHBOARD UI
# =========================
@app.route("/", methods=["GET"])
def dashboard():
    trade = load_trade()
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
            Price: <input name="price">
            <button type="submit">Update Price</button>
        </form>
    </div>

    <div class="box">
        <h3>⚡ Actions</h3>

        <form method="post" action="/webhook">
            <input type="hidden" name="event" value="state">
            <button type="submit">Refresh State</button>
        </form>

        <form method="post" action="/webhook">
            <input type="hidden" name="event" value="flatten">
            <button type="submit" style="background:red;color:white;">FLATTEN</button>
        </form>
    </div>

    <div class="box">
        <h3>📊 Current Trade</h3>
        <pre>{trade}</pre>
    </div>

    <div class="box">
        <h3>🧠 System State</h3>
        <pre>{system}</pre>
    </div>

    </body>
    </html>
    """


# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or request.form

    print("RAW:", request.get_data(as_text=True))
    print("PARSED:", data)

    if not data:
        result = jsonify({"ok": False, "message": "No data received"})
        return redirect(url_for("dashboard")) if is_form_request() else (result, 400)

    event = data.get("event")

    trade = load_trade()
    system = get_system_state()

    # =========================
    # ENTER TRADE
    # =========================
    if event == "enter_trade":
        try:
            trade = {
                "symbol": data["symbol"],
                "direction": data["direction"],
                "entry_price": float(data["entry_price"]),
                "original_stop": float(data["stop_price"]),
                "current_stop": float(data["stop_price"]),
                "tp1_price": float(data["tp1_price"]),
                "be_trigger": float(data["be_trigger_price"]),
                "position_size": float(data["position_size"]),
                "remaining_size": float(data["position_size"]),
                "tp1_hit": False,
                "moved_to_be": False,
                "status": "active",
                "created_at": datetime.now().isoformat()
            }
        except (KeyError, TypeError, ValueError) as e:
            result = jsonify({"ok": False, "message": f"Invalid enter_trade payload: {str(e)}"})
            return redirect(url_for("dashboard")) if is_form_request() else (result, 400)

        save_trade(trade)

        try:
            entry = requests.post(
                "http://127.0.0.1:6000/execute",
                json={
                    "action": "submit_entry",
                    "symbol": trade["symbol"],
                    "direction": trade["direction"],
                    "qty": trade["position_size"]
                },
                timeout=5
            ).json()

            stop = requests.post(
                "http://127.0.0.1:6000/execute",
                json={
                    "action": "submit_stop",
                    "symbol": trade["symbol"],
                    "stop_price": trade["original_stop"]
                },
                timeout=5
            ).json()

            trade["stop_order_id"] = stop.get("broker_order_id")

            tp1 = requests.post(
                "http://127.0.0.1:6000/execute",
                json={
                    "action": "submit_limit",
                    "symbol": trade["symbol"],
                    "limit_price": trade["tp1_price"],
                    "tag": "tp1"
                },
                timeout=5
            ).json()

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

    # =========================
    # PRICE UPDATE
    # =========================
    elif event == "price_update":
        if not trade:
            result = jsonify({"ok": False, "message": "No active trade"})
            return redirect(url_for("dashboard")) if is_form_request() else (result, 400)

        try:
            price = float(data["price"])
        except (KeyError, TypeError, ValueError):
            result = jsonify({"ok": False, "message": "Invalid or missing price"})
            return redirect(url_for("dashboard")) if is_form_request() else (result, 400)

        trade["last_price"] = price

        # BREAK EVEN
        if not trade["moved_to_be"]:
            if trade["direction"] == "long" and price >= trade["be_trigger"]:
                trade["current_stop"] = trade["entry_price"]
                trade["moved_to_be"] = True
                print("✅ MOVED TO BE")

            elif trade["direction"] == "short" and price <= trade["be_trigger"]:
                trade["current_stop"] = trade["entry_price"]
                trade["moved_to_be"] = True
                print("✅ MOVED TO BE")

        # TP1
        if not trade["tp1_hit"]:
            if (
                (trade["direction"] == "long" and price >= trade["tp1_price"]) or
                (trade["direction"] == "short" and price <= trade["tp1_price"])
            ):
                trade["tp1_hit"] = True
                trade["remaining_size"] = trade["position_size"] / 2

                try:
                    if trade.get("stop_order_id"):
                        requests.post(
                            "http://127.0.0.1:6000/execute",
                            json={
                                "action": "cancel_order",
                                "broker_order_id": trade.get("stop_order_id")
                            },
                            timeout=5
                        )

                    new_stop = requests.post(
                        "http://127.0.0.1:6000/execute",
                        json={
                            "action": "submit_stop",
                            "symbol": trade["symbol"],
                            "stop_price": trade["original_stop"]
                        },
                        timeout=5
                    ).json()

                    trade["stop_order_id"] = new_stop.get("broker_order_id")
                    print("🔁 STOP RESET:", new_stop)

                except Exception as e:
                    print("❌ TP1 error:", str(e))

        save_trade(trade)

        if is_form_request():
            return redirect(url_for("dashboard"))
        return jsonify({"ok": True, "trade": trade})

    # =========================
    # STATE VIEW
    # =========================
    elif event == "state":
        payload = {
            "ok": True,
            "trade": trade,
            "system": system,
            "trade_log": load_trade_log()
        }
        if is_form_request():
            return redirect(url_for("dashboard"))
        return jsonify(payload)

    # =========================
    # FLATTEN
    # =========================
    elif event == "flatten":
        if trade and trade.get("status") == "active":
            try:
                requests.post(
                    "http://127.0.0.1:6000/execute",
                    json={
                        "action": "flatten_symbol",
                        "symbol": trade["symbol"]
                    },
                    timeout=5
                )
            except Exception as e:
                print("❌ Flatten error:", str(e))

            trade["status"] = "closed"
            trade["exit_reason"] = "manual_flatten"
            trade["closed_at"] = datetime.now().isoformat()
            trade["remaining_size"] = 0
            save_trade(trade)

        if is_form_request():
            return redirect(url_for("dashboard"))
        return jsonify({"ok": True, "trade": trade})

    result = jsonify({"ok": False, "message": f"Unknown event: {event}"})
    return redirect(url_for("dashboard")) if is_form_request() else (result, 400)


if __name__ == "__main__":
    print("🚀 Trade Manager Running on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)