"""Opt-in adapter injection for the disposable R1E host process only."""

from __future__ import annotations

import os
import sys


if os.environ.get("RANDLE_CC_R1E_HARNESS") == "1":
    fixture_root = os.environ.get("R1E_FIXTURE_ROOT")
    if fixture_root and fixture_root not in sys.path:
        sys.path.insert(0, fixture_root)
    import command_center_service_control as _control
    from production_shaped_adapter import ProductionShapedAdapter

    _control.ProductionServiceAdapter = ProductionShapedAdapter
