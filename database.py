import sqlite3
import json
from datetime import datetime

DB_NAME = "randle.db"


# =========================
# CONNECT
# =========================
def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# =========================
# INIT DATABASE
# =========================
def init_db():
    conn = get_conn()
    c = conn.cursor()

    # One row per trade
    c.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        trade_id TEXT PRIMARY KEY,
        slot_id INTEGER,
        status TEXT,
        data TEXT NOT NULL
    )
    """)

    # Single row for system state
    c.execute("""
    CREATE TABLE IF NOT EXISTS system_state (
        id INTEGER PRIMARY KEY,
        data TEXT NOT NULL
    )
    """)

    # Trade event log
    c.execute("""
    CREATE TABLE IF NOT EXISTS trade_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id TEXT,
        event_type TEXT,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


# =========================
# TRADE HELPERS
# =========================
def save_trade(trade: dict):
    """
    Insert or replace a trade by trade_id.
    """
    trade_id = trade.get("trade_id")
    if not trade_id:
        raise ValueError("save_trade requires trade['trade_id']")

    slot_id = trade.get("slot_id")
    status = trade.get("status", "unknown")

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    INSERT INTO trades (trade_id, slot_id, status, data)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(trade_id) DO UPDATE SET
        slot_id = excluded.slot_id,
        status = excluded.status,
        data = excluded.data
    """, (
        trade_id,
        slot_id,
        status,
        json.dumps(trade)
    ))

    conn.commit()
    conn.close()


def load_trade(trade_id: str):
    """
    Load a single trade by trade_id.
    """
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT data FROM trades WHERE trade_id = ?", (trade_id,))
    row = c.fetchone()

    conn.close()

    if row:
        return json.loads(row["data"])
    return None


def load_trades_by_slot(slot_id: int):
    """
    Load all trades assigned to a slot.
    Usually slot 1 or slot 2.
    """
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    SELECT data
    FROM trades
    WHERE slot_id = ?
    ORDER BY rowid DESC
    """, (slot_id,))
    rows = c.fetchall()

    conn.close()

    return [json.loads(r["data"]) for r in rows]


def load_active_trades():
    """
    Load all trades whose row-level status is active-ish.
    Adjust statuses later if needed.
    """
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    SELECT data
    FROM trades
    WHERE json_extract(data, '$.status') = 'active'
    ORDER BY json_extract(data, '$.slot_id') ASC
    """)

    rows = c.fetchall()

    conn.close()

    return [json.loads(r["data"]) for r in rows]


def load_all_trades(limit: int = 100):
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    SELECT data
    FROM trades
    ORDER BY rowid DESC
    LIMIT ?
    """, (limit,))
    rows = c.fetchall()

    conn.close()

    return [json.loads(r["data"]) for r in rows]


def delete_trade(trade_id: str):
    conn = get_conn()
    c = conn.cursor()

    c.execute("DELETE FROM trades WHERE trade_id = ?", (trade_id,))

    conn.commit()
    conn.close()


def clear_all_trades():
    """
    Admin/reset only.
    """
    conn = get_conn()
    c = conn.cursor()

    c.execute("DELETE FROM trades")

    conn.commit()
    conn.close()


# =========================
# SYSTEM STATE
# =========================
def save_system_state(state: dict):
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    INSERT INTO system_state (id, data)
    VALUES (1, ?)
    ON CONFLICT(id) DO UPDATE SET
        data = excluded.data
    """, (json.dumps(state),))

    conn.commit()
    conn.close()


def load_system_state():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT data FROM system_state WHERE id = 1")
    row = c.fetchone()

    conn.close()

    if row:
        return json.loads(row["data"])
    return None


# =========================
# TRADE LOG
# =========================
def log_trade_event(trade_id: str, event_type: str, payload: dict):
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    INSERT INTO trade_log (trade_id, event_type, data, created_at)
    VALUES (?, ?, ?, ?)
    """, (
        trade_id,
        event_type,
        json.dumps(payload),
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


def load_trade_log(trade_id: str | None = None, limit: int = 50):
    conn = get_conn()
    c = conn.cursor()

    if trade_id:
        c.execute("""
        SELECT trade_id, event_type, data, created_at
        FROM trade_log
        WHERE trade_id = ?
        ORDER BY id DESC
        LIMIT ?
        """, (trade_id, limit))
    else:
        c.execute("""
        SELECT trade_id, event_type, data, created_at
        FROM trade_log
        ORDER BY id DESC
        LIMIT ?
        """, (limit,))

    rows = c.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "trade_id": r["trade_id"],
            "event_type": r["event_type"],
            "data": json.loads(r["data"]),
            "created_at": r["created_at"]
        })

    return results