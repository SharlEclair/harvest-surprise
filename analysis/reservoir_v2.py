"""Reservoir water extent v2 - fixed grid, water fraction, validity gate.

The v1 attempt failed (R2 0.07-0.21, no skill against the gauge). Three defects,
each fixed here:

1. **Area was computed over valid pixels only**, so any cloud or mask shifted the
   denominator and some scenes reported zero water. Fixed: every scene is
   reprojected onto one fixed grid and expressed as a *fraction* of valid pixels
   inside a region of interest that is the union of all observed water.
2. **No fixed footprint.** A different bbox intersection per scene meant the
   estimator saw different ground each time. Fixed: one 0.001 degree grid per
   reservoir, built once.
3. **The L2A BOA offset was ignored.** Since processing baseline 04.00 (Jan 2022)
   Sentinel-2 L2A DN carries a +1000 offset; BOA = (DN - 1000)/10000. Applying
   NDWI to raw DN compresses every index toward zero, so post-2022 scenes
   systematically under-detect water. That alone can produce a spurious
   time-varying bias that kills the area-elevation relationship.

Output: data/processed/reservoir_v2_<name>.npz and reservoir_v2_grids.json
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

os.environ.setdefault("GDAL_HTTP_TIMEOUT", "20")
os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "10")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "1")
os.environ.setdefault("CPL_VSIL_CURL_USE_HEAD", "NO")

import numpy as np
import planetary_computer as pc
import rasterio
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window
from rasterio.windows import from_bounds as window_from_bounds

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"

RESERVOIRS = {
    "Shasta": (-122.47, 40.68, -122.28, 40.82),
    "Oroville": (-121.52, 39.50, -121.38, 39.62),
    "Don Pedro": (-120.47, 37.66, -120.36, 37.76),
}
YEARS = ("2021-01-01", "2025-12-31")
MAX_CLOUD = 25
MAX_SCENES = 40
RES_DEG = 0.001          # ~110 m grid
NDWI_THRESHOLD = 0.10
SCL_BAD = {3, 8, 9, 10, 11}
BOA_OFFSET_FROM = 4.0    # baseline 04.00 introduced the -1000 DN offset


def grid_for(bbox):
    w = int(round((bbox[2] - bbox[0]) / RES_DEG))
    h = int(round((bbox[3] - bbox[1]) / RES_DEG))
    return from_bounds(*bbox, w, h), h, w


def scenes_for(bbox, catalog):
    found = catalog.search(collections=["sentinel-2-l2a"], bbox=list(bbox),
                           datetime=f"{YEARS[0]}/{YEARS[1]}",
                           query={"eo:cloud_cover": {"lt": MAX_CLOUD}},
                           limit=400)
    items = sorted(found.items(), key=lambda i: i.properties["datetime"])
    seen, uniq = set(), []
    for it in items:
        day = it.properties["datetime"][:10]
        if day in seen:
            continue
        seen.add(day)
        uniq.append(it)
    if len(uniq) > MAX_SCENES:
        idx = np.linspace(0, len(uniq) - 1, MAX_SCENES).round().astype(int)
        uniq = [uniq[i] for i in sorted(set(idx))]
    return uniq


def boa_offset(item) -> float:
    try:
        baseline = float(str(item.properties.get("s2:processing_baseline", "0")).split(".")[0])
    except ValueError:
        baseline = 0.0
    return -1000.0 if baseline >= BOA_OFFSET_FROM else 0.0


def scene_fractions(item, bbox, dst_transform, h, w):
    off = boa_offset(item)
    try:
        with rasterio.open(pc.sign(item.assets["B03"].href)) as src:
            left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox,
                                                        densify_pts=21)
            win = window_from_bounds(left, bottom, right, top,
                                     transform=src.transform).round_offsets().round_lengths()
            win = win.intersection(Window(0, 0, src.width, src.height))
            if win.width < 5 or win.height < 5:
                return None
            green = src.read(1, window=win).astype("float32") + off
            tr, crs = src.window_transform(win), src.crs
        with rasterio.open(pc.sign(item.assets["B08"].href)) as src:
            nir = src.read(1, window=win).astype("float32") + off
        with rasterio.open(pc.sign(item.assets["SCL"].href)) as src:
            scl_w = window_from_bounds(left, bottom, right, top,
                                       transform=src.transform).round_offsets().round_lengths()
            scl_w = scl_w.intersection(Window(0, 0, src.width, src.height))
            cls = src.read(1, window=scl_w, out_shape=green.shape,
                           resampling=Resampling.nearest)
    except Exception:  # noqa: BLE001
        return None

    valid = (~np.isin(cls, list(SCL_BAD))) & (green > -500) & (nir > -500)
    denom = green + nir
    with np.errstate(invalid="ignore", divide="ignore"):
        ndwi = np.where(np.abs(denom) > 1e-6, (green - nir) / denom, np.nan)
    water = valid & np.isfinite(ndwi) & (ndwi > NDWI_THRESHOLD)
    if valid.sum() < 1000:
        return None

    wf = np.zeros((h, w), dtype="float32")
    vf = np.zeros((h, w), dtype="float32")
    reproject(water.astype("float32"), wf, src_transform=tr, src_crs=crs,
              dst_transform=dst_transform, dst_crs="EPSG:4326",
              resampling=Resampling.average)
    reproject(valid.astype("float32"), vf, src_transform=tr, src_crs=crs,
              dst_transform=dst_transform, dst_crs="EPSG:4326",
              resampling=Resampling.average)
    return wf.ravel(), vf.ravel()


def main() -> int:
    catalog = Client.open(STAC)
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {}

    for name, bbox in RESERVOIRS.items():
        dst_transform, h, w = grid_for(bbox)
        items = scenes_for(bbox, catalog)
        print(f"{name}: {len(items)} scenes, grid {h}x{w}", flush=True)
        t0 = time.time()
        wfs, vfs, dates, clouds, offsets = [], [], [], [], []
        for k, it in enumerate(items):
            res = scene_fractions(it, bbox, dst_transform, h, w)
            if res is None:
                continue
            wf, vf = res
            wfs.append(wf.astype("float16"))
            vfs.append(vf.astype("float16"))
            dates.append(it.properties["datetime"][:10])
            clouds.append(it.properties.get("eo:cloud_cover"))
            offsets.append(boa_offset(it))
            if k % 5 == 0:
                print(f"  {k}/{len(items)} {dates[-1]} ({time.time()-t0:.0f}s)", flush=True)
        np.savez_compressed(OUT / f"reservoir_v2_{name.lower().replace(' ', '_')}.npz",
                            water=np.array(wfs), valid=np.array(vfs),
                            dates=np.array(dates), cloud=np.array(clouds, dtype="float32"),
                            offset=np.array(offsets, dtype="float32"))
        meta[name] = {"h": h, "w": w, "bbox": bbox, "n": len(dates)}
        print(f"  saved {len(dates)} scenes", flush=True)

    (OUT / "reservoir_v2_grids.json").write_text(json.dumps(meta, indent=2))
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
