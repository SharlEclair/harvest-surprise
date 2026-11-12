# Harvest Surprise — project brief

**One line:** free satellites photograph every corn field on Earth every few days.
This project measures whether that information is worth money in CBOT corn, and tries
to prove the answer *before* building the model that would trade on it.

**Status of this document:** a proposal, not a result. It contains one completed
feasibility spike (see `spike/RESULTS.md`) and a great many things explicitly marked
*unverified*. The point of the document is to be reviewed and attacked.

---

## 1. The pitch

> A hedge fund pays six figures a year to count cars in Walmart car parks. The video
> this project follows did it for free, found the shadows in Cushing oil tanks, proved
> the measurement against the EIA, ran the backtest — and lost money. He then found the
> mistake: he had asked *can I measure it?* for two months before asking *would knowing
> it even pay?* asked once, at the end, and the answer was no.
>
> This project asks the second question first.

Three deliverables, in order of how much they matter:

1. **A break-even surface.** What accuracy and what latency does a corn-yield signal
   need before it pays for its own trading costs? Computed from public price history and
   public report history, before any satellite work. This is the thing nobody in this
   genre publishes, and it is cheap to produce.
2. **A working nowcast.** Free Sentinel-2 / Sentinel-1 / MODIS data → per-county crop
   condition → national yield estimate with calibrated uncertainty, scored
   out-of-sample against USDA, using only data that existed at the timestamp claimed.
3. **A verdict.** Not "look at this equity curve" — a pre-registered test with null
   models, and an honest statement of what the sample can and cannot distinguish.

If (1) says the required accuracy is unreachable, (2) still ships because it is the
measurement rig, and (3) is a negative result with a precise reason. That is a better
portfolio piece than a curve, and it is much harder to fake.

### Why this one, given the existing portfolio

| Existing repo | What it proves | What this project adds |
|---|---|---|
| `f1-pitwall-platform` | data engineering at the messy end: ingest, validation with quarantine, dbt, an honestly evaluated model, limits written down | the same discipline pointed at physical measurement and money |
| `transit-desert-platform` | H3 grids, DuckDB, FastAPI + MapLibre, spatial joins at city scale | the same stack at *continental* scale, on raster instead of vectors |
| `f1-strategy-engine` | Bayesian inference, survival analysis, vectorised Monte Carlo under uncertainty | uncertainty quantification that is calibrated (conformal) rather than asserted |
| `vct-prediction-engine` | an ML pipeline with scrapers, features, evaluation | ML where the baseline is a government agency, not a coin flip |
| `home-credit-agent` | LLM agents, evals, Docker | not used here — and that is deliberate, see below |

The gap it fills is **physical-world measurement → market signal**, which none of the
others touch, and which is the thing the video is actually about. It also gives the
portfolio a piece where the interesting claim is a *negative* one, argued carefully —
the rarest and most senior-looking artifact in a data-science portfolio.

Deliberately **not** in scope: an LLM anywhere in the pipeline. Bolting a chat interface
onto a yield model would be the easy, obviously-generated move, and it would dilute the
one thing this project is for.

**Positioning line:** *"I measured how much tradable information free satellite data
actually carries about the US corn crop — and published the accuracy it would need to
carry before it was worth trading."*

---

## 2. Why this is not the usual "NDVI → corn" project

The genre is crowded: Descartes Labs published corn forecasts from satellite in 2019,
Gro Intelligence and Kayrros sell the same thing, the USDA publishes weekly crop
condition ratings and its own monthly yield forecast, and half the GitHub projects in
this space train a random forest on NDVI and show a correlation. A reviewer will have
seen it. Four things separate this one:

| Common version | This version |
|---|---|
| Target = yield level | Target = the *surprise* (USDA revision, or deviation from a public benchmark), because markets price surprise, not level |
| Trains on all years, evaluates on a random split | Leave-one-year-out, features truncated at the vintage timestamp, revisions handled point-in-time |
| Reports R² and a backtest curve | Reports RMSE against two baselines, a power calculation, and null-model percentiles |
| "It worked" | Pre-registered kill criteria, and a stated threshold below which the result is honestly called indistinguishable from noise |

The intellectual content is not the model. It is the **signal-to-noise budget**: how much
information the physics gives you, how much the market already has, and where the two
overlap.

---

## 3. The four traps

Every one of these has killed a project like this before. They are the reason the design
looks the way it does.

### Trap 1 — predicting yield is not predicting price
Corn futures price the *surprise* relative to expectation. A model with a 2 bu/ac error
tells you nothing new if the market's existing expectation already carries a 2 bu/ac
error. The target must be a revision or a residual against something public, and the
expectation benchmark has to be chosen and frozen in advance.

*Consequence:* true analyst consensus is paywalled (Bloomberg/Refinitiv/LSEG), but the
paywall turned out to be mostly avoidable. NASS publishes, in Quick Stats, the state
yields **it was forecasting in each WASDE** — `reference_period_desc` takes the values
`YEAR - AUG FORECAST`, `- SEP`, `- OCT`, `- NOV`. So the surprise can be defined as
*model estimate minus the forecast NASS itself published*, which is public, dated to the
release, and exactly what the market trades around. What this does **not** give you is the
market's own expectation — only the government's — and the two differ when the market
disagrees with USDA. That residual gap is stated rather than hidden.

### Trap 2 — point-in-time
USDA county yields are revised for years. Sentinel-2 L2A is typically available 1–3 days
after acquisition. Crop Progress is released Monday 16:00 ET. A feature built from a
county yield published in 2024, used to "predict" 2019, is a time machine, and this is
the single most common defect in public ag-ML repos.

*Consequence:* every table carries a `vintage` column and every training row is built
from an as-of join. Backtests use the vintage, not the final value.

### Trap 3 — statistical power
Worked example, with assumptions to be replaced by measurement in Gate 0:

- 5 yield-relevant reports a year (Aug, Sep, Oct, Nov, Jan).
- Assume a report day has σ ≈ 2.5 % of price; assume a round-trip cost of 0.2 %.
- A signal with information coefficient IC earns ≈ IC × 2.5 % per event, so break-even
  is IC ≈ 0.08.
- Detecting IC = 0.08 at 95 % confidence needs N ≈ (1.96 / 0.08)² ≈ 600 events.
- Public price history plus the satellite era gives roughly 130 events. The standard
  error on IC is then ≈ 1/√130 ≈ 0.09 — *the same size as the effect being tested.*

**A real, small edge is undetectable in the sample that exists.** That is not a reason to
give up; it is a reason to stop pretending a backtest curve is evidence, and to pick a
target where the effect is large enough to see (see §4).

### Trap 4 — the Corn Belt is the most-watched crop on Earth
The commenter said "focus on the Corn Belt". Directionally right (crops are big enough
for 10 m pixels, multispectral helps, the futures contract is liquid) and strategically
wrong: it is the one place where USDA survey data, private satellite firms, and every
trading desk are already converged. The Corn Belt is where the *measurement* is easiest
and the *edge* is hardest.

*Consequence:* the Corn Belt is the calibration rig — the place with ground truth good
enough to prove the pipeline works. Deployment is somewhere the data is thin (§6).

---

## 4. The sharpened objective

Two candidate questions. The project commits to one after Gate 0, and Gate 0 is designed
to pick between them.

**Q-A (regression).** Can free satellite data forecast the national corn yield to better
than 2 bu/ac out-of-sample, before the August WASDE?
*Power: weak (see Trap 3). Value: it is the measurement that everything else needs.*

**Q-B (tail detection).** Can free satellite data say, by mid-July, that the national
crop is in the bottom decile?
*Power: better than Q-A if the target is built as a continuous stress index; much worse
if it is built as a binary classifier, because there is almost nothing to train on. See
the measurement below.*

The base rate is measured, not guessed. On the national series since 1961, using a
quadratic trend on OWID/FAO yield:

| threshold | 1961–2025 (n = 65) | 2000–2025 (n = 26) |
|---|---|---|
| ≥ 5 % below trend | 12 years ≈ **1 in 5.4** | 3 years (2002, 2011, 2012) ≈ **1 in 8.7** |
| ≥ 10 % below trend | 6–7 years ≈ **1 in 10** | 1 year (2012) |

The modern sample is milder — better seed, drainage, irrigation — and that changes the
design: **a binary "bad year" classifier would have three positive examples.** So Q-B is
specified as a **continuous crop-stress index** (heat × water deficit during the silking
window, weighted by observed canopy condition), evaluated by:

1. rank correlation (IC) against detrended yield across all 25 satellite years — this uses
   the whole sample, not just the tails;
2. whether the index crosses its pre-registered threshold before the market moved in the
   three known tail years, which is a *case study*, reported as a case study and not
   counted as statistical evidence;
3. performance against the free weather baseline below, which is the bar that matters.

That is weaker than "I built a bad-year detector" and considerably more honest. The
brief's claim is that this is the only version of the claim that survives contact with
n ≈ 25.

Notes that make Q-B credible rather than hand-wavy:
- It has to beat a trivial baseline: "was June–July precipitation in the 6 main states
  below the 20th percentile?" Weather data is free and old, and if it wins, the satellite
  adds nothing and the project says so.
- Silking date matters more than calendar date; a state-level GDD model from PRISM
  shifts the window by up to three weeks between Iowa and Kansas.
- The stress index must be computed from the same vintage-aware features as Q-A, or the
  two questions are not comparable.

---

## 5. The gates

Nothing downstream starts until the gate above it passes, and the criteria are written
down before the data is touched.

### Gate 0 — would perfect knowledge pay? (about 1 week, no satellite data)
1. Reconstruct WASDE corn yield history. **Solved and verified:** USDA publishes the
   report tables as CSV, one file per month at
   `usda.gov/sites/default/files/documents/oce-wasde-report-data-YYYY-MM.csv`, plus ZIPs
   covering 2010-04 → 2020-12. Each row carries `Commodity`, `Attribute`
   (`Yield per Harvested Acre`), `MarketYear`, `Value`, `Unit`, `ReleaseDate` and
   `ReleaseTime` — i.e. the point-in-time timestamp comes free. About 190 releases.
2. Event study: report-day return vs yield surprise, with controls for the acreage
   revision that lands in the same report. Estimate β (percent price move per bu/ac).
3. Add trading costs (commission, half-spread, slippage at size) and a realistic fill
   assumption for a report released at 12:00 ET.
4. **Output:** a break-even surface — x = forecast RMSE in bu/ac, y = days of lead time
   before the report, colour = expected annual net return and its standard error. The
   contour where it crosses zero is the project's real result, and it is public
   regardless of what happens afterwards.

*Kill criterion:* if even a zero-error oracle with one week of lead does not clear costs
by a margin larger than one standard error, the trading framing is dead and the project
becomes a measurement paper. (This is what happened to the crude-oil version.)

### Gate 1 — does the measurement work? (2–3 weeks)
1. H3 res 7 grid over the Corn Belt; Sentinel-2 L2A + S1 GRD + MODIS 13Q1 via STAC,
   windowed COG reads, no bulk download.
2. Crop mask per year (USDA CDL) — necessary because corn/soy rotation means the same
   cell is a different crop each year; a commenter on the video raised exactly this.
3. Features: greening date, NDVI/EVI integral to a phenological anchor, senescence
   slope, SAR VV/VH, heat-degree days, water balance.
4. Model: LightGBM per state, shrunk to a national estimate; conformal prediction
   intervals so the uncertainty is calibrated, not asserted.
5. **Output:** out-of-sample RMSE vs (a) the USDA's own August forecast error, (b) a
   trend + weather baseline. Leave-one-year-out; also leave-one-state-out to test
   spatial transfer.

*Kill criterion:* if the model does not beat trend + weather on held-out years, the
satellite is not adding information and no amount of tuning will fix that.

### Gate 2 — is it priced? (1–2 weeks)
1. Convert the model output into a surprise against the frozen benchmark.
2. Event study on the *first tradable moment* after the signal is computable — not the
   report date.
3. Costed backtest, then four null models: random entry with matched holding periods;
   signal dates shuffled within year; a placebo instrument (corn signal applied to a
   wheat ETF); and a decade-block bootstrap.
4. **Output:** a percentile, not a Sharpe ratio. "This signal beat 93 % of 2,000
   random portfolios" is a claim with a distribution behind it; "+34 % annualised" is not.

---

## 6. Where the edge might actually be

If Gate 2 fails on corn futures — the base case — there are three places the same
pipeline could still pay. Each is a testable extension, not a hand-wave.

1. **Cross-market.** A yield surprise hits corn futures in seconds, but the equity
   analysts covering Deere, Corteva, Nutrien, CF and Tyson do not run satellite models.
   The video's best insight was "trade the landlords, not the commodity": the signal
   moved the tank owners, not the oil. The ag analogue is that the same information may
   diffuse into *ag equities* over days. Testable with free daily equity data.
2. **Brazilian safrinha.** The second corn crop is roughly 90–100 Mt in recent seasons
   (the majority of Brazil's corn), exports into the same futures contract, and is far
   less well instrumented than Iowa: CONAB and USDA regularly disagree, and the
   disagreements move CBOT. Mato Grosso is one state, one
   crop calendar, cloud-free in the dry season, and Sentinel-2 covers it. This is where
   a free-data edge is most plausible — and it is the exact inverse of the commenter's
   advice: **calibrate where truth is known, deploy where it is not.**
3. **Sub-state resolution.** USDA publishes state-level condition ratings; the market
   trades the state and national numbers. A county-level nowcast is a genuine
   information advantage on a statistic that is published coarsely.

The project's shape, in one sentence: **the Corn Belt is the calibration rig; Brazil is
the deployment.**

---

## 7. Architecture

```
 STAC catalogue (Planetary Computer — no auth, no egress cost)
   sentinel-2-l2a   10 m, 5-day    2017 →   optical, needs cloud mask (SCL)
   sentinel-1-grd   10 m, 6-12 day 2015 →   SAR, sees through cloud
   landsat-c2-l2    30 m, 16-day   1984 →   long history
   modis-13q1       250 m, 16-day  2000 →   long history, cheap
        │  windowed COG reads (HTTP range), never a full-scene download
        ▼
 per-scene zonal reduce onto an H3 res-7 grid (~5 km²)
        │  cloud/QA mask → index (NDVI, EVI, NDWI, VV, VH)
        ▼
 Parquet  (h3, date, index, value, n_pixels, qa_flag)   ~5-10 M rows / year
        │  join annual crop mask (CDL) and weather (PRISM)
        ▼
 DuckDB  ── feature build per (h3, year) ── phenology anchors, integrals, stress days
        │
        ▼
 model layer: LightGBM per state → hierarchical shrink to national
              conformal intervals; leave-one-year-out; vintage-aware
        │
        ▼
 signal layer: surprise vs frozen benchmark → event study → costed backtest → nulls
        │
        ▼
 FastAPI + MapLibre dashboard (daily refresh), Parquet artifacts, reproducible CLI
```

Two engineering decisions worth defending:

- **No cloud bill.** Planetary Computer hosts the imagery and signs the URLs; the whole
  pipeline runs on a laptop. Reducing to an H3 grid *before* storing anything is what
  makes that possible — the raw archive is petabytes, the reduced table is a few GB.
- **H3 rather than county polygons.** Uniform area, no MAUP, cheap joins, and it is
  already the idiom used in the transit project, so the dashboard generalises.

---

## 8. Data inventory

Verified means: fetched it from this machine, today, and it returned what is claimed.

| Source | Use | Access | Status |
|---|---|---|---|
| Microsoft Planetary Computer STAC | Sentinel-2, Sentinel-1, Landsat, MODIS | anonymous | **verified** — searched, signed and read MODIS NDVI; assets confirmed |
| MODIS MOD13Q1 (250 m, 16-day) | long-history vegetation index | via PC | **verified** — 2001–2025 pull in `spike/` |
| Sentinel-2 L2A | 10 m optical + `SCL` cloud mask | via PC | **verified** — collection and band list inspected |
| Yahoo Finance (`ZC=F`, `ZS=F`) | daily corn/soy futures | `yfinance` | **verified** — 719 daily bars returned |
| USDA NASS Quick Stats API | state yields incl. in-season forecasts, acreage, weekly condition | free key (have it) | **verified** — 4 datasets pulled, 14/14 validation checks pass; state yields reconcile to the published national 177.3 / 179.3 bu/ac |
| USDA Crop Progress archive (Cornell ESMIS) | weekly condition ratings, 1986→ | public `.txt`/`.pdf` | **verified reachable** — release file listing confirmed |
| USDA WASDE report archive | the surprise benchmark | public CSV, 2010-04 → | **verified** — one CSV per month; corn `Yield per Harvested Acre` rows confirmed, with `ReleaseDate`/`ReleaseTime` |
| USDA CDL / CropScape | per-year crop mask | public | not yet tested |
| PRISM / ERA5 weather | GDD, precipitation | public (PRISM via Oregon State; ERA5 via Copernicus CDS) | not yet tested |
| Analyst consensus yield | the true expectation | **paywalled** | unavailable — substitute public proxies, state the substitution |
| CFTC COT | positioning controls | public | not tested |

The remaining gaps are all solvable in a day each: a free NASS key, the CDL crop mask, a
weather source, and a proper CME settlement history to replace the Yahoo continuous
series. None of them blocks Gate 0.

---

## 9. Evaluation protocol (pre-registration)

Before the first backtest, commit a `PREREGISTRATION.md` containing:

1. The exact target definition and the benchmark it is measured against.
2. The exact feature cut-off timestamp for each report.
3. The train/test split rule (leave-one-year-out, no shuffling).
4. The primary metric, the secondary metrics, and the decision threshold.
5. The null models and how many draws.
6. The claim that will not be made if the numbers do not support it.

After that, every change is appended with a date and a reason — the same discipline as
`PROGRESS.md` in the F1 project. Rule: a hypothesis may be added at any time, but it is
scored on data after the date it was written down. This is the only honest defence
against the garden of forking paths, and it is also the most interesting thing a reviewer
can read, because it shows what was predicted vs what was found.

Reporting rules:
- Every number gets a CI or a "n = X, too small to say".
- The backtest is reported against the null distribution, not as a standalone return.
- Anything that failed gets its own section ("Limits and things that did not work"), as
  in the pitwall README.

---

## 10. Deliverables

| # | Artifact | Audience |
|---|---|---|
| 1 | `PREREGISTRATION.md` | reviewer — proves this is not data dredging |
| 2 | Break-even surface (interactive + PNG) | anyone — answers "would this even pay" |
| 3 | Pipeline: STAC → H3 → Parquet → DuckDB, `make data` in one command | engineer |
| 4 | Model card: RMSE vs two baselines, calibration plot, failure cases | DS |
| 5 | Live dashboard: this season's yield estimate vs USDA vs market-implied | demo |
| 6 | `RESULTS.md`: the verdict, with the null distribution | everyone |
| 7 | 6–8 minute write-up: "I measured the tradable information in free satellite data for US corn" | hiring manager |

The dashboard is what gets looked at; the pre-registration is what gets believed.

---

## 11. Timeline

**MVP — 3 weeks, and it stands alone.**
Week 1: Gate 0 (break-even surface + power calculation) using public report and price
history only.
Week 2: Corn Belt pipeline for one state, 2018–2025, end to end.
Week 3: All main states, one model, out-of-sample RMSE, verdict on Q-A.

**Full arc — 6–8 weeks.** Adds SAR, the tail detector (Q-B), the null-model backtest,
the dashboard, and — if Gate 2 is negative — the Brazilian extension.

**Fallback if the trading framing dies at Gate 0:** the break-even surface plus the
nowcast is still a strong, publishable piece, and it takes three weeks.

---

## 12. How this project could fail

Stated up front, because a reviewer will ask.

1. **The signal is real and already priced.** Most likely outcome. Mitigation: Gate 0
   tells you before you spend the other five weeks.
2. **Cloud cover destroys the optical signal in exactly the years that matter.** 2019's
   wet spring is the known case. Mitigation: SAR is in the architecture from day one;
   but SAR biomass retrieval is much harder than NDVI and may not deliver.
3. **The August WASDE already contains satellite information.** NASS runs its own farmer
   surveys and weekly condition ratings, and private vendors sell satellite estimates to
   desks. If the incremental information is ~0, Gate 1 fails honestly.
4. **N is too small to say anything.** True by construction for the trading question
   (Trap 3). The project's defence is to aim at a large effect (Q-B) and to be explicit
   about what the sample cannot resolve.
5. **Scope.** Six weeks is long for a portfolio. Mitigation: the MVP is designed to be
   postable on its own after three.
6. **Licensing.** Sentinel and Landsat are open; MODIS is public domain; derivative
   products are fine to publish with attribution. Check before publishing tiles.

---

## 13. Prior art (read before building)

- Descartes Labs, *A peek at 2019 US corn yields from space* (2019) — the closest public
  analogue, and worth reading for how they handle county-level aggregation.
- Lobell et al., *Satellite-based crop yield monitoring* — the canonical review of what
  actually correlates with yield and at what scale.
- Johnson (2014), *An assessment of pre- and within-season remotely sensed variables for
  forecasting corn yield* — establishes NDVI's saturation problem and the July window.
- You et al. (2017), *Deep Gaussian process for crop yield prediction* — the standard
  ML benchmark on county data; note their use of county-level USDA as labels.
- USDA NASS weekly Crop Condition ratings — the incumbent public signal the model has to
  beat; free, weekly, state-level, and the market already reads it.
- The video's own conclusion: measurement without a pricing model is a hobby.

---

## 14. Open questions for you

1. **Scope.** Is three weeks the budget, or is this the big one for the year?
2. **The NASS key.** Worth registering (free, instant) — it unlocks state and county
   yields and weekly condition ratings, which is most of Gate 1.
3. **Verdict tolerance.** If Gate 2 says "no edge", is a rigorous negative result the
   deliverable, or does the project need a positive story to be worth posting?
4. **Brazil.** Is the safrinha extension interesting, or scope creep?
5. **Name.** `harvest-surprise` is the working title. Alternatives: `corn-belt-oracle`,
   `green-pixel`, `silking`.

---

## Appendix A — what the 337 top-level comments actually propose

Pulled with `yt-dlp --write-comments` (535 comments total). The distribution is
informative: almost nobody proposed a different *domain*; almost everybody proposed a
better *sensor* or a better *image-processing trick*.

| Cluster | Count | Representative | Worth anything? |
|---|---|---|---|
| Sensor/resolution upgrade (Planet, Airbus, InSAR, drones, own satellite) | ~25 % | "InSAR with Sentinel-1 is at least part of the answer" | Yes for the measurement; the whole point is that free data is the constraint, so this concedes the premise |
| Sun-angle/seasonality critique of the tank shadows | ~10 % | "even at the same local time, the sun's position changes with the season" | Correct and important; the video's sun-synchronous argument is weaker than claimed |
| Different domain (agriculture, retail, ports, tankers, scrap yards) | ~12 % | the ag comment at 237 likes | Agriculture is the best of them — big objects, multispectral bonus, liquid contract |
| "This is already done / no edge left" | ~5 % | "all the major players have integrated this" | The most useful category, and the one the project is designed to answer rather than dismiss |
| Image-processing improvements (subpixel, shadow modelling, clustering, super-resolution) | ~10 % | "cluster tanks by shadow pattern" | Straightforwardly useful; the subpixel-darkening trick generalises to partial canopy cover |
| Risk/derivatives framing (options, sizing, drawdown) | ~3 % | "buy options so downside is capped" | Out of scope but a real weakness of the video's long/short-only test |

> **Later check (2026-11-11).** These percentages were a reading, not a coded
> count. A keyword screen over `research/comments_all.csv` confirms the base
> number at **337 top-level comments** and supports four clusters to within about
> two points (sun-angle 8.9 % vs 10 %, different domain 10.7 % vs 12 %, already
> done 6.2 % vs 5 %, risk 4.2 % vs 3 %). Two are materially lower under that
> screen: **sensor/resolution 14.8 % vs the ~25 % claimed**, and **image
> processing 2.1 % vs ~10 %**. A keyword screen undercounts paraphrase, so these
> are a sanity check rather than a recount - but a five-fold gap on the
> image-processing cluster is too large to blame on wording alone. Treat the two
> high figures as **upper bounds until someone codes the corpus by hand**.

The single most useful reply in the thread, and the thesis of §6:

> "The issue with the stock market is that if it's easier to do… then the price is more
> likely to be correct rather than lagging. So the rarer the data the higher the variance
> of the actual price and the predicted price, meaning more profit if you are correct."

Also worth noting: one commenter claims to be a working ag trader and offers to answer
questions (`@user-7a15cd`). An hour of domain interview would be worth more than
a week of feature engineering, and it is the cheapest thing in this document to do.

And one correction the thread makes that the pipeline must absorb: crop rotation. The
same field is corn this year and soy next; a naive cell-level time series is measuring a
different plant each year. Hence the per-year crop mask in Gate 1.

---

## Appendix B — what was actually run for this brief

See `spike/RESULTS.md`. Summary: 25 years of MODIS NDVI over the Corn Belt were pulled
from Planetary Computer with no authentication — three composite dates a year across four
tiles, ~45 s per year — and joined to a national maize-yield series.

The result is more useful as a warning than as a win:

- July NDVI vs detrended yield: r = **0.56** (n = 24, p = 0.005); slope **+3.5 bu/ac per
  +0.01 NDVI**; leave-one-year-out RMSE improves from 10.25 to 9.82 bu/ac against a trend
  alone.
- **Remove 2012 and r falls to 0.33 (p = 0.12).** One drought is carrying the signal.
- In 2012 the NDVI anomaly understated the yield hit by a factor of four; in 2011 the
  canopy looked normal and the crop still came in 10 bu/ac below trend; in 2019 the
  canopy was the worst in the sample while yield barely moved, because that year's loss
  was acreage, not yield.

That is the evidence base for three design choices in the main proposal: heat and water
balance are required rather than a nice-to-have (2011 and 2012 both fail on greenness
alone); features must be phenology-anchored, not calendar-anchored; and the target must be
separated from acreage (2019). It is a data-access proof and a problem statement, not a
forecast.
