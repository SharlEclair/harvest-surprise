# ingest — NASS Quick Stats

Two scripts, no dependencies beyond `pandas` and `requests`.

```powershell
$env:NASS_API_KEY = "..."          # or put NASS_API_KEY=... in ../.env
python ingest/nass.py              # ~3 min, writes ../data/raw/*.csv
python ingest/verify.py            # 14 assertions, exit 0 = pass
```

## What comes back

All state-level, corn, 2000–2025 unless noted. Quick Stats returns the full
history for these filters, so the files actually start much earlier (yield from
1866).

| file | rows | grain |
|---|---|---|
| `nass_yield.csv` | 14,121 | `reference_period_desc` ∈ {`YEAR`, `YEAR - AUG FORECAST`, `- SEP`, `- OCT`, `- NOV`} × 41 states |
| `nass_area_harvested.csv` | 10,199 | acres, by state-year |
| `nass_area_planted.csv` | 6,718 | acres, by state-year |
| `nass_condition.csv` | 82,414 | weekly, `week_ending` 2000-05-21 → 2025-11-16, five percentage categories per state-week |

`*_FORECAST` rows are the find that matters. NASS publishes the state yields it
was forecasting in each WASDE, so the "surprise" target does not need the
paywalled analyst consensus: it can be defined as *model estimate minus the
forecast NASS itself published*, which is public, dated, and exactly what the
market prices around. Median |Aug forecast − final| is 6.0 bu/ac at state level
(n = 1,692 state-years), and 92 % of August forecasts are subsequently revised.

## Gotchas, both measured rather than read

1. **`year__GE` / `year__LE` do not filter.** `year__GE=2020&year__LE=2020`
   returns 31,120 condition rows; `year=2020` returns 4,835. The range form
   silently returns more than the bracket. Use exact `year=` and filter locally,
   or you will quietly pull three decades of data into a "single year".
2. **`AREA PLANTED` rejects `util_practice_desc=GRAIN`** with HTTP 400. Planted
   area is not split by use, so the filter is invalid there and valid for
   `AREA HARVESTED` and `YIELD`.
3. A single response caps at 50,000 rows, so weekly condition has to be pulled
   one year at a time (82k rows total).

## Validation

`verify.py` is not decoration. It checks that state yields weighted by harvested
acres reconcile to the published national number — 177.3 bu/ac for 2023 and
179.3 for 2024, both reproduced to 0.1 — plus no duplicate state-year-period
rows, forecast periods present, condition percentages summing to 100, and
planted ≥ harvested.

Two of the original assertions failed on first run because I had written the
expected Iowa and Illinois yields from memory (200 and 214). The data said 201
and 206. The data was right; the test was wrong. Replaced with the
acreage-weighted reconciliation, which does not depend on my memory.
