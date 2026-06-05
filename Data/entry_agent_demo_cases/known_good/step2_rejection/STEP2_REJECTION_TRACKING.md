# Step 2 Rejection Tracking

## Approved Fixtures

### atr_stack/exact_threshold_distance_stacks

| Field | Value |
| --- | --- |
| Fixture | atr_stack/exact_threshold_distance_stacks |
| Category | ATR Stack |
| Direction | LONG |
| Level Type | Stacked Low |
| Levels | PML 100 / ONL 90 |
| Simulated Daily ATR | 100 |
| Stack Threshold | 10 |
| Distance | 10 |
| Rule Decision | Exact 10% ATR distance DOES stack |
| Qualification Boundary | ONL 90 |
| Close | 89.75 |
| Expected Result | valid_step2 |
| User Review | APPROVED |
| Status | PASS |
| Notes | Valid Step 2 rejection. Close is beyond qualification boundary. This becomes an approved Step 2 rule. |

### atr_stack/exact_threshold_distance_stacks - Approved Specification

| Field | Value |
| --- | --- |
| Fixture | atr_stack/exact_threshold_distance_stacks |
| Category | ATR Stack |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | Distance exactly equal to 10% of Daily ATR is considered STACKED. |
| PML | 100 |
| ONL | 90 |
| Simulated ATR | 100 |
| Stack Threshold | 10 |
| Distance | 10 |
| Qualification Boundary | ONL 90 |
| Close | 89.75 |
| Expected Result | valid_step2 |
| Notes | This fixture is now considered KNOWN GOOD and becomes part of the approved Step 2 rejection specification. |

### atr_stack/high_within_10pct_atr_valid

| Field | Value |
| --- | --- |
| Fixture | atr_stack/high_within_10pct_atr_valid |
| Category | ATR Stack |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | High-side levels within 10% of Daily ATR are considered STACKED. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture is now KNOWN GOOD and becomes part of the approved Step 2 rejection specification. |

Relationship to Existing Approved Rule:

- atr_stack/exact_threshold_distance_stacks approved
- atr_stack/high_within_10pct_atr_valid approved

Approved ATR Stack Rules So Far:

1. Distance exactly equal to 10% ATR stacks.
2. High-side levels within 10% ATR stack.
3. Low-side levels within 10% ATR stack.

### atr_stack/levels_outside_10pct_atr_do_not_stack

| Field | Value |
| --- | --- |
| Fixture | atr_stack/levels_outside_10pct_atr_do_not_stack |
| Category | ATR Stack |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | Levels separated by more than 10% of Daily ATR do NOT stack. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture is now KNOWN GOOD and becomes part of the approved Step 2 rejection specification. |

Approved ATR Stack Rules So Far:

1. Distance exactly equal to 10% ATR stacks.
2. High-side levels within 10% ATR stack.
3. Low-side levels within 10% ATR stack.
4. Levels outside 10% ATR do NOT stack.

### atr_stack/low_within_10pct_atr_close_inside_invalid

| Field | Value |
| --- | --- |
| Fixture | atr_stack/low_within_10pct_atr_close_inside_invalid |
| Category | ATR Stack |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | A valid ATR stack alone does NOT qualify Step 2. |
| Expected Result | invalid_step2 |
| Notes | User reviewed and approved. This fixture confirms that stack detection and Step 2 qualification are separate decisions. |

For low-side stacks:

- Levels may be correctly stacked.
- Qualification boundary may be identified correctly.
- If the close remains inside the stack and does not close beyond the qualification boundary, Step 2 is INVALID.

Approved ATR Stack Rules So Far:

1. Distance exactly equal to 10% ATR stacks.
2. High-side levels within 10% ATR stack.
3. Low-side levels within 10% ATR stack.
4. Levels outside 10% ATR do NOT stack.
5. A valid stack does not automatically qualify Step 2.
6. Close must finish beyond the qualification boundary to activate Step 2.

### atr_stack/low_within_10pct_atr_valid

| Field | Value |
| --- | --- |
| Fixture | atr_stack/low_within_10pct_atr_valid |
| Category | ATR Stack |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a valid low-side ATR stack, levels stack when within 10% ATR, the qualification boundary is determined from the stack, and a close beyond the qualification boundary makes Step 2 VALID. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture forms the approved counterpart to atr_stack/low_within_10pct_atr_close_inside_invalid. |

Together these fixtures confirm:

1. Stack detection and Step 2 qualification are separate decisions.
2. A valid ATR stack does not automatically activate Step 2.
3. Close must finish beyond the qualification boundary.
4. Closing beyond the qualification boundary activates Step 2.

Approved ATR Stack Rules So Far:

1. Distance < 10% ATR stacks.
2. Distance = 10% ATR stacks.
3. Distance > 10% ATR does not stack.
4. High-side levels within threshold stack.
5. Low-side levels within threshold stack.
6. A valid stack alone does not qualify Step 2.
7. Close inside qualification boundary = INVALID.
8. Close beyond qualification boundary = VALID.

### atr_stack/triple_high_outer_distance_splits

| Field | Value |
| --- | --- |
| Fixture | atr_stack/triple_high_outer_distance_splits |
| Category | ATR Stack |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | A triple stack is NOT allowed when the outer distance exceeds the ATR stack threshold. |
| Notes | User reviewed and approved. This fixture establishes the split-overlap stack rule. |

Example:

- PMH <-> ONH = within threshold
- ONH <-> YH = within threshold
- PMH <-> YH = outside threshold

Approved Result:

- PMH/ONH stack exists
- ONH/YH stack exists
- PMH/ONH/YH triple stack does NOT exist

Approved ATR Stack Rules So Far:

1. Distance < 10% ATR stacks.
2. Distance = 10% ATR stacks.
3. Distance > 10% ATR does not stack.
4. High-side levels within threshold stack.
5. Low-side levels within threshold stack.
6. A valid stack alone does not qualify Step 2.
7. Close inside qualification boundary = INVALID.
8. Close beyond qualification boundary = VALID.
9. Triple stacks are invalid when the outermost levels exceed the ATR threshold.
10. Overlapping pair stacks are allowed.
11. A middle level may participate in more than one stack.

### atr_stack/high_three_levels_split_overlap

| Field | Value |
| --- | --- |
| Fixture | atr_stack/high_three_levels_split_overlap |
| Category | ATR Stack |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | When three high-side levels exist, Level 1/2 is within threshold, Level 2/3 is within threshold, and Level 1/3 exceeds threshold, create overlapping pair stacks and do not create a triple stack. |
| Notes | User reviewed and approved. Middle level may participate in both stacks. |

Approved Result:

- PMH/ONH Liquidity exists
- ONH/YH Liquidity exists
- PMH/ONH/YH Liquidity does NOT exist

### atr_stack/low_three_levels_split_overlap

| Field | Value |
| --- | --- |
| Fixture | atr_stack/low_three_levels_split_overlap |
| Category | ATR Stack |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | When three low-side levels exist, Level 1/2 is within threshold, Level 2/3 is within threshold, and Level 1/3 exceeds threshold, create overlapping pair stacks and do not create a triple stack. |
| Notes | User reviewed and approved. Middle level may participate in both stacks. |

Approved Result:

- PML/ONL Liquidity exists
- ONL/YL Liquidity exists
- PML/ONL/YL Liquidity does NOT exist

Approved ATR Stack Rules Added:

12. Three-level structures may form multiple overlapping pair stacks.
13. The middle level may belong to more than one stack.
14. Triple stacks are invalid when the outermost levels exceed the ATR stack threshold.
15. Stack grouping is determined by pairwise threshold qualification, not by chaining all nearby levels into one group.

### edge_cases/active_liquidity_name_ordered_correctly

| Field | Value |
| --- | --- |
| Fixture | edge_cases/active_liquidity_name_ordered_correctly |
| Category | Boundary Mapping / Stack Ownership |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For stacked liquidity, boundary ownership and displayed boundary prices must remain internally consistent. |
| Notes | User reviewed and approved. |

Approved Example:

- PMH = 100
- ONH = 101

Approved Result:

- Close Boundary Level = PMH
- Close Boundary Price = 100
- Extreme Boundary Level = ONH
- Extreme Boundary Price = 101
- Qualification Boundary = ONH 101

This fixture confirms:

1. Stack ownership naming must match actual component prices.
2. Close boundary price cannot inherit the qualification boundary price.
3. Displayed boundary values must match the underlying stack component prices.
4. PMH/ONH ownership ordering is displayed correctly.

Approved Rules Added:

16. Boundary labels and boundary prices must remain internally consistent.
17. Stack ownership naming cannot override actual component boundary prices.
18. Close Boundary, Extreme Boundary, and Qualification Boundary must each display their correct underlying level prices.

### edge_cases/close_through_stale_inactive_level

| Field | Value |
| --- | --- |
| Fixture | edge_cases/close_through_stale_inactive_level |
| Category | Level Freshness / Active Liquidity Selection |
| Status | RETRACTED / NOT APPROVED |
| User Review | RETRACTED |
| Rule Approved | Retracted. No approved rule from this fixture. |
| Notes | User approval was mistaken because the demo page was stale at the time of review. Too vague; must define why the level is inactive before this can be approved. Removed from active Step 2 review and hidden from the Step 2 Rejection selector. Replaced by specific inactive-reason investigation fixtures under investigations/step2_inactive_liquidity/. |

Approved Result:

- Price may close through the stale level.
- Step 2 remains inactive.
- The stale level cannot become the active liquidity owner.
- Qualification must occur against currently active liquidity only.

Retracted claim:

1. Liquidity freshness matters.
2. Inactive/stale levels cannot activate Step 2.
3. Close-through alone is insufficient if the level is no longer active.
4. Active liquidity selection must occur before Step 2 qualification is evaluated.

Required future clarification:

- `inactive_reason` must be explicit, such as consumed, stack ownership transfer, session freshness, opposite-side control, or reset law.
- Replacement investigation fixtures: close_through_consumed_level, close_through_session_expired_level, close_through_stack_owner_replaced_level, close_through_opposite_side_control_inactivated_level, close_through_continuation_reset_inactivated_structure.
- Historical fixture remains at known_good/step2_rejection/edge_cases/close_through_stale_inactive_level with `deprecated=true` and `hidden_from_review=true` for traceability only.

Retracted Rules:

19. Step 2 may only evaluate against active liquidity.
20. Stale or inactive liquidity levels are ignored for Step 2 qualification.
21. A close-through of inactive liquidity cannot activate Step 2.
22. Active liquidity ownership takes precedence over historical/stale levels.

### edge_cases/close_through_wrong_side_level

| Field | Value |
| --- | --- |
| Fixture | edge_cases/close_through_wrong_side_level |
| Category | Active Liquidity Selection / Wrong-Side Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | Step 2 qualification must occur against the active liquidity for the setup direction. A close-through of wrong-side liquidity does not activate Step 2. |
| Notes | Fixture reviewed with the correct demo state loaded. |

Approved Result:

- Active liquidity remains controlling.
- Wrong-side liquidity is ignored for Step 2 qualification.
- Close-through alone is insufficient if the level is not the active qualifying liquidity.

Approved Example:

- Direction = LONG
- Active Liquidity = PML 100
- Other Level = ONH 101
- Close = 101.25
- Result = Step 2 ignored

Explanation:

Price closed through ONH, but the setup was evaluating low-side liquidity PML. The close-through occurred on the wrong-side liquidity and therefore does not qualify Step 2.

Approved Rules Added:

27. Step 2 qualification is evaluated against active liquidity, not any liquidity touched.
28. Wrong-side liquidity cannot activate Step 2.
29. A close-through must occur at the qualifying-side active liquidity to activate Step 2.

### edge_cases/equal_price_stack_components

| Field | Value |
| --- | --- |
| Fixture | edge_cases/equal_price_stack_components |
| Category | Stack Ownership / Equal-Price Components |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | Equal-price liquidity components are valid stack members and must remain grouped as a stack when multiple liquidity levels share the exact same price. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents equal-price stack grouping only; no Step 2 logic change is implied. |

Approved Result:

- PML and ONL share the exact same low-side price.
- The active liquidity remains grouped as PML/ONL Liquidity.
- A close one tick beyond the shared stack boundary activates Step 2 rejection.

Approved Rules Added:

30. Equal-price liquidity components are valid stack members and must remain grouped as a stack when multiple liquidity levels share the exact same price.

### edge_cases/gaps_through_level

| Field | Value |
| --- | --- |
| Fixture | edge_cases/gaps_through_level |
| Category | Close-Through Qualification / Gap Through Level |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | A gap through the active liquidity level qualifies Step 2 when the completed candle close is beyond the active liquidity boundary. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents gap-through qualification for the active liquidity only; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH 100.
- Direction = SHORT.
- Candle opens beyond the active high-side liquidity and closes beyond it.
- Step 2 rejection activates because the completed close is beyond the active liquidity boundary.

Approved Rules Added:

31. A gap through the active liquidity level qualifies Step 2 when the completed candle close is beyond the active liquidity boundary.

### regular_long/body_close_beyond_liquidity_no_stack

| Field | Value |
| --- | --- |
| Fixture | regular_long/body_close_beyond_liquidity_no_stack |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked long rejection setup, a completed candle close beyond the active low-side liquidity level qualifies Step 2. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents close-through qualification for single active low-side liquidity only; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML 100.
- Direction = LONG.
- No stack is present.
- Candle closes one tick below the active low-side liquidity at 99.75.
- Step 2 rejection activates because the completed close is beyond the active liquidity boundary.

Approved Rules Added:

32. For a regular non-stacked long rejection setup, a completed candle close beyond the active low-side liquidity level qualifies Step 2.

### regular_short/body_close_beyond_liquidity

| Field | Value |
| --- | --- |
| Fixture | regular_short/body_close_beyond_liquidity |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For non-stacked liquidity, a short-side body close beyond the active liquidity level qualifies Step 2. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents close-through qualification for single active high-side liquidity only; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH 100.
- Direction = SHORT.
- No stack is present.
- Candle closes one tick above the active high-side liquidity at 100.25.
- Step 2 rejection activates because the completed body close is beyond the active liquidity boundary.

Approved Rules Added:

33. For non-stacked liquidity, a short-side body close beyond the active liquidity level qualifies Step 2.

### regular_long/wick_touches_liquidity_close_not_beyond

| Field | Value |
| --- | --- |
| Fixture | regular_long/wick_touches_liquidity_close_not_beyond |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked long rejection setup, a wick touch of active low-side liquidity does not qualify Step 2 unless the completed candle close is beyond the active liquidity level. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that wick contact alone is insufficient for Step 2 qualification; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML 100.
- Direction = LONG.
- No stack is present.
- Candle wick touches the active low-side liquidity at 100.0.
- Candle closes back inside at 100.5.
- Step 2 rejection does not activate because the completed close is not beyond the active liquidity boundary.

Approved Rules Added:

34. For a regular non-stacked long rejection setup, a wick touch of active low-side liquidity does not qualify Step 2 unless the completed candle close is beyond the active liquidity level.

### regular_long/body_close_exactly_at_liquidity

| Field | Value |
| --- | --- |
| Fixture | regular_long/body_close_exactly_at_liquidity |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked long rejection setup, a completed candle close exactly at the active liquidity level does not qualify Step 2; the close must be beyond the active liquidity level. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that exact contact at the active liquidity boundary is insufficient for Step 2 qualification; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML 100.
- Direction = LONG.
- No stack is present.
- Candle closes exactly at the active low-side liquidity at 100.0.
- Step 2 rejection does not activate because the completed close is not beyond the active liquidity boundary.

Approved Rules Added:

35. For a regular non-stacked long rejection setup, a completed candle close exactly at the active liquidity level does not qualify Step 2; the close must be beyond the active liquidity level.

### regular_short/body_close_exactly_at_liquidity

| Field | Value |
| --- | --- |
| Fixture | regular_short/body_close_exactly_at_liquidity |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked short rejection setup, a completed candle close exactly at the active liquidity level does not qualify Step 2; the close must be beyond the active liquidity level. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that exact contact at the active high-side liquidity boundary is insufficient for Step 2 qualification; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH 100.
- Direction = SHORT.
- No stack is present.
- Candle closes exactly at the active high-side liquidity at 100.0.
- Step 2 rejection does not activate because the completed close is not beyond the active liquidity boundary.

Approved Rules Added:

36. For a regular non-stacked short rejection setup, a completed candle close exactly at the active liquidity level does not qualify Step 2; the close must be beyond the active liquidity level.

### regular_long/body_close_beyond_no_wick_beyond

| Field | Value |
| --- | --- |
| Fixture | regular_long/body_close_beyond_no_wick_beyond |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked long rejection setup, a completed candle close beyond the active low-side liquidity level qualifies Step 2 even when there is no additional wick extension beyond the close. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents that Step 2 qualification is based on the completed close beyond active liquidity; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML 100.
- Direction = LONG.
- No stack is present.
- Candle closes one tick below the active low-side liquidity at 99.75.
- The candle has no additional lower wick beyond the close.
- Step 2 rejection activates because the completed close is beyond the active liquidity boundary.

Approved Rules Added:

37. For a regular non-stacked long rejection setup, a completed candle close beyond the active low-side liquidity level qualifies Step 2 even when there is no additional wick extension beyond the close.

### regular_short/body_close_beyond_no_wick_beyond

| Field | Value |
| --- | --- |
| Fixture | regular_short/body_close_beyond_no_wick_beyond |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked short rejection setup, a completed candle close beyond the active high-side liquidity level qualifies Step 2 even when there is no additional wick extension beyond the close. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents that Step 2 qualification is based on the completed close beyond active liquidity; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH 100.
- Direction = SHORT.
- No stack is present.
- Candle closes one tick above the active high-side liquidity at 100.25.
- The candle has no additional upper wick beyond the close.
- Step 2 rejection activates because the completed close is beyond the active liquidity boundary.

Approved Rules Added:

38. For a regular non-stacked short rejection setup, a completed candle close beyond the active high-side liquidity level qualifies Step 2 even when there is no additional wick extension beyond the close.

### regular_long/body_close_beyond_with_wick_beyond

| Field | Value |
| --- | --- |
| Fixture | regular_long/body_close_beyond_with_wick_beyond |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked long rejection setup, a completed candle close beyond the active low-side liquidity level qualifies Step 2 when the wick also extends beyond that level. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents close-through qualification when both the close and wick are beyond active liquidity; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML 100.
- Direction = LONG.
- No stack is present.
- Candle wick extends below active low-side liquidity to 99.25.
- Candle closes one tick below active low-side liquidity at 99.75.
- Step 2 rejection activates because the completed close is beyond the active liquidity boundary.

Approved Rules Added:

39. For a regular non-stacked long rejection setup, a completed candle close beyond the active low-side liquidity level qualifies Step 2 when the wick also extends beyond that level.

### regular_short/body_close_beyond_with_wick_beyond

| Field | Value |
| --- | --- |
| Fixture | regular_short/body_close_beyond_with_wick_beyond |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked short rejection setup, a completed candle close beyond the active high-side liquidity level qualifies Step 2 when the wick also extends beyond that level. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents close-through qualification when both the close and wick are beyond active liquidity; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH 100.
- Direction = SHORT.
- No stack is present.
- Candle wick extends above active high-side liquidity to 100.75.
- Candle closes one tick above active high-side liquidity at 100.25.
- Step 2 rejection activates because the completed close is beyond the active liquidity boundary.

Approved Rules Added:

40. For a regular non-stacked short rejection setup, a completed candle close beyond the active high-side liquidity level qualifies Step 2 when the wick also extends beyond that level.

### regular_long/body_close_near_liquidity_not_through

| Field | Value |
| --- | --- |
| Fixture | regular_long/body_close_near_liquidity_not_through |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked long rejection setup, a completed candle close near active low-side liquidity does not qualify Step 2 unless the close is beyond the active liquidity level. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that proximity to active liquidity is insufficient for Step 2 qualification; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML 100.
- Direction = LONG.
- No stack is present.
- Candle touches the active low-side liquidity at 100.0.
- Candle closes one tick inside the active low-side liquidity at 100.25.
- Step 2 rejection does not activate because the completed close is not beyond the active liquidity boundary.

Approved Rules Added:

41. For a regular non-stacked long rejection setup, a completed candle close near active low-side liquidity does not qualify Step 2 unless the close is beyond the active liquidity level.

### regular_short/body_close_near_liquidity_not_through

| Field | Value |
| --- | --- |
| Fixture | regular_short/body_close_near_liquidity_not_through |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked short rejection setup, a completed candle close near active high-side liquidity does not qualify Step 2 unless the close is beyond the active liquidity level. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that proximity to active liquidity is insufficient for Step 2 qualification; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH 100.
- Direction = SHORT.
- No stack is present.
- Candle touches the active high-side liquidity at 100.0.
- Candle closes one tick inside the active high-side liquidity at 99.75.
- Step 2 rejection does not activate because the completed close is not beyond the active liquidity boundary.

Approved Rules Added:

42. For a regular non-stacked short rejection setup, a completed candle close near active high-side liquidity does not qualify Step 2 unless the close is beyond the active liquidity level.

### regular_long/no_wick_close_does_not_reach_liquidity

| Field | Value |
| --- | --- |
| Fixture | regular_long/no_wick_close_does_not_reach_liquidity |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked long rejection setup, Step 2 does not qualify when price does not reach the active low-side liquidity level and the completed close remains inside that level. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that no-reach candles do not qualify Step 2; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML 100.
- Direction = LONG.
- No stack is present.
- Candle low remains above active low-side liquidity at 100.5.
- Candle closes above active low-side liquidity at 100.5.
- Step 2 rejection does not activate because price did not reach the active liquidity and the completed close is not beyond the active liquidity boundary.

Approved Rules Added:

43. For a regular non-stacked long rejection setup, Step 2 does not qualify when price does not reach the active low-side liquidity level and the completed close remains inside that level.

### regular_short/no_wick_close_does_not_reach_liquidity

| Field | Value |
| --- | --- |
| Fixture | regular_short/no_wick_close_does_not_reach_liquidity |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked short rejection setup, Step 2 does not qualify when price does not reach the active high-side liquidity level and the completed close remains inside that level. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that no-reach candles do not qualify Step 2; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH 100.
- Direction = SHORT.
- No stack is present.
- Candle high remains below active high-side liquidity at 99.5.
- Candle closes below active high-side liquidity at 99.5.
- Step 2 rejection does not activate because price did not reach the active liquidity and the completed close is not beyond the active liquidity boundary.

Approved Rules Added:

44. For a regular non-stacked short rejection setup, Step 2 does not qualify when price does not reach the active high-side liquidity level and the completed close remains inside that level.

### regular_short/wick_beyond_close_back_inside

| Field | Value |
| --- | --- |
| Fixture | regular_short/wick_beyond_close_back_inside |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked short rejection setup, a wick beyond active high-side liquidity does not qualify Step 2 unless the completed candle close is beyond the active liquidity level. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that wick penetration alone is insufficient for Step 2 qualification; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH 100.
- Direction = SHORT.
- No stack is present.
- Candle wick extends beyond active high-side liquidity to 100.5.
- Candle closes back inside active high-side liquidity at 99.75.
- Step 2 rejection does not activate because the completed close is not beyond the active liquidity boundary.

Approved Rules Added:

45. For a regular non-stacked short rejection setup, a wick beyond active high-side liquidity does not qualify Step 2 unless the completed candle close is beyond the active liquidity level.

### stacked_high/close_beyond_extreme_boundary

| Field | Value |
| --- | --- |
| Fixture | stacked_high/close_beyond_extreme_boundary |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked high-side rejection setup, a completed candle close beyond the stack extreme boundary qualifies Step 2. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents close-through qualification for stacked high-side liquidity using the stack extreme boundary; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH/ONH 101.
- Direction = SHORT.
- Stack components are PMH 100 and ONH 101.
- The controlling high-side stack extreme boundary is ONH 101.
- Candle closes one tick beyond the stack extreme boundary at 101.25.
- Step 2 rejection activates because the completed close is beyond the active stacked liquidity boundary.

Approved Rules Added:

46. For a stacked high-side rejection setup, a completed candle close beyond the stack extreme boundary qualifies Step 2.

### stacked_low/close_beyond_extreme_boundary

| Field | Value |
| --- | --- |
| Fixture | stacked_low/close_beyond_extreme_boundary |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked low-side rejection setup, a completed candle close beyond the stack extreme boundary qualifies Step 2. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents close-through qualification for stacked low-side liquidity using the stack extreme boundary; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML/ONL 99.
- Direction = LONG.
- Stack components are PML 100 and ONL 99.
- The controlling low-side stack extreme boundary is ONL 99.
- Candle closes one tick beyond the stack extreme boundary at 98.75.
- Step 2 rejection activates because the completed close is beyond the active stacked liquidity boundary.

Approved Rules Added:

47. For a stacked low-side rejection setup, a completed candle close beyond the stack extreme boundary qualifies Step 2.

### stacked_high/close_beyond_extreme_with_wick_beyond

| Field | Value |
| --- | --- |
| Fixture | stacked_high/close_beyond_extreme_with_wick_beyond |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked high-side rejection setup, a completed candle close beyond the stack extreme boundary qualifies Step 2 when the wick also extends beyond that boundary. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents close-through qualification when both the close and wick are beyond the stacked high-side extreme boundary; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH/ONH 101.
- Direction = SHORT.
- Stack components are PMH 100 and ONH 101.
- The controlling high-side stack extreme boundary is ONH 101.
- Candle wick extends beyond the stack extreme boundary to 101.75.
- Candle closes one tick beyond the stack extreme boundary at 101.25.
- Step 2 rejection activates because the completed close is beyond the active stacked liquidity boundary.

Approved Rules Added:

48. For a stacked high-side rejection setup, a completed candle close beyond the stack extreme boundary qualifies Step 2 when the wick also extends beyond that boundary.

### stacked_low/close_beyond_extreme_with_wick_beyond

| Field | Value |
| --- | --- |
| Fixture | stacked_low/close_beyond_extreme_with_wick_beyond |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked low-side rejection setup, a completed candle close beyond the stack extreme boundary qualifies Step 2 when the wick also extends beyond that boundary. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents close-through qualification when both the close and wick are beyond the stacked low-side extreme boundary; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML/ONL 99.
- Direction = LONG.
- Stack components are PML 100 and ONL 99.
- The controlling low-side stack extreme boundary is ONL 99.
- Candle wick extends beyond the stack extreme boundary to 98.25.
- Candle closes one tick beyond the stack extreme boundary at 98.75.
- Step 2 rejection activates because the completed close is beyond the active stacked liquidity boundary.

Approved Rules Added:

49. For a stacked low-side rejection setup, a completed candle close beyond the stack extreme boundary qualifies Step 2 when the wick also extends beyond that boundary.

### stacked_high/body_close_exactly_at_extreme_boundary

| Field | Value |
| --- | --- |
| Fixture | stacked_high/body_close_exactly_at_extreme_boundary |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked high-side rejection setup, a completed candle close exactly at the stack extreme boundary does not qualify Step 2; the close must be beyond the stack extreme boundary. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that exact contact at the stacked high-side extreme boundary is insufficient for Step 2 qualification; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH/ONH 101.
- Direction = SHORT.
- Stack components are PMH 100 and ONH 101.
- The controlling high-side stack extreme boundary is ONH 101.
- Candle closes exactly at the stack extreme boundary at 101.0.
- Step 2 rejection does not activate because the completed close is not beyond the active stacked liquidity boundary.

Approved Rules Added:

50. For a stacked high-side rejection setup, a completed candle close exactly at the stack extreme boundary does not qualify Step 2; the close must be beyond the stack extreme boundary.

### stacked_low/body_close_exactly_at_extreme_boundary

| Field | Value |
| --- | --- |
| Fixture | stacked_low/body_close_exactly_at_extreme_boundary |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked low-side rejection setup, a completed candle close exactly at the stack extreme boundary does not qualify Step 2; the close must be beyond the stack extreme boundary. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that exact contact at the stacked low-side extreme boundary is insufficient for Step 2 qualification; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML/ONL 99.
- Direction = LONG.
- Stack components are PML 100 and ONL 99.
- The controlling low-side stack extreme boundary is ONL 99.
- Candle closes exactly at the stack extreme boundary at 99.0.
- Step 2 rejection does not activate because the completed close is not beyond the active stacked liquidity boundary.

Approved Rules Added:

51. For a stacked low-side rejection setup, a completed candle close exactly at the stack extreme boundary does not qualify Step 2; the close must be beyond the stack extreme boundary.

### stacked_high/close_inside_stack_not_through_extreme

| Field | Value |
| --- | --- |
| Fixture | stacked_high/close_inside_stack_not_through_extreme |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked high-side rejection setup, a completed candle close inside the stack, but not beyond the stack extreme boundary, does not qualify Step 2. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that a close between stacked high-side components is insufficient for Step 2 qualification unless the close is beyond the stack extreme boundary; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH/ONH 101.
- Direction = SHORT.
- Stack components are PMH 100 and ONH 101.
- The controlling high-side stack extreme boundary is ONH 101.
- Candle closes inside the stack at 100.5.
- Step 2 rejection does not activate because the completed close is not beyond the active stacked liquidity boundary.

Approved Rules Added:

52. For a stacked high-side rejection setup, a completed candle close inside the stack, but not beyond the stack extreme boundary, does not qualify Step 2.

### stacked_low/close_inside_stack_not_through_extreme

| Field | Value |
| --- | --- |
| Fixture | stacked_low/close_inside_stack_not_through_extreme |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked low-side rejection setup, a completed candle close inside the stack, but not beyond the stack extreme boundary, does not qualify Step 2. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that a close between stacked low-side components is insufficient for Step 2 qualification unless the close is beyond the stack extreme boundary; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML/ONL 99.
- Direction = LONG.
- Stack components are PML 100 and ONL 99.
- The controlling low-side stack extreme boundary is ONL 99.
- Candle closes inside the stack at 99.5.
- Step 2 rejection does not activate because the completed close is not beyond the active stacked liquidity boundary.

Approved Rules Added:

53. For a stacked low-side rejection setup, a completed candle close inside the stack, but not beyond the stack extreme boundary, does not qualify Step 2.

### stacked_high/close_through_first_component_not_extreme

| Field | Value |
| --- | --- |
| Fixture | stacked_high/close_through_first_component_not_extreme |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked high-side rejection setup, a completed candle close through a non-extreme stack component, but not beyond the stack extreme boundary, does not qualify Step 2. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that closing through the first high-side stack component is insufficient for Step 2 qualification unless the close is beyond the stack extreme boundary; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH/ONH 101.
- Direction = SHORT.
- Stack components are PMH 100 and ONH 101.
- The controlling high-side stack extreme boundary is ONH 101.
- Candle closes beyond PMH at 100.25 but remains below ONH 101.
- Step 2 rejection does not activate because the completed close is not beyond the active stacked liquidity boundary.

Approved Rules Added:

54. For a stacked high-side rejection setup, a completed candle close through a non-extreme stack component, but not beyond the stack extreme boundary, does not qualify Step 2.

### stacked_low/close_through_first_component_not_extreme

| Field | Value |
| --- | --- |
| Fixture | stacked_low/close_through_first_component_not_extreme |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked low-side rejection setup, a completed candle close through a non-extreme stack component, but not beyond the stack extreme boundary, does not qualify Step 2. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that closing through the first low-side stack component is insufficient for Step 2 qualification unless the close is beyond the stack extreme boundary; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML/ONL 99.
- Direction = LONG.
- Stack components are PML 100 and ONL 99.
- The controlling low-side stack extreme boundary is ONL 99.
- Candle closes beyond PML at 99.75 but remains above ONL 99.
- Step 2 rejection does not activate because the completed close is not beyond the active stacked liquidity boundary.

Approved Rules Added:

55. For a stacked low-side rejection setup, a completed candle close through a non-extreme stack component, but not beyond the stack extreme boundary, does not qualify Step 2.

### stacked_high/close_through_lower_priority_component_only

| Field | Value |
| --- | --- |
| Fixture | stacked_high/close_through_lower_priority_component_only |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked high-side rejection setup, a completed candle close through only the lower-priority non-extreme stack component does not qualify Step 2 when the close is not beyond the stack extreme boundary. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that closing through only the lower-priority high-side stack component is insufficient for Step 2 qualification unless the close is beyond the stack extreme boundary; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH/ONH 101.
- Direction = SHORT.
- Stack components are PMH 100 and ONH 101.
- The controlling high-side stack extreme boundary is ONH 101.
- Candle closes beyond lower-priority PMH at 100.25 but remains below ONH 101.
- Step 2 rejection does not activate because the completed close is not beyond the active stacked liquidity boundary.

Approved Rules Added:

56. For a stacked high-side rejection setup, a completed candle close through only the lower-priority non-extreme stack component does not qualify Step 2 when the close is not beyond the stack extreme boundary.

### stacked_low/close_through_lower_priority_component_only

| Field | Value |
| --- | --- |
| Fixture | stacked_low/close_through_lower_priority_component_only |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked low-side rejection setup, a completed candle close through only the lower-priority non-extreme stack component does not qualify Step 2 when the close is not beyond the stack extreme boundary. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that closing through only the lower-priority low-side stack component is insufficient for Step 2 qualification unless the close is beyond the stack extreme boundary; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML/ONL 99.
- Direction = LONG.
- Stack components are PML 100 and ONL 99.
- The controlling low-side stack extreme boundary is ONL 99.
- Candle closes beyond lower-priority PML at 99.75 but remains above ONL 99.
- Step 2 rejection does not activate because the completed close is not beyond the active stacked liquidity boundary.

Approved Rules Added:

57. For a stacked low-side rejection setup, a completed candle close through only the lower-priority non-extreme stack component does not qualify Step 2 when the close is not beyond the stack extreme boundary.

### stacked_high/wick_through_extreme_close_back_inside_stack

| Field | Value |
| --- | --- |
| Fixture | stacked_high/wick_through_extreme_close_back_inside_stack |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked high-side rejection setup, a wick through the stack extreme boundary does not qualify Step 2 unless the completed candle close is beyond the stack extreme boundary. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that wick penetration through the stacked high-side extreme boundary is insufficient for Step 2 qualification when the completed close returns inside the stack; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH/ONH 101.
- Direction = SHORT.
- Stack components are PMH 100 and ONH 101.
- The controlling high-side stack extreme boundary is ONH 101.
- Candle wick extends beyond ONH to 101.5.
- Candle closes back inside the stack at 100.5.
- Step 2 rejection does not activate because the completed close is not beyond the active stacked liquidity boundary.

Approved Rules Added:

58. For a stacked high-side rejection setup, a wick through the stack extreme boundary does not qualify Step 2 unless the completed candle close is beyond the stack extreme boundary.

### stacked_low/wick_through_extreme_close_back_inside_stack

| Field | Value |
| --- | --- |
| Fixture | stacked_low/wick_through_extreme_close_back_inside_stack |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked low-side rejection setup, a wick through the stack extreme boundary does not qualify Step 2 unless the completed candle close is beyond the stack extreme boundary. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that wick penetration through the stacked low-side extreme boundary is insufficient for Step 2 qualification when the completed close returns inside the stack; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML/ONL 99.
- Direction = LONG.
- Stack components are PML 100 and ONL 99.
- The controlling low-side stack extreme boundary is ONL 99.
- Candle wick extends beyond ONL to 98.5.
- Candle closes back inside the stack at 99.5.
- Step 2 rejection does not activate because the completed close is not beyond the active stacked liquidity boundary.

Approved Rules Added:

59. For a stacked low-side rejection setup, a wick through the stack extreme boundary does not qualify Step 2 unless the completed candle close is beyond the stack extreme boundary.

### stacked_low/stack_display_ownership_name

| Field | Value |
| --- | --- |
| Fixture | stacked_low/stack_display_ownership_name |
| Category | Stacked Liquidity / Display Ownership |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked low-side rejection setup, when Step 2 activates against a stacked liquidity owner, the active liquidity display name must preserve the stack ownership name. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents that stacked low-side Step 2 activation reports the stack owner as PML/ONL Liquidity; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML/ONL 99.
- Direction = LONG.
- Stack components are PML 100 and ONL 99.
- Candle closes beyond the controlling low-side stack extreme boundary at 98.75.
- Step 2 rejection activates.
- Active liquidity name is reported as PML/ONL Liquidity.

Approved Rules Added:

60. For a stacked low-side rejection setup, when Step 2 activates against a stacked liquidity owner, the active liquidity display name must preserve the stack ownership name.

### stacked_high/stack_display_ownership_name

| Field | Value |
| --- | --- |
| Fixture | stacked_high/stack_display_ownership_name |
| Category | Stacked Liquidity / Display Ownership |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a stacked high-side rejection setup, when Step 2 activates against a stacked liquidity owner, the active liquidity display name must preserve the stack ownership name. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents that stacked high-side Step 2 activation reports the stack owner as PMH/ONH Liquidity; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH/ONH 101.
- Direction = SHORT.
- Stack components are PMH 100 and ONH 101.
- Candle closes beyond the controlling high-side stack extreme boundary at 101.25.
- Step 2 rejection activates.
- Active liquidity name is reported as PMH/ONH Liquidity.

Approved Rules Added:

61. For a stacked high-side rejection setup, when Step 2 activates against a stacked liquidity owner, the active liquidity display name must preserve the stack ownership name.

### regular_long/wick_beyond_close_back_inside

| Field | Value |
| --- | --- |
| Fixture | regular_long/wick_beyond_close_back_inside |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked long rejection setup, a wick beyond active low-side liquidity does not qualify Step 2 unless the completed candle close is beyond the active liquidity level. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that wick penetration alone is insufficient for Step 2 qualification when the completed close returns inside the regular low-side liquidity level; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML 100.
- Direction = LONG.
- No stack is present.
- Candle wick extends beyond active low-side liquidity to 99.5.
- Candle closes back inside active low-side liquidity at 100.25.
- Step 2 rejection does not activate because the completed close is not beyond the active liquidity boundary.

Approved Rules Added:

62. For a regular non-stacked long rejection setup, a wick beyond active low-side liquidity does not qualify Step 2 unless the completed candle close is beyond the active liquidity level.

### regular_short/wick_touches_liquidity_close_not_beyond

| Field | Value |
| --- | --- |
| Fixture | regular_short/wick_touches_liquidity_close_not_beyond |
| Category | Regular Liquidity / Close-Through Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked short rejection setup, a wick touch of active high-side liquidity does not qualify Step 2 unless the completed candle close is beyond the active liquidity level. |
| Expected Result | ignored |
| Notes | User reviewed and approved. This fixture documents that wick contact alone is insufficient for Step 2 qualification when the completed close is not beyond the regular high-side liquidity level; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PMH 100.
- Direction = SHORT.
- No stack is present.
- Candle wick touches active high-side liquidity at 100.0.
- Candle closes below active high-side liquidity at 99.5.
- Step 2 rejection does not activate because the completed close is not beyond the active liquidity boundary.

Approved Rules Added:

63. For a regular non-stacked short rejection setup, a wick touch of active high-side liquidity does not qualify Step 2 unless the completed candle close is beyond the active liquidity level.

### edge_cases/multiple_levels_nearby_active_controls

| Field | Value |
| --- | --- |
| Fixture | edge_cases/multiple_levels_nearby_active_controls |
| Category | Active Liquidity Selection / Nearby Levels |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | Nearby same-side stack candidates must be explicitly included in the stack components before Step 2 approval. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved after fixture rework. Nearby same-side ONL is explicitly included in the PML/ONL stack; no Step 2 close-through logic change is implied. |

### edge_cases/newer_lower_priority_nearby_does_not_take_owner

| Field | Value |
| --- | --- |
| Fixture | edge_cases/newer_lower_priority_nearby_does_not_take_owner |
| Category | Stacked Liquidity / Active Ownership |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a manually configured stacked low-side rejection setup, a nearby lower-priority low level does not replace the configured active stack owner. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents that the configured PML/ONL stack remains the active owner even when a nearby lower-priority LL is present; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML/ONL 99.
- Direction = LONG.
- Configured stack components are PML 100 and ONL 99.
- Nearby lower-priority LL is present at 99.25.
- Step 2 rejection activates against PML/ONL Liquidity.
- LL does not replace the configured active stack owner.

Approved Rules Added:

64. For a manually configured stacked low-side rejection setup, a nearby lower-priority low level does not replace the configured active stack owner.

### edge_cases/slightly_separated_stack_components

| Field | Value |
| --- | --- |
| Fixture | edge_cases/slightly_separated_stack_components |
| Category | Stacked Liquidity / Extreme Boundary Qualification |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a manually configured stacked low-side rejection setup with separated components, a completed candle close beyond the extreme stack component qualifies Step 2. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents close-through qualification for a configured low-side stack whose components are separated in price; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML/ONL 99.
- Direction = LONG.
- Configured stack components are PML 100 and ONL 99.
- The controlling low-side stack extreme boundary is ONL 99.
- Candle closes beyond the stack extreme boundary at 98.75.
- Step 2 rejection activates against PML/ONL Liquidity.

Approved Rules Added:

65. For a manually configured stacked low-side rejection setup with separated components, a completed candle close beyond the extreme stack component qualifies Step 2.

### edge_cases/opens_beyond_level_closes_beyond_level

| Field | Value |
| --- | --- |
| Fixture | edge_cases/opens_beyond_level_closes_beyond_level |
| Category | Close-Through Qualification / Open Beyond Level |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | For a regular non-stacked long rejection setup, a candle that opens beyond active low-side liquidity and completes with a close still beyond that liquidity qualifies Step 2 on the completed close. |
| Expected Result | valid_step2 |
| Notes | User reviewed and approved. This fixture documents that Step 2 activation is based on the completed close remaining beyond active low-side liquidity even when the candle opened beyond the level; no Step 2 logic change is implied. |

Approved Result:

- Active Liquidity = PML 100.
- Direction = LONG.
- No stack is present.
- Candle opens beyond active low-side liquidity at 99.5.
- Candle closes beyond active low-side liquidity at 99.5.
- Step 2 rejection activates because the completed close is beyond the active liquidity boundary.

Approved Rules Added:

66. For a regular non-stacked long rejection setup, a candle that opens beyond active low-side liquidity and completes with a close still beyond that liquidity qualifies Step 2 on the completed close.

## Open Items

- Open item: continuation controlling boundary must be derived from prior/pre-close structure, not from the Step 2 close candle extreme. Requires multi-candle fixture validation before approval.
- Resolved and approved fixture-construction item: edge_cases/multiple_levels_nearby_active_controls was reworked to explicitly include nearby same-side ONL in the PML/ONL stack.
- Resolved and approved fixture-construction item: edge_cases/london_pm_on_priority_owner_configured was reworked to explicitly include nearby same-side LL in the PML/ONL/LL stack.
