# Step 2 Continuation Tracking

## Approved Fixtures

### wick_reset/lower_wick_below_does_not_activate

| Field | Value |
| --- | --- |
| Fixture | wick_reset/lower_wick_below_does_not_activate |
| Category | Wick Reset / Updated Continuation Boundary |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | A wick below active lower continuation-side liquidity does not activate Step 2 continuation when the candle closes back inside; it resets the future lower qualifying boundary to the wick low. |
| Expected Result | WAIT |
| Notes | User reviewed and approved. This fixture documents lower-side continuation wick-reset behavior; no live Step 2 strategy logic change is implied. |

Approved Result:

- Active Liquidity = PML 100.
- Continuation Type = R/S.
- Candle wicks below PML to 99.5.
- Candle closes back above PML at 100.25.
- Step 2 continuation remains WAIT.
- Future lower qualifying boundary resets to 99.5.

### wick_reset/lower_close_below_original_above_wick_boundary_waits

| Field | Value |
| --- | --- |
| Fixture | wick_reset/lower_close_below_original_above_wick_boundary_waits |
| Category | Wick Reset / Updated Continuation Boundary |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | After a lower continuation wick reset, a later close below the original liquidity price but above the wick-low boundary does not activate Step 2 continuation. |
| Expected Result | WAIT |
| Notes | User reviewed and approved. This fixture confirms continuation qualification is evaluated against the updated wick boundary, not the original lower liquidity price. |

Approved Result:

- Original Active Liquidity = PML 100.
- Wick-reset boundary = 99.5.
- Later candle closes below original PML at 99.75.
- Later candle remains above wick-reset boundary 99.5.
- Step 2 continuation remains WAIT.

### wick_reset/lower_close_beyond_wick_boundary_activates

| Field | Value |
| --- | --- |
| Fixture | wick_reset/lower_close_beyond_wick_boundary_activates |
| Category | Wick Reset / Updated Continuation Boundary |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | After a lower continuation wick reset, a later close beyond the wick-low boundary activates Step 2 continuation. |
| Expected Result | ACTIVE |
| Notes | User reviewed and approved. This fixture is the activating counterpart to the lower continuation wick-reset wait case. |

Approved Result:

- Original Active Liquidity = PML 100.
- Wick-reset boundary = 99.5.
- Later candle closes beyond wick-reset boundary at 99.25.
- Step 2 continuation activates against the updated lower boundary.

### wick_reset/upper_wick_above_does_not_activate

| Field | Value |
| --- | --- |
| Fixture | wick_reset/upper_wick_above_does_not_activate |
| Category | Wick Reset / Updated Continuation Boundary |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | A wick above active upper continuation-side liquidity does not activate Step 2 continuation when the candle closes back inside; it resets the future upper qualifying boundary to the wick high. |
| Expected Result | WAIT |
| Notes | User reviewed and approved. This fixture documents upper-side continuation wick-reset behavior; no live Step 2 strategy logic change is implied. |

Approved Result:

- Active Liquidity = PMH 100.
- Continuation Type = S/R.
- Candle wicks above PMH to 100.5.
- Candle closes back below PMH at 99.75.
- Step 2 continuation remains WAIT.
- Future upper qualifying boundary resets to 100.5.

### wick_reset/upper_close_above_original_below_wick_boundary_waits

| Field | Value |
| --- | --- |
| Fixture | wick_reset/upper_close_above_original_below_wick_boundary_waits |
| Category | Wick Reset / Updated Continuation Boundary |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | After an upper continuation wick reset, a later close above the original liquidity price but below the wick-high boundary does not activate Step 2 continuation. |
| Expected Result | WAIT |
| Notes | User reviewed and approved. This fixture confirms continuation qualification is evaluated against the updated wick boundary, not the original upper liquidity price. |

Approved Result:

- Original Active Liquidity = PMH 100.
- Wick-reset boundary = 100.5.
- Later candle closes above original PMH at 100.25.
- Later candle remains below wick-reset boundary 100.5.
- Step 2 continuation remains WAIT.

### wick_reset/upper_close_beyond_wick_boundary_activates

| Field | Value |
| --- | --- |
| Fixture | wick_reset/upper_close_beyond_wick_boundary_activates |
| Category | Wick Reset / Updated Continuation Boundary |
| Status | APPROVED PASS |
| User Review | APPROVED |
| Rule Approved | After an upper continuation wick reset, a later close beyond the wick-high boundary activates Step 2 continuation. |
| Expected Result | ACTIVE |
| Notes | User reviewed and approved. This fixture is the activating counterpart to the upper continuation wick-reset wait case. |

Approved Result:

- Original Active Liquidity = PMH 100.
- Wick-reset boundary = 100.5.
- Later candle closes beyond wick-reset boundary at 100.75.
- Step 2 continuation activates against the updated upper boundary.

Approved Rules Added:

1. Wick through continuation-side liquidity activates nothing when the completed candle closes back inside the active continuation boundary.
2. Wick through continuation-side liquidity resets the future Step 2 continuation qualifying boundary to the wick extreme.
3. After a lower continuation wick reset, a later close below the original liquidity price but above the wick-low boundary does not activate Step 2 continuation.
4. After a lower continuation wick reset, only a later close beyond the wick-low boundary activates Step 2 continuation.
5. After an upper continuation wick reset, a later close above the original liquidity price but below the wick-high boundary does not activate Step 2 continuation.
6. After an upper continuation wick reset, only a later close beyond the wick-high boundary activates Step 2 continuation.
