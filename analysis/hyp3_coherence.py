"""Analyse a HyP3 INSAR_GAMMA product over the Cushing tank farm.

HyP3 returns a zip containing (among others):
    *_corr.tif            coherence, 0-1
    *_unw_phase.tif       unwrapped phase, radians
    *_los_displacement.tif line-of-sight displacement, metres
    *_inc_map.tif         incidence angle

The question this answers: **is coherence on the tank roofs high enough for phase
to mean anything?** If coherence is near zero there, InSAR over moving roofs is
dead and the tank-fill idea is finished in every free form. If it is high, the
displacement series becomes worth extracting.

Output: data/processed/hyp3_coherence.csv, hyp3_coherence.png
"""
from __future__ import annotations

import json
import sys
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


def find_member(zf: zipfile.ZipFile, suffix: str) -> str | None:
    for n in zf.namelist():
        if n.lower().endswith(suffix):
            return n
    return None


def main() -> int:
    zips = sorted((RAW / "hyp3").glob("*.zip"))
    if not zips:
        raise SystemExit("no HyP3 product in data/raw/hyp3")
    path = zips[-1]
    print(f"product: {path.name} ({path.stat().st_size/1e6:.0f} MB)")

    tanks = np.array(json.loads((RAW / "cushing_tanks.json").read_text()), dtype="float64")

    with zipfile.ZipFile(path) as zf:
        print("members:", len(zf.namelist()))
        corr_name = find_member(zf, "_corr.tif")
        if corr_name is None:
            raise SystemExit(f"no coherence band; members: {zf.namelist()[:20]}")
        with zf.open(corr_name) as fh, rasterio.io.MemoryFile(fh.read()) as mem:
            with mem.open() as src:
                coh = src.read(1).astype("float32")
                tr, crs = src.transform, src.crs
                nodata = src.nodata
        print(f"coherence grid {coh.shape}, crs {crs}, nodata {nodata}")

    if nodata is not None:
        coh = np.where(coh == nodata, np.nan, coh)
    coh = np.where((coh >= 0) & (coh <= 1), coh, np.nan)

    xs, ys = warp_transform("EPSG:4326", crs, tanks[:, 1], tanks[:, 0])
    rr, cc = rasterio.transform.rowcol(tr, xs, ys)
    rr, cc = np.array(rr), np.array(cc)
    inside = (rr >= 0) & (rr < coh.shape[0]) & (cc >= 0) & (cc < coh.shape[1])
    tank_coh = coh[rr[inside], cc[inside]]
    tank_coh = tank_coh[np.isfinite(tank_coh)]

    rng = np.random.default_rng(0)
    gr, gc = rng.integers(0, coh.shape[0], 20000), rng.integers(0, coh.shape[1], 20000)
    ground = coh[gr, gc]
    ground = ground[np.isfinite(ground)]

    print(f"\ntanks in scene: {len(tank_coh)}")
    print(f"median coherence, tank roofs: {np.median(tank_coh):.3f} "
          f"(p25 {np.percentile(tank_coh,25):.3f}, p75 {np.percentile(tank_coh,75):.3f})")
    print(f"median coherence, whole scene: {np.median(ground):.3f}")

    pd.DataFrame([
        {"class": "tank", "n": len(tank_coh), "median_coherence": float(np.median(tank_coh)),
         "p25": float(np.percentile(tank_coh, 25)), "p75": float(np.percentile(tank_coh, 75))},
        {"class": "scene", "n": len(ground), "median_coherence": float(np.median(ground)),
         "p25": float(np.percentile(ground, 25)), "p75": float(np.percentile(ground, 75))},
    ]).to_csv(OUT / "hyp3_coherence.csv", index=False)

    fig, ax = plt.subplots(figsize=(7, 3.8), dpi=140)
    ax.hist(ground, bins=60, alpha=0.5, density=True, label="whole scene", color="#999")
    ax.hist(tank_coh, bins=60, alpha=0.7, density=True, label="tank roofs", color="#1f3b57")
    ax.set_xlabel("interferometric coherence")
    ax.set_title("HyP3 coherence: tank roofs vs scene", fontsize=10, loc="left")
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "hyp3_coherence.png")
    print(f"wrote {OUT/'hyp3_coherence.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
