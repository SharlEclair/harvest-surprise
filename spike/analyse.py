"""Spike analysis: does a Corn Belt vegetation index track the US corn yield?

Inputs (both produced by scripts in this folder):
  data/years/ndvi_<year>.csv   one row per (composite date, MODIS tile)
  data/us_maize_yield_owid.csv national maize yield, t/ha and bu/ac

Output: a printed table, data/spike_merged.csv and data/spike_figure.png.

This is a feasibility check, not a result. n is small, the yield series is
national while the NDVI is a fixed Corn Belt box with no crop mask, and the
detrending is fitted on the whole sample (mild look-ahead, acceptable for a
descriptive spike, not for the real evaluation).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DATA = HERE / "data"


def load_ndvi() -> pd.DataFrame:
    files = sorted((DATA / "years").glob("ndvi_*.csv"))
    if not files:
        raise SystemExit("no per-year NDVI files yet")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)

    # Tiles overlap at the AOI edge, so weight by valid pixel count.
    tmp = df.assign(w=df.ndvi * df.n_pixels)
    agg = tmp.groupby(["year", "date"])[["w", "n_pixels"]].sum()
    per_date = (agg.w / agg.n_pixels).rename("ndvi").reset_index()

    per_year = per_date.groupby("year")["ndvi"].agg(["mean", "count"]).reset_index()
    per_year.columns = ["year", "ndvi", "n_composites"]
    return per_year[per_year.n_composites >= 3]


def detrend(df: pd.DataFrame, col: str) -> pd.Series:
    z = (df["year"] - df["year"].mean()) / df["year"].std()
    beta = np.polyfit(z.to_numpy(float), df[col].to_numpy(float), 2)
    return pd.Series(df[col].to_numpy(float) - np.polyval(beta, z.to_numpy(float)), index=df.index)


def loo_rmse(df: pd.DataFrame, with_ndvi: bool) -> float:
    """Leave-one-year-out RMSE of yield on a year trend, +/- NDVI."""
    errs = []
    for year in df["year"]:
        train, test = df[df.year != year], df[df.year == year]
        z = (train["year"] - df["year"].mean()).to_numpy(float)
        cols = [np.ones(len(train)), z]
        test_cols = [np.ones(1), np.array([(test["year"].iloc[0] - df["year"].mean())])]
        if with_ndvi:
            cols.append(train["ndvi"].to_numpy(float))
            test_cols.append(test["ndvi"].to_numpy(float))
        coef, *_ = np.linalg.lstsq(np.column_stack(cols), train["yield_bu_ac"].to_numpy(float), rcond=None)
        pred = float((np.column_stack(test_cols) @ coef)[0])
        errs.append(pred - float(test["yield_bu_ac"].iloc[0]))
    return float(np.sqrt(np.mean(np.square(errs))))


def main() -> None:
    ndvi = load_ndvi()
    y = pd.read_csv(DATA / "us_maize_yield_owid.csv")[["year", "yield_bu_ac"]]
    df = ndvi.merge(y, on="year").dropna().sort_values("year").reset_index(drop=True)
    if len(df) < 5:
        raise SystemExit(f"only {len(df)} overlapping years")

    df["yield_dt"] = detrend(df, "yield_bu_ac")
    df["ndvi_dt"] = detrend(df, "ndvi")

    r_raw = float(np.corrcoef(df.ndvi, df.yield_bu_ac)[0, 1])
    r_dt = float(np.corrcoef(df.ndvi_dt, df.yield_dt)[0, 1])
    rmse_trend = loo_rmse(df, with_ndvi=False)
    rmse_model = loo_rmse(df, with_ndvi=True)

    print(f"years: {df.year.min():.0f}-{df.year.max():.0f}  n={len(df)}")
    print(f"composites per year: median {df.n_composites.median():.0f}")
    print(f"corr(NDVI, yield)          r = {r_raw:+.3f}")
    print(f"corr(detrended)            r = {r_dt:+.3f}")
    print(f"LOO RMSE trend only        {rmse_trend:5.2f} bu/ac")
    print(f"LOO RMSE trend + NDVI      {rmse_model:5.2f} bu/ac")
    print(f"yield sd over sample       {df.yield_bu_ac.std():5.2f} bu/ac")

    df.to_csv(DATA / "spike_merged.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=140)
    ax = axes[0]
    ax.plot(df.year, df.yield_bu_ac, "o-", ms=3, lw=1.2, color="#1f3b57")
    ax.set_title("US maize yield, bu/ac (left axis)", loc="left", fontsize=10)
    ax.tick_params(labelsize=8)
    ax2 = ax.twinx()
    ax2.plot(df.year, df.ndvi, "s-", ms=3, lw=1.0, color="#c9822b")
    ax2.set_title("Corn Belt Jul NDVI (right axis)", loc="right", fontsize=9, color="#c9822b")
    ax2.tick_params(labelsize=8, colors="#c9822b")

    ax = axes[1]
    ax.scatter(df.ndvi_dt, df.yield_dt, s=18, color="#1f3b57")
    b = np.polyfit(df.ndvi_dt, df.yield_dt, 1)
    xs = np.linspace(df.ndvi_dt.min(), df.ndvi_dt.max(), 20)
    ax.plot(xs, np.polyval(b, xs), color="#c9822b", lw=1.2)
    ax.set_xlabel("NDVI anomaly vs trend", fontsize=9)
    ax.set_ylabel("yield anomaly vs trend, bu/ac", fontsize=9)
    ax.set_title(f"detrended, r = {r_dt:+.2f}, n = {len(df)}", loc="left", fontsize=10)
    ax.tick_params(labelsize=8)
    ax.grid(alpha=0.25)

    fig.tight_layout()
    out = DATA / "spike_figure.png"
    fig.savefig(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

