"""Reservoir storage from free Sentinel-2, validated against CDEC gauges.

The measurement: water area from NDWI on 10 m bands, then a per-reservoir
area-to-elevation rating curve fitted on the overlapping observations. The
validation: the CDEC gauge reads elevation every day, so the satellite estimate
can be scored against a number nobody disputes.

This is the one signal in the comment thread where a solo researcher can get
free, daily, high-quality ground truth for a large physical quantity, which is
why it is the first candidate to be tested end to end.

Output: data/processed/reservoir_scenes.csv, reservoir_validation.csv, figure
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("GDAL_HTTP_TIMEOUT", "20")
os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "10")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "1")
os.environ.setdefault("CPL_VSIL_CURL_USE_HEAD", "NO")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import planetary_computer as pc
import rasterio
from pystac_client import Client
from rasterio.warp import transform_bounds
from rasterio.windows import Window
from rasterio.windows import from_bounds as window_from_bounds

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"

# name: (min_lon, min_lat, max_lon, max_lat)
RESERVOIRS = {
    "Shasta": (-122.47, 40.68, -122.28, 40.82),
    "Oroville": (-121.52, 39.50, -121.38, 39.62),
    "Don Pedro": (-120.47, 37.66, -120.36, 37.76),
}
YEARS = ("2021-01-01", "2025-12-31")
MAX_SCENES = 40      # evenly sampled; the point is the rating curve, not every pass
MAX_CLOUD = 25
NDWI_THRESHOLD = 0.10
# Sentinel-2 scene classification: 3 cloud shadow, 8/9 cloud, 10 cirrus, 11 snow
SCL_BAD = {3, 8, 9, 10, 11}


def scenes_for(bbox, catalog) -> list:
    found = catalog.search(collections=["sentinel-2-l2a"], bbox=list(bbox),
                           datetime=f"{YEARS[0]}/{YEARS[1]}",
                           query={"eo:cloud_cover": {"lt": MAX_CLOUD}},
                           limit=400)
    items = [it for it in found.items() if it.properties.get("eo:cloud_cover", 100) < MAX_CLOUD]
    # one scene per day per reservoir
    seen, uniq = set(), []
    for it in sorted(items, key=lambda i: i.properties["datetime"]):
        day = it.properties["datetime"][:10]
        if day in seen:
            continue
        seen.add(day)
        uniq.append(it)
    if len(uniq) > MAX_SCENES:
        idx = np.linspace(0, len(uniq) - 1, MAX_SCENES).round().astype(int)
        uniq = [uniq[i] for i in sorted(set(idx))]
    return uniq


def water_area(item, bbox) -> float | None:
    try:
        b03 = pc.sign(item.assets["B03"].href)
        b08 = pc.sign(item.assets["B08"].href)
        scl = pc.sign(item.assets["SCL"].href)
        with rasterio.open(b03) as src:
            left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox,
                                                        densify_pts=21)
            win = window_from_bounds(left, bottom, right, top,
                                     transform=src.transform).round_offsets().round_lengths()
            try:
                win = win.intersection(Window(0, 0, src.width, src.height))
            except rasterio.errors.WindowError:
                return None
            if win.width < 5 or win.height < 5:
                return None
            green = src.read(1, window=win).astype("float32")
            transform, crs = src.window_transform(win), src.crs
        with rasterio.open(b08) as src:
            nir = src.read(1, window=win).astype("float32")
        with rasterio.open(scl) as src:
            # SCL is 20 m: read the same footprint and upsample by nearest
            from rasterio.enums import Resampling
            scl_w = window_from_bounds(*transform_bounds("EPSG:4326", src.crs, *bbox,
                                                         densify_pts=21),
                                       transform=src.transform).round_offsets().round_lengths()
            scl_w = scl_w.intersection(Window(0, 0, src.width, src.height))
            cls = src.read(1, window=scl_w, out_shape=green.shape,
                           resampling=Resampling.nearest)
    except Exception:  # noqa: BLE001 - a bad scene should not kill the run
        return None

    valid = (~np.isin(cls, list(SCL_BAD))) & (green > 0) & (nir > 0)
    if valid.sum() < 100:
        return None
    ndwi = (green - nir) / (green + nir)
    water = valid & (ndwi > NDWI_THRESHOLD)
    pixel_m2 = abs(transform.a * transform.e)
    return float(water.sum() * pixel_m2)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = Client.open(STAC)

    cdec = pd.read_csv(RAW / "cdec_reservoirs.csv", parse_dates=["date"])
    cdec = cdec[(cdec.elevation_ft > 0) & (cdec.elevation_ft < 10000)]

    rows = []
    for name, bbox in RESERVOIRS.items():
        items = scenes_for(bbox, catalog)
        print(f"{name}: {len(items)} candidate scenes", flush=True)
        got = 0
        for k, it in enumerate(items):
            if k % 10 == 0:
                print(f"  {name} {k}/{len(items)} {it.properties['datetime'][:10]}", flush=True)
            area = water_area(it, bbox)
            if area is None:
                continue
            got += 1
            rows.append({"reservoir": name, "datetime": it.properties["datetime"],
                         "area_m2": area, "cloud": it.properties.get("eo:cloud_cover"),
                         "item": it.id})
        print(f"  measured {got}", flush=True)

    sc = pd.DataFrame(rows)
    if sc.empty:
        raise SystemExit("no scenes measured")
    sc["date"] = pd.to_datetime(sc.datetime).dt.normalize()
    sc.to_csv(OUT / "reservoir_scenes.csv", index=False)

    j = sc.merge(cdec[["date", "reservoir", "elevation_ft", "storage_af"]],
                 on=["date", "reservoir"], how="inner")
    print(f"\nscenes matched to a gauge reading: {len(j)}")

    summary = []
    for name, g in j.groupby("reservoir"):
        g = g.sort_values("area_m2")
        if len(g) < 8:
            summary.append({"reservoir": name, "n": len(g), "rmse_ft": np.nan})
            continue
        # leave-one-out on a linear area -> elevation rating curve
        preds = []
        for i in range(len(g)):
            train = g.drop(g.index[i])
            b = np.polyfit(train.area_m2, train.elevation_ft, 1)
            preds.append(float(np.polyval(b, g.area_m2.iloc[i])))
        g = g.assign(pred=preds)
        rmse = float(np.sqrt(np.mean((g.pred - g.elevation_ft) ** 2)))
        r2 = float(np.corrcoef(g.area_m2, g.elevation_ft)[0, 1] ** 2)
        summary.append({"reservoir": name, "n": len(g), "rmse_ft": rmse,
                        "r2_area_elev": r2,
                        "elev_range_ft": float(g.elevation_ft.max() - g.elevation_ft.min())})
        g.to_csv(OUT / f"reservoir_{name.lower().replace(' ', '_')}.csv", index=False)

    sm = pd.DataFrame(summary)
    sm.to_csv(OUT / "reservoir_validation.csv", index=False)
    print("\nvalidation (leave-one-out, area -> elevation):")
    print(sm.round(2).to_string(index=False))

    fig, axes = plt.subplots(1, len(RESERVOIRS), figsize=(12, 3.6), dpi=140)
    axes = np.atleast_1d(axes)
    for ax, (name, _) in zip(axes, RESERVOIRS.items()):
        g = j[j.reservoir == name]
        if len(g) < 3:
            ax.set_title(f"{name}: no data", fontsize=9)
            continue
        ax.scatter(g.area_m2 / 1e6, g.elevation_ft, s=12, color="#1f3b57")
        ax.set_title(f"{name} (n={len(g)})", fontsize=9)
        ax.set_xlabel("water area (km2)", fontsize=8)
        ax.set_ylabel("gauge elevation (ft)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "reservoir_area.png")
    print(f"wrote {OUT/'reservoir_area.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
