import contextlib
import importlib.util
import io
import json
import logging
import secrets
import sys
import threading
from pathlib import Path

import requests
from werkzeug.serving import make_server


ROOT = Path(__file__).resolve().parent


def load_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"ok": True, "delivery_disposition": "ACCEPTED"}


def run_server(app, handler, calls):
    stream = io.StringIO()
    stdout = io.StringIO()
    stderr = io.StringIO()
    log_handler = logging.StreamHandler(stream)
    logger = logging.getLogger("werkzeug")
    old_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(log_handler)
    app_logger = app.logger
    app_old_level = app_logger.level
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(log_handler)
    server = make_server("127.0.0.1", 0, app, request_handler=handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        thread.start()
        try:
            results = [call(server.server_port) for call in calls]
        finally:
            server.shutdown()
            thread.join(timeout=5)
    logger.removeHandler(log_handler)
    logger.setLevel(old_level)
    app_logger.removeHandler(log_handler)
    app_logger.setLevel(app_old_level)
    return results, stream.getvalue() + stdout.getvalue() + stderr.getvalue()


def test_access_redactor_covers_werkzeug_path_requestline_and_all_query_values():
    manager = load_path("oa_r2c_redactor", ROOT / "Engines" / "trade_manager.py")
    value = "POST /webhook/tv-context?token=secret-one&probe=secret-two&empty= HTTP/1.1"
    redacted = manager._redact_tv_access_requestline(value)
    assert "secret-one" not in redacted
    assert "secret-two" not in redacted
    assert "token=<REDACTED>" in redacted
    assert "probe=<REDACTED>" in redacted
    assert "empty=<REDACTED>" in redacted


def test_valid_invalid_missing_and_malformed_public_credentials_never_reach_logs_or_spool(monkeypatch, tmp_path):
    public = "R2C_SENTINEL_PUBLIC_" + secrets.token_hex(16)
    wrong = "R2C_SENTINEL_WRONG_" + secrets.token_hex(16)
    malformed = "R2C_SENTINEL_MALFORMED_" + secrets.token_hex(16)
    internal = "R2C_SENTINEL_INTERNAL_" + secrets.token_hex(16)
    spool = tmp_path / "spool"
    monkeypatch.setenv("TV_WEBHOOK_INGRESS_TOKEN", public)
    monkeypatch.setenv("TV_CONTEXT_INTERNAL_RELAY_TOKEN", internal)
    monkeypatch.setenv("TV_CONTEXT_SPOOL_DIR", str(spool))
    manager = load_path("oa_r2c_public_logs", ROOT / "Engines" / "trade_manager.py")
    http_post = requests.post
    monkeypatch.setattr(manager.requests, "post", lambda *_args, **_kwargs: FakeResponse())
    payload = json.loads((ROOT / "tests" / "fixtures" / "tradingview" / "v14_canonical_liquidity_sender_ym_stacked_yh.json").read_text(encoding="utf-8"))

    def post(token):
        def invoke(port):
            params = {} if token is None else {"token": token}
            return http_post(f"http://127.0.0.1:{port}/webhook/tv-context", params=params, json=payload, timeout=5)
        return invoke

    responses, logs = run_server(
        manager.app,
        manager.RedactedCredentialRequestHandler,
        [post(public), post(wrong), post(None), post(malformed)],
    )
    assert [response.status_code for response in responses] == [200, 401, 401, 401]
    for secret in (public, wrong, malformed, internal):
        assert secret not in logs
    assert "/webhook/tv-context?token=<REDACTED>" in logs
    assert "PUBLIC_INGRESS_AUTH_REJECTED reason=invalid" in logs
    assert "PUBLIC_INGRESS_AUTH_REJECTED reason=missing" in logs
    artifacts = b"".join(path.read_bytes() for path in spool.rglob("*") if path.is_file())
    for secret in (public, wrong, malformed, internal):
        assert secret.encode() not in artifacts


def test_authenticated_exception_path_redacts_public_credential(monkeypatch, tmp_path):
    public = "R2C_SENTINEL_EXCEPTION_" + secrets.token_hex(16)
    monkeypatch.setenv("TV_WEBHOOK_INGRESS_TOKEN", public)
    monkeypatch.setenv("TV_CONTEXT_INTERNAL_RELAY_TOKEN", "R2C_INTERNAL_EXCEPTION_" + secrets.token_hex(16))
    monkeypatch.setenv("TV_CONTEXT_SPOOL_DIR", str(tmp_path / "spool"))
    manager = load_path("oa_r2c_exception_logs", ROOT / "Engines" / "trade_manager.py")
    monkeypatch.setattr(manager, "_validate_tv_context_envelope", lambda _payload: (_ for _ in ()).throw(RuntimeError("forced isolated exception")))

    def invoke(port):
        return requests.post(
            f"http://127.0.0.1:{port}/webhook/tv-context",
            params={"token": public}, json={}, timeout=5,
        )

    responses, logs = run_server(manager.app, manager.RedactedCredentialRequestHandler, [invoke])
    assert responses[0].status_code == 500
    assert public not in logs
    assert "/webhook/tv-context?token=<REDACTED>" in logs
    assert "forced isolated exception" in logs


def test_internal_relay_header_never_reaches_entry_logs(monkeypatch, tmp_path):
    internal = "R2C_SENTINEL_INTERNAL_" + secrets.token_hex(16)
    wrong = "R2C_SENTINEL_INTERNAL_WRONG_" + secrets.token_hex(16)
    monkeypatch.setenv("TV_CONTEXT_INTERNAL_RELAY_TOKEN", internal)
    monkeypatch.setenv("TV_CONTEXT_ACCEPTANCE_LEDGER_PATH", str(tmp_path / "ledger.json"))
    sys.path.insert(0, str(ROOT / "EntryAgent"))
    receiver = load_path("oa_r2c_internal_logs", ROOT / "EntryAgent" / "tv_context_server.py")

    def post_with(token):
        def invoke(port):
            return requests.post(
                f"http://127.0.0.1:{port}/webhook/tv-context",
                headers={"X-Randle-Relay-Token": token}, json={}, timeout=5,
            )
        return invoke

    responses, logs = run_server(receiver.app, None, [post_with(wrong), post_with(internal)])
    assert responses[0].status_code == 401
    assert responses[1].status_code != 401
    assert internal not in logs
    assert wrong not in logs
    persisted = b"".join(path.read_bytes() for path in tmp_path.rglob("*") if path.is_file())
    assert internal.encode() not in persisted
    assert wrong.encode() not in persisted


def test_startup_helper_and_ngrok_launch_are_secret_safe():
    helper = load_path("oa_r2c_startup_helper", ROOT / "startup_public_health_check.py")
    secret = "R2C_SENTINEL_STARTUP_" + secrets.token_hex(16)
    detail = helper.redacted_exception_detail(RuntimeError(f"request failed token={secret}"), secret)
    assert secret not in detail
    assert "<redacted>" in detail
    launch = (ROOT / "launch_all.ps1").read_text(encoding="utf-8")
    assert '"--inspect=false"' in launch
    assert "TV_WEBHOOK_INGRESS_TOKEN" in launch
    assert "?token=$" not in launch
