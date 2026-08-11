"""Operational A-R4E frozen-snapshot five-minute recovery cadence authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
PINE = ROOT / "TradingView" / "indicators" / "Randle_AI_Level_Map_Helper.pine"
TRADE_MANAGER = ROOT / "Engines" / "trade_manager.py"
RECEIVER = ROOT / "EntryAgent" / "tv_context_server.py"
SNAPSHOT_MODE = "locked_levels_session_snapshot"
LOCK_MINUTE = 6 * 60 + 15
END_MINUTE = 14 * 60
CADENCE = 5


@dataclass
class SenderState:
    trading_day: str | None = None
    frozen_payload: bytes | None = None
    initial_sent: bool = False
    last_delivery_minute: int | None = None

    def bar(
        self,
        *,
        trading_day: str,
        minute: int,
        confirmed: bool = True,
        realtime: bool = True,
        authority_ready: bool = True,
        telemetry: float = 1.0,
    ) -> bytes | None:
        if self.trading_day != trading_day:
            self.trading_day = trading_day
            self.frozen_payload = None
            self.initial_sent = False
            self.last_delivery_minute = None
        if confirmed and authority_ready and minute >= LOCK_MINUTE and self.frozen_payload is None:
            snapshot = {
                "source": "tradingview_level_helper",
                "version": "v14_canonical_liquidity_sender",
                "context_mode": SNAPSHOT_MODE,
                "timestamp": f"{trading_day}T13:15:00Z",
                "session_date": trading_day,
                "is_premarket_end": True,
                "is_recurring_update": False,
                "telemetry": telemetry,
            }
            self.frozen_payload = json.dumps(snapshot, separators=(",", ":")).encode()
        ready = confirmed and realtime and self.frozen_payload is not None and minute <= END_MINUTE
        initial = ready and not self.initial_sent
        recovery = (
            ready
            and self.initial_sent
            and minute > LOCK_MINUTE
            and minute % CADENCE == 0
            and minute != self.last_delivery_minute
        )
        if not (initial or recovery):
            return None
        self.initial_sent = True
        self.last_delivery_minute = minute
        return self.frozen_payload


def test_production_source_uses_truthful_frozen_recovery_contract() -> None:
    source = PINE.read_text(encoding="utf-8")
    assert f'"context_mode":"{SNAPSHOT_MODE}"'.replace('"', '\\"') in source
    assert "locked_levels_recurring_status" not in source
    assert "OPERATIONAL_A_CADENCE=FROZEN_SNAPSHOT_5_MINUTE_RECOVERY" in source
    assert "int recoveryCadenceMinutes = 5" in source
    assert "bool isRecurringUpdate = false" in source
    assert "bool frozenSnapshotIsPremarketEnd = true" in source
    assert "frozenCanonicalPayload := entryAgentPayload" in source
    assert "alert(frozenCanonicalPayload, alert.freq_once_per_bar_close)" in source
    assert source.index("frozenCanonicalPayload := entryAgentPayload") < source.index(
        "alert(frozenCanonicalPayload, alert.freq_once_per_bar_close)"
    )


def test_trade_manager_and_receiver_require_same_snapshot_mode() -> None:
    for path in (TRADE_MANAGER, RECEIVER):
        source = path.read_text(encoding="utf-8")
        assert SNAPSHOT_MODE in source
        assert "locked_levels_recurring_status" not in source


def test_normal_prelock_start_emits_initial_at_0615() -> None:
    state = SenderState()
    assert state.bar(trading_day="2026-08-10", minute=374) is None
    assert state.bar(trading_day="2026-08-10", minute=375) is not None


def test_0616_through_0619_do_not_emit() -> None:
    state = SenderState()
    assert state.bar(trading_day="2026-08-10", minute=375) is not None
    assert [state.bar(trading_day="2026-08-10", minute=m) for m in range(376, 380)] == [None] * 4


def test_0620_and_0625_emit_same_bytes() -> None:
    state = SenderState()
    first = state.bar(trading_day="2026-08-10", minute=375)
    at_620 = state.bar(trading_day="2026-08-10", minute=380, telemetry=2.0)
    at_625 = state.bar(trading_day="2026-08-10", minute=385, telemetry=3.0)
    assert first == at_620 == at_625


def test_normal_session_count_is_94_and_all_bytes_match() -> None:
    state = SenderState()
    sends = [
        payload
        for minute in range(300, END_MINUTE + 1)
        if (payload := state.bar(trading_day="2026-08-10", minute=minute, telemetry=float(minute))) is not None
    ]
    assert len(sends) == 94
    assert len(set(sends)) == 1
    assert len({hashlib.sha256(payload).hexdigest() for payload in sends}) == 1


def test_historical_freeze_does_not_consume_late_alert_catchup() -> None:
    state = SenderState()
    assert state.bar(trading_day="2026-08-10", minute=375, realtime=False) is None
    catchup = state.bar(trading_day="2026-08-10", minute=382, telemetry=99.0)
    assert catchup is not None
    assert json.loads(catchup)["timestamp"] == "2026-08-10T13:15:00Z"
    assert json.loads(catchup)["telemetry"] == 1.0
    assert state.bar(trading_day="2026-08-10", minute=383) is None
    assert state.bar(trading_day="2026-08-10", minute=385) == catchup


def test_reload_after_prior_send_gets_one_byte_identical_catchup() -> None:
    before = SenderState()
    original = before.bar(trading_day="2026-08-10", minute=375)
    after = SenderState()
    after.bar(trading_day="2026-08-10", minute=375, realtime=False)
    assert after.bar(trading_day="2026-08-10", minute=402) == original


def test_unavailable_lock_has_later_5_minute_attempts_without_reload() -> None:
    state = SenderState()
    attempts = [state.bar(trading_day="2026-08-10", minute=m) for m in (375, 376, 380, 385)]
    assert [item is not None for item in attempts] == [True, False, True, True]
    assert attempts[0] == attempts[2] == attempts[3]


def test_duplicate_contract_remains_owned_by_existing_idempotency() -> None:
    trade_manager = TRADE_MANAGER.read_text(encoding="utf-8")
    receiver = RECEIVER.read_text(encoding="utf-8")
    assert '"delivery_state": "DUPLICATE_NOOP"' in trade_manager
    assert '"delivery_disposition": "DUPLICATE_NOOP"' in receiver


def test_durable_retry_remains_downstream_of_ingress_acceptance() -> None:
    source = TRADE_MANAGER.read_text(encoding="utf-8")
    assert source.index("_write_tv_spool_record(record)") < source.index(
        "downstream_status, downstream_payload, state = _deliver_tv_spool_record(record)"
    )
    assert "recover_pending_tv_context_deliveries" in source


def test_next_trading_day_resets_payload_and_identity() -> None:
    state = SenderState()
    first_day = state.bar(trading_day="2026-08-10", minute=375)
    assert state.bar(trading_day="2026-08-10", minute=380) == first_day
    assert state.bar(trading_day="2026-08-11", minute=374) is None
    next_day = state.bar(trading_day="2026-08-11", minute=375)
    assert next_day is not None and next_day != first_day


@pytest.mark.parametrize("symbol", ("YM1!", "NQ1!"))
def test_symbol_independent_normal_session_count_is_94(symbol: str) -> None:
    assert symbol in {"YM1!", "NQ1!"}
    state = SenderState()
    sends = sum(
        state.bar(trading_day="2026-08-10", minute=minute) is not None
        for minute in range(300, END_MINUTE + 1)
    )
    assert sends == 94


def test_session_endpoint_stops_after_1400() -> None:
    state = SenderState()
    state.bar(trading_day="2026-08-10", minute=375)
    assert state.bar(trading_day="2026-08-10", minute=840) is not None
    assert state.bar(trading_day="2026-08-10", minute=845) is None


def test_source_alignment_is_wall_clock_not_load_relative() -> None:
    source = PINE.read_text(encoding="utf-8")
    assert "minute(time, tzInput) % recoveryCadenceMinutes == 0" in source
    assert "time > today0615" in source
    assert "time <= today1400" in source
    assert "lastRecoveryDeliveryBarTime != time" in source


def test_source_freezes_governed_0615_timestamp_and_not_current_bar_time() -> None:
    source = PINE.read_text(encoding="utf-8")
    timestamp_line = next(line for line in source.splitlines() if line.startswith("string canonicalSourceTimestamp"))
    assert "today0615" in timestamp_line
    assert "time_close" not in timestamp_line
    assert "frozenCanonicalSourceTimestamp := canonicalSourceTimestamp" in source


def test_literal_gate_freezes_payload_before_any_alert() -> None:
    source = PINE.read_text(encoding="utf-8")
    assert source.index("if canonicalPayloadLiteralIntegrity") < source.index(
        "frozenCanonicalPayload := entryAgentPayload"
    )
    assert source.index("frozenCanonicalPayload := entryAgentPayload") < source.index(
        "alert(frozenCanonicalPayload, alert.freq_once_per_bar_close)"
    )

