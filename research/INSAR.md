# InSAR at Cushing: first pair

**Job:** HyP3 `INSAR_GAMMA`, 2024-06-05 → 2024-06-17, track 34 ascending, 10 credits.
**Product:** 276 MB, coherence + unwrapped phase + LOS and vertical displacement.
**Credit balance after:** 7,990 of 8,000.

## The result that matters: coherence is high

| | median coherence | p25 | p75 |
|---|---|---|---|
| **tank roofs (416 tanks)** | **0.637** | 0.511 | 0.767 |
| whole scene | 0.745 | - | - |

Coherence over the tank roofs is **0.64**, comfortably above the ~0.3 that phase
needs. My prediction that moving roofs would decorrelate was **wrong**: metal roofs
on stable foundations are good radar targets, and 319 of 416 tanks pass a 0.5
threshold.

This is the finding that matters, because it means the radar route is not blocked
by physics the way the optical route was.

## The result I do not believe

The displacement over those tanks is **-2.68 cm vertical** (LOS -1.99 cm), with sd
0.63 cm across 319 pixels, while the surrounding scene sits at -0.28 cm.

Two checks kill it as a fill signal:

1. **The sign is wrong.** EIA Cushing stocks went from 33,815 kbbl (2024-06-07) to
   34,122 (2024-06-14): **+307 kbbl**. Stocks rose, so roofs should have risen.
   The implied motion is about +0.01 cm, not -2.7 cm.
2. **It is too uniform.** A -2.68 cm shift, identical across ~300 separate tanks
   with different fill levels, is not what fill-driven motion looks like.

The most likely cause is **not** DEM height error, which I checked: at a baseline
of 98.75 m a 20 m tank-height error produces only about 4 mm of apparent
displacement, not 27 mm.

A sharper test settles it. Fitting a plane to the per-tank displacement:

| | |
|---|---|
| tanks with usable phase | 374 |
| per-tank LOS displacement | -2.00 cm (sd 0.59) |
| tanks within 1 cm of the median | 95% |
| corr with longitude / latitude | -0.53 / -0.57 |
| **plane R-squared** | **0.667** |
| residual scatter after the plane | **0.34 cm** |

**Two thirds of the tank "displacement" is a smooth ramp across the scene** - the
signature of residual orbit error or atmospheric delay, not of roofs moving. The
tanks are not special; they are just where the ramp happens to be sampled densely.

The useful number is the residual: **3.4 mm**. If roof motion is centimetre-scale
between acquisitions, it sits above that floor once the ramp is removed. So the
measurement is viable, but only after deramping, which is a step HyP3 does not do
for you.

## What would settle it

Run several pairs with **different perpendicular baselines**. DEM error scales with
baseline; roof motion does not. If the tank offset tracks the baseline, it is an
artefact and the next fix is a better DEM or a base-pair choice with small baseline.
If it does not, the phase is measuring the roof and a time series against weekly EIA
stocks becomes worth building.

Cost: 10 credits per pair, 7,990 remaining - the constraint is time, not credits.

## Practical notes for whoever picks this up

- HyP3 is reachable and authenticated from the logged-in browser session:
  `GET /user`, `GET /costs`, `POST /jobs` with `validate_only: true` to price a job
  before submitting it.
- Products download from a public CloudFront link, no auth, ~260 MB, 21 seconds.
- Granule names must be exactly 67 characters and come from the ASF search API;
  inventing or truncating one returns `400 Some requested scenes could not be found`.
- Coherence GeoTIFF is on a 20 m grid, EPSG:32614, nodata 0.


---

# Round 5: three pairs, and the answer

Two more pairs were run to test the baseline dependence. All three, at 20 m
coherence grid, tank pixels with coherence > 0.5:

| pair | perpendicular baseline | median tank displacement | plane R2 | residual sd |
|---|---|---|---|---|
| 2024-06-05 to 06-17 | **-98.75 m** | **-2.00 cm** | 0.67 | 0.34 cm |
| 2024-06-05 to 06-29 | **+5.82 m** | **+0.11 cm** | 0.09 | 0.64 cm |
| 2024-06-17 to 06-29 | **+104.57 m** | **+2.39 cm** | 0.27 | 0.58 cm |

**The tank displacement is proportional to the perpendicular baseline and passes
through zero at zero baseline.**

That is not a fill signal. A roof that has moved does not care how far apart the
two satellite orbits were. This is the classic signature of a geometry-dependent
phase term - DEM error on structures that are taller than the terrain model, or a
baseline-dependent residual ramp. The near-zero-baseline pair, which should show
almost nothing if the roofs were still, shows +0.11 cm.

## Correction to the previous round

I wrote that InSAR was "alive" on the strength of a 3.4 mm residual. That was
wrong, for two reasons:

1. The residual is **not independent noise**. Nearest-neighbour correlation of the
   residuals is 0.88-0.98 across all three pairs, so the "3.4 mm" is a smooth
   field, not a per-tank precision floor. The effective number of independent
   samples is a handful, not 374.
2. The apparent motion is explained by the baseline, and the baseline is not a
   free parameter - it is set by the orbit pair.

## What would still be needed

A DEM that contains the tank shells, or enough pairs at many baselines to estimate
each tank's height error and subtract it. Both are real options; neither is what
HyP3 gives you off the shelf. Until then, **the honest reading is that free InSAR
at this configuration does not measure Cushing tank fill either.**

So the three instruments now agree, for three different reasons:

| route | why it fails |
|---|---|
| optical 10 m | signal 2.4% against 8.9% noise; needs 307% of capacity |
| SAR amplitude | no within-year correlation (+0.03 held out) |
| **InSAR phase** | **coherent (0.64) but dominated by a baseline-dependent geometric term** |


---

# Round 6: the pixel is not the roof

The baseline artefact was one problem. A bigger one shows up when the expected
motion is computed from the inventories.

## What the tanks should have done

One Cushing tank holds roughly 115-215 kbbl (48-90 Mbbl over ~416 tanks, 20 m
tall). A 1.286 Mbbl draw spread over the hub lowers every floating roof by
**25 to 54 cm**, depending on which capacity figure is used.

| pair | EIA stock change | expected roof motion | observed LOS |
|---|---|---|---|
| 2024-06-05 to 06-17 | **-1,286 kbbl** | **-29 to -54 cm** | -2.0 cm |
| 2024-06-17 to 06-29 | +119 kbbl | +2.6 to +5.0 cm | +2.4 cm |
| 2024-06-05 to 06-29 | **-1,167 kbbl** | **-26 to -49 cm** | +0.1 cm |

The observed motion is roughly a twentieth of what the inventories imply.

## The aliasing hypothesis, and why it is wrong

First explanation: at C-band one fringe is 2.79 cm, so 50 cm is ~18 fringes
across a 60 m tank, which at 20 m looks is six fringes per pixel - far above
Nyquist - so the phase would be aliased and the unwrapper would return garbage.

The wrapped phase tests it directly. Median horizontal phase gradient:

| | rad / pixel |
|---|---|
| tank pixels | **0.29** |
| whole scene | 0.15 |
| share of tanks above 1.0 rad/px | 3% |

Aliasing would put the gradient near pi (3.14). It is an order of magnitude
below that, and the tanks are only twice the scene. **The phase over the tanks is
smooth, so it is not aliased, which means the roofs are not moving the way the
inventory implies.**

## The explanation that survives

At 20 m resolution a 60 m tank is about three pixels. The backscatter from that
cell is dominated by whatever returns most energy - the steel shell, the rim, the
deck edge - not by the floating roof. The shell does not move. Coherence is high
(0.64) precisely because the shell is an excellent, stable scatterer, and the
phase is smooth because nothing in the cell is moving much.

The small residual offsets that do appear scale with the perpendicular baseline:
that is DEM error on a structure whose height is not in the terrain model.

**So the measurement is of the tank, not of the oil.** That is a different failure
from the optical one, and it is not fixed by better unwrapping.

## What would actually measure the roof

1. **Full-resolution SLC with the roof isolated** - if the roof is the dominant
   scatterer inside a tank, a single-look pixel at 10 m on the tank centre might
   see it. This is testable and I have not tested it.
2. **L-band** (ALOS-2, NISAR): lambda ~24 cm, so 50 cm is 2 fringes and phase
   would survive the geometry, but the pixel-content problem remains.
3. **Counting fringes across the tank geometrically** rather than unwrapping,
   which also does not help if the shell dominates.

## The honest summary of the tank thread

| route | why it fails |
|---|---|
| optical 10 m | signal 2.4% vs 8.9% noise; SNR 2 needs 307% of capacity |
| SAR amplitude | no within-year correlation |
| InSAR (HyP3, 20x4) | the 20 m pixel is dominated by the static shell, not the roof |
| InSAR (unwrapping) | **not the problem** - the phase is smooth, not aliased |

The tanks are detectable. What is not detectable, at this resolution, is the oil
inside them.


---

# Round 7: the distribution closes it

One hypothesis was left: maybe only a *subset* of tanks moves, so the median
cancels opposing motions. The near-zero-baseline pair (5.8 m) is the clean test,
because geometry contributes nothing there.

Per-tank LOS displacement, 347 tanks:

| quantile | displacement |
|---|---|
| p01 | -0.97 cm |
| p05 | -0.73 cm |
| p25 | -0.22 cm |
| p50 | +0.11 cm |
| p75 | +0.91 cm |
| p95 | +1.39 cm |
| p99 | +1.55 cm |

| | |
|---|---|
| share of tanks moving more than 5 cm | **0.0%** |
| share moving more than 10 cm | **0.0%** |

The whole distribution spans about two centimetres. There is no hidden population
of tanks carrying a 20-50 cm draw. **At 20 m resolution, the phase over Cushing
does not respond to inventory changes at all.**

## Where the failure actually lives

The scattering profile says the tanks are 17-30x brighter than the ground, peaking
at about 20 m radius - the wall - while the roof centre is bright but not dominant.
So a 20 m product pixel is a mixture of roof and wall, weighted toward the wall.

That dilution is a factor of two or three, not the factor of twenty observed. The
rest is not explained, and I will not pretend otherwise: the honest statement is
that the measurement does not respond, and the mixing explains only part of why.

## Recommendation: stop here

| route | status |
|---|---|
| optical 10 m | dead, SNR 0.27 (arithmetic) |
| SAR amplitude | dead, +0.03 held out |
| InSAR 20 m | dead, no response to inventory; distribution spans 2 cm |
| full-res SLC | **untested** - a different project |

Remaining credits: 7,920 of 8,000. More pairs will not change a distribution that
spans two centimetres.


---

# Round 8: the resolution was never what I said

Every statement in this document about "20 m pixels" was wrong. Reading the
GeoTIFF transform instead of assuming it:

| product | looks requested | true pixel size |
|---|---|---|
| 20240605-20240617 | 20x4 | **80 m** |
| 20240605-20240629 | 20x4 | **80 m** |
| 20240617-20240629 | 20x4 | **80 m** |
| 20240605-20240629 | 10x2 | **40 m** |

HyP3's `looks` parameter is range x azimuth looks on a ~2.3 m x 14 m SLC pixel,
not a request for a metre grid. The finest InSAR_GAMMA option it sells is 10x2,
which is 40 m.

**A Cushing tank is 30-60 m across. At 80 m it is smaller than one pixel.** So the
"pixel is not the roof" conclusion was right for a stronger reason than I gave: the
pixel contains the tank, several neighbours, and the ground between them, and is
dominated by whichever is most coherent - the ground.

This explains everything that was puzzling:

- the phase gradient is smooth (0.29 rad/px), because it is mostly ground phase
- per-tank displacements are nearly identical, because adjacent tanks share pixels
- the offsets follow the perpendicular baseline, because that is the ground's
  DEM error
- coherence is high, because ground and steel are both stable scatterers

## The 40 m experiment, and what it proves

The same 12-day pair, processed at 40 m instead of 80 m:

| looks | pixel | median tank displacement | spread (p01-p99) |
|---|---|---|---|
| 20x4 | 80 m | **+0.11 cm** | -0.97 to +1.55 cm |
| 10x2 | 40 m | **+6.72 cm** | +5.50 to +8.17 cm |

**The same interferogram, the same two dates, gives a displacement that differs by
6.6 cm depending only on the output grid.** No roof changed height because the
product was resampled. That is conclusive: the quantity is an artefact of
processing geometry, not a measurement of oil.

## Consequence

To see a roof at all, the phase would have to be computed at the native SLC
resolution (~2.3 m in range) and sampled on the roof itself. HyP3 does not offer
that, so this is not a matter of a better DEM - it needs a different processor.
