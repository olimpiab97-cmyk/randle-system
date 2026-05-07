import requests
from pprint import pprint

BASE = "http://127.0.0.1:6001"
EXECUTE_URL = f"{BASE}/execute"
ORDERS_URL = f"{BASE}/orders"
HEALTH_URL = f"{BASE}/health"

TRADE_ID = "T-TEST-1"
SYMBOL = "NQ"

def post(payload, label):
    print(f"\n--- {label} ---")
    print("REQUEST:")
    pprint(payload)

    r = requests.post(EXECUTE_URL, json=payload)
    print("STATUS:", r.status_code)
    try:
        pprint(r.json())
        return r.json()
    except Exception:
        print(r.text)
        return None

def get(url, label):
    print(f"\n--- {label} ---")
    r = requests.get(url)
    print("STATUS:", r.status_code)
    try:
        pprint(r.json())
        return r.json()
    except Exception:
        print(r.text)
        return None

# 1) HEALTH
get(HEALTH_URL, "HEALTH CHECK")

# 2) ENTRY
entry_resp = post({
    "action": "submit_entry",
    "trade_id": TRADE_ID,
    "symbol": SYMBOL,
    "direction": "long",
    "qty": 2
}, "SUBMIT ENTRY")

# 3) STOP
stop_resp = post({
    "action": "submit_stop",
    "trade_id": TRADE_ID,
    "symbol": SYMBOL,
    "stop_price": 20125.00,
    "qty": 2
}, "SUBMIT STOP")

# 4) DUPLICATE STOP (should fail)
dup_stop_resp = post({
    "action": "submit_stop",
    "trade_id": TRADE_ID,
    "symbol": SYMBOL,
    "stop_price": 20120.00,
    "qty": 2
}, "DUPLICATE STOP")

# 5) LIMIT
limit_resp = post({
    "action": "submit_limit",
    "trade_id": TRADE_ID,
    "symbol": SYMBOL,
    "tag": "TP1",
    "limit_price": 20150.00,
    "qty": 1
}, "SUBMIT LIMIT")

# 6) SHOW ORDERS
orders_resp = get(ORDERS_URL, "ALL ORDERS")

# 7) CANCEL LIMIT
limit_order_id = None
if limit_resp and limit_resp.get("ok"):
    limit_order_id = limit_resp.get("broker_order_id")

if limit_order_id:
    post({
        "action": "cancel_order",
        "broker_order_id": limit_order_id
    }, "CANCEL LIMIT")

# 8) SHOW ORDERS AFTER CANCEL
get(ORDERS_URL, "ORDERS AFTER CANCEL")

# 9) FLATTEN TRADE
post({
    "action": "flatten_trade",
    "trade_id": TRADE_ID
}, "FLATTEN TRADE")

# 10) SHOW ORDERS AFTER FLATTEN TRADE
get(ORDERS_URL, "ORDERS AFTER FLATTEN TRADE")

# 11) NEW TRADE FOR SYMBOL FLATTEN TEST
TRADE_ID_2 = "T-TEST-2"

post({
    "action": "submit_entry",
    "trade_id": TRADE_ID_2,
    "symbol": SYMBOL,
    "direction": "short",
    "qty": 1
}, "ENTRY FOR SYMBOL FLATTEN")

post({
    "action": "submit_stop",
    "trade_id": TRADE_ID_2,
    "symbol": SYMBOL,
    "stop_price": 20200.00,
    "qty": 1
}, "STOP FOR SYMBOL FLATTEN")

# 12) FLATTEN SYMBOL
post({
    "action": "flatten_symbol",
    "symbol": SYMBOL
}, "FLATTEN SYMBOL")

# 13) FINAL ORDERS
get(ORDERS_URL, "FINAL ORDERS")