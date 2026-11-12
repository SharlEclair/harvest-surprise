# Water, rice, and the first real link

## The chain

Spring water in the Sierra Nevada decides how much surface water California
allocates. Allocation decides how much rice gets planted. Rice is the most
water-responsive field crop in the state, and its acreage is a number the market
trades but nobody publishes until June.

Every link in that chain is measurable with free data:

- **storage** — CDEC daily gauges, 10 reservoirs, 1990-2025, keyless;
- **storage, from space** — the validated Sentinel-2 measurement in
  `RESERVOIR.md` (Spearman 0.71-0.89 against the gauge);
- **acreage** — NASS Quick Stats, California rice, 1990-2025;
- **price** — rough rice futures `ZR=F` from Yahoo, 1999-2025.

## Result 1: storage predicts planted acreage

`analysis/water_rice.py`, dependent variable is log planted acres, predictor is
log 1 April total storage across ten major reservoirs.

| specification | elasticity | std. error | t | R² | n |
|---|---|---|---|---|---|
| trend only | — | — | — | — | 36 |
| **+ log storage** | **+0.407** | 0.078 | **+5.24** | 0.455 | 36 |
| 1990-2020 only (used out of sample) | +0.281 | 0.057 | +4.97 | - | 31 |
| 1990-2014 only | +0.265 | 0.042 | +6.26 | - | 25 |
| + trend + log rice price | **+0.488** | 0.120 | **+4.05** | 0.523 | 27 |
| placebo: next year's storage | +0.165 | 0.103 | +1.60 | — | 35 |

Reading: a **10% increase in spring storage is associated with 4-5% more rice
acreage**, the coefficient survives a rice-price control, and the placebo - using
next year's water, which cannot cause this year's planting - is a third the size
and not significant.

This is a genuine physical-to-economic link on free data, and it is the first
result in this project that is both well-powered and economically meaningful.

## Result 2: storage and the June acreage revision (suggestive only)

NASS publishes prospective plantings on 31 March and the acreage estimate on
30 June. The revision between them is what a trader would care about, and April
storage is known before either.

`analysis/rice_surprise.py`:

- Only **8 years** have both the March and June series for California rice
  (2018-2025). That is the binding constraint, not the model.
- On those 8: elasticity +0.405 (t +4.15), R² 0.742, direction hit 100%,
  leave-one-out skill +38% against predicting no revision.

**Eight observations and a two-parameter fit is not evidence.** A 100% hit rate
on eight points is exactly what overfitting looks like. It is reported because it
is the right test to run, and it must be re-run when the March series is longer.

## What is still missing

**The price leg is not retrieved.** CAISO OASIS rejects both hub node
identifiers (`TH_NP15_GEN-APND`, `TH_SP15_GEN-APND`) with `ERR_CODE 1001,
Invalid Parameters of the given report name`, the node-list queries return
`INVALID_REQUEST`, and unpaced request bursts return 429. Without a working node
identifier there is no electricity price series, so the water-to-power link
stays untested.

This matters because the power link was the more interesting one: rice acreage
is a small market, while hydro and power are large. The alternative pursued here
is honest but secondary.

## What "production ready" would require

1. Replace the gauge with the **satellite storage estimate** as the predictor,
   for the years it covers, and show the chain still holds. That is the whole
   point: a measurement that works where no gauge exists.
2. Extend to the **Murray-Darling**, where BOM publishes free daily storage for
   hundreds of dams and rice is again the water-responsive crop.
3. Rebuild the revision test when the March series is long enough, and add the
   futures reaction to the 30 June report.
4. Package: one command, tests on the joins, and a data dictionary.

## Files

| File | What |
|---|---|
| `analysis/water_rice.py` | storage -> acreage, with price control and placebo |
| `analysis/rice_surprise.py` | storage -> June-vs-March revision (n=8, flagged) |
| `data/processed/water_rice.csv` | merged panel, 36 years |
| `data/processed/rice_surprise.csv` | the 8 revision years |
| `data/raw/rice_price.csv` | annual mean `ZR=F` |
| `data/processed/water_rice.png`, `rice_surprise.png` | figures |
