"""Repository verification for the complete canonical Pine v14 liquidity sender.

TradingView is the only Pine compiler. These tests bind source structure and
deterministic synthetic serializer outputs; they do not claim Pine compilation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_DIR = ROOT / "EntryAgent"
if str(ENTRY_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(ENTRY_AGENT_DIR))

import tv_context_server as server


PINE = ROOT / "TradingView" / "indicators" / "Randle_AI_Level_Map_Helper.pine"
REPLACEMENT_TAIL = ROOT / "REPLACE_ENTRY_AGENT_WEBHOOK_OVERLAPPING_FINALIZED_TABLE_STATE.pine"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "tradingview"
ACCEPTED_TAIL_SHA256 = "7A677CB6B40AFF4A180A121890C64F50D036E21F96E227ED3A3DBB1ABB2E911F"
LEVEL_ORDER = ("PMH", "PML", "LH", "LL", "ONH", "ONL", "YH", "YL")
TOP_LEVEL_ORDER = (
    "source",
    "version",
    "context_mode",
    "timestamp",
    "session_date",
    "session_locked",
    "locked",
    "is_premarket_end",
    "is_recurring_update",
    "price_is_true_level",
    "display_offsets_applied_to_chart_only",
    "symbol",
    "time_zone",
    "timeframe",
    "atr_1m_14",
    "daily_atr14",
    "stack_threshold",
    "stack_threshold_pct",
    "session_lock_price",
    "pm_atr_pct",
    "daily_range_pct",
    "levels",
    "stacks",
    "liquidity_map",
    "midpoints",
    "exhaustion_boundaries",
)
CANONICAL_RECEIVER_AVAILABLE = all(
    hasattr(server, name)
    for name in (
        "RANDLE_TAYLOR_MAP_SOURCE",
        "_rebuild_frozen_lock_from_latest_tv",
        "liquidity_stack_structure_error",
    )
)
requires_canonical_receiver = pytest.mark.skipif(
    not CANONICAL_RECEIVER_AVAILABLE,
    reason="canonical Entry Agent receiver implementation is outside this source-only commit",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def webhook_section() -> str:
    source = PINE.read_text(encoding="utf-8")
    marker = "// ENTRY AGENT TRADINGVIEW CONTEXT WEBHOOK"
    return source[source.rindex(marker) :]


def payload_expression() -> str:
    section = webhook_section()
    start = section.index("string entryAgentPayload =")
    end = section.index("alert(entryAgentPayload", start)
    return section[start:end]


def pine_delimiters_outside_strings_and_comments(source: str) -> list[str]:
    delimiters: list[str] = []
    for line in source.splitlines():
        in_string = False
        escaped = False
        index = 0
        while index < len(line):
            char = line[index]
            if not in_string and char == "/" and index + 1 < len(line) and line[index + 1] == "/":
                break
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char in "()[]{}":
                delimiters.append(char)
            index += 1
        assert not in_string, f"unterminated Pine string: {line}"
    return delimiters


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def level(name: str, price: float, stack_group: str = "NONE") -> dict[str, object]:
    groups = [] if stack_group == "NONE" else [stack_group]
    return {
        "name": name,
        "price": price,
        "status": "ACTIVE",
        "stack_group": stack_group,
        "stack_groups": groups,
        "stack_display": stack_group,
    }


def synthetic_pine_payload(symbol: str, *, stacked_yh: bool) -> dict[str, object]:
    prices = {
        "PMH": 52720.0,
        "PML": 52320.0,
        "LH": 52680.0,
        "LL": 52380.0,
        "ONH": 52789.0,
        "ONL": 52262.0,
        "YH": 52835.0,
        "YL": 52174.0,
    }
    labels = {name: "NONE" for name in LEVEL_ORDER}
    stacks: list[dict[str, object]] = []
    if stacked_yh:
        labels["ONH"] = labels["YH"] = "HIGH 1"
        stacks.append(
            {
                "id": "HIGH 1",
                "side": "HIGH",
                "members": ["ONH", "YH"],
                "innermost_price": prices["ONH"],
                "outermost_price": prices["YH"],
            }
        )

    rows = [level(name, prices[name], labels[name]) for name in LEVEL_ORDER]
    nested_levels = {
        row["name"]: {key: value for key, value in row.items() if key != "name"}
        for row in rows
    }
    return {
        "source": "tradingview_level_helper",
        "version": "v14_canonical_liquidity_sender",
        "context_mode": "locked_levels_recurring_status",
        "timestamp": "2026-07-20T13:16:00Z",
        "session_date": "2026-07-20",
        "session_locked": True,
        "locked": True,
        "is_premarket_end": False,
        "is_recurring_update": True,
        "price_is_true_level": True,
        "display_offsets_applied_to_chart_only": True,
        "symbol": symbol,
        "time_zone": "America/Los_Angeles",
        "timeframe": "1",
        "atr_1m_14": 42.25,
        "daily_atr14": 590.0,
        "stack_threshold": 59.0,
        "stack_threshold_pct": 10.0,
        "session_lock_price": 52500.0,
        "pm_atr_pct": 30.0,
        "daily_range_pct": 70.0,
        "levels": nested_levels,
        "stacks": copy.deepcopy(stacks),
        "liquidity_map": {"levels": rows, "stacks": copy.deepcopy(stacks)},
        "midpoints": {},
        "exhaustion_boundaries": {},
    }


def strict_taylor_payload() -> dict[str, object]:
    levels = [
        {"name": name, "price": 100.0 + index, "status": "ACTIVE", "stack_group": "NONE"}
        for index, name in enumerate(LEVEL_ORDER)
    ]
    return {
        "source": "randle_taylor_map",
        "symbol": "NQ1!",
        "timestamp": "2026-07-20T13:16:00Z",
        "session_date": "2026-07-20",
        "time_zone": "America/Los_Angeles",
        "locked": True,
        "session_lock_price": 100.0,
        "stack_threshold": 10.0,
        "atr_1m_14": 5.0,
        "daily_atr14": 100.0,
        "liquidity_map": {"levels": levels, "stacks": []},
        "taylor_context": {"t_plus": {"state": "UP"}},
    }


def test_complete_source_and_accepted_tail_provenance() -> None:
    source = PINE.read_text(encoding="utf-8")
    tail = REPLACEMENT_TAIL.read_text(encoding="utf-8")

    assert sha256(REPLACEMENT_TAIL) == ACCEPTED_TAIL_SHA256
    assert source.startswith('//@version=6\nindicator("Randle AI - Level Map Helper v14 Canonical"')
    assert source.count("//@version=") == 1
    assert source.count("\nindicator(") == 1
    assert "Replace the production source" not in source
    assert source.count("string entryAgentPayload =") == 1
    assert source.count("alert(entryAgentPayload, alert.freq_once_per_bar_close)") == 1
    for complete_section in (
        "// INPUTS",
        "// SESSION TRACKERS",
        "// DAILY ATR / RANGE METRICS",
        "// STATUS ENGINE",
        "// SESSION-END LOCK",
        "// STACK GROUP LOGIC - FINAL MERGED COMPONENT STACKS",
        "// DYNAMIC LADDER / EXHAUSTION BOUNDARY HELPERS",
        "// LIVE PLOTS",
        "// DYNAMIC PRICE-ACTION TABLE",
        "// ENTRY AGENT TRADINGVIEW CONTEXT WEBHOOK",
    ):
        assert complete_section in source
    for signature in (
        "payloadLevelNameAtIndex(int levelIdx) =>",
        "payloadExplicitStackObjectJson(string stackLabel, string side) =>",
        "payloadExplicitStacksArrayJson() =>",
        "payloadLevelJson(int levelIdx) =>",
    ):
        assert signature in tail
        assert signature in source
    accepted_reference_line = '+ "\\\"session_lock_price\\\":" + f_json_num(sessionLockPrice_eff) + ","'
    assert tail.count(accepted_reference_line) == 1
    assert source.count(accepted_reference_line) == 1


def test_complete_source_has_balanced_structural_delimiters() -> None:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for delimiter in pine_delimiters_outside_strings_and_comments(PINE.read_text(encoding="utf-8")):
        if delimiter in "([{":
            stack.append(delimiter)
        else:
            assert stack and stack.pop() == pairs[delimiter]
    assert stack == []


def test_source_time_uses_confirmed_bar_close_in_utc_not_execution_clock() -> None:
    section = webhook_section()
    assert 'str.format_time(time_close, "yyyy-MM-dd\'T\'HH:mm:ss\'Z\'", "UTC")' in section
    assert '\\"timestamp\\":" + f_json_str(canonicalSourceTimestamp)' in section
    assert "timenow" not in section
    assert "barstate.isconfirmed" in section
    assert "alert.freq_once_per_bar_close" in section


def test_session_date_uses_exchange_trading_day_and_binds_to_frozen_lock() -> None:
    source = PINE.read_text(encoding="utf-8")
    section = webhook_section()
    assert 'str.format_time(time_tradingday, "yyyy-MM-dd", "UTC")' in section
    assert "sessionTradingDay_lock := time_tradingday" in source
    assert "time_tradingday == sessionTradingDay_lock" in section
    assert '\\"session_date\\":" + f_json_str(canonicalSessionDate)' in section

    monday_trading_day = int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp() * 1000)
    assert datetime.fromtimestamp(monday_trading_day / 1000, timezone.utc).strftime("%Y-%m-%d") == "2026-07-20"
    # TradingView supplies this same trading-day identity to Sunday-evening,
    # post-midnight, and Monday-morning intraday futures bars in one session.
    assert len({monday_trading_day for _bar in ("Sun 15:01 PT", "Mon 00:01 PT", "Mon 06:15 PT", "Mon 07:30 PT")}) == 1


def test_frozen_reference_is_separate_and_never_falls_back_to_current_price() -> None:
    source = PINE.read_text(encoding="utf-8")
    expression = payload_expression()
    assert "float sessionLockPrice_eff = sessionLocked ? sessionLockPrice_lock : na" in source
    assert '\\"session_lock_price\\":" + f_json_num(sessionLockPrice_eff)' in expression
    assert "not na(sessionLockPrice_eff)" in webhook_section()
    assert '\\"stack_threshold\\":" + f_json_num(stackThreshold_eff)' in expression
    assert expression.index('\\"stack_threshold\\"') < expression.index('\\"session_lock_price\\"')


def test_sender_fail_closed_gate_covers_every_required_authority() -> None:
    section = webhook_section()
    gate = section[section.index("bool canonicalPayloadReady =") : section.index("if canonicalPayloadReady")]
    for required in (
        "timeframe.isminutes",
        "timeframe.multiplier == 1",
        "barstate.isconfirmed",
        "tzInput == canonicalTimeZone",
        "sessionLocked",
        "not na(sessionTradingDay_lock)",
        "time_tradingday == sessionTradingDay_lock",
        "str.length(canonicalSourceTimestamp) > 0",
        "str.length(canonicalSessionDate) == 10",
        "not na(sessionLockPrice_eff)",
        "not na(stackThreshold_eff)",
        "not na(atr1m14)",
        "not na(dailyATR14)",
    ):
        assert required in gate
    assert section.count("alert(entryAgentPayload") == 1
    assert section.index("if canonicalPayloadReady") < section.index("alert(entryAgentPayload")


def test_exact_serializer_field_inventory_and_order() -> None:
    expression = payload_expression()
    positions: list[int] = []
    for key in TOP_LEVEL_ORDER[:21]:
        token = f'\\"{key}\\"'
        assert expression.count(token) == 1
        positions.append(expression.index(token))
    assert positions == sorted(positions)
    assert expression.count('\\"stacks\\"') == 2
    assert expression.count('\\"liquidity_map\\"') == 1
    assert '+ levelsJson + ","' in expression
    assert '+ midpointsJson + ","' in expression
    assert '+ exhaustionJson' in expression
    assert ',}' not in expression


@pytest.mark.parametrize(
    ("symbol", "stacked_yh", "fixture_name"),
    (
        ("YM1!", True, "v14_canonical_liquidity_sender_ym_stacked_yh.json"),
        ("NQ1!", False, "v14_canonical_liquidity_sender_nq_unstacked_yh.json"),
    ),
)
def test_deterministic_synthetic_pine_json_is_valid_typed_and_complete(
    symbol: str,
    stacked_yh: bool,
    fixture_name: str,
) -> None:
    payload = synthetic_pine_payload(symbol, stacked_yh=stacked_yh)
    encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    decoded = json.loads(encoded, object_pairs_hook=reject_duplicate_keys)
    fixture = json.loads(
        (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )

    assert decoded == fixture
    assert tuple(decoded) == TOP_LEVEL_ORDER
    assert decoded["timestamp"].endswith("Z")
    assert decoded["session_date"] == "2026-07-20"
    assert isinstance(decoded["session_lock_price"], float)
    assert isinstance(decoded["stack_threshold"], float)
    assert tuple(decoded["levels"]) == LEVEL_ORDER
    assert [row["name"] for row in decoded["liquidity_map"]["levels"]] == list(LEVEL_ORDER)
    assert decoded["stacks"] == decoded["liquidity_map"]["stacks"]
    if stacked_yh:
        assert decoded["levels"]["YH"]["stack_group"] == "HIGH 1"
        assert decoded["stacks"][0]["members"] == ["ONH", "YH"]
    else:
        assert decoded["levels"]["YH"]["stack_group"] == "NONE"
        assert decoded["stacks"] == []


def test_nq_and_ym_share_one_serializer_without_symbol_exception() -> None:
    section = webhook_section()
    nq = synthetic_pine_payload("NQ1!", stacked_yh=False)
    ym = synthetic_pine_payload("YM1!", stacked_yh=True)
    assert "syminfo.ticker" in section
    assert '"NQ"' not in section and '"YM"' not in section
    assert tuple(nq) == tuple(ym)
    assert {key: type(value) for key, value in nq.items()} == {key: type(value) for key, value in ym.items()}


@pytest.mark.parametrize(("symbol", "stacked_yh"), (("YM1!", True), ("NQ1!", False)))
@requires_canonical_receiver
def test_entry_agent_accepts_complete_canonical_liquidity_fixture(symbol: str, stacked_yh: bool) -> None:
    payload = synthetic_pine_payload(symbol, stacked_yh=stacked_yh)
    context, error = server.build_context(payload)

    assert error is None
    assert context is not None
    assert context["timestamp"] == payload["timestamp"]
    assert context["session_date"] == payload["session_date"]
    assert context["session_lock_price"] == payload["session_lock_price"]
    assert context["liquidity_map"]["stacks"] == payload["liquidity_map"]["stacks"]


@pytest.mark.parametrize("missing_field", ("timestamp", "session_date"))
@requires_canonical_receiver
def test_entry_agent_strict_profile_rejects_missing_source_identity(missing_field: str) -> None:
    payload = strict_taylor_payload()
    payload.pop(missing_field)
    context, error = server.build_context(payload)
    assert context is None
    assert error == {"error": f"{missing_field} is required"}


@requires_canonical_receiver
def test_entry_agent_rejects_invalid_source_timestamp() -> None:
    payload = strict_taylor_payload()
    payload["timestamp"] = "not-a-timestamp"
    context, error = server.build_context(payload)
    assert context is None
    assert error == {"error": "timestamp must be a valid ISO string or epoch value"}


@requires_canonical_receiver
def test_entry_agent_keeps_precise_missing_reference_rejection_for_stacked_yh() -> None:
    payload = synthetic_pine_payload("YM1!", stacked_yh=True)
    payload.pop("session_lock_price")
    context, error = server.build_context(payload)
    assert context is None
    assert error == {
        "code": "STACK_REFERENCE_PRICE_MISSING",
        "error": "a frozen market reference is required to validate YH in HIGH 1",
        "level": "YH",
        "stack_group": "HIGH 1",
    }


@requires_canonical_receiver
def test_rehydration_rejects_prior_session_identity() -> None:
    current_date = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    stale_date = (current_date - timedelta(days=1)).isoformat()
    locked_tv = synthetic_pine_payload("YM1!", stacked_yh=True)
    locked_tv["session_date"] = stale_date
    route_context = {
        "last_tv_context_levels": locked_tv["levels"],
        "last_tv_context_session_date": stale_date,
        "session_date": stale_date,
        "received_at": "2026-07-19T13:16:00Z",
    }
    rebuilt, error = server._rebuild_frozen_lock_from_latest_tv(
        "YM",
        route_context,
        {"locked": True, "disabled": False, "tv_context": locked_tv},
    )
    assert rebuilt is None
    assert error == {
        "error": "not_current_session",
        "current_session_date": current_date.isoformat(),
        "locked_session_date": stale_date,
    }
