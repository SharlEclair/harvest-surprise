"""Does the Cushing tank-brightness index track EIA weekly stocks?

The video compared two dates and got a -41% estimate against a -63% actual.
This uses ~300 scenes and weekly EIA data, so the question becomes whether the
index has any cross-sectional signal at all, not whether two points happened to
line up.

Three tests, in increasing strictness:
  1. levels, raw correlation
  2. levels, after removing a season-month mean (sun angle and crop cover change)
  3. the four-week change in the index against the four-week change in stocks,
     which is the flow signal a trading rule would actually use

Output: data/processed/cushing_validation.csv, cushing.png
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


def load_merged() -> pd.DataFrame:
    sc = pd.read_csv(OUT / "cushing_scenes.csv", parse_dates=["date"])
    eia = pd.read_csv(RAW / "eia_cushing_weekly.csv", parse_dates=["date"])
    eia = eia.sort_values("date")
    sc = sc.sort_values("date")
    sc["stocks_kbbl"] = np.interp(sc.date.astype("int64"),
                                  eia.date.astype("int64"), eia.stocks_kbbl)
    sc["month"] = sc.date.dt.month
    return sc


def main() -> int:
    df = load_merged()
    if len(df) < 30:
        raise SystemExit(f"only {len(df)} scenes matched")
    print(f"scenes {len(df)}, {df.date.min().date()} to {df.date.max().date()}")
    print(f"stocks range {df.stocks_kbbl.min():.0f} to {df.stocks_kbbl.max():.0f} kbbl")

    r_raw = float(np.corrcoef(df["index"], df.stocks_kbbl)[0, 1])
    # de-seasonalise by month
    df["index_ds"] = df["index"] - df.groupby("month")["index"].transform("mean")
    df["stocks_ds"] = df.stocks_kbbl - df.groupby("month").stocks_kbbl.transform("mean")
    r_ds = float(np.corrcoef(df.index_ds, df.stocks_ds)[0, 1])

    # four-week change, using the nearest scene at least 21 days earlier
    df = df.sort_values("date").reset_index(drop=True)
    diffs = []
    for i, row in df.iterrows():
        prior = df[(df.date <= row.date - pd.Timedelta(days=21)) & (df.date >= row.date - pd.Timedelta(days=70))]
        if prior.empty:
            continue
        p = prior.iloc[-1]
        diffs.append({"date": row.date, "d_index": row["index"] - p["index"],
                      "d_stocks": row.stocks_kbbl - p.stocks_kbbl})
    dd = pd.DataFrame(diffs)
    r_diff = float(np.corrcoef(dd.d_index, dd.d_stocks)[0, 1]) if len(dd) > 10 else np.nan

    out = pd.DataFrame([
        {"test": "levels, raw", "n": len(df), "corr": round(r_raw, 3)},
        {"test": "levels, de-seasonalised", "n": len(df), "corr": round(r_ds, 3)},
        {"test": "4-week change", "n": len(dd), "corr": round(r_diff, 3)},
    ])
    out.to_csv(OUT / "cushing_validation.csv", index=False)
    print("\n" + out.to_string(index=False))

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), dpi=140)
    axes[0].scatter(df.stocks_kbbl / 1000, df["index"], s=10, color="#1f3b57")
    axes[0].set_xlabel("EIA Cushing stocks (million bbl)")
    axes[0].set_ylabel("tank / ground brightness")
    axes[0].set_title(f"levels, r={r_raw:+.2f}", fontsize=9, loc="left")
    axes[1].scatter(dd.d_stocks / 1000, dd.d_index, s=10, color="#c9822b")
    axes[1].axhline(0, color="k", lw=0.6)
    axes[1].axvline(0, color="k", lw=0.6)
    axes[1].set_xlabel("4-week change in stocks (million bbl)")
    axes[1].set_ylabel("4-week change in index")
    axes[1].set_title(f"changes, r={r_diff:+.2f}", fontsize=9, loc="left")
    for ax in axes:
        ax.grid(alpha=0.25)
        ax.tick_params(labelsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "cushing.png")
    print(f"\nwrote {OUT/'cushing.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
