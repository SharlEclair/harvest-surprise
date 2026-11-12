"""Is the 8.9% noise floor a Cushing fact or a general one?

The detectability calculation turns on one measured input: the per-tank brightness
variability after scene effects are removed. If that is much lower at a cleaner
site - desert ground instead of Oklahoma grass and dirt - the SNR improves and a
hub might cross into detection.

Three hubs are tried, whichever OSM knows about:
    Fujairah (UAE)          desert, very large tank farm
    Rotterdam (NL)          port, mixed industrial
    Houston / Galena Park   refinery belt

For each: tank coordinates from OSM, ~20 cloud-free summer scenes, and the same
per-tank residual standard deviation as Cushing.

Output: data/processed/hub_noise.csv
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

os.environ.setdefault("GDAL_HTTP_TIMEOUT", "20")
os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "10")
os.environ.setdefault("CPL_VSIL_CURL_USE_HEAD", "NO")

import numpy as np
import pandas as pd
import planetary_computer as pc
import rasterio
import requests
from pystac_client import Client
from rasterio.warp import transform as warp_transform
from rasterio.warp import transform_bounds
from rasterio.windows import Window
from rasterio.windows import from_bounds as window_from_bounds

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
SCL_BAD = {3, 8, 9, 10, 11}

HUBS = {
    "Fujairah": (56.28, 25.05, 56.40, 25.20),
    "Rotterdam": (4.00, 51.87, 4.12, 51.97),
    "Houston": (-95.26, 29.68, -95.14, 29.79),
}
MAX_SCENES = 20


def osm_tanks(bbox) -> np.ndarray:
    q = (f'[out:json][timeout:90];(node["man_made"="storage_tank"]'
         f'({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});'
         f'way["man_made"="storage_tank"]'
         f'({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}););out center;')
    for attempt in range(3):
        try:
            r = requests.post("https://overpass-api.de/api/interpreter",
                              data={"data": q}, timeout=180,
                              headers={"User-Agent": "harvest-surprise/1.0"})
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
                pts = []
                for e in r.json().get("elements", []):
                    lat = e.get("lat") or e.get("center", {}).get("lat")
                    lon = e.get("lon") or e.get("center", {}).get("lon")
                    if lat and lon:
                        pts.append([lat, lon])
                return np.array(pts, dtype="float64") if pts else np.empty((0, 2))
        except Exception:  # noqa: BLE001
            pass
        time.sleep(20)
    return np.empty((0, 2))


def measure(hub: str, bbox, tanks: np.ndarray, catalog) -> dict | None:
    items = list(catalog.search(collections=["sentinel-2-l2a"], bbox=list(bbox),
                                datetime="2021-01-01/2025-12-31",
                                query={"eo:cloud_cover": {"lt": 8}}, limit=400).items())
    items = [it for it in items if 4 <= int(it.properties["datetime"][5:7]) <= 10]
    items.sort(key=lambda i: i.properties["datetime"])
    if len(items) > MAX_SCENES:
        idx = np.linspace(0, len(items) - 1, MAX_SCENES).round().astype(int)
        items = [items[i] for i in sorted(set(idx))]

    series = []
    for it in items:
        try:
            with rasterio.open(pc.sign(it.assets["B04"].href)) as src:
                left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox,
                                                            densify_pts=21)
                win = window_from_bounds(left, bottom, right, top,
                                         transform=src.transform).round_offsets().round_lengths()
                win = win.intersection(Window(0, 0, src.width, src.height))
                red = src.read(1, window=win).astype("float32")
                tr, crs = src.window_transform(win), src.crs
            with rasterio.open(pc.sign(it.assets["SCL"].href)) as src:
                sw = window_from_bounds(left, bottom, right, top,
                                        transform=src.transform).round_offsets().round_lengths()
                sw = sw.intersection(Window(0, 0, src.width, src.height))
                scl = src.read(1, window=sw, out_shape=red.shape)
        except Exception:  # noqa: BLE001
            continue
        xs, ys = warp_transform("EPSG:4326", crs, tanks[:, 1], tanks[:, 0])
        rr, cc = rasterio.transform.rowcol(tr, xs, ys)
        rr, cc = np.array(rr), np.array(cc)
        inside = (rr >= 0) & (rr < red.shape[0]) & (cc >= 0) & (cc < red.shape[1])
        if inside.sum() < 20:
            continue
        vals = np.full(len(tanks), np.nan, dtype="float32")
        r_i, c_i = rr[inside], cc[inside]
        ok = (~np.isin(scl[r_i, c_i], list(SCL_BAD))) & (red[r_i, c_i] > 0)
        vals[np.where(inside)[0][ok]] = red[r_i[ok], c_i[ok]]
        series.append(vals)

    if len(series) < 8:
        return None
    M = np.array(series)
    R = M - np.nanmean(M, axis=1, keepdims=True)
    sd = np.nanstd(R, axis=0)
    sd = sd[np.isfinite(sd)]
    if len(sd) < 20:
        return None
    return {"hub": hub, "tanks": len(sd), "scenes": len(M),
            "median_tank_sd_dn": float(np.median(sd)),
            "median_level_dn": float(np.nanmedian(M)),
            "noise_fraction": float(np.median(sd) / np.nanmedian(M))}


def main() -> int:
    catalog = Client.open(STAC)
    rows = []
    for hub, bbox in HUBS.items():
        tanks = osm_tanks(bbox)
        print(f"{hub}: {len(tanks)} tanks from OSM", flush=True)
        if len(tanks) < 30:
            rows.append({"hub": hub, "tanks": len(tanks), "scenes": 0,
                         "noise_fraction": np.nan})
            continue
        res = measure(hub, bbox, tanks, catalog)
        if res:
            rows.append(res)
            print(f"  noise {res['noise_fraction']:.1%} over {res['scenes']} scenes",
                  flush=True)
        else:
            rows.append({"hub": hub, "tanks": len(tanks), "scenes": 0,
                         "noise_fraction": np.nan})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "hub_noise.csv", index=False)
    print("\n" + df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
