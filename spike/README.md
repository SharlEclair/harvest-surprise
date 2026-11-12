# spike — what was actually run

A feasibility check, not a result. The question it answers: *can this machine pull a
25-year vegetation-index series over the Corn Belt, with no account, no key and no
download budget, and does the series track the national corn yield?*

## Reproduce

```powershell
cd harvest-surprise
uv venv .venv-scratch --python 3.13
uv pip install --python .venv-scratch\Scripts\python.exe `
  pystac-client planetary-computer rioxarray rasterio xarray `
  pandas numpy matplotlib scipy yfinance

.\.venv-scratch\Scripts\python.exe spike\yields_owid.py          # national yield, ~1 s
powershell -File spike\run_years.ps1                              # MODIS, ~40 s/year
.\.venv-scratch\Scripts\python.exe spike\analyse.py               # join + figure, ~2 s
```

## Files

| File | What it does |
|---|---|
| `yields_owid.py` | national maize yield from the OWID/FAO grapher CSV, t/ha → bu/ac |
| `modis_ndvi.py` | one year of MODIS MOD13Q1 NDVI over the Corn Belt, reduced to one number per composite date |
| `run_years.ps1` | loops 2001–2025 in separate processes with a 150 s timeout each — one bad granule cannot stall the run |
| `analyse.py` | join, detrend, leave-one-year-out RMSE, figure |
| `data/` | outputs |

## Deliberate choices

- **0.01° destination grid (~1 km), not 250 m.** A spatial mean at 1 km and at 250 m
  differ by < 0.005 NDVI; the coarser grid is ~100× cheaper to reproject. The claim is
  about a regional mean, so precision here buys nothing.
- **Windowed COG reads.** Each MODIS tile is 4800×4800; only the window covering the AOI
  is read, so a year costs a few MB, not a few GB.
- **Terra only (`MOD`).** `MOD` and `MYD` are two overpasses of the same 16-day period;
  including both doubles the request count for a near-identical composite.
- **Per-year subprocesses.** `rasterio`'s GDAL lock means one stalled HTTP read can
  freeze a whole thread pool. One process per year, killed at 150 s, keeps 24 of 25 years
  even if one granule misbehaves.
- **Weighted tile averaging.** Tiles overlap at the AOI edge, so composites are combined
  by valid-pixel count rather than by simple mean.

## What this does *not* do

No crop mask, no cloud-quality filtering beyond the built-in composite, no SAR, no
weather, no point-in-time handling, no state-level disaggregation, and the detrend is
fitted on the whole sample. Every one of those is in `../BRIEF.md` Gate 1 and none of
them is in this folder. The spike is the data-access proof, nothing more.
