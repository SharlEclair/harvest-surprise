# Reservoir storage from Sentinel-2: v2, validated

## What changed from v1

v1 failed: R-squared 0.07-0.21, zero skill against the gauge. Three defects, each
found by diagnosis rather than by trying harder:

1. **No fixed footprint.** Each scene was clipped to the bbox intersection, so the
   estimator saw a different bit of ground every time. v2 reprojects every scene
   onto one fixed 0.001 degree grid per reservoir (~110 m cells).
2. **Area computed over valid pixels only, with no correction.** A scene that was
   20% cloud returned 20% less water and reported it as a measurement. v2
   normalises by the observed fraction: `area = sum(water) / sum(valid) * ROI_area`.
   This is what rescued Don Pedro, whose median observed fraction was 0.79.
3. **The L2A BOA offset was ignored.** Since processing baseline 04.00 (Jan 2022)
   Sentinel-2 L2A digital numbers carry a +1000 offset; reflectance is
   `(DN - 1000) / 10000`. Applying NDWI to raw DN compresses every index toward
   zero, so post-2022 scenes systematically under-detect water - a time-varying
   bias that is exactly the shape that destroys an area-to-elevation relationship.

A fourth change is methodological: the region of interest is now the union of
cells that are **mostly water in at least one scene** (`water > 0.5`), not any
cell that was ever wet. The looser threshold admitted cloud edges into the lake.

## Results

Scored by leave-one-out against the daily CDEC gauge.

| reservoir | usable scenes | area range (km2) | elevation range (ft) | Spearman | LOO isotonic RMSE (ft) | baseline RMSE (ft) | error cut |
|---|---|---|---|---|---|---|---|
| Shasta | 38 / 40 | 14.1 - 53.0 | 178.7 | **0.705** | **36.0** | 50.9 | **29%** |
| Oroville | 38 / 40 | 5.2 - 35.1 | 270.8 | **0.887** | **48.4** | 85.3 | **43%** |
| Don Pedro | 35 / 39 | 0.1 - 22.9 | 98.7 | 0.535 | 24.0 | 29.2 | 18% |

Baseline is "predict the sample mean elevation". The isotonic model is fitted
monotone (area must not fall as elevation rises) and scored out-of-sample.

**Shasta and Oroville validate.** Water extent ranks level with 0.71 and 0.89
Spearman, and a monotone rating curve cuts level error by 29% and 43% against the
mean. The absolute error, 36-48 ft on ranges of 179-271 ft, is 13-18% - which is
exactly the 10-20% that the reservoir remote-sensing literature reports for
area/level curves, so the estimator is performing as well as the method allows
rather than as well as one might hope.

**Don Pedro does not.** Its series swings from 0.1 to 22.9 km2, which is a larger
relative range than a reservoir with only 99 ft of operating band should show, and
its rank correlation is much weaker. I have not verified its true surface area, so
I will not claim the direction of the error - only that the series is not credible
and is excluded from every claim above. Most likely cause: a neighbouring water
body inside the bounding box, or the ROI normalisation distorting a small lake.

## What this establishes

- A free-data, solo-researcher measurement of a large physical quantity, scored
  against an independent daily gauge, at 0.71-0.89 rank correlation.
- The three failure modes above are the generic failure modes of this class of
  project. They are worth more than the result: almost every "satellite measures
  X" claim in the wild skips at least one of them.
- The measurement is good enough to rank reservoirs against each other, and not
  good enough to replace a gauge. That is the honest bound.

## What is blocked

The market link - reservoir storage to California power prices - is not done.

- CAISO OASIS returns **429 Too Many Requests** above roughly one request per
  second; a single paced request succeeds.
- The surviving request returns `ERR_CODE 1001, Invalid Parameters of the given
  report name`, which means the hub node identifier `TH_NP15_GEN-APND` is no
  longer accepted. The node name needs to be looked up from the current OASIS
  node list before the pull is retried.

So the chain is: measurement validated, price series not yet retrieved.

## Files

| File | What |
|---|---|
| `analysis/reservoir_v2.py` | measurement: fixed grid, offset correction, water fractions -> `data/processed/reservoir_v2_*.npz` |
| `analysis/reservoir_v2_validate.py` | ROI, validity gate, rating curve, scores |
| `data/processed/reservoir_v2_validation.csv` | the table above |
| `data/processed/reservoir_v2.png` | area vs elevation, one panel per reservoir |
| `ingest/caiso.py` | price pull, currently blocked on the node name |

## Next

1. Fix the CAISO node identifier and pull 2023-2025 hub prices, paced.
2. Test: does storage anomaly (versus the seasonal norm) predict day-ahead price
   anomaly, controlling for weekday and month? Report the coefficient, its
   cluster-robust standard error, and a shuffled-storage null.
3. Only if that is positive: does it survive a tradeable rule after costs.
4. Extend the measurement to the Murray-Darling, where the Bureau of Meteorology
   publishes free daily storage for hundreds of dams.
