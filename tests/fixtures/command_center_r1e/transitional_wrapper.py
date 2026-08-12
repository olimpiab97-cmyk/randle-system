"""Pinned transitional wrapper model used only by the R1E disposable runtime."""

from __future__ import annotations

import argparse
import os
import runpy
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True, choices=("entry_agent", "trade_manager"))
    args = parser.parse_args()
    root = Path(os.environ["R1E_FIXTURE_ROOT"]).resolve()
    target = root / ("EntryAgent/tv_context_server.py" if args.service == "entry_agent" else "Engines/trade_manager.py")
    os.environ["R1E_TRANSITIONAL_SERVICE"] = args.service
    runpy.run_path(str(target), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
