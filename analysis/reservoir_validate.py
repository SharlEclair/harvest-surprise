"""Validate the Sentinel-2 water-area measurement against CDEC gauges.

Reads the scene table produced by analysis/reservoir_area.py (water area per
scene) and joins it to the daily gauge reading, then fits a per-reservoir
area-to-elevation rating curve by leave-one-out and scores it in feet.

Baseline: predicting the mean elevation of the sample. A rating curve that does
not beat that baseline has measured nothing.

Output: data/processed/reservoir_validation.csv, reservoir_fit.csv, figure.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"


def main() -> int:
    sc = pd.read_csv(OUT / "reservoir_scenes.csv")
    sc["date"] = (pd.to_datetime(sc["datetime"], utc=True)
                  .dt.tz_localize(None).dt.normalize())

    cdec = pd.read_csv(RAW / "cdec_reservoirs.csv", parse_dates=["date"])
    cdec = cdec[(cdec.elevation_ft > 0) & (cdec.elevation_ft < 10000)]
    cdec = cdec[(cdec.storage_af > 0)]

    j = sc.merge(cdec[["date", "reservoir", "elevation_ft", "storage_af"]],
                 on=["date", "reservoir"], how="inner")
    print(f"scenes {len(sc)}, matched to a gauge reading {len(j)}")
    j.to_csv(OUT / "reservoir_matched.csv", index=False)

    rows = []
    fits = []
    for name, g in j.groupby("reservoir"):
        g = g.sort_values("area_m2").reset_index(drop=True)
        if len(g) < 8:
            rows.append({"reservoir": name, "n": len(g)})
            continue
        preds = []
        for i in range(len(g)):
            train = g.drop(index=i)
            b = np.polyfit(train.area_m2, train.elevation_ft, 1)
            preds.append(float(np.polyval(b, g.area_m2.iloc[i])))
        g["pred_elev"] = preds
        g["err"] = g.pred_elev - g.elevation_ft
        rmse = float(np.sqrt(np.mean(g.err ** 2)))
        base = float(np.sqrt(np.mean((g.elevation_ft - g.elevation_ft.mean()) ** 2)))
        # map predicted elevation to storage using the gauge's own curve
        curv = g.sort_values("elevation_ft")
        pred_storage = np.interp(g.pred_elev, curv.elevation_ft, curv.storage_af,
                                 left=np.nan, right=np.nan)
        st_err = (pred_storage - g.storage_af) / g.storage_af * 100
        rows.append({
            "reservoir": name, "n": len(g),
            "rmse_ft": round(rmse, 1),
            "baseline_rmse_ft": round(base, 1),
            "skill_vs_baseline": round(1 - rmse / base, 2),
            "r2_area_elev": round(float(np.corrcoef(g.area_m2, g.elevation_ft)[0, 1] ** 2), 3),
            "elev_range_ft": round(float(g.elevation_ft.max() - g.elevation_ft.min()), 1),
            "median_abs_storage_err_pct": round(float(np.nanmedian(np.abs(st_err))), 1),
        })
        b = np.polyfit(g.area_m2, g.elevation_ft, 1)
        fits.append({"reservoir": name, "slope_ft_per_km2": b[0] * 1e6,
                     "intercept_ft": b[1]})
        g.to_csv(OUT / f"reservoir_{name.lower().replace(' ', '_')}.csv", index=False)

    sm = pd.DataFrame(rows)
    sm.to_csv(OUT / "reservoir_validation.csv", index=False)
    pd.DataFrame(fits).to_csv(OUT / "reservoir_fit.csv", index=False)
    print()
    print(sm.to_string(index=False))

    fig, axes = plt.subplots(1, len(sm), figsize=(12, 3.6), dpi=140)
    axes = np.atleast_1d(axes)
    for ax, (_, r) in zip(axes, sm.iterrows()):
        g = j[j.reservoir == r.reservoir]
        ax.scatter(g.area_m2 / 1e6, g.elevation_ft, s=14, color="#1f3b57")
        if "rmse_ft" in r and not pd.isna(r.rmse_ft):
            ax.set_title(f"{r.reservoir}: RMSE {r.rmse_ft:.0f} ft "
                         f"(baseline {r.baseline_rmse_ft:.0f})", fontsize=8)
        else:
            ax.set_title(r.reservoir, fontsize=9)
        ax.set_xlabel("water area (km2)", fontsize=8)
        ax.set_ylabel("gauge elevation (ft)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "reservoir_area.png")
    print(f"\nwrote {OUT/'reservoir_area.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
