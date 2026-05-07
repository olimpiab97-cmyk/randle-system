# lifecycle_engine.py

from datetime import datetime


# =========================
# STATE VALIDATION
# =========================

VALID_STATES = ["created", "active", "runner_active", "closed", "cancelled"]


def is_trade_closed(trade):
    return trade["status"] in ["closed", "cancelled"]


# =========================
# MAIN ENTRY POINT
# =========================

def evaluate_trade_update(trade, price):
    """
    Called on every price update.
    Determines event → triggers transition → returns actions
    """

    if is_trade_closed(trade):
        return []

    # PRIORITY ORDER
    if check_stop_hit(trade, price):
        return transition_trade(trade, "STOP_HIT", price)

    if check_be_and_tp1_same_update(trade, price):
        return transition_trade(trade, "BE_AND_TP1_SAME_UPDATE", price)

    if check_tp1_hit(trade, price):
        return transition_trade(trade, "TP1_HIT", price)

    if check_be_trigger(trade, price):
        return transition_trade(trade, "BE_TRIGGER_HIT", price)

    return []


# =========================
# EVENT CHECKS
# =========================

def check_stop_hit(trade, price):
    if trade["direction"] == "long":
        return price <= trade["current_stop"]
    else:
        return price >= trade["current_stop"]


def check_tp1_hit(trade, price):
    if trade["tp1_hit"]:
        return False

    if trade["direction"] == "long":
        return price >= trade["tp1_price"]
    else:
        return price <= trade["tp1_price"]


def check_be_trigger(trade, price):
    if trade["moved_to_be"]:
        return False

    if trade["direction"] == "long":
        return price >= trade["be_trigger"]
    else:
        return price <= trade["be_trigger"]


def check_be_and_tp1_same_update(trade, price):
    return (
        check_tp1_hit(trade, price)
        and check_be_trigger(trade, price)
    )


# =========================
# TRANSITION ENGINE
# =========================

def transition_trade(trade, event, price):
    """
    Validates + applies lifecycle transitions
    Returns executor actions
    """

    actions = []
    now = datetime.utcnow().isoformat()

    status = trade["status"]

    # =========================
    # CREATED STATE
    # =========================
    if status == "created":

        if event == "ENTRY_FILLED":
            trade["status"] = "active"
            trade["entry_filled"] = True
            trade["filled_at"] = now

        elif event == "ENTRY_CANCELLED":
            trade["status"] = "cancelled"
            trade["closed_at"] = now
            trade["exit_reason"] = "entry_cancelled"

        return actions


    # =========================
    # ACTIVE STATE
    # =========================
    if status == "active":

        # STOP HIT
        if event == "STOP_HIT":
            trade["remaining_size"] = 0
            trade["status"] = "closed"
            trade["exit_reason"] = "stop_loss"

            actions.append({
                "action": "flatten_symbol",
                "trade_id": trade["trade_id"],
                "symbol": trade["symbol"]
            })

            return actions


        # BE + TP1 SAME UPDATE
        if event == "BE_AND_TP1_SAME_UPDATE":

            trade["be_then_tp1_same_update"] = True

            # Execute TP1 first
            actions.extend(handle_tp1(trade, now))

            # Then BE logic for runner
            actions.extend(handle_be(trade, now))

            return actions


        # TP1 ONLY
        if event == "TP1_HIT":

            actions.extend(handle_tp1(trade, now))
            trade["status"] = "runner_active"

            return actions


        # BE ONLY
        if event == "BE_TRIGGER_HIT":

            actions.extend(handle_be(trade, now))
            return actions


    # =========================
    # RUNNER STATE
    # =========================
    if status == "runner_active":

        if event == "STOP_HIT":

            trade["remaining_size"] = 0
            trade["status"] = "closed"
            trade["exit_reason"] = "tp1_runner_stop"

            actions.append({
                "action": "flatten_symbol",
                "trade_id": trade["trade_id"],
                "symbol": trade["symbol"]
            })

            return actions


    return actions


# =========================
# ACTION BUILDERS
# =========================

def handle_tp1(trade, now):

    if trade["tp1_hit"]:
        return []

    trade["tp1_hit"] = True
    trade["tp1_hit_at"] = now

    # Reduce position
    trade["remaining_size"] = trade["position_size"] / 2

    return [{
        "action": "submit_limit",
        "trade_id": trade["trade_id"],
        "symbol": trade["symbol"],
        "qty": trade["remaining_size"],
        "limit_price": trade["tp1_price"]
    }]


def handle_be(trade, now):

    if trade["moved_to_be"]:
        return []

    trade["moved_to_be"] = True
    trade["be_hit_at"] = now
    trade["current_stop"] = trade["entry_price"]
    trade["stop_state"] = "break_even"

    return [
        {
            "action": "cancel_order",
            "trade_id": trade["trade_id"],
            "symbol": trade["symbol"]
        },
        {
            "action": "submit_stop",
            "trade_id": trade["trade_id"],
            "symbol": trade["symbol"],
            "stop_price": trade["entry_price"],
            "qty": trade["remaining_size"]
        }
    ]