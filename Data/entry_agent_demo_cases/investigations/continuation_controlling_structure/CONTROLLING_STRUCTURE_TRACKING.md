# Continuation Controlling Structure Tracking

## Rule 6.3B Summary

Continuation entries require valid Shared Leg 1, valid Shared Leg 2, and a wick sweep of the active Continuation Controlling Structure. Without the controlling-structure sweep, entry permission remains WAIT_BLOCKED_NO_CONTROLLING_STRUCTURE_SWEEP. After the required sweep, continuation entry models may evaluate normally.

## Fixture List

All fixtures in this folder are investigations and are not approved yet.

1. sr_no_sweep_blocks_entry
2. sr_sweep_allows_entry
3. rs_no_sweep_blocks_entry
4. rs_sweep_allows_entry
5. sr_reset_on_bull_close_above_prior_bear_close
6. sr_new_bear_push_after_reset_becomes_controlling
7. sr_old_structure_swept_after_reset_does_not_allow_entry
8. sr_new_structure_swept_after_reset_allows_entry
9. rs_reset_on_bear_close_below_prior_bull_close
10. rs_new_bull_push_after_reset_becomes_controlling
11. rs_old_structure_swept_after_reset_does_not_allow_entry
12. rs_new_structure_swept_after_reset_allows_entry
13. sr_multi_candle_bear_push_last_uninterrupted_push_controls
14. rs_multi_candle_bull_push_last_uninterrupted_push_controls
15. sr_wick_sweep_before_reclaim_does_not_count
16. rs_wick_sweep_before_reclaim_does_not_count
17. sr_body_close_without_wick_sweep_does_not_count
18. rs_body_close_without_wick_sweep_does_not_count
19. sr_exact_touch_of_controlling_high
20. rs_exact_touch_of_controlling_low

## Approved

None yet.

## Investigations

All fixtures remain investigation cases pending user review.

## Open Questions

- Does exact touch count as sweep?
- Does sweep before reclaim count?
- Does body close beyond structure without wick sweep count?
