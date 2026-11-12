"""Cushing v2: per-tank, scene-demeaned, with a held-out tank selection.

The pooled index in cushing_tanks.py correlated +0.63 with stocks in levels, but
the year-by-year correlations swing from -0.56 to +0.60, so the aggregate is a
between-year artefact. The honest metric is within-year: does the index track
stocks after both series have had their annual means removed?

Three indices are compared:

  pooled     median brightness across all tanks (the v1 measurement)
  demeaned   median of (tank - scene mean), which removes illumination,
             atmosphere and sensor drift shared by every tank in the scene
  selected   tanks picked for responsiveness on the TRAIN years only, then
             scored on the held-out years, so selection cannot leak

Metrics: within-year level correlation, within-year 4-week change correlation,
and the same on levels without demeaning for reference.

Output: data/processed/cushing_v2_metrics.csv, cushing_v2.png
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

TRAIN_YEARS = (2018, 2021)
TEST_YEARS = (2022, 2025)
MIN_VALID = 100
TOP_FRAC = 0.15


def within_year_r(x: np.ndarray, y: np.ndarray, years: np.ndarray) -> float:
    xd = x - pd.Series(x).groupby(years).transform("mean").to_numpy()
    yd = y - pd.Series(y).groupby(years).transform("mean").to_numpy()
    if np.std(xd) == 0 or np.std(yd) == 0:
        return np.nan
    return float(np.corrcoef(xd, yd)[0, 1])


def changes(dates: pd.Series, x: np.ndarray, y: np.ndarray, gap: int = 21, tol: int = 45):
    order = np.argsort(dates.to_numpy())
    d, xs, ys = dates.to_numpy()[order], x[order], y[order]
    dx, dy, dyears = [], [], []
    for i in range(len(d)):
        lo = np.searchsorted(d, d[i] - np.timedelta64(tol, "D"))
        hi = np.searchsorted(d, d[i] - np.timedelta64(gap, "D"))
        if hi <= lo:
            continue
        j = hi - 1
        if not (np.isfinite(xs[i]) and np.isfinite(xs[j])):
            continue
        dx.append(xs[i] - xs[j])
        dy.append(ys[i] - ys[j])
        dyears.append(pd.Timestamp(d[i]).year)
    return np.array(dx), np.array(dy), np.array(dyears)


def main() -> int:
    z = np.load(OUT / "cushing_tank_matrix.npz", allow_pickle=True)
    B = z["brightness"]                     # scenes x tanks
    V = z["valid"]
    dates = pd.to_datetime(z["dates"])
    elev = z["solar_elev"]

    eia = pd.read_csv(RAW / "eia_cushing_weekly.csv", parse_dates=["date"]).sort_values("date")
    stocks = np.interp(dates.astype("int64"), eia.date.astype("int64"), eia.stocks_kbbl)
    years = dates.year.to_numpy()

    good = V.sum(axis=0) >= MIN_VALID
    print(f"scenes {B.shape[0]}, tanks {B.shape[1]}, tanks with >= {MIN_VALID} obs: {good.sum()}")

    # scene-level mean over usable tanks removes shared illumination drift
    scene_mean = np.nanmean(np.where(V > 0, B, np.nan), axis=1, keepdims=True)
    R = np.where(V > 0, B - scene_mean, np.nan)

    def agg(mat: np.ndarray, cols: np.ndarray) -> np.ndarray:
        return np.nanmedian(mat[:, cols], axis=1)

    pooled = agg(B, good)
    demeaned = agg(R, good)

    # select tanks on train years only
    tr = np.isin(years, np.arange(TRAIN_YEARS[0], TRAIN_YEARS[1] + 1))
    scores = []
    for j in np.where(good)[0]:
        s = R[tr, j]
        ok = np.isfinite(s) & np.isfinite(stocks[tr])
        if ok.sum() < 40:
            scores.append(np.nan)
            continue
        scores.append(within_year_r(s[ok], stocks[tr][ok], years[tr][ok]))
    scores = np.array(scores)
    ranked = np.argsort(-np.nan_to_num(scores, nan=-9))
    n_top = max(10, int(TOP_FRAC * len(ranked)))
    selected_cols = np.where(good)[0][ranked[:n_top]]
    selected = agg(R, selected_cols)
    print(f"selected {n_top} tanks; train-year mean r of selected "
          f"{np.nanmean(scores[ranked[:n_top]]):+.3f}")

    rows = []
    for name, idx in [("pooled", pooled), ("demeaned", demeaned), ("selected", selected)]:
        r_lvl = float(np.corrcoef(idx, stocks)[0, 1])
        r_within = within_year_r(idx, stocks, years)
        dx, dy, dyears = changes(dates, idx, stocks)
        r_chg = within_year_r(dx, dy, dyears) if len(dx) > 30 else np.nan
        rows.append({"index": name, "r_levels": round(r_lvl, 3),
                     "r_levels_within_year": round(r_within, 3),
                     "r_changes_within_year": round(r_chg, 3), "n_changes": len(dx)})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "cushing_v2_metrics.csv", index=False)
    print("\n" + out.to_string(index=False))
    print(f"\ncorr(index, solar elevation): pooled {np.corrcoef(pooled, elev)[0,1]:+.3f}, "
          f"demeaned {np.corrcoef(demeaned, elev)[0,1]:+.3f}")

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6), dpi=140)
    for ax, (name, idx) in zip(axes, [("pooled", pooled), ("demeaned", demeaned),
                                      ("selected", selected)]):
        ax.scatter(stocks / 1000, idx, s=8, c=years, cmap="viridis")
        ax.set_title(f"{name}: within-year r="
                     f"{within_year_r(idx, stocks, years):+.2f}", fontsize=9, loc="left")
        ax.set_xlabel("EIA stocks (million bbl)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "cushing_v2.png")
    print(f"wrote {OUT/'cushing_v2.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
