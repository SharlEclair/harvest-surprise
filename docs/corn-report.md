# Corn study - results report (phase 1)

> Archived: this is the corn-yield study that preceded the wider alternative-data
> work. The current top-level result is `FINAL_REPORT.md`.

**Date:** 2026-11-11. **Status:** complete for the three gates; every number below
is produced by a script in this repository and was reproduced end to end in
`data/processed/run_all.log` on the date above.

---

## 1. Verdict

Three questions, three answers.

1. **Would perfect knowledge pay?** Yes, but the prize is small. Knowing the sign
   of the WASDE corn-yield revision in advance is worth **+1.10% of notional per
   release**, t = 4.13, 64% hit rate, 83 releases. Trading **ten days early is
   worth more, +1.89%**, because the market drifts toward the revision before it
   is published. That drift is the interesting part: the information arrives
   before the report does.
2. **Does free satellite + weather data forecast the crop?** Weather does.
   Satellite does not, detectably. Point-in-time state yield RMSE improves from
   **17.63 bu/ac (trend) to 15.38 (trend + weather)**; adding the NDVI index
   moves it to **15.38 as well - a difference of 0.002 bu/ac**, and the bootstrap
   interval on the NDVI gain is [-15.4, +15.6]. The USDA's own August forecast is
   far better at **9.46 bu/ac**.
3. **Is the model's disagreement with the USDA tradable?** Not demonstrated.
   Point-in-time, corr(disagreement, subsequent revision) = **+0.146** with a
   year-block bootstrap 95% CI of **[-0.028, +0.300]** - it includes zero. The
   trade earns +7.63%/yr but simply buying and holding corn over the same windows
   earns **+9.73%/yr**, and the permutation p-value is 0.240.

**Overall:** the information content is real at the report level, the free-data
model does not produce it, and the trade that was supposed to monetise it loses
to buy-and-hold. That is a negative result, argued precisely, which is what the
brief said a project in this genre should be judged on.

---

## 2. What was built

| Layer | Script | Output |
|---|---|---|
| NASS yields, acreage, weekly condition | `ingest/nass.py` | `data/raw/nass_*.csv` (4 files) |
| NASS validation | `ingest/verify.py` | 14 assertions, all passing |
| WASDE history, 190 releases | `ingest/wasde.py` | `data/raw/wasde_corn.csv` |
| Daily futures | `ingest/prices.py` | `data/raw/prices_daily.csv` |
| Weather (NASA POWER) | `ingest/weather.py` | `data/raw/weather_state_year.csv` |
| Satellite index (MODIS) | `spike/modis_ndvi.py` | `spike/data/years/ndvi_*.csv` |
| Gate 0 | `analysis/gate0.py` | `gate0_events.csv`, `gate0_leadtime.csv`, `gate0_surface.csv` |
| Gate 1 | `analysis/gate1.py` | `gate1_predictions.csv`, `gate1_metrics.csv`, `gate1_national.csv` |
| Gate 2 | `analysis/gate2.py` | `gate2_state.csv`, `gate2_national.csv`, `gate2_trades.csv` |

Data volumes actually pulled: 14,121 NASS yield rows; 82,414 weekly condition
records; 10,199 harvested-acre rows; 6,718 planted-acre rows; 18,388 corn/US
WASDE rows across 190 releases; 4,489 daily corn futures bars; 468 state-years of
weather from 54 NASA POWER points; 25 years of MODIS composites.

---

## 3. Gate 0 - would perfect knowledge pay?

Built from the WASDE data files (one CSV per release, 2010-04 to 2026-11) and
daily corn futures. The surprise is the revision of the **newest marketing year
in each report** against the previous report for *the same marketing year*.

**Sample.** 172 events. **52% of releases do not revise yield at all** - the
median release-by-release change is zero, and among the revisions the median
absolute change is 1.6 bu/ac. sigma_u = 2.99 bu/ac.

**Oracle.** Trade the sign of the revision, one day, one unit of notional:

| lead (days before release) | mean | t | hit |
|---|---|---|---|
| 0 (on the report) | +1.095% | 4.13 | 64% |
| 1 | +1.307% | 4.51 | 65% |
| 3 | +1.429% | 4.95 | 67% |
| 5 | +1.666% | 5.40 | 70% |
| 10 | +1.888% | 3.73 | 69% |

The P&L **grows** with lead time. That is not a bug: it says the price drifts in
the direction of the eventual revision before the report is published. A forecast
that arrives early captures the drift as well as the jump. It also means the
"information advantage" story is about being early, not about being first at
12:00 ET.

**Price response, two estimates that bracket the truth.**

- OLS `return ~ d_yield + d_area`: **-0.132% per bu/ac** (se 0.056, t -2.35),
  acreage control +0.110% per million acres (t 0.47), R2 0.032.
- Sign-trade implied: **+0.426% per bu/ac** in absolute size
  (= -mean P&L / mean |revision|), the average move among releases that actually
  revised.

They differ by 3.2x because OLS averages over the 52% of releases with no
revision, which attenuates it. Both are reported; neither is "the" answer.

**Break-even surface (conservative OLS beta).**

| forecast RMSE | corr with surprise | net per event | annualised |
|---|---|---|---|
| 0 bu/ac | 1.00 | +0.243% | +1.23% |
| 1 | 0.95 | +0.225% | +1.14% |
| 2 | 0.71 | +0.131% | +0.66% |
| 3 | 0.00 | -0.150% | -0.76% |

Break-even is **RMSE < 3.0 bu/ac** at the conservative pass-through, and about
4.4 at the optimistic one. That is the number the whole project hangs on, and it
is published before any model was built.

---

## 4. Gate 1 - does the measurement work?

**Setup.** 468 state-years (18 states x 2000-2025). Prediction date 1 August.
Features: six NASA POWER weather aggregates with windows ending **31 July**
(`ingest/weather.py`), and a MODIS NDVI index from composites beginning 26 June
and 12 July - never the late-July composite, which contains August pixels.

Two evaluation schemes, and the difference is the whole story:

- **Leave-one-year-out (LOYO):** trains on every other year. Measures model
  skill, and is what most projects report.
- **Expanding window:** trains only on years *before* the target. Measures what
  a trader could actually have done.

| model | LOYO RMSE | expanding RMSE |
|---|---|---|
| B0 trend only | 15.61 | 17.63 |
| B1 trend + weather | **13.47** | **15.38** |
| B2 trend + weather + NDVI | **13.22** | **15.38** |
| B3 USDA August forecast | 9.46 | - |

National aggregate (harvested-acre weighted):

| model | LOYO | expanding |
|---|---|---|
| B0 | 10.30 | 12.13 |
| B1 | 6.87 | 9.11 |
| B2 | 6.45 | 9.06 |

**The NDVI result does not survive point-in-time.** LOYO says NDVI improves RMSE
by 0.26 bu/ac; the year-block bootstrap puts the 95% CI on that improvement at
**[-17.1, +3.5]** - it includes zero even in the flattering scheme. Under the
expanding window the improvement is 0.002 bu/ac with a CI of **[-15.4, +15.6]**,
which is what "no effect" looks like when written honestly. **No detectable
contribution from the satellite index.**

The USDA's August forecast (published 11-12 August, so it has eleven more days
than the model, stated rather than hidden) is 6 bu/ac better than the best free
model. Free data does not approach the incumbent.

---

## 5. Gate 2 - is it priced?

The model does not beat USDA on level, so the tradeable question is whether its
disagreement predicts the revision:

```
d   = model prediction (1 Aug)  -  NASS August forecast
rev = final state yield         -  NASS August forecast
```

**Point-in-time (expanding window), n = 360 state-years:**

- corr(d, rev) = **+0.146**, year-block bootstrap 95% CI **[-0.028, +0.300]**.
- Revisions occur in the direction of the disagreement **55%** of the time.
- Tercile means fall monotonically from **-2.45 bu/ac** (model low) to
  **-0.01** (model high), but the interval on the correlation includes zero.
- **National aggregate: corr = -0.120 (n = 20)** - the wrong sign.

**Trade: hold August WASDE to the following January, short when the model says
the crop is bigger than USDA.**

- n = 16 years, mean **+7.63%/yr**, se 6.47%, t 1.18, hit 69%.
- Always long over the same windows: **+9.73%/yr**. The strategy is *worse* than
  passive.
- Permutation null (10,000 shuffles of the position vector): p = 0.240.

**Verdict: no demonstrated edge.**

---

## 6. What the adversarial audit changed

Three independent audit agents reviewed Gate 0, 1 and 2 against the code. They
found nine major defects. Every one that could change a conclusion was fixed and
the analysis re-run. Recording them is the point of this section - the first
draft of these results was wrong in ways that flattered the project.

| # | Defect found | Effect | Fix |
|---|---|---|---|
| 1 | Gate 0 "implied beta" printed **+0.367%/bu with the wrong sign**, contradicting the OLS in the same output | report contained two contradictory price responses | now reports OLS beta and sign-trade beta separately, both signed |
| 2 | Gate 0 break-even surface was **circular** - beta was defined as mean/sigma_u, so the surface was a rescaling of the oracle mean | the surface could not test its own premise | rebuilt on the regression beta |
| 3 | Gate 0 had **no lead-time axis**, though the brief pre-registered one | the pre-registered question was unanswerable | measured P&L at 0/1/2/3/5/10 days - which produced the best finding in the project |
| 4 | Gate 1 "state-specific NDVI" was a **byte-for-byte copy** of a tile column; 18 states map to 4 tiles, and the clip put CO, TX and PA in tiles they do not overlap | the feature claimed to be state-level was not | removed |
| 5 | Gate 1 persistence feature used the **revised** prior-year yield, published 60 days after the prediction date | a point-in-time violation, worth 0.14 bu/ac | dropped |
| 6 | Gate 1 NDVI gain **not distinguishable from zero** (p = 0.34, worse in 12 of 26 years) | a 0.39 bu/ac "gain" was being reported as a result | replaced with a bootstrap interval |
| 7 | Gate 2 used **LOYO predictions**, which let the trend see future years | inflated corr from 0.146 to 0.288 | rebuilt with an expanding window |
| 8 | Gate 2 **silently dropped 2018 and 2020** (no January release in the archive) | sample 14 instead of 16 | falls back to the next release |
| 9 | Gate 2 charged **no transaction costs** | every number overstated | 0.15% round trip per trade |

The single most consequential finding of the project - that LOYO evaluation makes
the satellite model look informative and point-in-time evaluation does not - came
directly out of defect 7.

---

## 7. Verified, assumed, and known-broken

**Verified (ran on 2026-11-11, reproducible):**
- Every number in sections 3-5.
- NASS data integrity: 14/14 assertions, including state yields weighted by
  harvested acres reconciling to the published national 177.3 (2023) and 179.3
  (2024) bu/ac.
- WASDE structure: 190 releases, corn yield rows with `ReleaseDate`/`ReleaseTime`;
  471 yield rows carry a 12:00 release time and 99 an 08:30 one.
- Six one-day corn moves of 10-27% on dates with no WASDE release - the shape of
  a contract splice.
- Two Quick Stats API traps: `year__GE`/`year__LE` silently do not filter
  (31,120 rows vs 4,835 for the same nominal year), and `AREA PLANTED` rejects
  `utilization=GRAIN` with a 400.

**Assumed:**
- 0.15% round-trip cost. Real corn futures costs are lower (about 0.07-0.09%),
  which would help every trade equally.
- 5.05 yield-relevant releases per year, measured from the sample rather than
  assumed.
- Linearity and normal errors in the break-even formula.

**Known-broken, declared, not fixed:**
- **Prices are Yahoo's continuous front-month `ZC=F`, not CME settlements.** The
  series is not roll-adjusted: the six one-day moves above fall on dates with no
  release, which is what a roll splice looks like. Disqualifying for a published
  P&L and the first thing to replace.
- The 2010-2012 releases were at 08:30 ET, so the return window means different
  things across the sample.
- The May WASDE is only ever a baseline (it is the first forecast of a crop year,
  so it has no revision), which drops one event per year.
- 36 of 468 state-years have imputed NDVI (2000 has no satellite file; 2025 has
  only the June composite).

---

## 8. Reproduce

```powershell
cd harvest-surprise
uv venv .venv-scratch --python 3.13
uv pip install --python .venv-scratch\Scripts\python.exe `
  pandas numpy scipy matplotlib requests pystac-client planetary-computer `
  rioxarray rasterio xarray scikit-learn yfinance

$env:NASS_API_KEY = "<key in .env>"
.\.venv-scratch\Scripts\python.exe ingest\nass.py       # ~3 min
.\.venv-scratch\Scripts\python.exe ingest\wasde.py     # ~5 min
python ingest\prices.py                                 # system python: venv yfinance 1.8.0 is broken
.\.venv-scratch\Scripts\python.exe ingest\weather.py   # ~4 min first run, cached after
.\.venv-scratch\Scripts\python.exe ingest\verify.py
.\.venv-scratch\Scripts\python.exe analysis\gate0.py
.\.venv-scratch\Scripts\python.exe analysis\gate1.py
.\.venv-scratch\Scripts\python.exe analysis\gate2.py
```

Full console output from the last clean run: `data/processed/run_all.log`.

---

## 9. Where to attack this (for the reviewer)

Ordered by how much a correct answer would change the conclusion.

1. **The price series.** Replace `ZC=F` with contract-level settlements and
   explicit roll dates. Gate 2's returns are the weakest link in the chain.
2. **The NDVI feature.** One regional index over nine states is a weak
   instrument. A per-state, per-county index built from Sentinel-2 rather than
   250 m MODIS would test the satellite claim properly; the current negative
   result may be a statement about this feature, not about satellite data.
3. **The national inconsistency.** State-level corr(d, rev) = +0.146 but national
   = -0.120. With n = 20 the national number is noise, but a reader should not
   have to guess that.
4. **The 2015+ subsample.** corr(d, rev) = +0.295, CI [+0.143, +0.428], and it
   excludes zero. It is also a subsample chosen after seeing the full-sample
   result, so it is a hypothesis, not a finding. Anyone quoting it as evidence is
   quoting a garden of forking paths.
5. **Gate 0's two betas.** The 3.2x gap between OLS and sign-trade beta is doing a
   lot of work. A cleaner estimate would come from intraday prices around the
   release, which this project does not have.

---

## 10. File map

```
BRIEF.md            project proposal (written before any of this)
REPORT.md           this file
REVIEW.md           claim-by-claim verification sheet
ingest/             nass.py wasde.py prices.py weather.py verify.py + README
analysis/           gate0.py gate1.py gate2.py
spike/              the 25-year MODIS pull that started it, + RESULTS.md
research/           video transcript and the top comments that motivated it
data/raw/           immutable pulls (gitignored)
data/processed/     every number in this report, plus run_all.log and 3 figures
```
