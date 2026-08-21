import copy
import json
import math
import unittest
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def tick_round(value, tick):
    units = Decimal(str(value)) / Decimal(str(tick))
    return float(units.quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal(str(tick)))


def memberships(level):
    groups = level.get("stack_groups")
    if not isinstance(groups, list):
        singular = str(level.get("stack_group") or "").strip()
        groups = [] if not singular or singular.upper() == "NONE" else [singular]
    return sorted(set(str(group).strip() for group in groups if str(group).strip()))


def connected_members(level_name, levels):
    component_levels = {level_name}
    component_groups = set(memberships(levels[level_name]))
    changed = True
    while changed:
        changed = False
        for name, level in levels.items():
            groups = set(memberships(level))
            if name in component_levels or groups & component_groups:
                before = (len(component_levels), len(component_groups))
                component_levels.add(name)
                component_groups.update(groups)
                changed |= before != (len(component_levels), len(component_groups))
    return component_levels, component_groups


def effective_boundary(level_name, side, levels):
    names, groups = connected_members(level_name, levels)
    prices = [float(levels[name]["price"]) for name in names]
    return (max(prices) if side == "high" else min(prices)), names, groups


def derive(from_name, to_name, levels, tick, side="low"):
    from_price, from_names, from_groups = effective_boundary(from_name, side, levels)
    to_price, to_names, to_groups = effective_boundary(to_name, side, levels)
    if math.isclose(from_price, to_price):
        return None
    raw50 = from_price + (to_price - from_price) * 0.50
    raw75 = from_price + (to_price - from_price) * 0.75
    return {
        "from": from_price,
        "to": to_price,
        "raw50": raw50,
        "raw75": raw75,
        "line50": tick_round(raw50, tick),
        "line75": tick_round(raw75, tick),
        "from_members": sorted(from_names),
        "to_members": sorted(to_names),
        "from_groups": sorted(from_groups),
        "to_groups": sorted(to_groups),
    }


def level(price, groups=None, singular=None):
    value = {"price": price, "stack_groups": list(groups or [])}
    if singular is not None:
        value["stack_group"] = singular
    return value


class EffectiveBoundaryTests(unittest.TestCase):
    def test_no_stacks(self):
        result = derive("U", "L", {"U": level(100), "L": level(80)}, 0.25)
        self.assertEqual((result["line50"], result["line75"]), (90, 85))

    def test_upper_stacked(self):
        levels = {"U": level(100, ["HIGH 1"]), "UH": level(104, ["HIGH 1"]), "L": level(80)}
        self.assertEqual(derive("U", "L", levels, 0.25, side="high")["from"], 104)

    def test_lower_stacked(self):
        levels = {"U": level(100), "L": level(80, ["LOW 1"]), "LL": level(76, ["LOW 1"])}
        self.assertEqual(derive("U", "L", levels, 0.25)["to"], 76)

    def test_both_stacked(self):
        levels = {"U": level(100, ["H"]), "UH": level(96, ["H"]), "L": level(80, ["L"]), "LL": level(75, ["L"])}
        result = derive("U", "L", levels, 0.25)
        self.assertEqual((result["from"], result["to"]), (96, 75))

    def test_dual_membership_connects_groups(self):
        levels = {"L": level(90, ["LOW 1"]), "B": level(85, ["LOW 1", "LOW 2"]), "X": level(80, ["LOW 2"]), "U": level(110)}
        result = derive("U", "L", levels, 0.25)
        self.assertEqual(result["to_members"], ["B", "L", "X"])
        self.assertEqual(result["to"], 80)

    def test_ll_onl_yl_chain(self):
        levels = {"U": level(100), "LL": level(90, ["LOW 1"]), "ONL": level(85, ["LOW 1", "LOW 2"]), "YL": level(78, ["LOW 2"])}
        self.assertEqual(derive("U", "LL", levels, 0.25)["to"], 78)

    def test_high_chain(self):
        levels = {"U": level(100, ["HIGH 1"]), "ONH": level(105, ["HIGH 1", "HIGH 2"]), "YH": level(112, ["HIGH 2"]), "L": level(80)}
        self.assertEqual(derive("U", "L", levels, 0.25, side="high")["from"], 112)

    def test_disconnected_nearby_stacks_remain_separate(self):
        levels = {"U": level(100, ["H1"]), "A": level(102, ["H1"]), "B": level(103, ["H2"]), "L": level(80)}
        self.assertNotIn("B", derive("U", "L", levels, 0.25, side="high")["from_members"])

    def test_same_price_no_artificial_range(self):
        self.assertIsNone(derive("U", "L", {"U": level(100), "L": level(100)}, 0.25))

    def test_stack_order_independent(self):
        first = {"U": level(100), "L": level(90, ["L1", "L2"]), "X": level(80, ["L2"])}
        second = {"X": level(80, ["L2"]), "L": level(90, ["L2", "L1"]), "U": level(100)}
        self.assertEqual(derive("U", "L", first, 0.25), derive("U", "L", second, 0.25))

    def test_duplicate_group_is_logically_deduped(self):
        levels = {"U": level(100), "L": level(90, ["LOW 1", "LOW 1"]), "X": level(80, ["LOW 1"])}
        self.assertEqual(derive("U", "L", levels, 0.25)["to_members"], ["L", "X"])

    def test_plural_wins_over_null_legacy_singular(self):
        levels = {"U": level(100), "L": level(90, ["L1"], None), "X": level(80, ["L1"], "WRONG")}
        self.assertEqual(derive("U", "L", levels, 0.25)["to"], 80)

    def test_today_nq_pml_ll(self):
        result = derive("PML", "LL", {"PML": level(29467), "LL": level(29390.5)}, 0.25)
        self.assertEqual((result["raw50"], result["raw75"]), (29428.75, 29409.625))
        self.assertEqual((result["line50"], result["line75"]), (29428.75, 29409.75))

    def test_today_ym_control(self):
        levels = {"PMH": level(53230, ["HIGH 1"]), "ONH": level(53230, ["HIGH 1"]), "YH": level(53288), "PML": level(53119), "LL": level(52950), "ONL": level(52838)}
        self.assertEqual((derive("PMH", "YH", levels, 1, side="high")["line50"], derive("PMH", "YH", levels, 1, side="high")["line75"]), (53259, 53274))
        self.assertEqual((derive("PML", "LL", levels, 1)["line50"], derive("PML", "LL", levels, 1)["line75"]), (53035, 52992))

    def test_orientation_zero_upper_one_hundred_lower(self):
        result = derive("U", "L", {"U": level(100), "L": level(60)}, 0.25)
        self.assertEqual((result["raw50"], result["raw75"]), (80, 70))

    def test_nq_tick_rounding(self):
        self.assertEqual(tick_round(29409.625, 0.25), 29409.75)

    def test_ym_tick_rounding(self):
        self.assertEqual(tick_round(53034.5, 1), 53035)

    def test_serialization_and_command_center_shape(self):
        result = derive("U", "L", {"U": level(100), "L": level(80)}, 0.25)
        payload = {"midpoints": {"U_L": result["line50"]}, "exhaustion_boundaries": {"U_L": {"side": "low", "mid_50": result["line50"], "remaining_25": result["line75"]}}}
        self.assertEqual(json.loads(json.dumps(payload)), payload)

    def test_frozen_session_is_immutable_copy(self):
        live = {"midpoints": {"U_L": 90}, "exhaustion_boundaries": {"U_L": {"remaining_25": 85}}}
        frozen = copy.deepcopy(live)
        live["midpoints"]["U_L"] = 91
        self.assertEqual(frozen["midpoints"]["U_L"], 90)

    def test_legacy_payload_derives_without_metadata(self):
        result = derive("U", "L", {"U": {"price": 100, "stack_group": "NONE"}, "L": {"price": 80, "stack_group": "NONE"}}, 0.25)
        self.assertEqual(result["line75"], 85)

    def test_pine_candidate_contains_authority_fences(self):
        source = (Path(__file__).parent / "TradingView" / "indicators" / "Randle_AI_Level_Map_Helper.pine").read_text(encoding="utf-8")
        for marker in ("stackComponentMask", "stackComponentExtreme", "fixedSide or price > close", "fixedSide or price < close", "distinctEffectiveBoundaries", "roundToMintick((a + b) / 2.0)"):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
