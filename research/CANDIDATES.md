# Candidate signals: what the comments propose, and what the physics allows

Built from the full comment corpus (`comments_all.csv`: 535 comments, 337 root,
198 replies) plus `analysis/resolution_filter.py`.

Two filters are applied before any market argument:

1. **Physics.** Can a free sensor see it? `resolution_grid.csv` computes, for every
   candidate, the fraction of a pixel the object covers, the resulting
   signal-to-noise, and whether the object is countable or only visible in
   aggregate. Scene noise is 5% over mixed urban ground and 2% over uniform
   backgrounds; using 2% everywhere is what makes naive analyses claim a single
   car is detectable at 10 m. It is not.
2. **Revisit.** Does the signal move faster than the free sensor returns? A daily
   signal sampled every 5 days is aliased, not measured.

Only then does the market question arise.

---

## What the comments actually propose

54 comments propose a trackable domain. Sorted by what people actually meant:

| # | Proposal | Comment evidence | Likes |
|---|---|---|---|
| 1 | Wheat / other ag futures | "I've heard of people using satellites in wheat futures and other agriculture commodities" | 459 |
| 2 | Corn Belt yields | "Try agricultural yields instead... focus on the Corn Belt and backtest against CBOT corn futures" | 237 |
| 3 | Parking lots as a unit, not cars | "use the entire parking lot and take that as a unit, tracking changes in brightness" | 46, 3 |
| 4 | Oil tankers docking / at anchor | "checking for oil ships... when they dock in different ports" | 72 |
| 5 | Tankers at port, full supply chain | "going even further back in the supply chain and looking at satellite data for oil tankers docked at port" | 13 |
| 6 | Ports, containers, trucking, fallow farms | "retail, containers at ports, trucking companies with rigs that are parked vs out and about, farms cultivated vs fallow" | 0 |
| 7 | Reservoir water levels | "a similar idea being used to estimate the water level in reservoirs" | 1 |
| 8 | InSAR / SAR instead of optical | "InSAR with Sentinel-1 is at least part of the answer... WAY more accurate tank levels" | 3 |
| 9 | Drones instead of satellites | 8 separate comments propose flying a drone over the site | 2-7 |
| 10 | Super-resolution / subpixel | "low resolution imagery could potentially be super resolved"; "Subpixel feature detection is a thing" | 1-2 |
| 11 | Synthetic training data (Blender) | "train an image recognition model based on procedurally generated images" | 6 |
| 12 | Night lights / electricity | only one, indirectly ("Natural Gas likely goes up in winter") | 0 |
| 13 | Scrap yards, logging, misc | "There's a scrap yard just up the road... when the scrap pile is getting larger it means scrap prices are low" | 7 |

**Three meta-objections appear repeatedly and are correct:**

- *It is already done.* "All the major players have already integrated this data into their models so the information edge no longer exists" (5 likes, plus a 89-like variant). This is the alpha-decay problem and it is the single biggest risk to every candidate below.
- *You are ignoring 95% of what sets the price.* "if you are going to trade oil futures on tank levels, you are ignoring 95% of the data that determines the price of oil futures".
- *Goodhart.* "When a measure becomes a target it stops being a measure... this gonna do is make a market for fake parking lots."

---

## The physics verdict

From `analysis/resolution_filter.py`, using only free sensors:

| Signal | S2 10m | Landsat 30m | MODIS 250m | VIIRS 375m | Verdict |
|---|---|---|---|---|---|
| oil tank floating roof | countable | countable | aggregate | - | **works** |
| open pit mine bench | countable | countable | countable | countable | **works** |
| reservoir surface | countable | countable | countable | countable | **works** |
| corn field canopy | countable | countable | countable | countable | **works** (done) |
| construction site | countable | countable | - | - | **works** |
| coal / ore stockpile | countable | countable | countable | aggregate | **works** |
| product tanker at berth | countable | countable | aggregate | - | **works** |
| new single-family house | countable | aggregate | - | - | works in aggregate at 30 m |
| gas flare | countable | aggregate | - | countable (Nightfire) | works, revisit mismatch |
| night-time light | n/a | n/a | n/a | countable | VIIRS only |
| **car in a parking space** | **aggregate only** | not measurable | - | - | only as a lot average |
| **truck trailer** | **aggregate only** | aggregate only | - | - | only as a lot average |
| **shipping container** | **aggregate only** | aggregate only | - | - | only as a stack average |

Two results contradict the comment section directly:

- **Counting cars from Sentinel-2 does not work**; measuring a *parking lot's* mean
  brightness does, and that is exactly what the better comments proposed. The
  video's own framing ("count the cars") is the one that fails.
- **Shipping containers are not individually resolvable at 10 m**; the signal is
  the *stack* area, which is fine because ports are measured by throughput anyway.

And one result contradicts the video's central complaint: **the oil tank really is
countable at 30 m, not just at 10 m**, so the "10 m is terrible" premise was
overstated — the object was always large enough. What was hard was the
*radiometry*, not the resolution.

---

## The three-filter shortlist

Ranked by (physics works) AND (free data) AND (plausible market link that is not
already saturated).

| Rank | Signal | Why it survives | Main risk |
|---|---|---|---|
| 1 | Reservoir / water levels | large object, free altimetry, links to hydro and irrigation, thin public coverage | altimetry is point-based, lakes not reservoirs |
| 2 | Mine and smelter activity | large objects, free S2, links to metal prices and miner equities | monthly cadence, small market |
| 3 | Product tankers at berth | large object, free S1, links to freight and refinery runs | AIS is the cheaper substitute |
| 4 | Oil tank fill (the original, improved) | countable at 30 m, radiometry solvable with a reference patch | heavily saturated by vendors |
| 5 | Construction / housing starts | countable, free S2 | already sold widely |
| 6 | Parking-lot brightness | aggregate works, but revisit is 5 days vs a 1-day signal | aliasing + weak link to earnings |

Everything below rank 6 is either physically impossible with free data (cars,
containers individually) or a solved problem sold by three vendors.

---

## What this implies for the next step

The interesting gap is not "can I see X" — the filter above settles that in an
afternoon. It is **which of the physically-visible signals has a market link that
is not already arbitraged**, and the honest prior is: none of the obvious ones.

That is why the next document (`FEASIBILITY.md`, to follow once the web research
returns) scores each candidate on *existing product coverage* and *documented
alpha*, not just on physics. A signal three vendors sell cannot be the centre of
a portfolio project unless the project's contribution is the measurement method
itself.

---

## Corpus provenance

- `comments_all.csv` — 535 rows: id, author, likes, is_reply, parent, text.
- `build_corpus.py` — rebuilds it from the yt-dlp metadata dump.
- `resolution_grid.csv` — every signal x sensor pair with the arithmetic behind
  the verdict above.
