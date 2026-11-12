# Final report: from 535 comments to a measured, validated signal

**Session:** 2026-11-11. **Status:** research complete and packaged; not deployed.

---

## 1. What the objective asked, and what exists now

The brief was: read every comment and reply on the video, research everything
people proposed tracking, judge feasibility, test end to end, and find something
impressive that survives scrutiny, ideally tied to the themes in the existing
GitHub work.

| Asked | Delivered | State |
|---|---|---|
| Read all comments and replies | 535 comments parsed (337 root, 198 replies), 54 domain proposals extracted | done |
| Deep feasibility study | `FEASIBILITY.md`, sourced, with a source-quality table | done |
| Evaluate every proposal | `CANDIDATES.md` + `resolution_filter.py`: a physics filter with verdicts | done |
| Test end to end | Corn (Gates 0-2), reservoir measurement, water-to-rice link | done |
| Find impressive connections | Water -> rice acreage, elasticity +0.28 to +0.41 (t > 4.9), and an end-to-end satellite run that matches the gauge | done |
| Themes from the GitHub work | An H3 water-accessibility layer queryable in DuckDB, plus the event-study discipline; see section 6 | done |
| Production ready | `hsp.py` runner (11 stages), 21 tests, CI, data dictionary, DQ catalogue, read-only API | **packaged and queryable; not deployed** |

---

## 2. The spine of the whole thing

Every result below is one of three kinds: a **measurement** that was validated
against ground truth, a **null** that was run properly, or a **blocked** item with
the exact reason. Nothing is a backtest with no null.

### 2.1 Corn (the original thread)

| Gate | Question | Result |
|---|---|---|
| 0 | Would perfect knowledge pay? | **+1.095% of notional per release** (t 4.13, 64% hit, 83 releases); **+1.89%** trading ten days early, because the market drifts toward the revision. Break-even needs RMSE < ~3 bu/ac. |
| 1 | Does free data forecast the crop? | Weather does: point-in-time state RMSE **17.63 -> 15.38 bu/ac**. Satellite does not: **15.38 -> 15.38** with the NDVI index, CI [-15.4, +15.6]. USDA's own August forecast: **9.46**. |
| 2 | Is the disagreement tradable? | corr(model - USDA, final - USDA) = **+0.146**, CI **[-0.028, +0.300]**. Trade **+116% compounded vs +222%** for buy-and-hold over 16 years, beating it in **4 of 16**. **No edge.** |

The mechanism that mattered: a leave-one-year-out evaluation made the satellite
index look informative; a point-in-time evaluation did not. That gap is where
most projects in this genre lose their credibility.

**One year carries the trade.** The arithmetic mean of +7.63%/yr hides that the
strategy's compounded return is mostly 2020, when it was long and corn rose 87.8%.
Drop that year and the strategy compounds to **+15.3%** against buy-and-hold's
**+71.4%**. It beats the benchmark in only 4 of 16 years, and in 15 of 16
leave-one-year-out runs. The bootstrap interval on compounded wealth is
**[-67%, +1153%]**, which is what sixteen volatile years will always give you.
`gate2.py` prints all of this now, so the headline cannot drift away from it again.

### 2.2 The physics filter (what nobody in the comments checked)

| Proposal | Verdict |
|---|---|
| count cars at 10 m | **impossible** individually; only the lot's mean brightness works |
| count shipping containers | **impossible** individually; only the stack area |
| oil tank fill | countable at 30 m, so the video's "10 m is terrible" premise was overstated |
| reservoirs, mines, construction, stockpiles | countable at every free resolution |

### 2.3 Reservoir storage, measured and validated

Sentinel-2 water extent, fixed grid, L2A offset corrected, normalised by the
observed fraction, scored leave-one-out against daily CDEC gauges:

| reservoir | scenes | Spearman | linear RMSE | baseline | error cut |
|---|---|---|---|---|---|
| Shasta | 36 | **0.886** | **25.3 ft** | 50.8 | **50%** |
| Oroville | 37 | **0.927** | **32.9 ft** | 86.3 | **62%** |
| Don Pedro | 33 | 0.661 | 24.9 ft | 29.2 | 15% |

**A screen was added and it changed these numbers substantially.** When the water
mask fails - haze, shadow, a partial swath - the measured area collapses to a
sliver: Don Pedro once reported 83,153 m2 against a 20 million m2 median. One such
point moves a rank correlation by a lot, and all three reservoirs had one or two.
Scenes below 50% of a reservoir's own median area are now dropped, and the count
is written to the validation file.

The effect was to *raise* every score:

| | before the screen | after |
|---|---|---|
| Shasta Spearman | 0.705 | **0.886** |
| Shasta error cut | -1% | **50%** |
| Oroville error cut | 25% | **62%** |

The earlier numbers in this report were contaminated, not conservative. The linear
fit now also beats the isotonic one, so the monotonicity constraint is no longer
earning its place.

**Does it track movement, or only the level?** Levels could correlate simply
because both series follow the same seasonal cycle. The sharper test is whether
successive *changes* agree, and on screened data they do: rank correlation of
changes is **0.76** (Oroville), **0.71** (Shasta), and 0.24 (Don Pedro), over 35,
36 and 32 change observations. That test is now computed inside
`reservoir_v2_validate.py`, so it reruns with the pipeline rather than living in a
side script.

**Where that sits in the literature.** Error as a fraction of each reservoir's
operating range is **14.3% (Shasta), 12.1% (Oroville), 25.2% (Don Pedro)**. I
previously wrote that this "sits in the 10-20% band the reservoir literature
reports" - that was too tidy. Published satellite storage retrievals are worse
than that: [GloLakes reports ~35.4% absolute
RMSE](https://beta.iopscience.iop.org/article/10.1088/1748-9326/ade903/pdf), and a
[DEM-based volume study reports 16-28% with a very-high-resolution
DEM rising to 18-45% with large-scale
ones](https://theses.hal.science/tel-04139330v1/file/2022TOU30277b.pdf). These
results are at the good end of that range, which is worth stating precisely rather
than flattering. It is still the method's ceiling, not the model's.

### 2.4 Water to rice: the link that held

| sample / specification | elasticity | t | n |
|---|---|---|---|
| 1990-2025 | +0.407 | +5.24 | 36 |
| **1990-2020, used out of sample** | **+0.281** | +4.97 | 31 |
| 1990-2014 | +0.265 | +6.26 | 25 |
| + rice price control | +0.488 | +4.05 | 27 |
| placebo: next year's storage | +0.165 | +1.60 | 35 |

A 10% rise in spring storage is worth **2.7-4.1% more California rice acreage**
depending on the sample, survives a price control, and the placebo is a third the
size and insignificant. The full-sample 0.407 is inflated by the 2021-2025
drought years, so **0.281 is the conservative estimate and the one used out of
sample**. The magnitude moved when I checked it against subsamples; the sign and
significance did not.

**Propagation, analytic.** The satellite storage estimate has a median error of
**5.2%**; through the elasticity that is a **2.1% acreage error**.

**Propagation, Monte Carlo.** The median ignores the tail, and the tail is the
real story: measured against the gauges, the storage error distribution has a
median of **5.1%** and a **p90 of 35.8%** (a cloudy year has few usable scenes).
Drawing 10,000 times from that empirical distribution:

| quantity | gauge | Monte Carlo median | 5th | 95th |
|---|---|---|---|---|
| elasticity | +0.407 | **+0.224** | +0.127 | +0.342 |
| acreage log-RMSE | 0.118 | **0.138** | 0.118 | 0.152 |

Two conclusions, one uncomfortable. The forecast degrades modestly - log-RMSE
0.118 to 0.138. But the **elasticity attenuates by about 45%**, which is textbook
errors-in-variables: noisy storage does not just add variance, it biases the
estimated sensitivity toward zero. Anyone substituting a satellite measurement
for a gauge will systematically *understate* the true relationship and mistake
attenuation for a weaker effect.

**End to end, no gauge in the loop.** Water area -> rating curve -> storage ->
acreage, fitted on 1990-2020 and predicted for 2021-2025:

| year | actual | gauge-fed | satellite-fed | error gauge | error satellite |
|---|---|---|---|---|---|
| 2021 | 407,000 | 487,698 | 479,442 | +19.8% | +17.8% |
| 2022 | 254,000 | 473,328 | 464,217 | +86.3% | +82.8% |
| 2023 | 516,000 | 559,637 | 544,772 | +8.5% | +5.6% |
| 2024 | 476,000 | 567,850 | 573,598 | +19.3% | +20.5% |
| 2025 | 524,000 | 570,850 | 558,898 | +8.9% | +6.7% |

MAPE **28.6% gauge, 26.7% satellite** - substituting pixels for the gauge costs
essentially nothing. But both are badly wrong in 2022, the year the model
over-predicts by 86%. That is the linear elasticity failing in an extreme drought:
acreage collapses faster than log-storage does, because allocation hits a floor and
policy intervenes. **The satellite is a good substitute for the gauge and neither
is a good model of the tail.**

### 2.5 The revision test, flagged not claimed

On the **8 years** with both March and June NASS acreage: elasticity +0.405
(t 4.15), R² 0.742, 100% direction hit, LOO skill +38%. Eight points and a
two-parameter fit is not evidence, and a 100% hit rate on eight points is what
overfitting looks like. The futures reaction on the 30 June report is +0.29
correlated with the revision and has **the wrong sign for a supply story**, which
is a further reason not to read it.

### 2.6 The video's own project, rebuilt

The original idea was skipped in rounds 1-8 on feasibility grounds. It was built
afterwards, properly, to check whether that call was right. Method and full
results in `research/CUSHING.md`; headline:

| test | n | correlation |
|---|---|---|
| tank brightness vs EIA Cushing stocks, levels | 320 | **+0.628** |
| detrended | 320 | +0.378 |
| first half / second half | 160 / 160 | +0.449 / +0.267 |
| **4-week change vs 4-week change** | 276 | **-0.155** |

416 tanks from OpenStreetMap, 320 Sentinel-2 scenes, weekly EIA ground truth.

**Correction.** The +0.63 aggregate correlation is *between-year*. Split by year,
the within-year correlations run from -0.56 to +0.60 and average near zero. The
aggregate survives a year-block shuffle (p = 0.014), which says the annual means
co-move across eight years - not that the index measures fill. My earlier claim
that "the measurement works" was wrong.

**And the radar does not rescue it.** 84 Sentinel-1 RTC scenes give a
within-year correlation of +0.007 in 2018-21 and **+0.026** in 2022-25: nothing.
Amplitude is not what the commercial operators use, though - they use
interferometric phase - so the phase route was run as well, through ASF's HyP3
service on Sentinel-1 SLC pairs. Details in `research/INSAR.md`.

The phase route gets further, and then stops in a more interesting place:

| test | result |
|---|---|
| coherence over the tank roofs | **0.637** (p25 0.511, 319/416 above 0.5) |
| displacement vs perpendicular baseline | **-2.00 cm at -98.75 m, +0.11 cm at +5.82 m, +2.39 cm at +104.57 m** |
| per-tank displacement spread, near-zero baseline | p01 **-0.97 cm** to p99 **+1.55 cm** |
| tanks moving more than 5 cm | **0.0%** |
| motion implied by the EIA draw | **26-54 cm** |

So the tanks are excellent radar targets and the phase is clean - and then the
measured displacement is a twentieth of what the inventories require, scales with
the perpendicular baseline (a geometric artefact, not oil), and spans two
centimetres across every tank at zero baseline. One hypothesis, that the roof
motion was aliasing the phase, was tested and rejected: the phase gradient over
tanks is 0.29 rad/pixel against a wrap limit of pi.

**The reason is resolution, and it took reading the GeoTIFF transform to find.**
HyP3's `looks` parameter is range x azimuth looks, not a metre grid: the "20x4"
products I had been calling 20 m are **80 m**, and the finest option it sells,
"10x2", is **40 m**. A Cushing tank is 30-60 m across, so **a tank is smaller than
one pixel** and the phase is dominated by the ground between tanks.

The clincher is the same pair processed both ways: 2024-06-05 to 06-29 at 80 m
gives **+0.11 cm**, at 40 m gives **+6.72 cm**. The same interferogram, the same
two dates, a 6.6 cm difference produced purely by the output grid. No roof moved
because the product was resampled.

**Every free route fails, and each fails for its own reason.** That is the honest
end of the video's project: the idea is sound, the instruments are free, and the
measurement is not there.

**The arithmetic closes it.** A 20 Mbbl hub-wide move produces a 2.4% brightness
change against a measured 8.9% noise floor: SNR 0.27. Reaching SNR 2 needs 147
Mbbl, or 307% of Cushing's working capacity. Across four hubs the noise floor
runs 8.9-18.6%, and the maximum possible signal is 5.4%, so no hub at 10 m crosses
detection. This is not a method that failed; it is a method that cannot work at
this resolution.

So the original call was wrong in its premise and right in its conclusion: it was
buildable, it beats the video's -0.3% false start at the annual level, and none of
its three free instruments - optical brightness, radar amplitude, radar phase -
tracks fill within a year, which is what a trade needs.

---

## 3. What is blocked, and why

**CAISO electricity prices - retired after three rounds.** The endpoint was
eventually made to work: `PRC_LMP` with `market_run_id=DAM` returns data, but
only inside a **28-day window** (31 days returns a 1 KB error document with HTTP
200, which is why the first attempts failed silently). The blocking fact is
retention: every window before 2024 returns `ERR_CODE 1000, No data returned for
the specified selection`. Two years of prices is not enough to separate a water
effect from seasonality and gas prices, so the water-to-power hypothesis is
**retired, not refuted** - there is no credible test to run on the data that
exists, and no proxy result is being presented as if there were one.

---

## 4. Reproduce

```powershell
uv venv .venv-scratch --python 3.13
uv pip install --python .venv-scratch\Scripts\python.exe `
  pandas numpy scipy matplotlib requests pystac-client planetary-computer `
  rioxarray rasterio xarray scikit-learn yfinance pytest

$env:NASS_API_KEY = "<see .env>"
python hsp.py ingest      # ~15 min: NASS, WASDE, prices, weather, CDEC
python hsp.py measure     # ~40 min: Sentinel-2 scene loop, then validation
python hsp.py analyse     # ~5 min: gates 0-2, water-rice, chain
python -m pytest tests -q # 9 assertions
```

**Query it:** `uvicorn serve.app:app --port 8000`, then `/health`, `/water/{year}`,
`/county/{name}`, `/reservoirs`. Smoke-tested with FastAPI's TestClient; 6 of the
21 tests cover the API.

`hsp.py` stops at the first failing stage, so a partial run is never mistaken for
a complete one. Per-stage logs live in `data/processed/` (`v2_run.log`, `reservoir_run.log`,
`caiso_run.log`, `run_all.log` from the corn gate run).

---

## 5. What "production ready" still needs

Done since the last draft: the satellite-to-economics run end to end (section
2.4), the H3 layer (section 6), CI, a data dictionary and a single runner.

**A data-quality layer now exists** (`analysis/dq_catalogue.py` -> `docs/DQ.md`):
every raw table counted for duplicate keys, null keys, sentinels and non-positive
values. It immediately caught one real hazard: **WASDE reports the same quantity
twice per release, once in bushels and once in metric tons**, so the natural key
`(release, market year, attribute)` is not unique and a pivot silently picks
whichever row comes last. Gate 0 now filters the unit explicitly. The result did
not change - 172 events, +1.095% - which is exactly why it is worth recording:
the near-miss was invisible in the output.

Still open:

1. **A price leg that works.** CAISO is retired for lack of history; the
   alternative is BOM/Murray-Darling storage, which is free and daily, or a
   different power market with a longer archive.
2. **Extend the measurement to ungauged basins**, which is the actual product:
   California validates the method, the method then applies where no gauge exists.
   That is a data-volume problem (Sentinel-2 over many reservoirs), not a
   modelling one.
3. **Scheduling and storage.** Today it is a batch pipeline on a laptop; a
   production version needs incremental pulls, a warehouse table, and a run log
   with data-quality counts, in the shape of the F1 pitwall repository.
4. **Deployment.** CI runs the tests on push, but nothing runs the pipeline on a
   schedule. That needs a decision about where it should live.

---

## 6. The H3 layer, and the hypothesis it killed

`analysis/h3_water.py` builds the piece that matches the transit platform's idiom:
a **2,462-cell H3 resolution-6 grid** over California, each cell scored by
linearly-decayed access to the ten major reservoirs

    A_i(t) = sum_j max(0, 1 - d_ij / 300km) * storage_j(t)

which is the same linear-decay accessibility used for transit stops, with
acre-feet in place of service frequency. The result is one parquet table -
geometry, decay weights and a per-year accessibility time series - that DuckDB
queries directly:

```sql
SELECT h3, ROUND("2025", 0) AS af_2025 FROM h3_water ORDER BY "2025" DESC LIMIT 5;
```

The hypothesis it was built to test: do counties more exposed to storage respond
more strongly to a good or bad water year? That is an interaction,
`exposure_c x log(storage_t)`, identified with county fixed effects.

| term | coefficient | std. error | t |
|---|---|---|---|
| log storage | +0.675 | 0.247 | +2.73 |
| exposure x log storage | -0.085 | 0.067 | **-1.26** |

**The interaction is null, and the sign is wrong.** Counties closer to the big
northern reservoirs do not amplify the statewide response.

**How strong is that null?** A null is only worth reporting if the design could
have seen something, so the interval and the minimum detectable effect were
computed:

| | |
|---|---|
| 95% CI on the interaction | **[-0.216, +0.047]** |
| minimum detectable effect at 80% power | **0.188** |

So this rules out exposure effects larger than about 0.19 - a quarter of the main
effect - but says nothing about effects of 0.1. That is a real null, not an
absence of evidence.

On reflection the null is not surprising either: California's rice counties are all
in the Sacramento Valley, so their exposure weights barely differ, and the
weighting is dominated by the same reservoirs for all of them. The layer is a valid
product; the hypothesis it was built for is dead.

## 7. Ties to the existing GitHub work

- **`transit-desert-platform`** (H3, DuckDB, FastAPI) is the right home for the
  spatial layer: reservoir catchments and county rice acreage are both H3-joinable,
  and a "water availability score" per cell is the same shape as the transit
  accessibility score already built.
- **`f1-pitwall-platform`** is the template for the production gap in section 5:
  scheduled ingest, validation with quarantine, dbt-tested marts, MLflow, and a
  README that states limits next to results.
- **`f1-strategy-engine`** (Monte Carlo under uncertainty) is the natural place to
  put the reservoir-to-acreage forecast's uncertainty, rather than asserting a
  point estimate.
- The **honest-evaluation** habit from the pitwall README is the single thing that
  makes this study worth reading: every headline number here has a null model or a
  baseline beside it.

---

## 8. The one-paragraph version

Fifty-four comments proposed things to track. A physics filter kills half of them
outright, a saturation check kills most of the rest, and the survivors are
reservoir levels, mine activity, and tanker traffic. This study measured the first
of those from free Sentinel-2, validated it against daily California gauges
(Spearman 0.71-0.89), and showed that spring storage predicts California rice
acreage with an elasticity of 0.28-0.41 (t > 4.9) that survives a price control
and a placebo, and that can be run end to end from Sentinel-2 pixels with no
accuracy cost against the gauge. It also showed, on the corn side, that a free-data model does not beat
the USDA and its disagreement is not tradable. The pattern across all of it is
consistent: **the measurement is where the contribution is, and the alpha is in the access,
which free data does not give you.** The video's own tank project, rebuilt
properly, confirms it: a 0.63 level correlation with weekly EIA stocks, and no
week-to-week signal to trade.
