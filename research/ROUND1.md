# Round 1: comments, feasibility, and the first end-to-end test

## What was done

1. **Rebuilt the full comment corpus.** 535 comments (337 root, 198 replies),
   parsed into `comments_all.csv` with likes, parent ids and full text.
   **54 comments propose a trackable domain**, extracted in `CANDIDATES.md`.
2. **Built a physics filter** (`analysis/resolution_filter.py`) that scores every
   proposed signal on object size vs pixel size, signal timescale vs revisit, and
   whether the object is countable or only visible in aggregate
   (`resolution_grid.csv`).
3. **Researched the market side** of each signal family with sources
   (`FEASIBILITY.md`).
4. **Tested one candidate end to end**: reservoir storage from Sentinel-2 against
   CDEC gauges. It failed, and the failure is documented below.

## The three findings that change the project

### 1. Half the comment section is physically impossible, and the rest is already sold

The physics filter settles it in an afternoon rather than a weekend:

| Idea | Verdict |
|---|---|
| count cars individually | impossible at 10 m; only the parking lot as a whole works |
| count shipping containers | impossible at 10 m; only the stack |
| oil tank fill | countable at 30 m, so the video's "10 m is terrible" premise was overstated |
| reservoirs, mines, construction, stockpiles | countable at every free resolution |

And the market side: Kayrros already does **global** tank-roof measurement from the
**same free Sentinel-1** the video used; the Berkeley parking-lot study
(4.7M observations, 44 retailers) found a **4-5% edge that decayed as the data
became common**; the IMF publishes an AIS trade nowcast; the US Census Bureau
publishes an experimental **satellite housing-starts product**. The edge these
signals had came from data access, not analysis.

### 2. The video's own method is the least interesting part

The tank signal is capped physically: satellites read **external floating-roof
tanks only**. Fixed-roof tanks and underground caverns are invisible, and China
uses both deliberately. No amount of modelling fixes that.

### 3. Reservoir storage is the best remaining test case — and my first attempt failed

Why it is the right candidate: free daily ground truth exists (CDEC, 10
reservoirs, keyless), the object is huge, and the literature says most reservoirs
have **no validation at all**.

What I built: NDWI water mask on Sentinel-2 10 m bands with SCL cloud masking,
119 scenes across Shasta, Oroville and Don Pedro, 2021-2025, joined to the same
day's gauge reading, scored by leave-one-out on a linear area-to-elevation rating
curve.

**Result: it does not work.**

| reservoir | scenes | R²(area, elevation) | RMSE (ft) | baseline RMSE (ft) | skill |
|---|---|---|---|---|---|
| Shasta | 40 | 0.098 | 51.0 | 51.2 | 0.00 |
| Oroville | 40 | 0.070 | 80.8 | 83.8 | -0.03 |
| Don Pedro | 39 | 0.214 | 26.7 | 28.9 | 0.07 |

A rating curve with no skill is measuring noise. Diagnosis, from
`data/processed/reservoir_matched.csv`:

- **Some scenes measure zero water area** (Don Pedro range 0.0-16.5 km²,
  Oroville 0.0-32.8). A lake cannot have zero area, so the mask fails outright on
  a subset of scenes.
- **Cloud is not the cause.** Restricting to cloud cover below 5% does not improve
  R² (Shasta 0.094 vs 0.098). So this is not a cloud-contamination story.
- The likely causes, in order: (a) the area is computed over *valid* pixels only,
  so any masking shifts the denominator; (b) no fixed region of interest, so the
  estimator changes footprint between scenes; (c) possible misalignment between
  the 10 m B03 grid and the 20 m SCL resample; (d) the L2A processing-baseline
  BOA offset is not applied.

The fix is a rebuild, not a tweak: store a **water-fraction grid on a fixed ROI**
per reservoir (union of water masks), gate scenes on valid-fraction inside the
ROI, and only then fit the rating curve. That also makes the output a reusable
estimator rather than a per-scene area.

## What is ready now

| Artifact | Status |
|---|---|
| `research/comments_all.csv` | complete, 535 rows |
| `research/CANDIDATES.md` | complete, with physics verdicts |
| `research/FEASIBILITY.md` | complete, sourced, with a source-quality table |
| `analysis/resolution_filter.py` + `resolution_grid.csv` | complete, reproducible |
| `ingest/cdec.py` + `data/raw/cdec_reservoirs.csv` | complete, 32,870 station-days |
| `analysis/reservoir_area.py` | works but the estimator is wrong; superseded by the ROI rebuild |
| `analysis/reservoir_validate.py` | works, scores whatever the area script produces |

## Next round

1. Rebuild the reservoir estimator on a fixed ROI with a validity gate. Target:
   beat the baseline by a large margin or declare the signal unmeasurable.
2. Add the market link: CDEC storage -> CAISO day-ahead prices. The OASIS API is
   free and keyless and returns a ZIP of CSVs (verified: `PRC_LMP`, DAM, 200 OK).
3. If the reservoir measurement works, extend to the **Murray-Darling Basin**,
   which is where the user's own context is and where BOM publishes free daily
   storage for hundreds of dams.
4. Only after a validated measurement: does storage predict power prices, and
   does that beat the obvious alternatives.
