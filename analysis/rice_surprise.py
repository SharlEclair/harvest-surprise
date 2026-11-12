"""Can spring reservoir storage forecast the June rice acreage revision?

NASS publishes California rice area twice before harvest: prospective plantings
on 31 March, and the acreage estimate on 30 June. The difference between them is
the revision the market trades.

The predictor is 1 April reservoir storage, which is observable in April and
also measurable from satellite (see analysis/reservoir_v2.py). So the question
is: does water in the Sierra Nevada tell you the direction of a government
statistic two months before it is published, and does the market move on it?

Output: data/processed/rice_surprise.csv, printed stats, figure.
"""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
NASS = "https://quickstats.nass.usda.gov/api/api_GET/"


def load_key() -> str:
    key = os.environ.get("NASS_API_KEY", "").strip()
    if not key:
        # utf-8-sig strips a BOM, which would otherwise stay on the first key name
        for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("NASS_API_KEY"):
                key = line.split("=", 1)[1].strip()
    return key


def acreage(key: str) -> pd.DataFrame:
    p = {"key": key, "format": "JSON", "commodity_desc": "RICE",
         "statisticcat_desc": "AREA PLANTED", "agg_level_desc": "STATE",
         "state_alpha": "CA", "domain_desc": "TOTAL"}
    df = pd.DataFrame(requests.get(NASS, params=p, timeout=120).json()["data"])
    df = df[(df.unit_desc == "ACRES")
            & (df.class_desc.str.upper().str.contains("ALL CLASSES", na=False))]
    df["year"] = pd.to_numeric(df.year, errors="coerce")
    df["acres"] = pd.to_numeric(df.Value.astype(str).str.replace(",", ""), errors="coerce")
    df = df.dropna(subset=["year", "acres"])
    wide = df.pivot_table(index="year", columns="reference_period_desc",
                          values="acres", aggfunc="first")
    return wide.reset_index()


def storage() -> pd.DataFrame:
    c = pd.read_csv(RAW / "cdec_reservoirs.csv", parse_dates=["date"])
    c = c[(c.storage_af > 1000) & (c.storage_af < 6e6)]
    counts = c.groupby("station").storage_af.count()
    c = c[c.station.isin(counts[counts > 8000].index)]
    daily = c.groupby("date").agg(total_af=("storage_af", "sum"),
                                  n=("station", "nunique")).reset_index()
    daily = daily[daily.n >= 6]
    daily["year"] = daily.date.dt.year
    daily["doy"] = daily.date.dt.day_of_year
    apr = daily[(daily.doy >= 88) & (daily.doy <= 98)]
    return (apr.sort_values("date").groupby("year")
               .agg(storage_af=("total_af", "first")).reset_index())


def ols(y, X):
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    s2 = resid @ resid / (len(y) - X.shape[1])
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    r2 = 1 - (resid @ resid) / ((y - y.mean()) @ (y - y.mean()))
    return coef, se, r2


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    key = load_key()
    ac = acreage(key)
    st = storage()
    df = ac.merge(st, on="year", how="inner").dropna(subset=["storage_af"])

    mar = "YEAR - MAR ACREAGE"
    jun = "YEAR - JUN ACREAGE"
    if mar not in df or jun not in df:
        raise SystemExit(f"missing columns; have {list(df.columns)}")
    d = df.dropna(subset=[mar, jun]).copy()
    d["rev"] = d[jun] - d[mar]
    d["rev_pct"] = d.rev / d[mar]
    d = d[(d.year >= 1990) & (d[mar] > 50000)]
    d.to_csv(OUT / "rice_surprise.csv", index=False)
    print(f"years with both March and June acreage: {len(d)} "
          f"({d.year.min():.0f}-{d.year.max():.0f})")
    print(f"revision: mean {d.rev.mean():+.0f} acres, sd {d.rev.std():.0f}, "
          f"share non-zero {(d.rev != 0).mean():.0%}")

    x = np.log(d.storage_af.to_numpy(float))
    y = d.rev_pct.to_numpy(float)
    X = np.column_stack([np.ones(len(d)), x])
    coef, se, r2 = ols(y, X)
    t_stat = coef[1] / se[1]
    hit = float((np.sign(coef[0] + coef[1] * x) == np.sign(y)).mean())
    naive = float(np.sqrt(np.mean(y ** 2)))
    model = float(np.sqrt(np.mean((y - X @ coef) ** 2)))
    print(f"\nregression: revision% = {coef[0]:+.3f} {coef[1]:+.3f} * log(storage)")
    print(f"  elasticity {coef[1]:+.3f} (se {se[1]:.3f}, t {t_stat:+.2f}), R2 {r2:.3f}")
    print(f"  direction hit rate {hit:.0%}; RMSE {model:.3f} vs naive {naive:.3f} "
          f"({1 - model/naive:+.0%})")

    # leave-one-year-out, honest
    loo = []
    for i in range(len(d)):
        m = np.arange(len(d)) != i
        c, *_ = np.linalg.lstsq(np.column_stack([np.ones(m.sum()), x[m]]), y[m], rcond=None)
        loo.append(float(c[0] + c[1] * x[i]))
    loo = np.array(loo)
    print(f"  LOO RMSE {np.sqrt(np.mean((loo - y) ** 2)):.3f} vs naive {naive:.3f}, "
          f"skill {1 - np.sqrt(np.mean((loo - y) ** 2)) / naive:+.0%}, "
          f"LOO hit {(np.sign(loo) == np.sign(y)).mean():.0%}")

    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
    ax.scatter(d.storage_af / 1e6, d.rev_pct * 100, s=22, color="#1f3b57")
    xs = np.linspace(x.min(), x.max(), 40)
    ax.plot(np.exp(xs) / 1e6, (coef[0] + coef[1] * xs) * 100, color="#c9822b")
    ax.axhline(0, color="k", lw=0.7)
    ax.set_xlabel("1 April reservoir storage (million acre-feet)")
    ax.set_ylabel("June minus March acreage (%)")
    ax.set_title(f"Water in April predicts the June acreage revision (t={t_stat:+.1f})",
                 loc="left", fontsize=10)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "rice_surprise.png")
    print(f"\nwrote {OUT/'rice_surprise.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
