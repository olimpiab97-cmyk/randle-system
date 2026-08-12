"""Local, fail-closed service controls for the Command Center.

The Command Center delegates startup to the canonical ``launch_all.ps1``
orchestrator.  This module owns only the local control state machine, trading
safety gate, readiness projection, and the previously absent deterministic
shutdown operation.  No request parameter is ever used as a command, path, or
process selector.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, time as clock_time
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


CONFIRMATION_WINDOW_SECONDS = 5.0
CONTROL_AUTHORITY_RELATIVE_PATH = Path("Architecture") / "Command_Center" / "command_center_governed_service_manifest.json"
CONTROL_VERSION_PATTERN = re.compile(r"\Acommand_center_service_controls_r[1-9][0-9]*[a-z]?\Z")
CONTROL_GENERATION_SOURCE_PATHS = {
    "command_center_service_control.py",
    "command_center_host.py",
    "open_command_center.cmd",
    "open_command_center.ps1",
}
LOCAL_ZONE = ZoneInfo("America/Los_Angeles")
PUBLIC_TOKEN_FINGERPRINT = "eb6fb495e6c1644c24707876f2c25b50c1feb08feeb204af2d35e28dba9be47e"
INTERNAL_TOKEN_FINGERPRINT = "12b562560e2c28a6f0b305297d239673bec50c82a6beecabdb20273cd0e79967"
TERMINAL_ORDER_STATES = {"filled", "cancelled", "canceled", "closed", "rejected", "error", "expired"}
TERMINAL_TRADE_STATES = {"closed", "archived", "rejected", "error", "cancelled", "canceled"}


def _read_control_authority(repository_root: Path) -> dict[str, Any]:
    """Load and validate the portable Command Center generation authority."""

    root = repository_root.resolve()
    path = root / CONTROL_AUTHORITY_RELATIVE_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("control_version_authority_unresolved") from exc
    if not isinstance(payload, dict):
        raise ValueError("control_version_authority_invalid")
    if payload.get("schema_version") not in {
        "command_center_governed_service_manifest_v1",
        "command_center_governed_service_manifest_v2",
    }:
        raise ValueError("unsupported service manifest")

    version = payload.get("control_version")
    if not isinstance(version, str) or not CONTROL_VERSION_PATTERN.fullmatch(version):
        raise ValueError("control_version_authority_invalid")

    generation = payload.get("control_generation")
    source_hashes = generation.get("source_sha256") if isinstance(generation, dict) else None
    if not isinstance(source_hashes, dict) or set(source_hashes) != CONTROL_GENERATION_SOURCE_PATHS:
        raise ValueError("control_generation_authority_invalid")
    for relative_path, expected in source_hashes.items():
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("control_generation_hash_invalid")
        source_path = (root / relative_path).resolve()
        try:
            source_path.relative_to(root)
        except ValueError as exc:
            raise ValueError("control_generation_path_invalid") from exc
        try:
            actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ValueError("control_generation_source_unavailable") from exc
        if actual != expected:
            raise ValueError("control_generation_source_mismatch")

    deployment = payload.get("runtime_deployment")
    required_paths = deployment.get("required_paths") if isinstance(deployment, dict) else None
    rollback_paths = deployment.get("rollback_required_paths") if isinstance(deployment, dict) else None
    if not isinstance(required_paths, list) or not isinstance(rollback_paths, list):
        raise ValueError("control_runtime_deployment_authority_invalid")
    normalized_required = {str(item).replace("\\", "/") for item in required_paths}
    normalized_rollback = {str(item).replace("\\", "/") for item in rollback_paths}
    authority_path = str(CONTROL_AUTHORITY_RELATIVE_PATH).replace("\\", "/")
    if normalized_required != normalized_rollback or authority_path not in normalized_required:
        raise ValueError("control_runtime_deployment_authority_invalid")
    if not CONTROL_GENERATION_SOURCE_PATHS.issubset(normalized_required):
        raise ValueError("control_runtime_deployment_authority_incomplete")
    return payload


def load_control_version(repository_root: Path | None = None) -> str:
    root = (repository_root or Path(__file__).resolve().parent).resolve()
    return str(_read_control_authority(root)["control_version"])


CONTROL_VERSION = load_control_version()


class ControlState(str, Enum):
    OFFLINE = "OFFLINE"
    START_CONFIRM_REQUIRED = "START_CONFIRM_REQUIRED"
    STARTING = "STARTING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    SHUTDOWN_CONFIRM_REQUIRED = "SHUTDOWN_CONFIRM_REQUIRED"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    SHUTDOWN_BLOCKED = "SHUTDOWN_BLOCKED"
    ERROR = "ERROR"


class ServiceClassification(str, Enum):
    RUNNING_READY = "RUNNING_READY"
    RUNNING_NOT_READY = "RUNNING_NOT_READY"
    STOPPED = "STOPPED"
    DUPLICATE = "DUPLICATE"
    FOREIGN_PROCESS = "FOREIGN_PROCESS"
    UNKNOWN = "UNKNOWN"


class ServiceIdentity(str, Enum):
    TRUSTED = "TRUSTED"
    FOREIGN = "FOREIGN"
    UNKNOWN = "UNKNOWN"


class ServiceReadiness(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    STOPPED = "STOPPED"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    display_name: str
    process_name: str
    command_marker: str
    launch_path: str | None
    port: int | None
    readiness: dict[str, Any]
    start_order: int
    shutdown_order: int
    dependencies: tuple[str, ...]
    execution_identities: tuple[dict[str, Any], ...]
    write_authority_required: bool


def _utc_now() -> str:
    return datetime.now().astimezone().astimezone(ZoneInfo("UTC")).isoformat()


def load_service_manifest(repository_root: Path) -> dict[str, Any]:
    return _read_control_authority(repository_root)


def service_specs(manifest: dict[str, Any]) -> list[ServiceSpec]:
    return [
        ServiceSpec(
            name=str(row["name"]),
            display_name=str(row["display_name"]),
            process_name=str(row["process_name"]),
            command_marker=str(row["command_marker"]),
            launch_path=row.get("launch_path"),
            port=int(row["port"]) if row.get("port") is not None else None,
            readiness=dict(row.get("readiness") or {}),
            start_order=int(row["start_order"]),
            shutdown_order=int(row["shutdown_order"]),
            dependencies=tuple(row.get("dependencies") or ()),
            execution_identities=tuple(row.get("execution_identities") or ({
                "name": "legacy_direct",
                "type": "GOVERNED_DIRECT",
                "source_path": row.get("launch_path"),
                "command_marker": row.get("command_marker"),
                "authority": "GOVERNED_PRODUCTION",
            },)),
            write_authority_required=bool(row.get("write_authority_required", False)),
        )
        for row in manifest["services"]
    ]


class ServiceAdapter(Protocol):
    def snapshot(self) -> dict[str, Any]: ...
    def write_authority(self) -> dict[str, Any]: ...
    def start_stack(self) -> dict[str, Any]: ...
    def trading_safety(self) -> dict[str, Any]: ...
    def shutdown_stack(self) -> dict[str, Any]: ...
    def ladder_status(self) -> dict[str, Any]: ...


class ProductionServiceAdapter:
    """Windows adapter restricted to the source-derived governed manifest."""

    def __init__(self, repository_root: Path, *, timeout: float = 2.0) -> None:
        self.repository_root = repository_root.resolve()
        self.manifest = load_service_manifest(self.repository_root)
        self.services = service_specs(self.manifest)
        safety_read = self.manifest.get("safety_read") or {}
        self.safety_read_endpoint = str(safety_read.get("trade_manager_endpoint") or "")
        self.safety_read_attempt_timeout = float(safety_read.get("attempt_timeout_seconds") or 0)
        self.safety_read_max_attempts = int(safety_read.get("max_attempts") or 0)
        self.safety_read_total_budget = float(safety_read.get("total_budget_seconds") or 0)
        retry_on = tuple(safety_read.get("retry_on") or ())
        endpoint = urlsplit(self.safety_read_endpoint)
        if (
            endpoint.scheme != "http"
            or endpoint.hostname != "127.0.0.1"
            or endpoint.port != 7001
            or endpoint.path != "/trades"
            or endpoint.query
            or endpoint.fragment
            or self.safety_read_attempt_timeout <= 0
            or self.safety_read_max_attempts not in {1, 2}
            or self.safety_read_total_budget < self.safety_read_attempt_timeout
            or retry_on != ("transport_timeout",)
        ):
            raise ValueError("invalid safety-read authority")
        self.timeout = timeout
        self.launcher = (self.repository_root / str(self.manifest["canonical_launcher"])).resolve()
        if self.launcher.parent != self.repository_root or self.launcher.name != "launch_all.ps1":
            raise ValueError("canonical launcher path escaped repository authority")
        self._last_launcher: dict[str, Any] | None = None

    @staticmethod
    def _powershell() -> str:
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        path = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        return str(path)

    def _run_fixed_powershell(self, script: str, *, timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self._powershell(), "-NoProfile", "-NonInteractive", "-Command", script],
            cwd=str(self.repository_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )

    def _process_inventory(self) -> list[dict[str, Any]]:
        script = (
            "$ErrorActionPreference='Stop'; "
            "@(Get-CimInstance Win32_Process -OperationTimeoutSec 4 | "
            "Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine) | "
            "ConvertTo-Json -Compress -Depth 4"
        )
        result = self._run_fixed_powershell(script)
        if result.returncode != 0:
            raise RuntimeError("process_inventory_unavailable")
        raw = result.stdout.strip()
        if not raw:
            return []
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else [parsed]

    def _port_owners(self) -> dict[int, list[int]]:
        ports = sorted(spec.port for spec in self.services if spec.port is not None)
        port_literal = ",".join(str(port) for port in ports)
        script = (
            f"$ports=@({port_literal}); "
            "@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | "
            "Where-Object { $ports -contains $_.LocalPort } | "
            "Select-Object LocalPort,OwningProcess) | ConvertTo-Json -Compress"
        )
        result = self._run_fixed_powershell(script)
        if result.returncode != 0:
            raise RuntimeError("listener_inventory_unavailable")
        owners: dict[int, list[int]] = {port: [] for port in ports}
        raw = result.stdout.strip()
        if raw:
            parsed = json.loads(raw)
            rows = parsed if isinstance(parsed, list) else [parsed]
            for row in rows:
                owners.setdefault(int(row["LocalPort"]), []).append(int(row["OwningProcess"]))
        return owners

    def _json_get_result(self, url: str, *, timeout: float | None = None) -> tuple[int | None, dict[str, Any]]:
        request = Request(url, headers={"Accept": "application/json"}, method="GET")
        try:
            with urlopen(request, timeout=self.timeout if timeout is None else timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                status = int(getattr(response, "status", 200))
            return status, payload if isinstance(payload, dict) else {}
        except HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                payload = {}
            return int(exc.code), payload if isinstance(payload, dict) else {}
        except (OSError, URLError, TimeoutError, json.JSONDecodeError):
            return None, {}

    def _json_get(self, url: str) -> dict[str, Any]:
        status, payload = self._json_get_result(url)
        return payload if status is not None and 200 <= status < 300 else {}

    @staticmethod
    def _is_transport_timeout(exc: BaseException) -> bool:
        reason = exc.reason if isinstance(exc, URLError) else exc
        return isinstance(reason, (TimeoutError, socket.timeout))

    def _safety_deadline(self) -> float:
        return time.monotonic() + self.safety_read_total_budget

    def _safety_json_get_result(self, url: str, *, deadline: float | None = None) -> dict[str, Any]:
        """Read one trusted local safety endpoint under the bounded R1C policy.

        Only a transport timeout is retryable.  Connection failures, HTTP
        errors, malformed JSON, non-object responses, and responses arriving
        after the total budget all fail closed without optimistic fallback.
        A caller may share one deadline across several endpoint reads so an
        entire safety gate remains bounded by the same authority.
        """
        started = time.monotonic()
        deadline = started + self.safety_read_total_budget if deadline is None else deadline
        attempts = 0
        last_reason = "total_budget_exhausted"
        while attempts < self.safety_read_max_attempts:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            attempts += 1
            request = Request(url, headers={"Accept": "application/json"}, method="GET")
            try:
                with urlopen(request, timeout=min(self.safety_read_attempt_timeout, remaining)) as response:
                    raw = response.read()
                    status = int(getattr(response, "status", 200))
                payload = json.loads(raw.decode("utf-8"))
                if time.monotonic() > deadline:
                    last_reason = "total_budget_exhausted"
                    break
                if not 200 <= status < 300:
                    return {
                        "ok": False,
                        "payload": {},
                        "status": status,
                        "reason": "http_status_unavailable",
                        "attempts": attempts,
                        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                    }
                if not isinstance(payload, dict):
                    return {
                        "ok": False,
                        "payload": {},
                        "status": status,
                        "reason": "malformed_response",
                        "attempts": attempts,
                        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                    }
                return {
                    "ok": True,
                    "payload": payload,
                    "status": status,
                    "reason": "live_response",
                    "attempts": attempts,
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                }
            except HTTPError as exc:
                return {
                    "ok": False,
                    "payload": {},
                    "status": int(exc.code),
                    "reason": "http_status_unavailable",
                    "attempts": attempts,
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                }
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {
                    "ok": False,
                    "payload": {},
                    "status": 200,
                    "reason": "malformed_response",
                    "attempts": attempts,
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                }
            except (URLError, OSError, TimeoutError) as exc:
                if not self._is_transport_timeout(exc):
                    return {
                        "ok": False,
                        "payload": {},
                        "status": None,
                        "reason": "transport_unavailable",
                        "attempts": attempts,
                        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                    }
                last_reason = "transport_timeout"
                if attempts >= self.safety_read_max_attempts or time.monotonic() >= deadline:
                    break
        elapsed_ms = round((time.monotonic() - started) * 1000, 3)
        if time.monotonic() >= deadline:
            last_reason = "total_budget_exhausted"
        return {
            "ok": False,
            "payload": {},
            "status": None,
            "reason": last_reason,
            "attempts": attempts,
            "elapsed_ms": elapsed_ms,
        }

    @staticmethod
    def _validate_trade_manager_safety_payload(payload: dict[str, Any]) -> tuple[bool, str]:
        trades = payload.get("trades")
        orphan = payload.get("orphan_exposure")
        if payload.get("ok") is not True or not isinstance(trades, dict) or not isinstance(orphan, dict):
            return False, "trade_manager_safety_schema_invalid"
        if not isinstance(orphan.get("has_orphans"), bool) or not isinstance(orphan.get("has_manager_state_issue"), bool):
            return False, "trade_manager_safety_schema_invalid"
        if any(not isinstance(row, dict) or not isinstance(row.get("status"), str) for row in trades.values()):
            return False, "trade_manager_safety_schema_invalid"
        return True, "trade_manager_safety_schema_pass"

    def _trade_manager_safety_read(self, *, deadline: float | None = None) -> dict[str, Any]:
        result = self._safety_json_get_result(self.safety_read_endpoint, deadline=deadline)
        if not result.get("ok"):
            return result
        valid, reason = self._validate_trade_manager_safety_payload(result["payload"])
        if not valid:
            return {**result, "ok": False, "payload": {}, "reason": reason}
        return {**result, "authority": "trusted_live_loopback_trade_manager"}

    def _readiness_ok(self, spec: ServiceSpec) -> tuple[bool, str]:
        kind = spec.readiness.get("kind")
        if kind == "http_json":
            status, payload = self._json_get_result(str(spec.readiness["url"]), timeout=float(spec.readiness.get("timeout_seconds", self.timeout)))
            if not payload:
                return False, "readiness_http_unavailable"
            if status is None or not 200 <= status < 300:
                failures = payload.get("rehydration_failures") or []
                dependency_reason = next(
                    (str(row.get("reason")) for row in failures if isinstance(row, dict) and row.get("reason")),
                    str(payload.get("service_status") or "http_not_ready").lower(),
                )
                return False, f"readiness_http_{status or 'unavailable'}:{dependency_reason}"
            expected = spec.readiness.get("expected") or {}
            for key, value in expected.items():
                if payload.get(key) != value:
                    return False, f"readiness_field_mismatch:{key}"
            source_path_field = spec.readiness.get("source_path_field")
            if source_path_field and spec.launch_path:
                reported_path = payload.get(str(source_path_field))
                try:
                    source_matches = Path(str(reported_path or "")).resolve() == (self.repository_root / spec.launch_path).resolve()
                except OSError:
                    source_matches = False
                if not source_matches:
                    return False, "readiness_source_path_mismatch"
            return True, "readiness_http_pass"
        if kind == "ngrok_tunnel":
            payload = self._json_get("http://127.0.0.1:4040/api/tunnels")
            expected_target = str(spec.readiness["forward_to"])
            expected_host = str(spec.readiness["public_host"])
            matches = [
                tunnel for tunnel in payload.get("tunnels", [])
                if expected_host in str(tunnel.get("public_url") or "")
                and expected_target in str((tunnel.get("config") or {}).get("addr") or "")
            ]
            return (len(matches) == 1, "reserved_tunnel_pass" if len(matches) == 1 else "reserved_tunnel_mismatch")
        if kind == "feed_health_file":
            root = Path(os.getenv("RANDLE_DATA_ROOT") or (self.repository_root / "Data"))
            path = root / str(spec.readiness["relative_path"])
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                age = time.time() - path.stat().st_mtime
                symbols = payload.get("symbols") or {}
                ok = age <= float(spec.readiness.get("max_age_seconds", 15)) and all(symbol in symbols for symbol in ("NQ", "YM"))
                return ok, "feed_health_current" if ok else "feed_health_stale_or_incomplete"
            except (OSError, json.JSONDecodeError):
                return False, "feed_health_unavailable"
        return False, "readiness_kind_unknown"

    @staticmethod
    def _script_paths(command_line: str) -> list[Path]:
        matches = re.findall(r'"([^"]+\.py)"|([A-Za-z]:[^\s"]+\.py)|(\S+\.py)', command_line, re.IGNORECASE)
        return [Path(next(value for value in group if value)).resolve() for group in matches]

    @staticmethod
    def _file_sha256(path: Path) -> str | None:
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        except OSError:
            return None

    def _identity_match(self, spec: ServiceSpec, process: dict[str, Any], identity: dict[str, Any]) -> bool:
        command_line = str(process.get("CommandLine") or "")
        marker = str(identity.get("command_marker") or "")
        if marker and not re.search(marker, command_line, re.IGNORECASE):
            return False
        if not re.fullmatch(re.escape(spec.process_name) + r"(?:\.exe)?", str(process.get("Name") or ""), re.IGNORECASE):
            return False

        identity_type = str(identity.get("type") or "")
        if identity_type == "GOVERNED_DIRECT":
            source = identity.get("source_path")
            if source:
                expected = (self.repository_root / str(source)).resolve()
                return expected in self._script_paths(command_line)
            return True

        if identity_type != "GOVERNED_WRAPPED":
            return False
        script_paths = self._script_paths(command_line)
        wrapper_path = identity.get("wrapper_path")
        if wrapper_path:
            wrapper = (self.repository_root / str(wrapper_path)).resolve()
            if wrapper not in script_paths:
                return False
        else:
            filename = str(identity.get("wrapper_filename") or "").casefold()
            wrappers = [path for path in script_paths if path.name.casefold() == filename]
            if len(wrappers) != 1:
                return False
            wrapper = wrappers[0]
        if self._file_sha256(wrapper) != str(identity.get("wrapper_sha256") or "").lower():
            return False
        service_source = identity.get("service_source_path")
        if service_source:
            source_path = (self.repository_root / str(service_source)).resolve()
            expected_source_sha = identity.get("service_source_sha256")
            if not source_path.is_file() or (expected_source_sha and self._file_sha256(source_path) != str(expected_source_sha).lower()):
                return False
        return True

    def snapshot(self) -> dict[str, Any]:
        try:
            inventory = self._process_inventory()
            port_owners = self._port_owners()
        except (OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            return {
                "captured_at": _utc_now(),
                "services": [
                    {"name": spec.name, "display_name": spec.display_name, "identity": ServiceIdentity.UNKNOWN.value, "readiness": ServiceReadiness.DEGRADED.value, "classification": ServiceClassification.UNKNOWN.value, "reason": type(exc).__name__, "pids": []}
                    for spec in self.services
                ],
            }

        rows = []
        for spec in sorted(self.services, key=lambda item: item.start_order):
            process_rows = [row for row in inventory if re.fullmatch(re.escape(spec.process_name) + r"(?:\.exe)?", str(row.get("Name") or ""), re.IGNORECASE)]
            candidate_rows = [row for row in process_rows if re.search(spec.command_marker, str(row.get("CommandLine") or ""), re.IGNORECASE)]
            trusted: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for row in candidate_rows:
                for identity in spec.execution_identities:
                    if self._identity_match(spec, row, identity):
                        trusted.append((row, identity))
                        break
            pids = [int(row["ProcessId"]) for row, _ in trusted]
            reason = ""
            execution_identity = None
            identity_authority = None
            if len(pids) > 1 or (pids and len(candidate_rows) > len(trusted)):
                classification = ServiceClassification.DUPLICATE
                identity_state = ServiceIdentity.UNKNOWN
                readiness_state = ServiceReadiness.DEGRADED
                reason = "multiple_or_mixed_execution_identities"
            elif len(pids) == 0:
                foreign = bool(candidate_rows or (spec.port is not None and port_owners.get(spec.port)))
                classification = ServiceClassification.FOREIGN_PROCESS if foreign else ServiceClassification.STOPPED
                identity_state = ServiceIdentity.FOREIGN if foreign else ServiceIdentity.TRUSTED
                readiness_state = ServiceReadiness.DEGRADED if foreign else ServiceReadiness.STOPPED
                reason = "configured_identity_mismatch" if candidate_rows else "expected_process_absent_port_owned" if foreign else "expected_process_absent"
            else:
                execution_identity = str(trusted[0][1].get("type") or "")
                identity_authority = str(trusted[0][1].get("authority") or "")
                if spec.port is not None and set(port_owners.get(spec.port) or []) != set(pids):
                    classification = ServiceClassification.FOREIGN_PROCESS
                    identity_state = ServiceIdentity.FOREIGN
                    readiness_state = ServiceReadiness.DEGRADED
                    reason = "listener_owner_does_not_match_process"
                else:
                    ready, reason = self._readiness_ok(spec)
                    classification = ServiceClassification.RUNNING_READY if ready else ServiceClassification.RUNNING_NOT_READY
                    identity_state = ServiceIdentity.TRUSTED
                    readiness_state = ServiceReadiness.READY if ready else ServiceReadiness.NOT_READY
            rows.append({
                "name": spec.name,
                "display_name": spec.display_name,
                "identity": identity_state.value,
                "readiness": readiness_state.value,
                "execution_identity": execution_identity,
                "identity_authority": identity_authority,
                "classification": classification.value,
                "reason": reason,
                "pids": pids,
                "port": spec.port,
                "start_order": spec.start_order,
                "shutdown_order": spec.shutdown_order,
                "source_sha256": (
                    hashlib.sha256((self.repository_root / spec.launch_path).read_bytes()).hexdigest()
                    if spec.launch_path and (self.repository_root / spec.launch_path).is_file()
                    else None
                ),
            })
        return {"captured_at": _utc_now(), "services": rows}

    def _critical_write_roots(self) -> dict[str, Path]:
        data_root = Path(os.getenv("RANDLE_DATA_ROOT") or (self.repository_root / "Data")).resolve()
        spool = Path(os.getenv("TV_CONTEXT_SPOOL_DIR") or (self.repository_root / "Data" / "tv_context_spool")).resolve()
        entry = (data_root / "entry_agent").resolve() if os.getenv("RANDLE_DATA_ROOT") else (self.repository_root / "EntryAgent").resolve()
        return {"runtime_data": data_root, "trade_manager_spool": spool, "entry_agent_persistence": entry}

    def credential_authority(self) -> dict[str, Any]:
        public = os.getenv("TV_WEBHOOK_INGRESS_TOKEN", "")
        internal = os.getenv("TV_CONTEXT_INTERNAL_RELAY_TOKEN", "")
        public_fingerprint = hashlib.sha256(public.encode("utf-8")).hexdigest() if public else None
        internal_fingerprint = hashlib.sha256(internal.encode("utf-8")).hexdigest() if internal else None
        public_format = bool(re.fullmatch(r"[0-9a-f]{64}", public))
        internal_format = bool(re.fullmatch(r"[0-9a-f]{64}", internal))
        ok = (
            public_format
            and internal_format
            and public != internal
            and public_fingerprint == PUBLIC_TOKEN_FINGERPRINT
            and internal_fingerprint == INTERNAL_TOKEN_FINGERPRINT
        )
        return {
            "ok": ok,
            "public_present": bool(public),
            "internal_present": bool(internal),
            "public_format": public_format,
            "internal_format": internal_format,
            "distinct": bool(public and internal and public != internal),
            "public_fingerprint": public_fingerprint,
            "internal_fingerprint": internal_fingerprint,
        }

    def write_authority(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, root in self._critical_write_roots().items():
            probe = root / f".command-center-write-probe-{uuid.uuid4().hex}.tmp"
            try:
                root.mkdir(parents=True, exist_ok=True)
                probe.write_bytes(b"command-center-write-authority\n")
                readback = probe.read_bytes()
                if readback != b"command-center-write-authority\n":
                    raise OSError("write_probe_readback_mismatch")
                probe.unlink()
                results[name] = {"ok": True, "path_sha256": hashlib.sha256(str(root).encode("utf-8")).hexdigest()}
            except OSError as exc:
                try:
                    probe.unlink(missing_ok=True)
                except OSError:
                    pass
                results[name] = {"ok": False, "reason": type(exc).__name__, "path_sha256": hashlib.sha256(str(root).encode("utf-8")).hexdigest()}
        return {"ok": all(row["ok"] for row in results.values()), "roots": results}

    def protected_state_hashes(self) -> dict[str, str | None]:
        data_root = Path(os.getenv("RANDLE_DATA_ROOT") or (self.repository_root / "Data")).resolve()
        entry_root = (data_root / "entry_agent").resolve() if os.getenv("RANDLE_DATA_ROOT") else (self.repository_root / "EntryAgent").resolve()
        paths = {
            "trade_manager_persistence": data_root / "persistence_state.json",
            # executor.py derives this authority from its tracked source root,
            # independently of RANDLE_DATA_ROOT.
            "executor_state": self.repository_root / "Data" / "executor_state.json",
            "entry_agent_state": entry_root / "entry_agent_state.json",
            "entry_agent_context": entry_root / "tv_context_by_symbol.json",
            "entry_agent_ledger": entry_root / "tv_context_acceptance_ledger.json",
        }
        return {
            name: hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            for name, path in paths.items()
        }

    def _prestart_executor_exposure(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        executor = next((row for row in snapshot.get("services", []) if row.get("name") == "executor"), {})
        if executor.get("readiness") in {ServiceReadiness.READY.value, ServiceReadiness.NOT_READY.value}:
            orders_payload = self._json_get("http://127.0.0.1:6001/orders")
            positions_payload = self._json_get("http://127.0.0.1:6001/positions")
            if orders_payload.get("ok") is not True or positions_payload.get("ok") is not True:
                return {"ok": False, "safe": False, "reason": "running_executor_state_unavailable"}
            orders = orders_payload.get("orders")
            positions = positions_payload.get("positions")
            if not isinstance(orders, list) or not isinstance(positions, dict):
                return {"ok": False, "safe": False, "reason": "running_executor_state_invalid"}
            authority = "live_executor"
        else:
            state_path = self.repository_root / "Data" / "executor_state.json"
            if state_path.is_file():
                try:
                    persisted = json.loads(state_path.read_text(encoding="utf-8"))
                    order_store = persisted.get("orders")
                    positions = persisted.get("positions")
                    if not isinstance(order_store, dict) or not isinstance(positions, dict):
                        raise ValueError("executor_state_schema_invalid")
                    orders = list(order_store.values())
                except (OSError, ValueError, json.JSONDecodeError):
                    return {"ok": False, "safe": False, "reason": "persisted_executor_state_unavailable"}
                authority = "persisted_executor_state"
            else:
                # executor.load_executor_state() establishes an empty store when
                # this exact source-derived file is absent.
                orders = []
                positions = {}
                authority = "source_defined_empty_executor_state"

        active_orders = [
            row for row in orders
            if isinstance(row, dict)
            and str(row.get("status") or "active").lower() not in TERMINAL_ORDER_STATES
        ]
        nonzero_positions = [
            symbol for symbol, value in positions.items()
            if abs(self._quantity(value)) > 0
        ]
        safe = not active_orders and not nonzero_positions
        return {
            "ok": True,
            "safe": safe,
            "reason": "prestart_executor_exposure_clear" if safe else "prestart_executor_exposure_active",
            "active_orders": len(active_orders),
            "nonzero_positions": len(nonzero_positions),
            "authority": authority,
        }

    def start_safety(self, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        """Gate START without requiring a stopped Executor's unavailable APIs.

        A running Trade Manager must provide live pending/orphan authority.  If
        it is stopped, persisted state may gate whether it is safe to *start*;
        persisted state is never used to authorize SHUTDOWN.
        """
        policy = self.manifest.get("start_safety") or {}
        required = (
            policy.get("executor_may_start_without_live_exposure_api") is True
            and policy.get("require_zero_persisted_executor_exposure_when_stopped") is True
            and policy.get("require_executor_orders_positions_before_trade_manager_start") is True
            and policy.get("require_zero_persisted_pending_state_when_trade_manager_stopped") is True
            and policy.get("new_executable_action_before_readiness") is False
        )
        if not required:
            return {"ok": False, "safe": False, "reason": "start_safety_manifest_incomplete"}
        snapshot = snapshot or self.snapshot()
        executor_gate = self._prestart_executor_exposure(snapshot)
        if not executor_gate.get("safe"):
            return {
                "ok": executor_gate.get("ok") is True,
                "safe": False,
                "reason": executor_gate.get("reason"),
                "executor": executor_gate,
            }
        trade_manager = next((row for row in snapshot.get("services", []) if row.get("name") == "trade_manager"), {})
        if trade_manager.get("readiness") in {ServiceReadiness.READY.value, ServiceReadiness.NOT_READY.value}:
            safety_read = self._trade_manager_safety_read()
            if not safety_read.get("ok"):
                return {
                    "ok": False,
                    "safe": False,
                    "reason": "running_trade_manager_state_unavailable",
                    "safety_read_reason": safety_read.get("reason"),
                    "safety_read_attempts": safety_read.get("attempts"),
                    "safety_read_elapsed_ms": safety_read.get("elapsed_ms"),
                }
            live = safety_read["payload"]
            active = [row for row in live["trades"].values() if isinstance(row, dict) and str(row.get("status") or "active").lower() not in TERMINAL_TRADE_STATES]
            orphan = live.get("orphan_exposure") or {}
            blocked = bool(active or orphan.get("has_orphans") or orphan.get("has_manager_state_issue"))
            return {"ok": True, "safe": not blocked, "reason": "live_prestart_state_clear" if not blocked else "live_prestart_state_active", "pending_executable_actions": len(active), "orphan_exposure": bool(orphan.get("has_orphans") or orphan.get("has_manager_state_issue")), "authority": "live_trade_manager", "safety_read_attempts": safety_read.get("attempts"), "safety_read_elapsed_ms": safety_read.get("elapsed_ms"), "executor": executor_gate}

        data_root = Path(os.getenv("RANDLE_DATA_ROOT") or (self.repository_root / "Data")).resolve()
        path = data_root / "persistence_state.json"
        try:
            persisted = json.loads(path.read_text(encoding="utf-8"))
            trades = persisted.get("trades")
            if not isinstance(trades, dict):
                raise ValueError("trades_not_object")
            active = [row for row in trades.values() if isinstance(row, dict) and str(row.get("status") or "active").lower() not in TERMINAL_TRADE_STATES]
            orphan = persisted.get("orphan_exposure") or (persisted.get("system") or {}).get("orphan_exposure") or {}
            blocked = bool(active or (isinstance(orphan, dict) and (orphan.get("has_orphans") or orphan.get("has_manager_state_issue"))))
            return {"ok": True, "safe": not blocked, "reason": "persisted_prestart_state_clear" if not blocked else "persisted_prestart_state_active", "pending_executable_actions": len(active), "orphan_exposure": bool(blocked and not active), "authority": "persisted_start_gate_only", "executor": executor_gate}
        except (OSError, ValueError, json.JSONDecodeError):
            return {"ok": False, "safe": False, "reason": "persisted_prestart_state_unavailable"}

    def start_stack(self) -> dict[str, Any]:
        before = self.snapshot()
        classifications = {row["classification"] for row in before["services"]}
        unsafe = classifications.intersection({
            ServiceClassification.DUPLICATE.value,
            ServiceClassification.FOREIGN_PROCESS.value,
            ServiceClassification.UNKNOWN.value,
        })
        if unsafe:
            return {"ok": False, "message": "SYSTEM NOT READY", "reason": "unsafe_process_identity", "snapshot": before}
        start_safety = self.start_safety(before)
        if not start_safety.get("safe"):
            return {"ok": False, "message": "SYSTEM NOT READY", "reason": "start_safety_unavailable_or_active", "start_safety": start_safety, "snapshot": before}
        credential_authority = self.credential_authority()
        if not credential_authority["ok"]:
            return {"ok": False, "message": "SYSTEM NOT READY", "reason": "credential_authority_failed", "credential_authority": credential_authority, "snapshot": before}
        write_probe = self.write_authority()
        if not write_probe["ok"]:
            return {"ok": False, "message": "SYSTEM NOT READY", "reason": "production_write_authority_failed", "write_authority": write_probe, "snapshot": before}
        if classifications == {ServiceClassification.RUNNING_READY.value}:
            return {"ok": True, "already_ready": True, "message": "SYSTEM ALREADY READY", "credential_authority": credential_authority, "write_authority": write_probe, "start_safety": start_safety, "snapshot": before}
        # Never capture the canonical launcher's anonymous pipes.  The launcher
        # deliberately creates long-lived service children; on Windows those
        # children can inherit the pipe handles and keep ``subprocess.run``
        # waiting for EOF after PowerShell itself has exited.  Governed files
        # preserve the nonsecret diagnostics without coupling launcher
        # completion to descendant process lifetime.
        data_root = Path(os.getenv("RANDLE_DATA_ROOT") or (self.repository_root / "Data")).resolve()
        launcher_log_root = data_root / "startup"
        launcher_log_root.mkdir(parents=True, exist_ok=True)
        launcher_id = uuid.uuid4().hex
        launcher_stdout_path = launcher_log_root / f"command_center_launcher_{launcher_id}.stdout.log"
        launcher_stderr_path = launcher_log_root / f"command_center_launcher_{launcher_id}.stderr.log"
        with launcher_stdout_path.open("w", encoding="utf-8", newline="\n") as launcher_stdout, launcher_stderr_path.open(
            "w", encoding="utf-8", newline="\n"
        ) as launcher_stderr:
            completed = subprocess.run(
                [self._powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(self.launcher)],
                cwd=str(self.repository_root),
                stdout=launcher_stdout,
                stderr=launcher_stderr,
                text=True,
                timeout=1800,
                check=False,
                shell=False,
            )
        self._last_launcher = {
            "returncode": completed.returncode,
            "completed_at": _utc_now(),
            "stdout_path": str(launcher_stdout_path),
            "stderr_path": str(launcher_stderr_path),
        }
        after = self.snapshot()
        post_write_probe = self.write_authority()
        post_credential_authority = self.credential_authority()
        post_start_exposure = self.trading_safety()
        ready = (
            all(row["classification"] == ServiceClassification.RUNNING_READY.value for row in after["services"])
            and post_write_probe["ok"]
            and post_credential_authority["ok"]
            and post_start_exposure.get("ok") is True
        )
        return {
            "ok": ready,
            "already_ready": False,
            "message": "SYSTEM READY" if ready else "SYSTEM NOT READY",
            "reason": "canonical_launcher_completed" if ready else "canonical_launcher_or_readiness_failed",
            "launcher_returncode": completed.returncode,
            "write_authority": write_probe,
            "credential_authority": credential_authority,
            "start_safety": start_safety,
            "post_start_write_authority": post_write_probe,
            "post_start_credential_authority": post_credential_authority,
            "post_start_exposure": post_start_exposure,
            "snapshot": after,
        }

    @staticmethod
    def _quantity(value: Any) -> float:
        if isinstance(value, dict):
            value = value.get("qty", value.get("position_qty", value.get("quantity", 0)))
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def trading_safety(self) -> dict[str, Any]:
        deadline = self._safety_deadline()
        orders_read = self._safety_json_get_result("http://127.0.0.1:6001/orders", deadline=deadline)
        if not orders_read.get("ok"):
            return {"ok": False, "safe": False, "reason": "trading_state_unavailable", "safety_read_endpoint": "orders", "safety_read_reason": orders_read.get("reason"), "active_orders": None, "nonzero_positions": None, "pending_executable_actions": None, "orphan_exposure": None}
        positions_read = self._safety_json_get_result("http://127.0.0.1:6001/positions", deadline=deadline)
        if not positions_read.get("ok"):
            return {"ok": False, "safe": False, "reason": "trading_state_unavailable", "safety_read_endpoint": "positions", "safety_read_reason": positions_read.get("reason"), "active_orders": None, "nonzero_positions": None, "pending_executable_actions": None, "orphan_exposure": None}
        trades_read = self._trade_manager_safety_read(deadline=deadline)
        if not trades_read.get("ok"):
            reason = "trading_state_schema_invalid" if trades_read.get("reason") == "trade_manager_safety_schema_invalid" else "trading_state_unavailable"
            return {"ok": False, "safe": False, "reason": reason, "safety_read_endpoint": "trades", "safety_read_reason": trades_read.get("reason"), "active_orders": None, "nonzero_positions": None, "pending_executable_actions": None, "orphan_exposure": None}
        orders = orders_read["payload"]
        positions = positions_read["payload"]
        trades = trades_read["payload"]
        if not all(payload.get("ok") is True for payload in (orders, positions, trades)):
            return {"ok": False, "safe": False, "reason": "trading_state_unavailable", "active_orders": None, "nonzero_positions": None, "pending_executable_actions": None, "orphan_exposure": None}
        raw_orders = orders.get("orders")
        raw_positions = positions.get("positions")
        raw_trades = trades.get("trades")
        if not isinstance(raw_orders, list) or not isinstance(raw_positions, dict) or not isinstance(raw_trades, dict):
            return {"ok": False, "safe": False, "reason": "trading_state_schema_invalid", "active_orders": None, "nonzero_positions": None, "pending_executable_actions": None, "orphan_exposure": None}
        active_orders = [row for row in raw_orders if isinstance(row, dict) and str(row.get("status") or "active").lower() not in TERMINAL_ORDER_STATES]
        position_rows = raw_positions.items()
        nonzero_positions = [{"symbol": str(symbol), "qty": self._quantity(value)} for symbol, value in position_rows if abs(self._quantity(value)) > 0]
        trade_rows = raw_trades.values()
        pending = [
            {"trade_id": row.get("trade_id"), "status": row.get("status")}
            for row in trade_rows if isinstance(row, dict) and str(row.get("status") or "active").lower() not in TERMINAL_TRADE_STATES
        ]
        orphan = trades.get("orphan_exposure") or {}
        has_orphan = bool(orphan.get("has_orphans") or orphan.get("has_manager_state_issue"))
        if has_orphan:
            pending.append({"trade_id": None, "status": "orphan_exposure"})
        safe = not active_orders and not nonzero_positions and not pending
        return {
            "ok": True,
            "safe": safe,
            "reason": "zero_exposure" if safe else "active_trading_state",
            "active_orders": len(active_orders),
            "nonzero_positions": len(nonzero_positions),
            "pending_executable_actions": len(pending),
            "orphan_exposure": int(has_orphan),
            "blocking_categories": [
                name for name, count in (
                    ("ACTIVE_ORDERS", len(active_orders)),
                    ("NONZERO_POSITIONS", len(nonzero_positions)),
                    ("PENDING_EXECUTABLE_ACTIONS", len(pending)),
                ) if count
            ],
        }

    def _stop_pid(self, pid: int) -> bool:
        # Windows console Python processes do not always accept taskkill's
        # non-forced close request.  Try it first, then use the fixed governed
        # PID-tree fallback only after the zero-exposure/source-identity gates.
        for arguments in (
            ["taskkill.exe", "/PID", str(int(pid)), "/T"],
            ["taskkill.exe", "/PID", str(int(pid)), "/T", "/F"],
        ):
            result = subprocess.run(
                arguments,
                cwd=str(self.repository_root),
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
                shell=False,
            )
            if result.returncode == 0:
                return True
        return False

    def shutdown_stack(self) -> dict[str, Any]:
        initial = self.snapshot()
        if initial.get("services") and all(row["classification"] == ServiceClassification.STOPPED.value for row in initial["services"]):
            return {"ok": True, "blocked": False, "already_offline": True, "message": "SYSTEM OFFLINE", "stopped": [], "snapshot": initial}
        safety = self.trading_safety()
        if not safety.get("safe"):
            unavailable = safety.get("ok") is not True or safety.get("reason") in {"trading_state_unavailable", "trading_state_schema_invalid"}
            message = "SHUTDOWN BLOCKED — TRADING STATE UNAVAILABLE" if unavailable else "SHUTDOWN BLOCKED — ACTIVE TRADING STATE"
            return {"ok": False, "blocked": True, "message": message, "safety": safety, "stopped": []}
        before = initial
        unsafe = [row for row in before["services"] if row["classification"] in {ServiceClassification.DUPLICATE.value, ServiceClassification.FOREIGN_PROCESS.value, ServiceClassification.UNKNOWN.value}]
        if unsafe:
            return {"ok": False, "blocked": True, "message": "SHUTDOWN BLOCKED — RUNTIME AUTHORITY UNRESOLVED", "safety": safety, "services": unsafe, "stopped": []}
        protected_before = self.protected_state_hashes()
        rows = {row["name"]: row for row in before["services"]}
        stopped: list[str] = []
        for spec in sorted(self.services, key=lambda item: item.shutdown_order):
            row = rows[spec.name]
            for pid in row.get("pids", []):
                if not self._stop_pid(int(pid)):
                    return {"ok": False, "blocked": False, "message": "SYSTEM NOT OFFLINE", "reason": f"stop_failed:{spec.name}", "stopped": stopped}
            if row.get("pids"):
                stopped.append(spec.name)
        deadline = time.monotonic() + 20
        after = self.snapshot()
        while time.monotonic() < deadline and any(row["classification"] != ServiceClassification.STOPPED.value for row in after["services"]):
            time.sleep(0.25)
            after = self.snapshot()
        offline = all(row["classification"] == ServiceClassification.STOPPED.value for row in after["services"])
        protected_after = self.protected_state_hashes()
        protected_unchanged = protected_before == protected_after
        ok = offline and protected_unchanged
        return {
            "ok": ok,
            "blocked": False,
            "message": "SYSTEM OFFLINE" if ok else "SYSTEM NOT OFFLINE",
            "reason": "all_governed_services_stopped_state_unchanged" if ok else "shutdown_verification_failed",
            "safety": safety,
            "stopped": stopped,
            "snapshot": after,
            "protected_state_unchanged": protected_unchanged,
            "protected_state_before": protected_before,
            "protected_state_after": protected_after,
        }

    def ladder_status(self) -> dict[str, Any]:
        # Entry correctly returns HTTP 503 while canonical candles/ATR are
        # rehydrating, but that read-only payload still carries independently
        # authoritative current-day TV Ladder state.  Preserve the HTTP status
        # distinction while adjudicating the ladder from either 200 or the
        # governed fail-closed 503 projection.
        status, payload = self._json_get_result("http://127.0.0.1:7002/entry/status?symbols=NQ,YM", timeout=5.0)
        if status not in {200, 503}:
            payload = {}
        now = datetime.now(LOCAL_ZONE)
        expected_session = now.date().isoformat()
        statuses = payload.get("symbols") if isinstance(payload.get("symbols"), list) else []
        ready_symbols = []
        stale_symbols = []
        for row in statuses:
            context = row.get("market_context") if isinstance(row, dict) else None
            levels = context.get("levels") if isinstance(context, dict) else None
            locked = bool(
                isinstance(context, dict)
                and (context.get("locked") is True or context.get("liquidity_context_locked") is True)
            )
            level_count = len(levels) if isinstance(levels, (dict, list)) else 0
            ready = (
                isinstance(context, dict)
                and str(context.get("session_date") or "") == expected_session
                and locked
                and level_count == 8
            )
            symbol = str(row.get("symbol") or "") if isinstance(row, dict) else ""
            (ready_symbols if ready else stale_symbols).append(symbol)
        if len(ready_symbols) == 2:
            return {"state": "READY", "label": "TV LADDER — READY", "session_date": expected_session}
        before_lock = now.timetz().replace(tzinfo=None) < clock_time(6, 15)
        if before_lock:
            return {"state": "WAITING", "label": "TV LADDER — WAITING FOR CURRENT SESSION", "session_date": expected_session}
        return {"state": "STALE", "label": "TV LADDER — STALE", "session_date": expected_session, "symbols": stale_symbols}


class ControlManager:
    """Thread-safe two-step command state machine with one active operation."""

    def __init__(self, adapter: ServiceAdapter, audit_path: Path, *, confirmation_window: float = CONFIRMATION_WINDOW_SECONDS) -> None:
        self.adapter = adapter
        self.audit_path = audit_path
        self.confirmation_window = confirmation_window
        self._lock = threading.RLock()
        self._arms: dict[str, dict[str, Any]] = {}
        self._prearm: dict[str, Any] | None = None
        self._state: ControlState | None = None
        self._message: str | None = None
        self._operation: dict[str, Any] | None = None

    def _audit(self, event: dict[str, Any]) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        safe = {key: value for key, value in event.items() if key not in {"token", "url", "credential"}}
        safe["timestamp"] = _utc_now()
        with self.audit_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(safe, sort_keys=True, separators=(",", ":")) + "\n")

    @staticmethod
    def _derived_state(snapshot: dict[str, Any]) -> ControlState:
        values = [row.get("classification") for row in snapshot.get("services", [])]
        if values and all(value == ServiceClassification.RUNNING_READY.value for value in values):
            return ControlState.READY
        if values and all(value == ServiceClassification.STOPPED.value for value in values):
            return ControlState.OFFLINE
        return ControlState.DEGRADED

    def status(self) -> dict[str, Any]:
        snapshot = self.adapter.snapshot()
        derived_state = self._derived_state(snapshot)
        with self._lock:
            transient_states = {
                ControlState.START_CONFIRM_REQUIRED,
                ControlState.STARTING,
                ControlState.SHUTDOWN_CONFIRM_REQUIRED,
                ControlState.SHUTTING_DOWN,
                ControlState.SHUTDOWN_BLOCKED,
                ControlState.ERROR,
            }
            state = self._state if self._state in transient_states else derived_state
            has_explicit_message = self._message is not None and state == self._state
            message = self._message if has_explicit_message else {
                ControlState.READY: "SYSTEM READY",
                ControlState.OFFLINE: "SYSTEM OFFLINE",
                ControlState.DEGRADED: "SYSTEM DEGRADED",
            }.get(state, state.value)
            operation = dict(self._operation) if self._operation else None
        ladder = self.adapter.ladder_status()
        if state == ControlState.READY and ladder.get("state") == "WAITING" and (not has_explicit_message or message == "SYSTEM READY"):
            message = "SYSTEM SERVICES READY — WAITING FOR 06:15 TV LADDER"
        elif state == ControlState.READY and ladder.get("state") == "STALE":
            state = ControlState.DEGRADED
            message = "SYSTEM DEGRADED — TV LADDER STALE"
        return {"ok": True, "version": CONTROL_VERSION, "state": state.value, "message": message, "services": snapshot.get("services", []), "ladder": ladder, "operation": operation}

    @staticmethod
    def _session_fingerprint(session_id: str) -> str:
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _prearm_snapshot(self) -> dict[str, Any]:
        """Run the read-only Phase-A preflight before any arm clock exists."""

        reader = getattr(self.adapter, "prearm_snapshot", None)
        snapshot = reader() if callable(reader) else self.adapter.snapshot()
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("services"), list):
            raise ValueError("prearm_snapshot_invalid")
        return snapshot

    def arm(
        self,
        action: str,
        *,
        source: str = "local_command_center",
        session_id: str = "local_command_center",
    ) -> dict[str, Any]:
        """Perform Phase A, then atomically create the five-second Phase-B arm.

        The potentially slow production snapshot and its durable audit write are
        intentionally completed before ``armed_at`` is sampled.  Consequently,
        no part of Phase A can consume the operator-visible confirmation window.
        """

        normalized = str(action).strip().upper()
        if normalized not in {"START", "SHUTDOWN"}:
            return {"ok": False, "error": "unsupported_action"}
        normalized_session = str(session_id or "").strip()
        if not normalized_session:
            return {"ok": False, "error": "control_session_required"}

        self.expire_arms()
        preflight_id = str(uuid.uuid4())
        preflight_started = time.monotonic()
        with self._lock:
            if self._state in {ControlState.STARTING, ControlState.SHUTTING_DOWN}:
                return {"ok": False, "error": "control_operation_in_progress", "state": self._state.value}
            if self._prearm is not None:
                return {"ok": False, "error": "control_preflight_in_progress"}
            active_arm = next((row for row in self._arms.values() if not row.get("confirmed")), None)
            if active_arm is not None:
                return {
                    "ok": False,
                    "error": "control_confirmation_already_armed",
                    "state": self._state.value if self._state else None,
                }
            if self._operation and self._operation.get("status") == "RUNNING":
                return {"ok": False, "error": "control_operation_in_progress", "state": self._state.value if self._state else None}
            # A consumed arm remains useful for replay rejection until the next
            # deliberate Phase-A request begins.  It is safe to retire now.
            self._arms = {}
            self._prearm = {
                "preflight_id": preflight_id,
                "action": normalized,
                "session_id": normalized_session,
                "source": source,
                "started_at": preflight_started,
            }

        session_fingerprint = self._session_fingerprint(normalized_session)
        try:
            self._audit(
                {
                    "event": "control_preflight_started",
                    "phase": "PRE_ARM_PREFLIGHT",
                    "action": normalized,
                    "preflight_id": preflight_id,
                    "source": source,
                    "session_fingerprint": session_fingerprint,
                    "control_version": CONTROL_VERSION,
                }
            )
            snapshot = self._prearm_snapshot()
            preflight_finished = time.monotonic()
            preflight_duration = preflight_finished - preflight_started
            pre_state = self._derived_state(snapshot).value
            snapshot_fingerprint = self._snapshot_fingerprint(snapshot)
            request_id = str(uuid.uuid4())
            # Durable Phase-A/arm-ready evidence is written before the monotonic
            # confirmation clock begins, so audit I/O cannot consume the window.
            self._audit(
                {
                    "event": "control_armed",
                    "phase": "ARM_READY",
                    "action": normalized,
                    "request_id": request_id,
                    "preflight_id": preflight_id,
                    "source": source,
                    "session_fingerprint": session_fingerprint,
                    "control_version": CONTROL_VERSION,
                    "pre_state": pre_state,
                    "preflight_snapshot_sha256": snapshot_fingerprint,
                    "preflight_duration_seconds": round(preflight_duration, 6),
                    "confirmation_clock_starts_after_preflight": True,
                }
            )
        except Exception as exc:
            with self._lock:
                if self._prearm and self._prearm.get("preflight_id") == preflight_id:
                    self._prearm = None
                self._state = ControlState.ERROR
                self._message = "SYSTEM NOT READY"
            try:
                self._audit(
                    {
                        "event": "control_preflight_failed",
                        "phase": "PRE_ARM_PREFLIGHT",
                        "action": normalized,
                        "preflight_id": preflight_id,
                        "source": source,
                        "session_fingerprint": session_fingerprint,
                        "reason": type(exc).__name__,
                    }
                )
            except Exception:
                pass
            return {"ok": False, "error": "prearm_preflight_unavailable", "state": ControlState.ERROR.value, "message": "SYSTEM NOT READY"}

        with self._lock:
            if not self._prearm or self._prearm.get("preflight_id") != preflight_id:
                return {"ok": False, "error": "control_preflight_superseded"}
            if self._state in {ControlState.STARTING, ControlState.SHUTTING_DOWN}:
                self._prearm = None
                return {"ok": False, "error": "control_operation_in_progress", "state": self._state.value}
            armed_at = time.monotonic()
            expires_at = armed_at + self.confirmation_window
            armed_wall = datetime.now(ZoneInfo("UTC"))
            expires_wall = armed_wall + timedelta(seconds=self.confirmation_window)
            self._arms = {
                request_id: {
                    "action": normalized,
                    "armed_at": armed_at,
                    "expires_at": expires_at,
                    "armed_at_utc": armed_wall.isoformat(),
                    "expires_at_utc": expires_wall.isoformat(),
                    "source": source,
                    "session_id": normalized_session,
                    "session_fingerprint": session_fingerprint,
                    "control_version": CONTROL_VERSION,
                    "preflight_id": preflight_id,
                    "preflight_snapshot_sha256": snapshot_fingerprint,
                    "pre_state": pre_state,
                    "preflight_duration_seconds": preflight_duration,
                    "confirmed": False,
                }
            }
            self._prearm = None
            self._state = ControlState.START_CONFIRM_REQUIRED if normalized == "START" else ControlState.SHUTDOWN_CONFIRM_REQUIRED
            self._message = "PUSH AGAIN TO CONFIRM START" if normalized == "START" else "PUSH AGAIN TO CONFIRM SHUTDOWN"
            return {
                "ok": True,
                "request_id": request_id,
                "arm_id": request_id,
                "action": normalized,
                "state": self._state.value,
                "message": self._message,
                "control_version": CONTROL_VERSION,
                "preflight_id": preflight_id,
                "preflight_snapshot_sha256": snapshot_fingerprint,
                "pre_state": pre_state,
                "preflight_duration_seconds": round(preflight_duration, 6),
                "armed_at_utc": armed_wall.isoformat(),
                "expires_at_utc": expires_wall.isoformat(),
                "confirmation_window_seconds": self.confirmation_window,
                "expires_in_seconds": self.confirmation_window,
            }

    def expire_arms(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [request_id for request_id, row in self._arms.items() if not row["confirmed"] and now > row["expires_at"]]
            for request_id in expired:
                row = self._arms.pop(request_id)
                self._audit({"event": "control_arm_expired", "action": row["action"], "request_id": request_id, "preflight_id": row["preflight_id"], "source": row["source"], "session_fingerprint": row["session_fingerprint"], "control_version": row["control_version"], "arm_elapsed_seconds": round(now - row["armed_at"], 6)})
            if expired and not self._arms and self._state in {ControlState.START_CONFIRM_REQUIRED, ControlState.SHUTDOWN_CONFIRM_REQUIRED}:
                self._state = None
                self._message = None

    def confirm(
        self,
        request_id: str,
        *,
        session_id: str = "local_command_center",
        action: str | None = None,
        control_version: str = CONTROL_VERSION,
    ) -> dict[str, Any]:
        self.expire_arms()
        with self._lock:
            row = self._arms.get(str(request_id))
            if row is None:
                return {"ok": False, "error": "confirmation_missing_or_expired"}
            normalized_session = str(session_id or "").strip()
            if not normalized_session or not secrets.compare_digest(row["session_id"], normalized_session):
                return {"ok": False, "error": "confirmation_authority_mismatch"}
            normalized_action = str(action or row["action"]).strip().upper()
            if normalized_action != row["action"]:
                return {"ok": False, "error": "confirmation_authority_mismatch"}
            if str(control_version or "") != row["control_version"]:
                return {"ok": False, "error": "confirmation_authority_mismatch"}
            if row["confirmed"]:
                return {"ok": False, "accepted": False, "duplicate": True, "error": "confirmation_already_used", "operation": dict(self._operation or {})}
            if self._state in {ControlState.STARTING, ControlState.SHUTTING_DOWN}:
                return {"ok": False, "error": "control_operation_in_progress", "state": self._state.value}
            row["confirmed"] = True
            action = row["action"]
            operation_id = str(uuid.uuid4())
            self._state = ControlState.STARTING if action == "START" else ControlState.SHUTTING_DOWN
            self._message = "STARTING..." if action == "START" else "SHUTTING DOWN..."
            self._operation = {
                "operation_id": operation_id,
                "request_id": request_id,
                "action": action,
                "status": "RUNNING",
                "started_at": _utc_now(),
                "control_version": row["control_version"],
                "preflight_id": row["preflight_id"],
                "preflight_snapshot_sha256": row["preflight_snapshot_sha256"],
                "pre_state": row["pre_state"],
            }
            self._audit({"event": "control_confirmed", "action": action, "request_id": request_id, "operation_id": operation_id, "preflight_id": row["preflight_id"], "source": row["source"], "session_fingerprint": row["session_fingerprint"], "control_version": row["control_version"], "confirm_elapsed_seconds": round(time.monotonic() - row["armed_at"], 6)})
            thread = threading.Thread(target=self._run, args=(operation_id, action), daemon=True, name=f"command-center-{action.lower()}-{operation_id[:8]}")
            thread.start()
            return {"ok": True, "accepted": True, "duplicate": False, "state": self._state.value, "message": self._message, "operation_id": operation_id}

    def _run(self, operation_id: str, action: str) -> None:
        try:
            result = self.adapter.start_stack() if action == "START" else self.adapter.shutdown_stack()
        except Exception as exc:  # fail closed without exposing environment details
            result = {"ok": False, "message": "SYSTEM NOT READY" if action == "START" else "SYSTEM NOT OFFLINE", "reason": type(exc).__name__}
        with self._lock:
            if action == "SHUTDOWN" and result.get("blocked"):
                self._state = ControlState.SHUTDOWN_BLOCKED
                self._message = str(result.get("message") or "SHUTDOWN BLOCKED — ACTIVE TRADING STATE")
            elif result.get("ok"):
                self._state = ControlState.READY if action == "START" else ControlState.OFFLINE
                self._message = str(result.get("message") or ("SYSTEM READY" if action == "START" else "SYSTEM OFFLINE"))
            else:
                self._state = ControlState.ERROR
                self._message = str(result.get("message") or ("SYSTEM NOT READY" if action == "START" else "SYSTEM NOT OFFLINE"))
            if self._operation and self._operation.get("operation_id") == operation_id:
                self._operation.update({"status": "COMPLETE", "completed_at": _utc_now(), "result": result})
            self._audit({"event": "control_completed", "action": action, "operation_id": operation_id, "result": "PASS" if result.get("ok") else "BLOCKED" if result.get("blocked") else "FAIL", "post_state": self._state.value})

    def wait_for_idle(self, timeout: float = 30.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                running = bool(self._operation and self._operation.get("status") == "RUNNING")
            if not running:
                return self.status()
            time.sleep(0.01)
        raise TimeoutError("control operation did not complete")
