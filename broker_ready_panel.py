import os
import uuid
import requests
from typing import Optional, Dict, Any

# =========================
# CONFIG
# =========================

BROKER_MODE = os.environ.get("BROKER_MODE", "paper").lower()

RITHMIC_EXECUTOR_URL = os.environ.get("RITHMIC_EXECUTOR_URL", "http://127.0.0.1:6000")
RITHMIC_API_KEY = os.environ.get("RITHMIC_API_KEY", "dev-key")

# =========================
# BROKER RESULT OBJECT
# =========================

class BrokerOrderResult:
    def __init__(self, ok: bool, broker_order_id=None, broker_position_id=None,
                 status="unknown", message="", raw=None):
        self.ok = ok
        self.broker_order_id = broker_order_id
        self.broker_position_id = broker_position_id
        self.status = status
        self.message = message
        self.raw = raw or {}

# =========================
# BASE BROKER
# =========================

class BaseBroker:
    name = "base"

    def submit_entry(self, symbol, direction, qty, order_type, price):
        raise NotImplementedError

    def submit_stop(self, symbol, direction, qty, stop_price):
        raise NotImplementedError

    def submit_limit(self, symbol, direction, qty, limit_price, tag):
        raise NotImplementedError

    def cancel_order(self, broker_order_id):
        raise NotImplementedError

    def flatten_symbol(self, symbol):
        raise NotImplementedError

# =========================
# PAPER BROKER
# =========================

class PaperBroker(BaseBroker):
    name = "paper"

    def submit_entry(self, symbol, direction, qty, order_type, price):
        return BrokerOrderResult(True, status="filled", message="paper entry")

    def submit_stop(self, symbol, direction, qty, stop_price):
        return BrokerOrderResult(True, status="working", message="paper stop")

    def submit_limit(self, symbol, direction, qty, limit_price, tag):
        return BrokerOrderResult(True, status="working", message="paper limit")

    def cancel_order(self, broker_order_id):
        return BrokerOrderResult(True, status="cancelled", message="paper cancel")

    def flatten_symbol(self, symbol):
        return BrokerOrderResult(True, status="flattened", message="paper flatten")

# =========================
# MOCK BROKER
# =========================

class MockBroker(BaseBroker):
    name = "mock"

    def submit_entry(self, symbol, direction, qty, order_type, price):
        return BrokerOrderResult(True, broker_order_id=str(uuid.uuid4()), status="submitted")

    def submit_stop(self, symbol, direction, qty, stop_price):
        return BrokerOrderResult(True, broker_order_id=str(uuid.uuid4()), status="working")

    def submit_limit(self, symbol, direction, qty, limit_price, tag):
        return BrokerOrderResult(True, broker_order_id=str(uuid.uuid4()), status="working")

    def cancel_order(self, broker_order_id):
        return BrokerOrderResult(True, status="cancelled")

    def flatten_symbol(self, symbol):
        return BrokerOrderResult(True, status="flattened")

# =========================
# RITHMIC BROKER
# =========================

class RithmicBroker(BaseBroker):
    name = "rithmic"

    def _send(self, payload):
        try:
            resp = requests.post(
                f"{RITHMIC_EXECUTOR_URL}/execute",
                json=payload,
                headers={"X-API-Key": RITHMIC_API_KEY},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()

            return BrokerOrderResult(
                ok=data.get("ok", False),
                broker_order_id=data.get("broker_order_id"),
                broker_position_id=data.get("broker_position_id"),
                status=data.get("status", "unknown"),
                message=data.get("message", ""),
                raw=data
            )

        except Exception as e:
            return BrokerOrderResult(
                ok=False,
                status="rejected",
                message=str(e),
                raw={"error": str(e)}
            )

    def submit_entry(self, symbol, direction, qty, order_type, price):
        return self._send({
            "action": "submit_entry",
            "symbol": symbol,
            "direction": direction,
            "qty": qty,
            "order_type": order_type,
            "price": price
        })

    def submit_stop(self, symbol, direction, qty, stop_price):
        return self._send({
            "action": "submit_stop",
            "symbol": symbol,
            "direction": direction,
            "qty": qty,
            "stop_price": stop_price
        })

    def submit_limit(self, symbol, direction, qty, limit_price, tag):
        return self._send({
            "action": "submit_limit",
            "symbol": symbol,
            "direction": direction,
            "qty": qty,
            "limit_price": limit_price,
            "tag": tag
        })

    def cancel_order(self, broker_order_id):
        return self._send({
            "action": "cancel_order",
            "broker_order_id": broker_order_id
        })

    def flatten_symbol(self, symbol):
        return self._send({
            "action": "flatten_symbol",
            "symbol": symbol
        })

# =========================
# BROKER SELECTION
# =========================

if BROKER_MODE == "rithmic":
    BROKER = RithmicBroker()
elif BROKER_MODE == "mock":
    BROKER = MockBroker()
else:
    BROKER = PaperBroker()