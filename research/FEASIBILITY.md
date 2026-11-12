# Feasibility study: every signal the comments proposed

Scope: 535 comments (337 root, 198 replies) from the source video, plus targeted
web research on each proposed signal family. The question is not "is this a cool
idea" but "can a solo researcher measure it with free data, validate the
measurement, and does the market link still exist".

Three filters, applied in this order. A candidate fails at the first filter it
misses.

1. **Physics** — is the object big enough and does its signal move slower than the
   revisit? (`resolution_grid.csv`, summarised in `CANDIDATES.md`.)
2. **Ground truth** — can the measurement be validated against something free and
   independent? Without this, you cannot know whether you measured the thing.
3. **Saturation** — is someone already selling it? If three vendors sell it, the
   alpha is gone and the project's only defensible contribution is the method.

---

## 1. Scorecard

| Signal | Physics | Free ground truth | Saturation | Verdict |
|---|---|---|---|---|
| Oil tank fill (floating roof) | yes, countable at 30 m | **yes** — EIA weekly Cushing | **severe** — Kayrros, Ursa, OilX, Vortexa | research contribution only |
| Parking-lot traffic | aggregate only at 10 m | partial — store sales | severe, and **documented alpha decay** | dead for a solo project |
| Port / container throughput | yes at 10 m (stacks) | partial — port authority stats | high — IMF, nowcasting vendors | method, not edge |
| Vessel AIS flows | n/a (not imagery) | yes — port calls | severe | data is the moat, not skill |
| Mine / smelter activity | yes | partial — company production reports | high — DBX, Earth-i, Kayrros | interesting where a single asset dominates |
| Gas flaring | yes (VIIRS Nightfire) | yes — calibrated against controlled tests | medium — EOG publishes the product | **best open-data measurement** |
| Reservoir storage | yes | **yes** — CDEC/USBR daily gauges | low for *measurement*, high for *signal* | **best first test** |
| Night lights | yes (VIIRS only) | partial — GDP, electricity | high — NOAA publishes it | background variable, not a signal |
| Cars / containers individually | **no** | n/a | n/a | physically impossible at 10 m |
| Drones instead of satellites | yes | yes | n/a | illegal or uneconomic at scale |

---

## 2. What the evidence says, per family

### Oil tank fill — the original idea, and why improving it is hard

Kayrros already measures **global** crude tank roof heights from Sentinel-1 InSAR
and sells the resulting inventory picture ([EARSC case study](https://earsc.org/sebs/wp-content/uploads/2020/02/Sebs-flyer_oil_200203.pdf)).
So the video's "nobody has done this with free data" framing is wrong; the free
data is exactly what the incumbent uses.

More importantly, there is a hard ceiling that no algorithm fixes: satellites can
read **external floating-roof tanks only**. Fixed-roof tanks block both optical
and radar, and underground caverns are invisible. China uses both of the
unreadable modes deliberately, which is why public estimates of Chinese crude
stocks disagree so much ([Collins & Hung, via Project Fifty-Four](https://projectfifty4.com/wp-content/uploads/2026/10/can-satellites-see-china-oil-storage.pdf)).

**Implication for this project:** the market for "tank fill from space" is
saturated *and* physically capped. The only defensible contribution is a better
estimator on the subset that is visible — which is a measurement paper, not a
trading project.

### Parking lots — the best-documented case, and the best warning

The definitive study is Katona, Painter, Patatoukas and Zeng: **4.7 million daily
observations across 67,078 store locations and 44 US retailers**, using RS
Metrics and Orbital Insight feeds. The edge was real — **4-5% informational
advantage in the three days around earnings** — and it existed *because the data
was expensive and almost nobody had it*. As the feeds became standard, the edge
decayed ([summary](https://www.linkedin.com/posts/quant-craft_quantfinance-alphadecay-alternativedata-activity-7474830813793136640-9rPH);
the underlying paper is Katona et al., *On the Capital Market Consequences of
Alternative Data*).

This is the single most important result for this project, because it defines the
mechanism: **the alpha was in the access, not the analysis.** A free-data
replication cannot have that alpha, by construction.

### Ports and trade — real, and now an IMF product

The IMF publishes trade nowcasts built on AIS vessel data, including a ballast
water correction that materially improves cargo estimates
([IMF WP/25/093](https://meetings.imf.org/-/media/Files/Publications/WP/2025/English/wpiea2025093-print-pdf.ashx)).
A recent paper nowcasts **port-level** maritime trade from **publicly available**
satellite imagery with XGBoost ([arXiv 2604.15444](https://d.repec.org/n?u=RePEc:arx:papers:2604.15444)).
So the public-data version already exists in the literature — a solo project would
be reproducing it, not extending it.

### Mining and smelters — the most interesting "single asset" case

Commercial vendors track individual mine systems with AIS + SAR + thermal,
reporting things like mill throughput as a percentage of pre-incident levels
([DBX Commodities example, Grasberg](https://www.linkedin.com/posts/dbx-commodities_copper-coppermarket-commodities-activity-7418946688943288320-IgED)).
The signal logic is sound: a single large mine can move a metal price, and the
physical footprint (open pit, stockpile, mill, port) is enormous — the physics
filter says *countable at every resolution*.

The weakness is ground truth: production reports are quarterly and coarse. You
can measure activity, but you cannot easily prove your measurement is right.

### Gas flaring — the best-calibrated free measurement on Earth

VIIRS Nightfire estimates flared volume from radiant heat, **calibrated against
controlled flare tests**, now monthly and source-resolved from 2012 to 2025
([EOG / multiyear VNF study](https://www.scilit.com/publications/99e60f5b9a97c52fa8048abc896b1ef2)).
Global upstream flaring was **164.5 BCM in 2025**, the third consecutive annual
increase.

This is the gold standard for what a free-satellite measurement can look like:
physical units, calibration, uncertainty, monthly cadence. It is also *already
published*, so the value is in combining it with something else, not in
reproducing it.

### Reservoirs — free measurement *and* free ground truth

A review of reservoir remote sensing finds area-volume and level-volume curves
typically achieve **10-20% mean error**, and that volume estimates need in-situ
validation which is usually missing
([review](https://www.sciencedirect.com/science/article/pii/S2666017226000210/pdfft)).
That is the key sentence: *most reservoirs have no validation*.

California is the exception. CDEC publishes daily elevation and storage for every
major reservoir, free and keyless. So the measurement can be scored against a
gauge, which almost none of the other signals allow.

### Alpha decay — the meta-result

Hedge funds spend **over $10 billion a year** on alternative data, the catalogue
has tripled in five years, and the alpha window on commercial datasets "closes
faster than people expect" ([industry summary](https://www.linkedin.com/posts/zenpulsar_alternativedata-commoditymarkets-marketintelligence-activity-7442855113460809728-oT1z)).
Combined with the Berkeley result, the prior for any free-data replication of a
commercial signal is: **the edge is already gone**.

---

## 3. What this changes about the existing project

The corn project's conclusion was "the information is real, the free model does
not produce it". The research says the same mechanism explains the whole genre:

- The tank-fill idea is **commercially implemented on the same free data** the
  video used (Kayrros, Sentinel-1).
- The parking-lot idea's edge came from **data access**, and it decayed.
- Port nowcasting is an **IMF working paper** and an arXiv paper on public data.

So "find a physical signal and trade it" cannot be the contribution. What can be:

1. **A measurement contribution** — do something demonstrably better on a
   quantity that matters, validated against ground truth.
2. **A coverage contribution** — measure something nobody measures *because the
   ground truth is hard*, and prove it with the few places it is not.
3. **A negative result** — show precisely which of these signals are dead, and
   why, with the arithmetic.

The reservoir work is (1) and (2): free ground truth exists in California, so the
method can be validated there, and then applied to the thousands of reservoirs
where no gauge exists.

---

## 4. Chosen prototype: reservoir storage from Sentinel-2, validated against CDEC

Why this and not the others:

- **Physics passes**: reservoirs are 10^6-10^7 m², countable at every free
  resolution.
- **Ground truth exists and is free**: 10 California reservoirs, daily, 2017-2025,
  keyless.
- **Not commercially saturated as a measurement**: the vendors sell tank and port
  signals, not reservoir levels, and the literature explicitly says most
  reservoirs have no validation.
- **It has a real market link to test later**: reservoir storage -> hydro
  generation -> electricity prices, and -> irrigation deliveries -> crop acreage.

Method: NDWI water mask on Sentinel-2 10 m bands, cloud-masked with the scene
classification layer, water area per scene, then a per-reservoir area-to-elevation
rating curve fitted by leave-one-out and scored in feet against the gauge.

Results land in `REPORT_RESERVOIRS.md` (next), and the raw run in
`data/processed/reservoir_*`.

---

## 5. Source quality

| Claim | Source | Quality |
|---|---|---|
| Kayrros uses Sentinel-1 InSAR for tank roofs | EARSC case study PDF | trade body, solid |
| Only external floating-roof tanks are readable | Project Fifty-Four report | specialist, plausible, not peer-reviewed |
| 4.7M parking observations, 4-5% edge | Katona et al.; read via a secondary summary | **secondary** - the paper is not read here |
| IMF AIS trade nowcast | IMF working paper | strong |
| Port nowcast from public imagery | arXiv 2604.15444 | preprint |
| VIIRS Nightfire calibration and 164.5 BCM | EOG / Scilit summary | strong |
| Reservoir 10-20% curve error | ScienceDirect review | strong |
| $10B alt-data spend, alpha decay | LinkedIn industry post | **weak** - directional only |

Two of these I read only through a summary, and one is a social post. They are
flagged rather than dropped because the direction of each claim is corroborated
by the others, but they should not be quoted as precise numbers.
