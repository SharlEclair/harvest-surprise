# Cushing tank fill: the video's project, rebuilt

The video measured floating-roof fill from Sentinel-2 and compared two dates,
getting -41% against an actual -63%. He had 15 images and annual EIA numbers.
This uses **320 scenes** and **weekly EIA stocks**, and gets further — but not
all the way.

## What was built

| step | this version | the video |
|---|---|---|
| tank locations | **416 tanks from OpenStreetMap** | hand-picked X/Y points and radii |
| imagery | 320 Sentinel-2 L2A scenes, Apr-Oct 2018-2025, cloud < 10% | 15 images over 5 years |
| normalisation | tank-pixel median divided by ground-pixel median, per scene | learned the hard way after a -0.3% false result |
| ground truth | **EIA weekly Cushing stocks, 1,178 weeks, 2004-2026** | two annual EIA figures |
| metric | correlation across the full series | percent change between two dates |

The per-scene measurement is the median red-band brightness of the 416 tank
centres divided by the median brightness of non-tank pixels in the same window.
A floating roof that is emptying slides down and exposes a growing crescent of
shadow, so the ratio should fall as stocks fall.

## Results

| test | n | correlation |
|---|---|---|
| levels, raw | 320 | **+0.628** |
| levels, de-seasonalised by month | 320 | +0.638 |
| levels, detrended | 320 | **+0.378** |
| levels, excluding 2020-21 | 252 | +0.574 |
| first half of sample | 160 | +0.449 |
| second half of sample | 160 | +0.267 |
| **4-week change vs 4-week change** | 276 | **-0.155** |

### The aggregate correlation is between-year, not within-year

An adversarial check split the sample by year. **Within any single year the index
barely tracks stocks, and in 2022 it is strongly negative:**

| year | r | n |
|---|---|---|
| 2018 | -0.295 | 24 |
| 2019 | +0.097 | 40 |
| 2020 | -0.280 | 36 |
| 2021 | +0.036 | 32 |
| 2022 | **-0.557** | 57 |
| 2023 | +0.219 | 61 |
| 2024 | +0.600 | 32 |
| 2025 | -0.075 | 38 |

The +0.63 survives an iid shuffle (p < 0.0001) and a year-block shuffle (p = 0.014),
but that only says the *annual means* move together across eight years. It is
consistent with a slow confound - sensor drift, atmospheric correction changes,
ground cover, or the changing mix of tank types - and it is not evidence that the
index measures fill.

**The earlier claim that "the measurement works" was wrong.** The correct
statement is that annual averages co-move; within-year tracking is absent.

Three readings, and they point different ways.

1. **The aggregate is real but weak evidence.** Detrending leaves +0.38 and
   dropping the COVID years leaves +0.57, but the within-year breakdown above
   shows that whatever is driving it operates at the year level.
2. **It decays.** First half +0.45, second half +0.27. Either the measurement is
   drifting, or the relationship is getting noisier. That is the same alpha-decay
   shape the literature describes, and it argues against assuming it persists.
3. **The tradeable version does not work.** Levels correlate; *changes* do not
   (-0.155). A trading rule needs the flow, not the level, and the index does not
   have it. This is the same conclusion as the corn study, reached independently:
   the level is measurable, the surprise is not.

## What would be needed to make it tradeable

- **Separate floating-roof from fixed-roof tanks.** Only external floating-roof
  tanks carry the signal; averaging 416 tanks of unknown type dilutes it. OSM
  tags sometimes carry `tank:type`, but I did not verify coverage here.
- **Per-tank, not pooled.** The video's own insight was that the shadow never
  exceeds one radius, so the informative pixels are on one side. Measuring each
  tank's own time series would separate signal from scene-level brightness drift.
- **Intraday or same-day prices** rather than a weekly stocks target, if the goal
  is a trading claim rather than a measurement claim.

## Reproduce

```powershell
python analysis/cushing_tanks.py       # ~40 min, 320 scenes
python analysis/cushing_validate.py    # correlation table and figure
```

Outputs: `data/processed/cushing_scenes.csv`, `cushing_validation.csv`,
`cushing.png`. Data: `data/raw/cushing_tanks.json` (OSM) and
`data/raw/eia_cushing_weekly.csv` (EIA).


## Radar result

84 Sentinel-1 RTC scenes, 2018-2025 (every fourth acquisition; all ascending):

| subset | n | levels r | within-year train | within-year **test** | 4-week change train |
|---|---|---|---|---|---|
| all | 84 | -0.261 | +0.007 | **+0.026** | -0.110 |

**No within-year signal.** Amplitude backscatter does not track fill either.

That is not surprising in hindsight. The commercial method is **InSAR** - it uses
the *phase* difference between acquisitions to measure roof height changes at
centimetre scale, not the amplitude. Amplitude over a tank averages the roof, the
wall, the rim and the shadow into one number, which is the same problem the
optical method has.

So the free-data barrier is not image access - Sentinel-1 and Sentinel-2 are both
free and both cover Cushing every few days. **The barrier is processing
sophistication**: interferometric phase, coregistration and unwrapping, which is a
different project from this one.

## Verdict

Optical: aggregate correlation is between-year only; within-year -0.10 to +0.09
across every aggregation tried, and the one that looked good (+0.42) failed
out-of-sample at -0.10.

Radar amplitude: +0.03 out-of-sample. Nothing.

The video's conclusion - "does it make money? honestly, no, not yet" - survives a
much more thorough attempt. The difference is that this version can say *why*: not
because the idea is wrong, but because both free instruments need a processing
step (interferometric phase, or 3 m imagery) that the free-data route does not
supply.


---

# Round 3: why it cannot work at 10 m

Two nulls do not explain themselves. This computes the signal the method could
possibly see, and compares it to the noise actually measured.

**Signal.** A hub-wide stock change of `ds` drops every floating roof by
`dh = H * ds / C`. That casts a shadow of `L = dh / tan(theta)`, covering a
fraction `L/d` of the roof, which changes mean brightness by `(L/d) * contrast`.

**Noise**, measured rather than assumed: the median per-tank brightness standard
deviation after removing the scene mean is **594.9 DN on a level of 6,716, i.e.
8.9%**. That is temporal variability specific to a tank, with illumination and
atmosphere already removed.

| stock change (Mbbl) | roof drop (m) | shadow (m) | brightness change | SNR |
|---|---|---|---|---|
| 1 | 0.42 | 0.24 | 0.12% | **0.014** |
| 5 | 2.08 | 1.20 | 0.60% | 0.068 |
| 20 | 8.33 | 4.81 | 2.4% | 0.27 |
| 45 | 18.75 | 10.8 | 5.4% | 0.61 |

(at 48 Mbbl capacity, 60 m tanks, 20 m height, solar elevation 60 degrees)

**To reach SNR 2, Cushing would have to gain or lose 147 Mbbl - about 307% of its
working capacity.** That is not a hard problem, it is an impossible one at 10 m.

## It also reconciles the two results

Averaging N scenes improves SNR by root N. Annual means pool roughly 40 scenes,
so the 20 Mbbl seasonal signal reaches SNR 0.27 x 6.3 = **1.7** - marginal, which
is exactly why the aggregate correlation was real but weak and why it was a
between-year effect. A one-week change of 1 Mbbl stays at 0.014 even after
averaging within a season.

**The observed pattern was predicted by the arithmetic before I ran the last two
experiments.** That is the confidence this round was for.

## What this says about the commercial method

DigitalGlobe's Cushing estimates came from sub-metre imagery, where a 60 m tank is
120 pixels across and the crescent is directly resolvable. Kayrros uses InSAR
phase, which measures roof height at centimetre scale independent of pixel size.
Neither is a rival measurement to this one; both are on the other side of a
resolution or processing barrier that free 10 m imagery does not cross.


# Round 4: other places

The noise floor was the one input that could change the verdict, so it was
measured at three more hubs with the same method (OSM tanks, 20 cloud-free summer
scenes, per-tank residual SD after removing the scene mean):

| hub | tanks | noise floor | SNR at a 20 Mbbl move |
|---|---|---|---|
| **Cushing** | 416 | **8.9%** | 0.27 |
| Fujairah, UAE | 258 | 10.8% | 0.22 |
| Houston, TX | 674 | 11.9% | 0.20 |
| Rotterdam, NL | 460 | 18.6% | 0.13 |

The desert hypothesis was wrong: Fujairah is dirtier than Cushing, and Cushing is
the cleanest of the four. The best possible signal - a 45 Mbbl swing, near the
hub's whole working capacity - is 5.4%, and the cleanest site still buries it.

**No hub at 10 m crosses detection.** The result generalises, which is what makes
it a conclusion rather than a site-specific failure.
