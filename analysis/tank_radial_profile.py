"""Where does the radar energy come from inside a tank?

The conclusion from the InSAR work was that a 20 m HyP3 pixel is dominated by the
static tank shell rather than the floating roof. That is testable directly with
georeferenced 10 m RTC backscatter: average many tank patches around their
centres and look at the radial profile.

    bright centre, dim edge   -> the roof dominates, and a 10 m centre pixel is roof
    dim centre, bright ring   -> a rim or double-bounce dominates, and the roof is
                                 a minor contributor at any averaging scale

That decides whether full-resolution processing could ever see the roof.

Output: data/processed/tank_radial_profile.csv, tank_radial_profile.png
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("GDAL_HTTP_TIMEOUT", "20")
os.environ.setdefault("CPL_VSIL_CURL_USE_HEAD", "NO")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
HALF = 8          # 17 x 17 pixels at 10 m = 170 m, comfortably beyond a 60 m tank


def main() -> int:
    tanks = np.array(json.loads((RAW / "cushing_tanks.json").read_text()), dtype="float64")
    bbox = (tanks[:, 1].min() - 0.015, tanks[:, 0].min() - 0.015,
            tanks[:, 1].max() + 0.015, tanks[:, 0].max() + 0.015)
    catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    items = [it for it in catalog.search(collections=["sentinel-1-rtc"], bbox=list(bbox),
                                         datetime="2024-06-01/2024-08-31", limit=50).items()]
    if not items:
        raise SystemExit("no RTC scene")
    it = sorted(items, key=lambda i: i.properties["datetime"])[0]
    print("scene:", it.id)

    with rasterio.open(pc.sign(it.assets["vv"].href)) as src:
        left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox, densify_pts=21)
        win = window_from_bounds(left, bottom, right, top,
                                 transform=src.transform).round_offsets().round_lengths()
        win = win.intersection(Window(0, 0, src.width, src.height))
        arr = src.read(1, window=win).astype("float32")
        tr, crs = src.window_transform(win), src.crs
    print(f"window {arr.shape}, mean {np.nanmean(arr):.3f}")

    xs, ys = warp_transform("EPSG:4326", crs, tanks[:, 1], tanks[:, 0])
    rr, cc = rasterio.transform.rowcol(tr, xs, ys)

    patches, radii = [], []
    for r, c in zip(np.array(rr), np.array(cc)):
        if not (HALF <= r < arr.shape[0] - HALF and HALF <= c < arr.shape[1] - HALF):
            continue
        p = arr[r - HALF:r + HALF + 1, c - HALF:c + HALF + 1]
        if not np.isfinite(p).all() or np.median(p) <= 0:
            continue
        # normalise each patch by its own edge ring, so painting and brightness vary less
        edge = np.concatenate([p[0, :], p[-1, :], p[:, 0], p[:, -1]])
        ref = np.median(edge)
        if ref <= 0:
            continue
        patches.append(p / ref)
        yy, xx = np.mgrid[-HALF:HALF + 1, -HALF:HALF + 1]
        radii.append(np.hypot(yy, xx))
    if len(patches) < 20:
        raise SystemExit(f"only {len(patches)} usable tank patches")

    P = np.array(patches)
    R = radii[0]
    mean_patch = P.mean(axis=0)
    prof = []
    for lo in range(0, HALF + 1):
        m = (R >= lo) & (R < lo + 1)
        prof.append({"radius_px": lo, "radius_m": lo * 10,
                     "mean_rel_power": float(mean_patch[m].mean()),
                     "n_cells": int(m.sum())})
    df = pd.DataFrame(prof)
    df["n_tanks"] = len(patches)
    df.to_csv(OUT / "tank_radial_profile.csv", index=False)
    print(df.round(3).to_string(index=False))

    centre = df[df.radius_px <= 1].mean_rel_power.mean()
    ring = df[(df.radius_px >= 2) & (df.radius_px <= 4)].mean_rel_power.mean()
    edge = df[df.radius_px >= 5].mean_rel_power.mean()
    print(f"\ncentre (0-10 m): {centre:.2f}   tank body (20-40 m): {ring:.2f}   outside (50+ m): {edge:.2f}")
    verdict = ("roof dominates" if centre > ring * 1.2 else
               "rim/edge dominates" if ring > centre * 1.2 else "flat")
    print(f"verdict: {verdict}")

    fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=140)
    ax.plot(df.radius_m, df.mean_rel_power, "o-", color="#1f3b57")
    ax.axhline(1.0, color="#999", ls="--", lw=1, label="edge reference")
    ax.set_xlabel("distance from tank centre (m)")
    ax.set_ylabel("relative backscatter")
    ax.set_title(f"Radial scattering profile, {len(patches)} tanks", loc="left", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "tank_radial_profile.png")
    print(f"wrote {OUT/'tank_radial_profile.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
