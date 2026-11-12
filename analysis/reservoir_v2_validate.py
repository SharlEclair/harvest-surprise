"""Score the v2 water-extent measurement against CDEC gauges.

Reads the npz grids from analysis/reservoir_v2.py, builds the region of interest
as the union of every cell that is ever wet, gates on valid fraction, converts
water fraction to area, and fits area -> elevation three ways:

  linear      the v1 model, for comparison
  isotonic    monotone, because area must not fall as elevation rises
  pooled      one slope per reservoir, shared intercept, if fit fails per-site

Baseline is always "predict the mean elevation of the scored sample". A model
that does not beat it has measured nothing, whatever its R2 looks like.

Output: data/processed/reservoir_v2_validation.csv, reservoir_v2.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
MIN_VALID_FRAC = 0.60
ROI_WET_FRAC = 0.50     # a cell belongs to the lake only if it is mostly water when wet
# A reservoir cannot lose most of its surface between two visits. When the water
# mask fails (haze, shadow, a partial swath) the measured area collapses to a
# sliver - Don Pedro reported 83,153 m2 against a 20 million m2 median - and one
# such point drags the whole rank correlation down. Scenes below this fraction of
# the reservoir's own median are dropped, and the count is reported.
MIN_AREA_FRAC = 0.50


def cell_area_m2(lat: float) -> float:
    return (0.001 * 111320 * np.cos(np.radians(lat))) * (0.001 * 110574)


def main() -> int:
    meta = json.loads((OUT / "reservoir_v2_grids.json").read_text())
    cdec = pd.read_csv(RAW / "cdec_reservoirs.csv", parse_dates=["date"])
    cdec = cdec[(cdec.elevation_ft > 0) & (cdec.elevation_ft < 10000)
                & (cdec.storage_af > 0)]

    rows, scored = [], []
    for name, m in meta.items():
        f = OUT / f"reservoir_v2_{name.lower().replace(' ', '_')}.npz"
        if not f.exists():
            print(f"{name}: no npz yet")
            continue
        z = np.load(f, allow_pickle=True)
        water, valid = z["water"].astype("float32"), z["valid"].astype("float32")
        dates = pd.to_datetime(z["dates"])
        if len(dates) == 0:
            continue

        roi = (water > ROI_WET_FRAC).any(axis=0)
        if roi.sum() < 20:
            print(f"{name}: ROI too small ({roi.sum()} cells)")
            continue
        area_m2 = cell_area_m2((m["bbox"][1] + m["bbox"][3]) / 2)

        vfrac = valid[:, roi].mean(axis=1)
        # Normalise by the observed fraction: if 20% of the ROI is cloud, the
        # water that was hidden still existed. Without this the estimator has a
        # scene-specific downward bias, which is what killed Don Pedro.
        observed = np.clip(valid[:, roi].sum(axis=1), 1e-6, None)
        warea = (water[:, roi].sum(axis=1) / observed) * (roi.sum() * area_m2)
        df = pd.DataFrame({"date": dates.normalize(), "area_m2": warea,
                           "valid_frac": vfrac, "reservoir": name})
        df = df[(df.valid_frac >= MIN_VALID_FRAC) & (df.area_m2 > 0)]
        if len(df) < 8:
            print(f"{name}: only {len(df)} usable scenes after the validity gate")
            continue

        j = df.merge(cdec[["date", "reservoir", "elevation_ft", "storage_af"]],
                     on=["date", "reservoir"], how="inner")
        if len(j) < 8:
            print(f"{name}: only {len(j)} matched scenes")
            continue
        scored.append(j)

        spearman_all = round(float(j.area_m2.corr(j.elevation_ft, method="spearman")), 3)
        keep = j.area_m2 >= MIN_AREA_FRAC * j.area_m2.median()
        n_dropped = int((~keep).sum())
        if keep.sum() >= 8:
            j = j[keep]
        else:
            n_dropped = 0
        if n_dropped:
            print(f"{name}: dropped {n_dropped} area-collapse scene(s) "
                  f"(< {MIN_AREA_FRAC:.0%} of median area)")

        x, y = j.area_m2.to_numpy(), j.elevation_ft.to_numpy()

        # Levels can correlate simply because both series follow the seasonal
        # cycle. The sharper question is whether successive CHANGES agree, so that
        # is computed and reported alongside the level correlation.
        jj = j.sort_values("date")
        da = (jj.area_m2.diff() / jj.area_m2.shift()).to_numpy()
        de = jj.elevation_ft.diff().to_numpy()
        m = np.isfinite(da) & np.isfinite(de)
        chg_spearman = (round(float(pd.Series(da[m]).corr(pd.Series(de[m]),
                                                         method="spearman")), 3)
                        if m.sum() >= 8 else float("nan"))
        n_changes = int(m.sum())

        order = np.argsort(x)
        # linear, leave-one-out
        lin = []
        for i in range(len(x)):
            mask = np.arange(len(x)) != i
            b = np.polyfit(x[mask], y[mask], 1)
            lin.append(float(np.polyval(b, x[i])))
        lin = np.array(lin)
        # isotonic, leave-one-out: the honest version of the monotone fit
        iso_pred = np.empty_like(y)
        for i in range(len(x)):
            mask = np.arange(len(x)) != i
            m = IsotonicRegression(out_of_bounds="clip").fit(x[mask], y[mask])
            iso_pred[i] = float(m.predict([x[i]])[0])

        base = float(np.sqrt(np.mean((y - y.mean()) ** 2)))
        rows.append({
            "reservoir": name,
            "n_scenes": int(len(z["dates"])),
            "n_usable": int(len(df)),
            "n_scored": int(len(j)),
            "roi_cells": int(roi.sum()),
            "elev_range_ft": round(float(y.max() - y.min()), 1),
            "rmse_linear_ft": round(float(np.sqrt(np.mean((lin - y) ** 2))), 1),
            "rmse_isotonic_ft": round(float(np.sqrt(np.mean((iso_pred - y) ** 2))), 1),
            "baseline_rmse_ft": round(base, 1),
            "skill_linear": round(float(1 - np.sqrt(np.mean((lin - y) ** 2)) / base), 2),
            "spearman": round(float(pd.Series(x).corr(pd.Series(y), method="spearman")), 3),
            "spearman_changes": chg_spearman,
            "n_changes": n_changes,
            "spearman_all_scenes": spearman_all,
            "n_area_collapse_dropped": n_dropped,
        })

    if not rows:
        raise SystemExit("nothing scored")

    sm = pd.DataFrame(rows)
    sm.to_csv(OUT / "reservoir_v2_validation.csv", index=False)
    print(sm.to_string(index=False))

    if scored:
        allj = pd.concat(scored)
        allj.to_csv(OUT / "reservoir_v2_matched.csv", index=False)
        fig, axes = plt.subplots(1, len(scored), figsize=(12, 3.6), dpi=140)
        axes = np.atleast_1d(axes)
        for ax, g in zip(axes, scored):
            ax.scatter(g.area_m2 / 1e6, g.elevation_ft, s=16, color="#1f3b57")
            r = sm[sm.reservoir == g.reservoir.iloc[0]].iloc[0]
            ax.set_title(f"{g.reservoir.iloc[0]}: skill {r.skill_linear:+.2f}, "
                         f"rho {r.spearman:+.2f}", fontsize=8)
            ax.set_xlabel("water area (km2)", fontsize=8)
            ax.set_ylabel("gauge elevation (ft)", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(OUT / "reservoir_v2.png")
        print(f"wrote {OUT/'reservoir_v2.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
