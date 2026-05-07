# Context Decisions

Purpose: refine business decisions for Context Engine before changing code.

## 1. PM% Read

- Keep formula: `PM% = ((PMH - PML) / Daily ATR) * 100`
- Decision needed: exact bucket thresholds
- Current draft: `0-25` compressed, `25-50` normal, `50-75` wide, `75+` expanded
- Note: PM% is environmental context, not an entry trigger

## 2. DR% Read

- Keep formula: `DR% = ((current high - current low) / Daily ATR) * 100`
- Decision needed: whether DR% should include overnight/premarket + RTH current range, or RTH-only after 6:30
- Current draft: `0-50` limited, `50-75` moderate, `75-100` high, `100+` full ATR day
- Note: DR% affects target/risk expectations, not entry permission

## 3. London Bias

- Current draft midpoint rule is v1 only
- Decision needed: whether final London Bias should include:
  - swept London High/Low and reclaimed
  - close location relative to midpoint
  - direction into 6:15/6:30 PT
  - whether London High/Low is still active liquidity
- Note: midpoint-only is acceptable for v1 but not final edge

## 4. ATR Volatility Read

- Current draft compares current 1m ATR to Daily ATR
- Decision needed: whether better version should compare current 1m ATR to historical opening-session 1m ATR baseline
- v1 may remain simple until baseline data exists
- Note: volatility read adjusts aggressiveness and expectations

## 5. Day Profile

- Current categories: `BALANCED`, `DEVELOPING`, `DIRECTIONAL_PREMARKET`, `FULL_ATR_DAY`, `UNKNOWN`
- Decision needed: whether to simplify later to:
  - `BALANCED`
  - `EXPANSION_POTENTIAL`
  - `DIRECTIONAL`
  - `EXHAUSTED`
  - `UNKNOWN`
- Note: day_profile should not block trades by itself; it should influence quality scoring

## 6. Entry Engine Usage Rules

- Context Engine does not authorize trades
- Gateway Engine authorizes whether entries may be evaluated
- Context Engine modifies setup quality, aggressiveness, target expectations, and caution flags
- Step2/Entry logic must still require actual structure
