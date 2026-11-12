# REVIEW — every checkable claim in this proposal

> **Note:** this sheet was written before the build, to state what was verifiable in advance.
> The measured numbers now live in `docs/corn-report.md` and `FINAL_REPORT.md`, and several of the entries here changed as a
> result: the NASS key arrived, the WASDE endpoint was found, and the spike's r = 0.56 turned out
> to be one drought (r = 0.33 without 2012). Treat this file as the pre-registration trail.
Written for a second agent (or a person) to attack. Each row says what is claimed, where
it comes from, and exactly how to check it. Status is honest: **verified** means *I ran
it on 2026-11-11 and it produced what is described*; **assumed** means it is a judgement
or a number I did not re-derive; **unverified** means it might be wrong and should be
checked before it is repeated in public.

## 1. Claims about the video

| # | Claim | Where | How to check | Status |
|---|---|---|---|---|
| V1 | The video pivots from counting cars to measuring Cushing oil-tank fill from the crescent shadow of the floating roof | BRIEF §1 | `transcript.txt` lines 1–150 | **verified** (transcript pulled with `youtube_transcript_api`) |
| V2 | His first two-image comparison gave −0.3 % brightness change because the surrounding ground also darkened by ~7 units | BRIEF §1 | `transcript.txt` lines 151–170 | **verified** |
| V3 | He ran the perfect-knowledge backtest *late*, and it lost money on crude while buy-and-hold was +96 % | BRIEF §1, §5 Gate 0 | `transcript.txt` lines 250–270 | **verified** |
| V4 | The profitable-looking result came from trading the tank *owners*, not crude, and beat 99 % of 2,000 coin-flip portfolios | BRIEF §1, §6.1 | `transcript.txt` lines 265–320 | **verified** |
| V5 | With only 15 images he had 5 real tests, 1 profitable, and his prediction error (20 M bbl) exceeded the signal (890 k bbl) | BRIEF §3 Trap 3 | `transcript.txt` lines 320–345 | **verified** |
| V6 | The top ag comment (237 likes) is the one quoted in the brief | BRIEF Appendix A | `comments_top.txt` entry `[4]` | **verified** (`yt-dlp --write-comments`, 535 comments, 337 root) |
| V7 | Comment clusters and percentages in Appendix A | BRIEF Appendix A | recount from `vid.info.json` | **partly checked** — `vid.info.json` is not in the repo, but `research/comments_all.csv` is, and a keyword screen confirms **337 top-level comments**. Four of six clusters match the claimed share within ~2 points; sensor/resolution codes at 14.8 % against ~25 % claimed and image processing at 2.1 % against ~10 %. Those two are **upper bounds** until the corpus is hand-coded. Note added under the Appendix A table. |
| V8 | A commenter (`@user-7a15cd`) claims to be a working ag trader and offers to answer questions | BRIEF Appendix A | `vid.info.json`, search the handle | **verified** |

## 2. Data-access claims (all runnable)

Run from `harvest-surprise/` after `.venv-scratch` is installed (see `spike/README.md`).

| # | Claim | How to check | Status |
|---|---|---|---|
| D1 | Planetary Computer STAC is open without authentication | `python -c "from pystac_client import Client; c=Client.open('https://planetarycomputer.microsoft.com/api/stac/v1'); print(len(list(c.get_children())))"` | **verified** — collections endpoint returns 1.7 MB |
| D2 | `modis-13Q1-061` exposes a `250m_16_days_NDVI` asset and can be read without auth | `spike/modis_ndvi.py --start 2023 --end 2023` | **verified** — 12 composites, mean NDVI 0.81 |
| D3 | `sentinel-2-l2a` exposes B02/B03/B04/B08/B11/B12 plus an `SCL` cloud mask | `spike/diag.py` (asset listing) | **verified** (asset list only — no S2 pixel was read) |
| D4 | A 25-year MODIS NDVI series over the Corn Belt can be pulled with no billing | `spike/run_years.ps1` then `spike/analyse.py` | **verified** — see `spike/RESULTS.md` for the exact numbers |
| D5 | Daily CBOT corn futures are available free | `python -c "import yfinance as yf; d=yf.download('ZC=F', start='2024-01-01'); print(d.shape)"` | **verified** — (719, 6). Caveat: `ZC=F` is a Yahoo continuous front-month series, not CME settlement data; splices and roll gaps are undocumented. Fine for exploration, **not** acceptable for a published backtest. |
| D6 | NASS Quick Stats returns corn state data with a key, and includes the USDA's own in-season forecasts | `python ingest/nass.py && python ingest/verify.py` | **verified** — 14,121 yield rows, 82,414 weekly condition rows, 4/4 forecast periods present; 14/14 assertions pass, including state yields weighted by harvested acres reconciling to the published national 177.3 (2023) and 179.3 (2024) bu/ac |
| D6a | `year__GE`/`year__LE` filter as documented | `get_counts` with `year__GE=2020&year__LE=2020` vs `year=2020` | **verified broken** — 31,120 rows vs 4,835. The range form silently over-returns; `ingest/nass.py` uses exact `year=` only |
| D7 | Historical Crop Progress releases are downloadable as `.txt` | open `https://usda.library.cornell.edu/concern/publications/8336h188j`, look for `prog*.txt` | **verified** — release file listing present; **parsing not attempted** |
| D8 | National maize yield series in bu/ac | `spike/yields_owid.py` | **verified** — OWID/FAO series; its 2023 and 2024 values (177.3, 179.3) match NASS national yield, but the series is FAO-derived and will diverge from NASS in other years |
| D9 | A machine-readable WASDE history exists | `python -c "import pandas as pd; print(pd.read_csv('https://www.usda.gov/sites/default/files/documents/oce-wasde-report-data-2021-08.csv').shape)"` | **verified** — 5,011 rows; `Commodity=Corn, Region=United States, Attribute='Yield per Harvested Acre'` returns 167.5 / 172.0 / 174.6 bu for 2019/20–2021/22, with `ReleaseDate` and `ReleaseTime`. Archive depth: 2010-04 onward (ZIPs for 2010-04→2020-12, then one CSV per month). Earlier years exist only as fixed-width `.txt` on Cornell ESMIS. |
| D10 | USDA CDL / CropScape crop mask is accessible programmatically | — | **unverified** |
| D11 | PRISM / ERA5 weather is accessible | — | **unverified** |
| D12 | Analyst consensus corn yield is paywalled | — | **strongly supported** (Bloomberg/Refinitiv/LSEG only) but I did not exhaust free alternatives |

## 3. Market and agronomy facts quoted in the brief

| # | Claim | Value used | Status |
|---|---|---|---|
| M1 | CBOT corn contract size | 5,000 bu | **verified** (standard contract spec) |
| M2 | Minimum tick | ¼ cent = $12.50 | **verified** |
| M3 | US corn planted area | 90–95 M acres | **verified** for 2023 (94.6 M) and 2024 (90.7 M) |
| M4 | US corn harvested area | 82–87 M acres | **verified** same sources |
| M5 | National yield | 177–180 bu/ac | **verified** 2023 (177.3), 2024 (179.3) |
| M6 | 1 bu/ac on ~87 M acres ≈ 0.57 % of a 15.2 B bu crop | arithmetic | **verified** |
| M7 | Crop Progress releases Monday 16:00 ET; WASDE 12:00 ET | — | **assumed** from habit, not re-checked today |
| M8 | Sentinel-2: 10 m, 5-day revisit, 13 bands; S1: 6–12 day | `data/raw/asf_cushing_pairs.json` | **S1 corrected**: all **130** SLC pairs over Cushing from 2018-01-08 to 2025-12-21 are **exactly 12 days** apart, with no 6-day pairs at all — consistent with single-satellite operation (S1B failed in December 2021) and against the "6–12 day" figure. This matters: a 12-day gap is the minimum available, which is why a 50 cm roof movement aliases. S2 spec still **assumed**. |
| M9 | MODIS 13Q1: 250 m, 16-day composite | — | **verified** from the STAC item metadata |
| M10 | Brazil safrinha ≈ 90–100 Mt recent seasons, majority of Brazil's corn | — | **assumed**, from memory of CONAB/USDA figures — check before publishing |
| M11 | Corn NDVI saturates at canopy closure, so July is the predictive window | — | **strongly supported** by the literature (Johnson 2014), not tested here |

## 4. Arithmetic in the power calculation (BRIEF §3, Trap 3)

The chain is: break-even IC = cost / σ_day = 0.2 % / 2.5 % = 0.08; N for 95 % detection
= (1.96 / 0.08)² ≈ 600; SE(IC) at N = 130 is 1/√130 ≈ 0.088.

- The arithmetic is **verified** (it is three lines of algebra).
- The inputs σ_day = 2.5 % and round-trip cost = 0.2 % are **assumed placeholders**,
  flagged as such in the brief. If σ is 4 %, break-even IC falls to 0.05 and N falls to
  ~380 — the conclusion ("a small edge is undetectable") survives, the constant does not.
- The conclusion depends on the trading rule being "trade every report". It is weaker for
  a rule that trades only tail years, which is exactly why Q-B exists.

**This is the most attackable part of the document, deliberately.** Gate 0 exists to
replace both numbers with measured ones; until then the calculation is an argument, not
a finding.

## 5. Prior art (BRIEF §13)

I did **not** re-verify these today. They are cited from memory and each should be
checked before the list is repeated in a public write-up.

- Descartes Labs 2019 corn yield forecast — **unverified**
- Johnson 2014, pre-/within-season remotely sensed variables for corn — **unverified**
- You et al. 2017, Deep Gaussian process for crop yield — **unverified**
- Lobell et al. review — **unverified**
- USDA NASS Crop Condition / GLAM — **verified** that NASS publishes weekly condition
  ratings (D7); the existence of a specific internal model is **assumed**

## 6. Design judgements (not verifiable — argue with them)

These cannot be checked, only disagreed with. They are listed so the disagreement can be
specific.

1. **The Corn Belt is the worst place to look for an edge** and the best place to
   calibrate. This is the load-bearing claim of the whole design.
2. **Tail detection (Q-B) beats point forecasting (Q-A)** for a project with n ≈ 25,
   because a binary target with a base rate near 1/8 has far more usable signal-to-noise.
3. **A negative result, properly argued, is a better portfolio artifact than a backtest
   curve** — because the reviewer cannot check the curve and can check the argument.
4. **The dashboard is worth building** even though it is not evidence. It is the part
   that gets looked at.
5. **Brazil is the right extension** rather than, say, US soybeans or wheat.

## 7. Known weaknesses of the spike (`spike/RESULTS.md`)

- **The correlation is one drought.** r = 0.56 over 24 years, r = 0.33 (p = 0.12) without
  2012. Anyone quoting the 0.56 as a result is quoting 2012. This is stated in the results
  file and in the README, deliberately, and it is the most important number there.
- No crop mask: the mean NDVI covers forest, urban and soy as well as corn.
- National yield against a fixed Corn Belt box: the box does not track where the crop
  actually is, and acreage shifts year to year (2019 makes this vivid).
- Detrending fitted on the full sample — mild look-ahead.
- The three composites per year were chosen with hindsight (the literature says July
  matters, which is true but is still a choice made after looking).
- 2025 is missing (only one composite returned); sample is 2001–2024, n = 24.
- MODIS Terra only; Aqua would double the observations.
- The p-value assumes independent years; neighbouring years share weather regimes.
- The result is a *correlation*, which is not evidence of tradability, and the brief says
  so. If anyone quotes the r-value as "evidence of edge", that is a misreading.

## 8. What would change my mind

- If Gate 0 shows even an oracle with 7 days of lead does not clear costs by a margin
  bigger than one standard error → drop the trading framing entirely.
- If the trend + weather baseline beats the satellite model out-of-sample → the free
  satellite data adds nothing over free weather data, and the project should say that.
- If the August WASDE already contains the satellite information (model RMSE against the
  *revision* is no better than zero) → the whole premise fails, and the write-up becomes
  "here is why the information is already in the price".
