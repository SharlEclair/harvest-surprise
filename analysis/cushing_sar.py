"""Cushing with radar instead of optical.

Every optical aggregation failed the held-out test (within-year r between -0.30
and +0.09). The industry method is Sentinel-1 SAR, not Sentinel-2: a floating roof
sitting at a different height changes the double-bounce geometry between the roof
edge and the tank wall, which shows up in VV backscatter rather than in visible
brightness.

This measures, per scene:
    tank_vv   median VV over the tank centres
    ground_vv median VV well away from any tank
    ratio     tank_vv - ground_vv in dB

and writes the series for the same correlation tests.

Output: data/processed/cushing_sar.csv
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("GDAL_HTTP_TIMEOUT", "20")
os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "10")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "1")
os.environ.setdefault("CPL_VSIL_CURL_USE_HEAD", "NO")

import numpy as np
import pandas as pd
import planetary_computer as pc
import rasterio
from pystac_client import Client
from rasterio.warp import transform as warp_transform
from rasterio.warp import transform_bounds
from rasterio.windows import Window
from rasterio.windows import from_bounds as window_from_bounds

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"


def vv_key(item) -> str | None:
    for k in item.assets:
        if k.lower() in ("vv", "vh") and k.lower() == "vv":
            return k
    for k in item.assets:
        if "vv" in k.lower():
            return k
    return None


def main() -> int:
    tanks = np.array(json.loads((RAW / "cushing_tanks.json").read_text()), dtype="float64")
    bbox = (tanks[:, 1].min() - 0.01, tanks[:, 0].min() - 0.01,
            tanks[:, 1].max() + 0.01, tanks[:, 0].max() + 0.01)
    catalog = Client.open(STAC)
    items = list(catalog.search(collections=["sentinel-1-rtc"], bbox=list(bbox),
                                datetime="2018-01-01/2025-12-31", limit=1000).items())
    items.sort(key=lambda i: i.properties["datetime"])
    # RTC COGs are ~2.4 GB and a windowed read costs ~30 s, so every fourth scene
    # is used. That is still ~20 observations a year, far denser than the six
    # usable images the video had.
    items = items[::4]
    print(f"candidate SAR scenes (1 in 4): {len(items)}", flush=True)

    rows = []
    for k, it in enumerate(items):
        key = vv_key(it)
        if key is None:
            continue
        try:
            with rasterio.open(pc.sign(it.assets[key].href)) as src:
                left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox,
                                                            densify_pts=21)
                win = window_from_bounds(left, bottom, right, top,
                                         transform=src.transform).round_offsets().round_lengths()
                win = win.intersection(Window(0, 0, src.width, src.height))
                if win.width < 10 or win.height < 10:
                    continue
                arr = src.read(1, window=win).astype("float32")
                tr, crs = src.window_transform(win), src.crs
        except Exception:  # noqa: BLE001
            continue

        xs, ys = warp_transform("EPSG:4326", crs, tanks[:, 1], tanks[:, 0])
        rows_i, cols_i = rasterio.transform.rowcol(tr, xs, ys)
        rows_i, cols_i = np.array(rows_i), np.array(cols_i)
        inside = ((rows_i >= 0) & (rows_i < arr.shape[0])
                  & (cols_i >= 0) & (cols_i < arr.shape[1]))
        if inside.sum() < 50:
            continue
        rr, cc = rows_i[inside], cols_i[inside]
        tank_vals = arr[rr, cc]
        tank_vals = tank_vals[np.isfinite(tank_vals) & (tank_vals > 0)]
        if len(tank_vals) < 40:
            continue

        mask = np.ones(arr.shape, dtype=bool)
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                mask[np.clip(rr + dr, 0, arr.shape[0] - 1),
                     np.clip(cc + dc, 0, arr.shape[1] - 1)] = False
        gv = arr[mask & np.isfinite(arr) & (arr > 0)]
        if len(gv) < 500:
            continue

        rows.append({
            "date": it.properties["datetime"][:10],
            "tank_db": float(np.median(10 * np.log10(tank_vals))),
            "ground_db": float(np.median(10 * np.log10(gv))),
            "n_tanks": int(len(tank_vals)),
            "orbit": it.properties.get("sat:orbit_state"),
        })
        if k % 25 == 0:
            print(f"  {k}/{len(items)} {rows[-1]['date']} n={rows[-1]['n_tanks']}", flush=True)

    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("no SAR scenes measured")
    df["date"] = pd.to_datetime(df.date)
    df["ratio_db"] = df.tank_db - df.ground_db
    df.to_csv(OUT / "cushing_sar.csv", index=False)
    print(f"\nwrote {OUT/'cushing_sar.csv'} ({len(df)} scenes)")
    print(df[["date", "tank_db", "ground_db", "ratio_db", "orbit"]].tail(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
