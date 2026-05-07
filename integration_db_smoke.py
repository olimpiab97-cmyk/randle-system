from database import (
    init_db,
    save_trade,
    load_trade,
    load_active_trades,
    log_trade_event,
    load_trade_log
)

print("Starting DB test...")

# Init DB
init_db()

# Create trades
trade1 = {
    "trade_id": "T-1001",
    "slot_id": 1,
    "symbol": "NQ",
    "direction": "long",
    "status": "active"
}

trade2 = {
    "trade_id": "T-1002",
    "slot_id": 2,
    "symbol": "M2K",
    "direction": "short",
    "status": "active"
}

# Save
save_trade(trade1)
save_trade(trade2)

# Load individual
print("\n--- LOAD INDIVIDUAL ---")
print(load_trade("T-1001"))
print(load_trade("T-1002"))

# Load active
print("\n--- ACTIVE TRADES ---")
print(load_active_trades())

# Logs
log_trade_event("T-1001", "created", {"msg": "trade 1 created"})
log_trade_event("T-1002", "created", {"msg": "trade 2 created"})

print("\n--- LOG T1 ---")
print(load_trade_log("T-1001"))

print("\n--- LOG T2 ---")
print(load_trade_log("T-1002"))