# Context Final Decisions

## PM%

Formula:

```text
PM% = ((PMH - PML) / Daily ATR) * 100
```

Final buckets:

- `0-20`: `COMPRESSED`
- `20-40`: `NORMAL`
- `40-60`: `EXPANDED`
- `60+`: `STRETCHED`

## DR%

Formula:

```text
DR% = ((current high - current low) / Daily ATR) * 100
```

Final buckets:

- `0-35`: `LOW_USED`
- `35-70`: `HEALTHY`
- `70-100`: `MATURE`
- `100+`: `EXHAUSTED`

Range decision:

- DR% uses full session range, not RTH only.

## London Bias

London Bias uses a scoring model combining:

- Close in upper/lower half.
- Direction into US open.
- Sweep/reclaim of LH/LL.

## ATR Volatility

Final categories:

- `LOW`
- `NORMAL`
- `ACTIVE`
- `EXTREME`

## Day Profile

Final categories:

- `BALANCED`
- `EXPANSION_POTENTIAL`
- `DIRECTIONAL`
- `EXHAUSTED`
- `UNKNOWN`

## Usage Rule

- Context cannot authorize trades.
- Gateway authorizes.
- Structure triggers.
