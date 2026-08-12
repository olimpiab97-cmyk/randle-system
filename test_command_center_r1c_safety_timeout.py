"""R1C bounded Trade Manager safety-read authority regressions."""

from __future__ import annotations

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from command_center_service_control import (
    ProductionServiceAdapter,
    ServiceClassification,
    ServiceReadiness,
)


ROOT = Path(__file__).resolve().parent
SAFE_PAYLOAD = {
    "ok": True,
    "trades": {},
    "orphan_exposure": {
        "has_orphans": False,
        "has_manager_state_issue": False,
    },
}


class _Response:
    def __init__(self, payload: object = SAFE_PAYLOAD, *, raw: bytes | None = None, status: int = 200) -> None:
        self.status = status
        self._raw = raw if raw is not None else json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _DelayedHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        time.sleep(float(self.server.delay_seconds))  # type: ignore[attr-defined]
        body = json.dumps(SAFE_PAYLOAD).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return None


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value


class CommandCenterR1CSafetyTimeoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = ProductionServiceAdapter(ROOT)

    def _assert_delayed_healthy(self, delay_ms: int) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _DelayedHandler)
        server.delay_seconds = delay_ms / 1000.0  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.adapter.safety_read_endpoint = f"http://127.0.0.1:{server.server_port}/trades"
            result = self.adapter._trade_manager_safety_read()
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["attempts"], 1)
            self.assertGreaterEqual(result["elapsed_ms"], delay_ms - 100)
            self.assertLess(result["elapsed_ms"], 4000)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def _running_trade_manager_snapshot(self) -> dict[str, object]:
        return {
            "services": [
                {
                    "name": "executor",
                    "classification": ServiceClassification.STOPPED.value,
                    "readiness": ServiceReadiness.STOPPED.value,
                },
                {
                    "name": "trade_manager",
                    "classification": ServiceClassification.RUNNING_READY.value,
                    "identity": "TRUSTED",
                    "readiness": ServiceReadiness.READY.value,
                },
            ]
        }

    def _start_safety_with_payload(self, payload: dict[str, object]) -> dict[str, object]:
        self.adapter._prestart_executor_exposure = lambda _snapshot: {
            "ok": True,
            "safe": True,
            "reason": "fixture_clear",
            "active_orders": 0,
            "nonzero_positions": 0,
        }
        self.adapter._safety_json_get_result = lambda _url, deadline=None: {
            "ok": True,
            "payload": payload,
            "status": 200,
            "reason": "fixture_live",
            "attempts": 1,
            "elapsed_ms": 0,
        }
        return self.adapter.start_safety(self._running_trade_manager_snapshot())

    def test_1900_ms_healthy_response_passes(self) -> None:
        self._assert_delayed_healthy(1900)

    def test_2000_ms_healthy_response_passes(self) -> None:
        self._assert_delayed_healthy(2000)

    def test_2020_ms_r2_latency_response_passes(self) -> None:
        self._assert_delayed_healthy(2020)

    def test_2036_ms_r2_latency_response_passes(self) -> None:
        self._assert_delayed_healthy(2036)

    def test_2140_ms_r2_latency_response_passes(self) -> None:
        self._assert_delayed_healthy(2140)

    def test_2200_ms_healthy_response_passes(self) -> None:
        self._assert_delayed_healthy(2200)

    def test_original_two_second_boundary_is_replaced_by_measured_policy(self) -> None:
        self.assertLess(2.0, 2.140)
        self.assertEqual(self.adapter.safety_read_attempt_timeout, 4.0)
        self.assertEqual(self.adapter.safety_read_max_attempts, 2)
        self.assertEqual(self.adapter.safety_read_total_budget, 8.0)

    def test_unavailable_endpoint_fails_closed_without_retry(self) -> None:
        with patch("command_center_service_control.urlopen", side_effect=URLError(ConnectionRefusedError("refused"))) as opened:
            result = self.adapter._trade_manager_safety_read()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "transport_unavailable")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(opened.call_count, 1)

    def test_hung_endpoint_exhausts_bounded_total_budget(self) -> None:
        clock = _Clock()

        def timeout(_request: object, *, timeout: float) -> _Response:
            clock.value += timeout
            raise TimeoutError("hung")

        with patch("command_center_service_control.time.monotonic", side_effect=clock.monotonic), patch(
            "command_center_service_control.urlopen", side_effect=timeout
        ) as opened:
            result = self.adapter._trade_manager_safety_read()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "total_budget_exhausted")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["elapsed_ms"], 8000.0)
        self.assertEqual(opened.call_count, 2)

    def test_malformed_json_fails_closed_without_retry(self) -> None:
        with patch("command_center_service_control.urlopen", return_value=_Response(raw=b'{"ok":')) as opened:
            result = self.adapter._trade_manager_safety_read()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "malformed_response")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(opened.call_count, 1)

    def test_malformed_safety_schema_fails_closed(self) -> None:
        result = self._start_safety_with_payload({"ok": True, "trades": {}, "orphan_exposure": {}})
        self.assertFalse(result["safe"])
        self.assertEqual(result["reason"], "running_trade_manager_state_unavailable")
        self.assertEqual(result["safety_read_reason"], "trade_manager_safety_schema_invalid")

    def test_slow_zero_exposure_response_authorizes_start_gate(self) -> None:
        result = self._start_safety_with_payload(SAFE_PAYLOAD)
        self.assertTrue(result["safe"], result)
        self.assertEqual(result["pending_executable_actions"], 0)
        self.assertFalse(result["orphan_exposure"])

    def test_pending_action_blocks_start_gate(self) -> None:
        payload = {
            **SAFE_PAYLOAD,
            "trades": {"T-1": {"trade_id": "T-1", "status": "pending"}},
        }
        result = self._start_safety_with_payload(payload)
        self.assertFalse(result["safe"])
        self.assertEqual(result["pending_executable_actions"], 1)

    def test_orphan_exposure_blocks_start_gate(self) -> None:
        payload = {
            **SAFE_PAYLOAD,
            "orphan_exposure": {
                "has_orphans": True,
                "has_manager_state_issue": False,
            },
        }
        result = self._start_safety_with_payload(payload)
        self.assertFalse(result["safe"])
        self.assertTrue(result["orphan_exposure"])

    def test_one_timeout_only_retry_can_recover(self) -> None:
        responses = [TimeoutError("jitter"), _Response()]
        with patch("command_center_service_control.urlopen", side_effect=responses) as opened:
            result = self.adapter._trade_manager_safety_read()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(opened.call_count, 2)

    def test_success_arriving_after_total_budget_is_rejected(self) -> None:
        clock = _Clock()

        def late(_request: object, *, timeout: float) -> _Response:
            clock.value += self.adapter.safety_read_total_budget + 0.001
            return _Response()

        with patch("command_center_service_control.time.monotonic", side_effect=clock.monotonic), patch(
            "command_center_service_control.urlopen", side_effect=late
        ):
            result = self.adapter._trade_manager_safety_read()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "total_budget_exhausted")

    def test_shutdown_uses_shared_budget_and_fails_closed_when_unavailable(self) -> None:
        self.adapter._safety_json_get_result = lambda _url, deadline=None: {
            "ok": False,
            "payload": {},
            "status": None,
            "reason": "transport_timeout",
            "attempts": 2,
            "elapsed_ms": 8000,
        }
        result = self.adapter.trading_safety()
        self.assertFalse(result["safe"])
        self.assertEqual(result["reason"], "trading_state_unavailable")
        self.assertEqual(result["safety_read_reason"], "transport_timeout")

    def test_timeout_state_is_unavailable_not_foreign_identity(self) -> None:
        self.adapter._prestart_executor_exposure = lambda _snapshot: {"ok": True, "safe": True}
        self.adapter._safety_json_get_result = lambda _url, deadline=None: {
            "ok": False,
            "payload": {},
            "status": None,
            "reason": "transport_timeout",
            "attempts": 2,
            "elapsed_ms": 8000,
        }
        result = self.adapter.start_safety(self._running_trade_manager_snapshot())
        self.assertEqual(result["reason"], "running_trade_manager_state_unavailable")
        self.assertNotIn("foreign", json.dumps(result).lower())


if __name__ == "__main__":
    unittest.main()
