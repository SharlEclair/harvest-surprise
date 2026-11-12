"""Proxy coherence: do tank roofs stay the same between two acquisitions?

InSAR needs phase coherence, which needs SLC and a login. But the question that
decides whether phase is worth chasing can be asked with amplitude: if the radar
return from a tank roof changes between two acquisitions 12 days apart, the
surface moved (or changed), and phase coherence will be poor too. If the roof is
stable, the return is stable and phase has a chance.

Amplitude correlation is not interferometric coherence - it sees motion only
through its effect on the return - so this is a screen, not a verdict.

Output: data/processed/sar_stability.csv
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("GDAL_HTTP_TIMEOUT", "20")
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


def grid_for(src, bbox):
    left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox, densify_pts=21)
    win = window_from_bounds(left, bottom, right, top,
                             transform=src.transform).round_offsets().round_lengths()
    return win.intersection(Window(0, 0, src.width, src.height))


def main() -> int:
    tanks = np.array(json.loads((RAW / "cushing_tanks.json").read_text()), dtype="float64")
    bbox = (tanks[:, 1].min() - 0.01, tanks[:, 0].min() - 0.01,
            tanks[:, 1].max() + 0.01, tanks[:, 0].max() + 0.01)

    catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    items = list(catalog.search(collections=["sentinel-1-rtc"], bbox=list(bbox),
                                datetime="2024-01-01/2025-12-31", limit=400).items())
    items.sort(key=lambda i: i.properties["datetime"])
    pair = None
    for a, b in zip(items, items[1:]):
        d0 = np.datetime64(a.properties["datetime"][:10])
        d1 = np.datetime64(b.properties["datetime"][:10])
        if 11 <= int((d1 - d0).astype(int)) <= 13 and a.properties.get("sat:orbit_state") == b.properties.get("sat:orbit_state"):
            pair = (a, b)
            break
    if pair is None:
        raise SystemExit("no 12-day pair found in RTC")
    a, b = pair
    print(f"pair: {a.properties['datetime'][:10]} and {b.properties['datetime'][:10]}")

    arrs = []
    for it in (a, b):
        with rasterio.open(pc.sign(it.assets["vv"].href)) as src:
            win = grid_for(src, bbox)
            arrs.append(src.read(1, window=win).astype("float32"))
            tr, crs = src.window_transform(win), src.crs
    A, B = arrs
    if A.shape != B.shape:
        n = min(A.shape[0], B.shape[0]), min(A.shape[1], B.shape[1])
        A, B = A[:n[0], :n[1]], B[:n[0], :n[1]]

    ok = np.isfinite(A) & np.isfinite(B) & (A > 0) & (B > 0)
    xs, ys = warp_transform("EPSG:4326", crs, tanks[:, 1], tanks[:, 0])
    rr, cc = rasterio.transform.rowcol(tr, xs, ys)
    rr, cc = np.array(rr), np.array(cc)
    inside = (rr >= 0) & (rr < A.shape[0]) & (cc >= 0) & (cc < A.shape[1])

    # 5x5 correlation around each tank and around a random ground sample
    def local_corr(r0, c0, k=2):
        ra, rb = A[r0-k:r0+k+1, c0-k:c0+k+1], B[r0-k:r0+k+1, c0-k:c0+k+1]
        m = np.isfinite(ra) & np.isfinite(rb) & (ra > 0) & (rb > 0)
        if m.sum() < 9:
            return np.nan
        x, y = np.log(ra[m]), np.log(rb[m])
        if x.std() == 0 or y.std() == 0:
            return np.nan
        return float(np.corrcoef(x, y)[0, 1])

    tank_c = [local_corr(int(r), int(c)) for r, c in zip(rr[inside], cc[inside])]
    tank_c = np.array([v for v in tank_c if np.isfinite(v)])

    rng = np.random.default_rng(0)
    gr, gc = rng.integers(5, A.shape[0]-5, 2000), rng.integers(5, A.shape[1]-5, 2000)
    # keep ground samples away from tanks
    tank_mask = np.zeros(A.shape, bool)
    tank_mask[rr[inside], cc[inside]] = True
    keep = [i for i in range(len(gr)) if not tank_mask[max(0,gr[i]-5):gr[i]+6, max(0,gc[i]-5):gc[i]+6].any()]
    ground_c = np.array([local_corr(int(gr[i]), int(gc[i])) for i in keep[:800]])
    ground_c = ground_c[np.isfinite(ground_c)]

    print(f"tank pixels: {len(tank_c)}, ground samples: {len(ground_c)}")
    print(f"median local amplitude correlation, tanks:  {np.median(tank_c):+.3f}")
    print(f"median local amplitude correlation, ground: {np.median(ground_c):+.3f}")

    import pandas as pd
    pd.DataFrame([
        {"class": "tank", "n": len(tank_c), "median_corr": float(np.median(tank_c)),
         "p25": float(np.percentile(tank_c, 25)), "p75": float(np.percentile(tank_c, 75))},
        {"class": "ground", "n": len(ground_c), "median_corr": float(np.median(ground_c)),
         "p25": float(np.percentile(ground_c, 25)), "p75": float(np.percentile(ground_c, 75))},
    ]).to_csv(OUT / "sar_stability.csv", index=False)
    print(f"wrote {OUT/'sar_stability.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
