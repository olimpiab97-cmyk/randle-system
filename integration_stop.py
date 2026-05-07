import requests

url = "http://127.0.0.1:6001/execute"

# STEP 1: ENTRY
entry_payload = {
    "action": "submit_entry",
    "trade_id": "T-1",
    "symbol": "NQ",
    "direction": "long",
    "qty": 2
}

requests.post(url, json=entry_payload)

# STEP 2: STOP
stop_payload = {
    "action": "submit_stop",
    "trade_id": "T-1",
    "symbol": "NQ",
    "stop_price": 20125.00,
    "qty": 2
}

response = requests.post(url, json=stop_payload)

print(response.json())

# STEP 3: TRY DUPLICATE (should fail)
response = requests.post(url, json=stop_payload)

print(response.json())