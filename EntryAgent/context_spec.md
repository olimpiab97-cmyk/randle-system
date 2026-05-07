# Context Engine Spec

## 1. PM% Read Ranges + Meaning

`PM%` measures premarket range as a percentage of daily ATR.

Formula:

```text
PM% = ((PMH - PML) / Daily ATR) * 100
```

Ranges:

- `0-25%`: compressed premarket range.
- `25-50%`: normal premarket development.
- `50-75%`: wide premarket range.
- `75%+`: expanded premarket range.

Meaning:

- Lower PM% means less premarket range has been used.
- Higher PM% means more daily range has already been built before regular-session execution.

## 2. DR% Read Ranges + Meaning

`DR%` measures current day range as a percentage of daily ATR.

Formula:

```text
DR% = ((current high - current low) / Daily ATR) * 100
```

Ranges:

- `0-50%`: limited day range used.
- `50-75%`: moderate day range used.
- `75-100%`: high day range usage.
- `100%+`: full ATR day or extended range day.

Meaning:

- Lower DR% means the session still has unused daily range.
- Higher DR% means the session has already consumed a large portion of expected daily range.

## 3. London Bias Rules

London Bias uses London session high, low, and close.

Rules:

- `BULLISH`: London close is above the midpoint of London high/low.
- `BEARISH`: London close is below the midpoint of London high/low.
- `NEUTRAL`: London close is exactly at the midpoint.
- `UNKNOWN`: missing high, low, close, or invalid London range.

Formula:

```text
London midpoint = (London high + London low) / 2
```

Meaning:

- Bullish bias means London closed in the upper half of its range.
- Bearish bias means London closed in the lower half of its range.
- Neutral means London closed at range midpoint.

## 4. ATR Volatility Ranges + Meaning

ATR Volatility compares current 1-minute ATR to daily ATR.

Formula:

```text
ATR Volatility % = (current 1m ATR / Daily ATR) * 100
```

Ranges:

- `< 0.10%`: `COMPRESSED`
- `0.10%-0.35%`: `NORMAL`
- `> 0.35%`: `EXPANDED`
- Missing or invalid data: `UNKNOWN`

Meaning:

- `COMPRESSED`: current 1-minute movement is small relative to daily ATR.
- `NORMAL`: current 1-minute movement is within expected range.
- `EXPANDED`: current 1-minute movement is elevated relative to daily ATR.
- `UNKNOWN`: insufficient input quality for classification.

## 5. Day Profile Categories

Day Profile combines PM%, DR%, and London Bias.

Categories:

- `BALANCED`
- `DEVELOPING`
- `DIRECTIONAL_PREMARKET`
- `FULL_ATR_DAY`
- `UNKNOWN`

Rules:

- `UNKNOWN`: PM% or DR% is missing.
- `FULL_ATR_DAY`: DR% is `100%+`.
- `DIRECTIONAL_PREMARKET`: PM% is `50%+` and London Bias is `BULLISH` or `BEARISH`.
- `BALANCED`: PM% is `< 25%` and DR% is `< 50%`.
- `DEVELOPING`: all other valid combinations.

Meaning:

- `BALANCED`: compressed or contained conditions.
- `DEVELOPING`: range and bias are still forming.
- `DIRECTIONAL_PREMARKET`: premarket built meaningful range with directional London close.
- `FULL_ATR_DAY`: daily ATR has already been reached or exceeded.
- `UNKNOWN`: required context is incomplete.
