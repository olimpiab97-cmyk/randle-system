from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path


ENV_VAR = "RANDLE_DATA_ROOT"
REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = REPO_ROOT / "Data"
LOCAL_RUNTIME_SUBDIR = "RandleRuntimeData"


def get_data_root() -> Path:
    raw_root = str(os.getenv(ENV_VAR, "") or "").strip()
    data_root = Path(raw_root).expanduser() if raw_root else DEFAULT_DATA_ROOT
    data_root.mkdir(parents=True, exist_ok=True)
    return data_root.resolve()


def data_path(*parts: str) -> Path:
    return get_data_root().joinpath(*parts)


def get_local_runtime_data_root() -> Path:
    raw_local_appdata = str(os.getenv("LOCALAPPDATA", "") or "").strip()
    candidates = []
    if raw_local_appdata:
        candidates.append(Path(raw_local_appdata).expanduser() / LOCAL_RUNTIME_SUBDIR)
    candidates.append(Path(tempfile.gettempdir()) / LOCAL_RUNTIME_SUBDIR)

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except Exception:
            continue
        if directory_is_writable(candidate):
            return candidate.resolve()

    raise PermissionError("No writable local runtime data root available")


def directory_is_writable(path: Path) -> bool:
    target = Path(path)
    probe_path = None
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe_path = target / f".write_probe.{uuid.uuid4().hex}.tmp"
        with probe_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write("ok")
            handle.flush()
            os.fsync(handle.fileno())
        probe_path.unlink(missing_ok=True)
        return True
    except Exception:
        try:
            if probe_path is not None:
                probe_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def writable_data_path(*parts: str, fallback_local_root: Path | None = None) -> Path:
    primary_root = get_data_root()
    if directory_is_writable(primary_root):
        return primary_root.joinpath(*parts)
    local_root = fallback_local_root or get_local_runtime_data_root()
    local_root.mkdir(parents=True, exist_ok=True)
    return local_root.joinpath(*parts)


def feed_health_data_path() -> Path:
    return writable_data_path("rithmic_feed_health.json")


def has_explicit_data_root() -> bool:
    return bool(str(os.getenv(ENV_VAR, "") or "").strip())


def local_or_shared_path(local_base: Path, *parts: str, shared_prefix: str | None = None) -> Path:
    if has_explicit_data_root():
        target = get_data_root()
        if shared_prefix:
            target = target / shared_prefix
        return target.joinpath(*parts)
    return local_base.joinpath(*parts)


def is_default_local_data_root() -> bool:
    return get_data_root() == DEFAULT_DATA_ROOT.resolve()


def log_active_data_root(component_name: str) -> None:
    data_root = get_data_root()
    source = "default_local" if is_default_local_data_root() else "env"
    print(f"DATA ROOT component={component_name} path={data_root} source={source}")
    if source == "default_local":
        print(
            "DATA ROOT WARNING "
            f"component={component_name} using_local_default_data_root path={data_root} "
            f"hint=set {ENV_VAR} to a shared folder"
        )
