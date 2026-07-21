from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
ENTRY_AGENT_SOURCE = ROOT / "EntryAgent" / "entry_agent.py"
TV_SERVER_SOURCE = ROOT / "EntryAgent" / "tv_context_server.py"


ENTRY_AGENT_WRITERS = {
    "_write_json",
    "append_entry_agent_audit_row",
    "persist_confirmed_rejection_anchor_from_authoritative_snapshot",
    "log_step2_owner_diagnostic",
    "persist_pre_open_observed_extreme",
    "persist_state",
    "record_consumed_entry_setup",
    "record_submitted_entry_setup",
    "repair_same_candle_audit_row",
}

TV_SERVER_WRITERS = {
    "_write_json",
    "append_context_event",
    "append_entry_decision_log",
    "append_entry_reasoning_log",
    "append_operator_route_audit",
    "safe_write_json",
}

LIFECYCLE_EVALUATORS = {
    "run_once",
    "evaluate_live_step_2_1a",
    "evaluate_live_step25",
    "evaluate_live_step3",
    "evaluate_live_step4",
    "evaluate_live_step5",
    "evaluate_live_step6",
    "evaluate_gateway",
}


def module_call_graph(path: Path) -> tuple[dict[str, ast.AST], dict[str, set[str]]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    calls = {
        name: {
            call.func.id
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id in functions
        }
        for name, node in functions.items()
    }
    return functions, calls


def reachable_calls(calls: dict[str, set[str]], root: str) -> set[str]:
    reached: set[str] = set()
    pending = [root]
    while pending:
        name = pending.pop()
        if name in reached:
            continue
        reached.add(name)
        pending.extend(calls.get(name, set()) - reached)
    return reached


def direct_named_calls(node: ast.AST) -> set[str]:
    return {
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }


def keyword_boolean_calls(node: ast.AST, function_name: str, keyword: str) -> list[bool | None]:
    values: list[bool | None] = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            continue
        if call.func.id != function_name:
            continue
        selected = next((item.value for item in call.keywords if item.arg == keyword), None)
        values.append(selected.value if isinstance(selected, ast.Constant) and isinstance(selected.value, bool) else None)
    return values


def calls_guarded_by_persist(node: ast.AST, writer_names: set[str]) -> list[tuple[str, int, bool]]:
    results: list[tuple[str, int, bool]] = []

    def walk(current: ast.AST, persist_guarded: bool = False) -> None:
        guarded = persist_guarded
        if isinstance(current, ast.If):
            guarded = guarded or (
                isinstance(current.test, ast.Name) and current.test.id == "persist"
            )
        if isinstance(current, ast.Call) and isinstance(current.func, ast.Name):
            if current.func.id in writer_names:
                results.append((current.func.id, current.lineno, persist_guarded))
        for child in ast.iter_child_nodes(current):
            walk(child, guarded)

    walk(node)
    return results


def decorator_names(node: ast.AST) -> set[str]:
    decorators = getattr(node, "decorator_list", [])
    return {
        decorator.id
        for decorator in decorators
        if isinstance(decorator, ast.Name)
    }


def test_status_call_graph_uses_guarded_projection_mode_and_no_route_writers() -> None:
    entry_functions, entry_calls = module_call_graph(ENTRY_AGENT_SOURCE)
    server_functions, server_calls = module_call_graph(TV_SERVER_SOURCE)

    status_projection = reachable_calls(entry_calls, "build_entry_status")
    assert "run_once" in status_projection
    assert "evaluation_mode_from_persist" in decorator_names(entry_functions["run_once"])
    assert direct_named_calls(entry_functions["build_entry_status"]).isdisjoint(ENTRY_AGENT_WRITERS)
    guarded_writes = calls_guarded_by_persist(entry_functions["run_once"], ENTRY_AGENT_WRITERS)
    assert guarded_writes
    assert all(guarded for _name, _line, guarded in guarded_writes), guarded_writes

    for writer in (
        "_write_json",
        "append_entry_agent_audit_row",
        "persist_pre_open_observed_extreme",
        "persist_state",
        "record_consumed_entry_setup",
        "record_submitted_entry_setup",
        "repair_same_candle_audit_row",
        "persist_confirmed_rejection_anchor_from_authoritative_snapshot",
    ):
        assert "require_authoritative_mutation" in direct_named_calls(entry_functions[writer])
    assert "authoritative_mutation_allowed" in direct_named_calls(entry_functions["log_step2_owner_diagnostic"])

    status_route = reachable_calls(server_calls, "get_entry_status")
    debug_route = reachable_calls(server_calls, "debug_entry_liquidity")
    assert status_route.isdisjoint(TV_SERVER_WRITERS)
    assert debug_route.isdisjoint(TV_SERVER_WRITERS)
    assert "build_entry_status" in direct_named_calls(server_functions["get_entry_status"])
    assert "build_entry_status" in direct_named_calls(server_functions["debug_entry_liquidity"])

    status_builders = {
        name
        for name, node in server_functions.items()
        if "build_entry_status" in direct_named_calls(node)
    }
    assert status_builders == {"get_entry_status", "debug_entry_liquidity"}
    for read_only_query in (
        "debug_entry_log",
        "entry_reasoning_log",
        "get_entry_executor_status",
        "debug_tv_context_receipt",
    ):
        assert reachable_calls(server_calls, read_only_query).isdisjoint(TV_SERVER_WRITERS)
    assert keyword_boolean_calls(entry_functions["build_entry_status"], "run_once", "persist") == [False]
    assert keyword_boolean_calls(entry_functions["run_watch"], "run_once", "persist") == [False]
    assert keyword_boolean_calls(entry_functions["main"], "run_once", "persist") == [False]
    assert keyword_boolean_calls(server_functions["receive_tv_context"], "run_once", "persist") == [True]


def test_read_side_writer_guard_rejects_full_and_narrow_authority_writes(tmp_path: Path) -> None:
    import sys

    entry_agent_dir = str(ROOT / "EntryAgent")
    if entry_agent_dir not in sys.path:
        sys.path.insert(0, entry_agent_dir)
    import entry_agent

    original_state = entry_agent.STATE_PATH
    entry_agent.STATE_PATH = tmp_path / "entry_agent_state.json"
    try:
        with entry_agent.entry_authority_mode(allow_mutation=False):
            with pytest.raises(RuntimeError, match="read-side projection"):
                entry_agent._write_json(entry_agent.STATE_PATH, {})
            with pytest.raises(RuntimeError, match="read-side projection"):
                entry_agent.persist_pre_open_observed_extreme({}, "NQ", None)
            with pytest.raises(RuntimeError, match="read-side projection"):
                entry_agent.persist_state({"normalized_symbol": "NQ"})
            with pytest.raises(RuntimeError, match="read-side projection"):
                entry_agent.record_consumed_entry_setup("NQ", {"key": "test"}, "test")
            with pytest.raises(RuntimeError, match="read-side projection"):
                entry_agent.persist_confirmed_rejection_anchor_from_authoritative_snapshot({}, {})
    finally:
        entry_agent.STATE_PATH = original_state


def test_run_once_persist_false_rejects_hidden_authoritative_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    entry_agent_dir = str(ROOT / "EntryAgent")
    if entry_agent_dir not in sys.path:
        sys.path.insert(0, entry_agent_dir)
    import entry_agent

    monkeypatch.setattr(
        entry_agent,
        "load_entry_state",
        lambda: {},
    )
    monkeypatch.setattr(
        entry_agent,
        "get_latest_market_snapshot",
        lambda _symbol="NQ": {
            "symbol": "NQ",
            "latest_price": 100.0,
            "latest_bar_time": "2026-07-16T13:20:00Z",
            "ohlc_is_closed": True,
            "ohlc": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        },
    )
    monkeypatch.setattr(entry_agent, "load_raw_tv_context", lambda _symbol=None: None)
    monkeypatch.setattr(entry_agent, "load_tv_context", lambda _symbol=None: None)
    monkeypatch.setattr(entry_agent, "load_rithmic_atr_snapshot", lambda _symbol: None)
    monkeypatch.setattr(
        entry_agent,
        "persist_pre_open_observed_extreme",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("projection called narrow writer")),
    )
    monkeypatch.setattr(
        entry_agent,
        "persist_state",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("projection called full writer")),
    )
    monkeypatch.setattr(
        entry_agent,
        "append_entry_agent_audit_row",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("projection called audit writer")),
    )

    snapshot = entry_agent.run_once("NQ", persist=False)
    assert snapshot["normalized_symbol"] == "NQ"


def test_accepted_tv_webhook_invokes_authoritative_candle_mode_not_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import copy
    import sys

    entry_agent_dir = str(ROOT / "EntryAgent")
    if entry_agent_dir not in sys.path:
        sys.path.insert(0, entry_agent_dir)
    import tv_context_server
    from test_nq_20260716_regressions import nq_context

    for name in (
        "LEVELS_PATH",
        "LEVELS_BY_SYMBOL_PATH",
        "TV_CONTEXT_PATH",
        "TV_CONTEXT_BY_SYMBOL_PATH",
        "TV_CONTEXT_EVENTS_PATH",
    ):
        monkeypatch.setattr(tv_context_server, name, tmp_path / f"{name.lower()}.json")

    original_latest = copy.deepcopy(tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL)
    tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
    calls: list[tuple[str, bool]] = []

    def authoritative_candle(symbol="NQ", persist=True):
        calls.append((str(symbol).upper(), persist))
        return {"latest_bar_time": "2026-07-16T13:24:00Z"}

    monkeypatch.setattr(tv_context_server, "run_once", authoritative_candle)
    monkeypatch.setattr(
        tv_context_server,
        "build_entry_status",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("webhook event processing must not be driven by status construction")
        ),
    )
    try:
        response = tv_context_server.app.test_client().post(
            "/webhook/tv-context",
            json=nq_context(),
        )
        payload = response.get_json()
        assert response.status_code == 200
        assert calls == [("NQ", True)]
        assert payload["lifecycle_processed_candle"] == "2026-07-16T13:24:00Z"
        assert payload["lifecycle_processing_error"] is None
    finally:
        tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL.clear()
        tv_context_server.LATEST_TV_CONTEXT_BY_SYMBOL.update(original_latest)
