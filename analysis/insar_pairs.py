"""Compare InSAR pairs: is the tank displacement real or baseline-dependent?

For each HyP3 product in data/raw/hyp3:
  * read the perpendicular baseline from the product metadata
  * take each tank's LOS displacement (median of a 3x3 around the tank centre)
  * fit a plane in lon/lat, because the first pair showed two thirds of the
    variance is a smooth ramp (orbit or atmosphere, not roofs)
  * report the plane magnitude, the residual scatter, and the residual's spatial
    correlation

The test: a DEM height error scales with the perpendicular baseline; roof motion
does not. If the tank offset grows with |baseline|, it is geometry, not oil.

Output: data/processed/insar_pairs.csv, insar_pairs.png
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import transform as warp_transform

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"


def read_tif(zf, suffix):
    name = [m for m in zf.namelist() if m.endswith(suffix)][0]
    with zf.open(name) as fh, rasterio.io.MemoryFile(fh.read()) as mem:
        with mem.open() as src:
            return src.read(1).astype("float32"), src.transform, src.crs, src.nodata


def read_meta(zf) -> dict:
    txt = [m for m in zf.namelist() if m.endswith(".txt")][0]
    body = zf.read(txt).decode("utf-8", "replace")
    out = {}
    for key in ("Baseline", "Reference Granule", "Secondary Granule",
                "Reference Orbit Number", "Secondary Orbit Number"):
        m = re.search(rf"{key}:\s*(.+)", body)
        if m:
            out[key] = m.group(1).strip()
    return out


def main() -> int:
    tanks = np.array(json.loads((RAW / "cushing_tanks.json").read_text()), dtype="float64")
    zips = sorted((RAW / "hyp3").glob("*.zip"))
    if not zips:
        raise SystemExit("no products")
    rows = []
    for path in zips:
        with zipfile.ZipFile(path) as zf:
            meta = read_meta(zf)
            coh, tr, crs, nd = read_tif(zf, "_corr.tif")
            los, _, _, ndl = read_tif(zf, "_los_disp.tif")
        coh = np.where(coh == nd, np.nan, coh)
        los = np.where(los == ndl, np.nan, los)

        xs, ys = warp_transform("EPSG:4326", crs, tanks[:, 1], tanks[:, 0])
        rr, cc = rasterio.transform.rowcol(tr, xs, ys)
        pts = []
        for r, c in zip(np.array(rr), np.array(cc)):
            if not (1 <= r < los.shape[0] - 1 and 1 <= c < los.shape[1] - 1):
                continue
            w, cw = los[r - 1:r + 2, c - 1:c + 2], coh[r - 1:r + 2, c - 1:c + 2]
            m = np.isfinite(w) & (cw > 0.5)
            if m.sum() >= 3:
                pts.append((tanks[np.where((rr == r) & (cc == c))[0][0], 1],
                            tanks[np.where((rr == r) & (cc == c))[0][0], 0],
                            float(np.median(w[m]) * 100)))
        if len(pts) < 50:
            print(f"{path.name}: only {len(pts)} usable tanks, skipped")
            continue
        P = np.array(pts)
        lon, lat, v = P[:, 0], P[:, 1], P[:, 2]

        A = np.column_stack([np.ones(len(v)), lon - lon.mean(), lat - lat.mean()])
        coef, *_ = np.linalg.lstsq(A, v, rcond=None)
        resid = v - A @ coef
        r2 = 1 - np.var(resid) / np.var(v)

        # spatial structure of the residual (nearest neighbour)
        d2 = ((lon[:, None] - lon[None, :]) ** 2
              + (lat[:, None] - lat[None, :]) ** 2)
        np.fill_diagonal(d2, np.inf)
        nn = np.argmin(d2, axis=1)
        nn_corr = float(np.corrcoef(resid, resid[nn])[0, 1])

        rows.append({
            "product": path.name[:60],
            "baseline_m": float(meta.get("Baseline", "nan")),
            "n_tanks": len(v),
            "median_disp_cm": float(np.median(v)),
            "plane_r2": float(r2),
            "plane_amp_cm": float(np.hypot(coef[1] * (lon.max() - lon.min()),
                                           coef[2] * (lat.max() - lat.min()))),
            "resid_sd_cm": float(np.std(resid)),
            "resid_nn_corr": nn_corr,
        })
        print(f"{path.name[:50]}: baseline {rows[-1]['baseline_m']:+.1f} m, "
              f"median {rows[-1]['median_disp_cm']:+.2f} cm, plane R2 {r2:.2f}, "
              f"resid sd {np.std(resid):.2f} cm")

    out = pd.DataFrame(rows).sort_values("baseline_m")
    out.to_csv(OUT / "insar_pairs.csv", index=False)
    print("\n" + out.round(2).to_string(index=False))

    if len(out) >= 2:
        fig, ax = plt.subplots(figsize=(6.5, 3.6), dpi=140)
        ax.plot(out.baseline_m.abs(), out.median_disp_cm, "o", color="#1f3b57")
        ax.set_xlabel("|perpendicular baseline| (m)")
        ax.set_ylabel("median tank displacement (cm)")
        ax.set_title("Does the tank offset scale with baseline?", loc="left", fontsize=10)
        ax.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(OUT / "insar_pairs.png")
        print(f"wrote {OUT/'insar_pairs.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
