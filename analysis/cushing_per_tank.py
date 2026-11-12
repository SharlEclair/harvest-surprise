"""Per-tank brightness matrix: one pass over the archive, everything after is offline.

The pooled index in analysis/cushing_tanks.py averaged 416 tanks, of which roughly
a third are fixed-roof and carry no fill signal at all
(223 floating + 116 fixed, per the DigitalGlobe coverage of Cushing in 2011).
Separating them needs each tank's own time series, which needs one more pass over
the imagery. After this, every experiment - detrending, tank selection, splits -
runs on a 320 x 416 matrix in seconds.

Output: data/processed/cushing_tank_matrix.npz
        (brightness, valid, dates, cloud, solar_elev, solar_azim, tank_latlon)
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

YEARS = ("2018-01-01", "2025-12-31")
MONTHS = (4, 10)
MAX_CLOUD = 10
SCL_BAD = {3, 8, 9, 10, 11}


def main() -> int:
    tanks = np.array(json.loads((RAW / "cushing_tanks.json").read_text()), dtype="float64")
    bbox = (tanks[:, 1].min() - 0.01, tanks[:, 0].min() - 0.01,
            tanks[:, 1].max() + 0.01, tanks[:, 0].max() + 0.01)
    catalog = Client.open(STAC)
    items = [it for it in catalog.search(collections=["sentinel-2-l2a"], bbox=list(bbox),
                                         datetime=f"{YEARS[0]}/{YEARS[1]}",
                                         query={"eo:cloud_cover": {"lt": MAX_CLOUD}},
                                         limit=1000).items()
             if MONTHS[0] <= int(it.properties["datetime"][5:7]) <= MONTHS[1]]
    items.sort(key=lambda i: i.properties["datetime"])
    print(f"tanks {len(tanks)}, candidate scenes {len(items)}", flush=True)

    bright, valid_m, dates, cloud, elev, azim = [], [], [], [], [], []
    for k, it in enumerate(items):
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
        rows, cols = rasterio.transform.rowcol(tr, xs, ys)
        rows, cols = np.array(rows), np.array(cols)
        inside = (rows >= 0) & (rows < red.shape[0]) & (cols >= 0) & (cols < red.shape[1])
        v = np.zeros(len(tanks), dtype="float32")
        b = np.full(len(tanks), np.nan, dtype="float32")
        if inside.any():
            rr, cc = rows[inside], cols[inside]
            ok = (~np.isin(scl[rr, cc], list(SCL_BAD))) & (red[rr, cc] > 0)
            v[np.where(inside)[0][ok]] = 1.0
            b[np.where(inside)[0][ok]] = red[rr[ok], cc[ok]]
        bright.append(b)
        valid_m.append(v)
        dates.append(it.properties["datetime"][:10])
        cloud.append(float(it.properties.get("eo:cloud_cover", np.nan)))
        elev.append(float(it.properties.get("s2:mean_solar_elevation", np.nan)))
        azim.append(float(it.properties.get("s2:mean_solar_azimuth", np.nan)))
        if k % 20 == 0:
            print(f"  {k}/{len(items)} {dates[-1]} valid {int(v.sum())}", flush=True)

    np.savez_compressed(
        OUT / "cushing_tank_matrix.npz",
        brightness=np.array(bright, dtype="float32"),
        valid=np.array(valid_m, dtype="float32"),
        dates=np.array(dates),
        cloud=np.array(cloud, dtype="float32"),
        solar_elev=np.array(elev, dtype="float32"),
        solar_azim=np.array(azim, dtype="float32"),
        tank_latlon=tanks,
    )
    print(f"saved {len(dates)} scenes x {len(tanks)} tanks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
