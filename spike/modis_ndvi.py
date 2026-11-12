"""Spike: MODIS MOD13Q1 (250 m, 16-day) NDVI over the US Corn Belt, read from
Microsoft Planetary Computer with no auth.

Each 16-day composite is read through a window covering the AOI, reprojected
onto a fixed EPSG:4326 grid at 0.01 deg (~1 km), and reduced to one number.
0.01 deg is deliberate: a spatial mean at 1 km and at 250 m differ by <0.005
NDVI, and the coarser grid is ~100x cheaper to reproject.

Usage:  python modis_ndvi.py --start 2001 --end 2025 --out data/ndvi_cornbelt.csv
"""
from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Must be set before rasterio/GDAL gets a chance to open a remote file.
# Without these a stalled blob read blocks forever instead of raising.
os.environ.setdefault("GDAL_HTTP_TIMEOUT", "20")
os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "10")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "1")
os.environ.setdefault("CPL_VSIL_CURL_USE_HEAD", "NO")

import numpy as np
import pandas as pd
import planetary_computer as pc
import rasterio
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import from_bounds as grid_from_bounds
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window
from rasterio.windows import from_bounds as window_from_bounds

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "modis-13Q1-061"
BAND = "250m_16_days_NDVI"

# Core Corn Belt: IA, IL, IN, NE, MN, MO, KS, SD, WI
BBOX = (-97.0, 39.5, -86.0, 45.2)
RES_DEG = 0.01
NDVI_SCALE = 1e-4
FILL = -3000

# Day-of-year start of each 16-day composite. 177 = late June, 209 = late July.
COMPOSITES = (177, 193, 209)

DST_TRANSFORM = grid_from_bounds(*BBOX, int(round((BBOX[2] - BBOX[0]) / RES_DEG)),
                            int(round((BBOX[3] - BBOX[1]) / RES_DEG)))
HEIGHT = int(round((BBOX[3] - BBOX[1]) / RES_DEG))
WIDTH = int(round((BBOX[2] - BBOX[0]) / RES_DEG))


def reduce_item(item: dict) -> dict | None:
    href = pc.sign(item.assets[BAND].href)
    with rasterio.open(href) as src:
        left, bottom, right, top = transform_bounds(
            "EPSG:4326", src.crs, *BBOX, densify_pts=21
        )
        win = window_from_bounds(left, bottom, right, top, transform=src.transform)
        win = win.round_offsets().round_lengths()
        try:
            win = win.intersection(Window(0, 0, src.width, src.height))
        except rasterio.errors.WindowError:
            return None  # tile does not overlap the AOI
        if win.width < 2 or win.height < 2:
            return None
        data = src.read(1, window=win)
        transform = src.window_transform(win)
        crs = src.crs

    dst = np.full((HEIGHT, WIDTH), FILL, dtype="int16")
    reproject(
        source=data,
        destination=dst,
        src_transform=transform,
        src_crs=crs,
        src_nodata=FILL,
        dst_transform=DST_TRANSFORM,
        dst_crs="EPSG:4326",
        dst_nodata=FILL,
        resampling=Resampling.bilinear,
    )
    valid = (dst != FILL) & (dst > 0) & (dst < 10000)
    if valid.sum() < 1000:
        return None
    dt = item.datetime or pd.Timestamp(item.properties["start_datetime"])
    return {
        "date": dt.date().isoformat(),
        "item": item.id,
        "ndvi": float(dst[valid].mean()) * NDVI_SCALE,
        "n_pixels": int(valid.sum()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2001)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", type=Path, default=Path("data/ndvi_cornbelt.csv"))
    args = ap.parse_args()

    catalog = Client.open(STAC)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".partial.csv").unlink(missing_ok=True)

    rows: list[dict] = []
    t_all = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for year in range(args.start, args.end + 1):
            t0 = time.time()
            items = []
            for doy in COMPOSITES:
                start = pd.Timestamp(year=year, month=1, day=1) + pd.Timedelta(days=doy - 1)
                end = start + pd.Timedelta(days=15)
                found = catalog.search(
                    collections=[COLLECTION],
                    bbox=list(BBOX),
                    datetime=f"{start:%Y-%m-%d}/{end:%Y-%m-%d}",
                    limit=50,
                ).items()
                # Terra only: MOD and MYD are two overpasses of the same 16 days.
                items += [it for it in found if it.id.startswith("MOD")]
            try:
                results = [r for r in pool.map(reduce_item, items, timeout=180) if r]
            except TimeoutError:
                print(f"{year}: TIMEOUT, partial only", flush=True)
                results = []
            for r in results:
                r["year"] = year
            rows += results
            # Write after every year so a later hang cannot lose earlier work.
            pd.DataFrame(rows).sort_values(["year", "date"]).to_csv(
                out.with_suffix(".partial.csv"), index=False
            )
            ndvi = np.mean([r["ndvi"] for r in results]) if results else float("nan")
            print(
                f"{year}: {len(results):2d}/{len(items):2d} composites, "
                f"mean NDVI {ndvi:.4f}  ({time.time() - t0:.1f}s)",
                flush=True,
            )

    pd.DataFrame(rows).sort_values(["year", "date"]).to_csv(out, index=False)
    out.with_suffix(".partial.csv").unlink(missing_ok=True)
    print(f"wrote {out} ({len(rows)} rows) in {time.time() - t_all:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
