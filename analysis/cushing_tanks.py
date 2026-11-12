"""The video's project: Cushing tank fill from orbit, done with weekly ground truth.

Differences from the video's version, all deliberate:

* **416 tank locations from OpenStreetMap**, not hand-picked X/Y points.
* **Radiometric normalisation per scene** against the surrounding ground, which is
  the fix he found the hard way after his first two-date comparison returned -0.3%.
* **~150 scenes across eight years**, not 15 images across five.
* **Weekly EIA Cushing stocks** as the target, not two annual snapshots.

The measurement per scene is the median brightness of tank roof pixels divided by
the median brightness of non-tank pixels in the same window. A floating-roof tank
that is emptying slides down and exposes a growing crescent of shadow, so the
ratio should fall as the tanks empty.

Output: data/processed/cushing_scenes.csv
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

YEARS = ("2018-01-01", "2025-12-31")
MONTHS = (4, 10)          # April-October: no snow, sun high enough
MAX_CLOUD = 10
SCL_BAD = {3, 8, 9, 10, 11}


def tank_points() -> np.ndarray:
    pts = json.loads((RAW / "cushing_tanks.json").read_text())
    return np.array(pts, dtype="float64")


def bbox_of(pts: np.ndarray, pad: float = 0.01):
    return (pts[:, 1].min() - pad, pts[:, 0].min() - pad,
            pts[:, 1].max() + pad, pts[:, 0].max() + pad)


def scene_index(item, tanks: np.ndarray, bbox) -> dict | None:
    try:
        with rasterio.open(pc.sign(item.assets["B04"].href)) as src:
            left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox,
                                                        densify_pts=21)
            win = window_from_bounds(left, bottom, right, top,
                                     transform=src.transform).round_offsets().round_lengths()
            win = win.intersection(Window(0, 0, src.width, src.height))
            if win.width < 10 or win.height < 10:
                return None
            red = src.read(1, window=win).astype("float32")
            tr, crs = src.window_transform(win), src.crs
        with rasterio.open(pc.sign(item.assets["SCL"].href)) as src:
            sw = window_from_bounds(left, bottom, right, top,
                                    transform=src.transform).round_offsets().round_lengths()
            sw = sw.intersection(Window(0, 0, src.width, src.height))
            scl = src.read(1, window=sw, out_shape=red.shape)
    except Exception:  # noqa: BLE001
        return None

    valid = (~np.isin(scl, list(SCL_BAD))) & (red > 0)
    if valid.mean() < 0.3:
        return None

    # pixel coordinates of every tank centre. The tanks are lon/lat; the scene
    # transform is UTM, so they must be reprojected first or rowcol returns
    # nonsense (which is exactly what happened on the first run).
    xs, ys = warp_transform("EPSG:4326", crs, tanks[:, 1], tanks[:, 0])
    rows, cols = rasterio.transform.rowcol(tr, xs, ys)
    rows, cols = np.array(rows), np.array(cols)
    keep = (rows >= 0) & (rows < red.shape[0]) & (cols >= 0) & (cols < red.shape[1])
    rows, cols = rows[keep], cols[keep]
    if len(rows) < 50:
        return None

    tv = red[rows, cols][valid[rows, cols]]
    # ground reference: everything in the window at least 2 px from a tank centre
    mask = np.ones(red.shape, dtype=bool)
    for dr in (-2, -1, 0, 1, 2):
        for dc in (-2, -1, 0, 1, 2):
            rr = np.clip(rows + dr, 0, red.shape[0] - 1)
            cc = np.clip(cols + dc, 0, red.shape[1] - 1)
            mask[rr, cc] = False
    gv = red[mask & valid]
    if len(tv) < 30 or len(gv) < 500:
        return None

    return {"tank_median": float(np.median(tv)), "ground_median": float(np.median(gv)),
            "n_tanks": int(len(tv)), "valid_frac": float(valid.mean())}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tanks = tank_points()
    bbox = bbox_of(tanks)
    print(f"tanks: {len(tanks)}, bbox {bbox}")

    catalog = Client.open(STAC)
    items = list(catalog.search(collections=["sentinel-2-l2a"], bbox=list(bbox),
                                datetime=f"{YEARS[0]}/{YEARS[1]}",
                                query={"eo:cloud_cover": {"lt": MAX_CLOUD}},
                                limit=1000).items())
    keep = [it for it in items
            if MONTHS[0] <= int(it.properties["datetime"][5:7]) <= MONTHS[1]]
    keep.sort(key=lambda i: i.properties["datetime"])
    print(f"candidate scenes: {len(keep)}")

    rows = []
    for k, it in enumerate(keep):
        res = scene_index(it, tanks, bbox)
        if res is None:
            continue
        rows.append({"date": it.properties["datetime"][:10],
                     "cloud": it.properties.get("eo:cloud_cover"),
                     "item": it.id, **res})
        if k % 10 == 0:
            print(f"  {k}/{len(keep)} {rows[-1]['date']} tanks={res['n_tanks']}", flush=True)

    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("no scenes measured")
    df["date"] = pd.to_datetime(df.date)
    df["index"] = df.tank_median / df.ground_median
    df.to_csv(OUT / "cushing_scenes.csv", index=False)
    print(f"\nwrote {OUT/'cushing_scenes.csv'} ({len(df)} scenes)")
    print(df[["date", "cloud", "tank_median", "ground_median", "index", "n_tanks"]]
          .tail(5).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

