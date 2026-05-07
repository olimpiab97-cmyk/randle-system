from flask import Flask, request, jsonify
from datetime import datetime
import uuid

app = Flask(__name__)

# =========================
# SIMPLE IN-MEMORY STORE
# =========================
ORDERS = {}

# =========================
# HELPERS
# =========================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def make_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

# =========================
# EXECUTION ENDPOINT
# =========================
@app.route("/execute", methods=["POST"])
def execute():
    data = request.get_json(force=True)

    action = data.get("action")
    symbol = data.get("symbol")

    log(f"📥 Incoming: {data}")

    # =========================
    # ENTRY
    # =========================
    if action == "submit_entry":
        order_id = make_id("ENTRY")

        ORDERS[order_id] = {
            "type": "entry",
            "symbol": symbol,
            "direction": data.get("direction"),
            "qty": data.get("qty"),
            "status": "filled"
        }

        log(f"✅ ENTRY FILLED: {order_id}")

        return jsonify({
            "ok": True,
            "status": "filled",
            "broker_order_id": order_id,
            "message": "entry filled (sim)"
        })

    # =========================
    # STOP
    # =========================
    if action == "submit_stop":
        order_id = make_id("STOP")

        ORDERS[order_id] = {
            "type": "stop",
            "symbol": symbol,
            "stop_price": data.get("stop_price"),
            "qty": data.get("qty"),
            "status": "working"
        }

        log(f"🛑 STOP PLACED: {order_id}")

        return jsonify({
            "ok": True,
            "status": "working",
            "broker_order_id": order_id,
            "message": "stop working (sim)"
        })

    # =========================
    # LIMIT (TP1)
    # =========================
    if action == "submit_limit":
        order_id = make_id("LIMIT")

        ORDERS[order_id] = {
            "type": "limit",
            "symbol": symbol,
            "limit_price": data.get("limit_price"),
            "qty": data.get("qty"),
            "tag": data.get("tag"),
            "status": "working"
        }

        log(f"🎯 LIMIT PLACED: {order_id}")

        return jsonify({
            "ok": True,
            "status": "working",
            "broker_order_id": order_id,
            "message": "limit working (sim)"
        })

    # =========================
    # CANCEL
    # =========================
    if action == "cancel_order":
        oid = data.get("broker_order_id")

        if oid in ORDERS:
            ORDERS[oid]["status"] = "cancelled"
            log(f"❌ CANCELLED: {oid}")

        return jsonify({
            "ok": True,
            "status": "cancelled",
            "message": "order cancelled"
        })

    # =========================
    # FLATTEN
    # =========================
    if action == "flatten_symbol":
        log(f"⚡ FLATTEN: {symbol}")

        return jsonify({
            "ok": True,
            "status": "flattened",
            "message": f"{symbol} flattened"
        })

    # =========================
    # UNKNOWN
    # =========================
    return jsonify({
        "ok": False,
        "message": f"Unknown action: {action}"
    }), 400

# =========================
# RUN SERVER
# =========================
if __name__ == "__main__":
    log("🚀 Rithmic Executor Running on port 6000")
    app.run(host="0.0.0.0", port=6000)