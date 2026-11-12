"""Does California reservoir storage predict California rice acreage?

The chain: winter/spring storage decides how much surface water is allocated,
allocation decides how much rice gets planted, and rice is the most
water-responsive field crop in the state. Both ends are free and public - CDEC
gauges and NASS acreage - so the link can be tested rather than asserted.

Controls: a linear time trend (acreage has drifted for reasons unrelated to
water), and a placebo that uses NEXT year's storage, which cannot cause this
year's planting.

Output: data/processed/water_rice.csv, water_rice.png, printed regression.
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

MAX_AF = 6e6


def load_key() -> str:
    key = os.environ.get("NASS_API_KEY", "").strip()
    if not key:
        # utf-8-sig strips a BOM, which would otherwise stay on the first key name
        for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("NASS_API_KEY"):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit("no NASS_API_KEY")
    return key


def rice_acreage(key: str) -> pd.DataFrame:
    params = {
        "key": key, "format": "JSON", "commodity_desc": "RICE",
        "statisticcat_desc": "AREA PLANTED", "agg_level_desc": "STATE",
        "state_alpha": "CA", "domain_desc": "TOTAL",
    }
    r = requests.get(NASS, params=params, timeout=120)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["data"])
    df = df[(df.reference_period_desc == "YEAR") & (df.unit_desc == "ACRES")]
    df = df[df.class_desc.str.upper().str.contains("ALL CLASSES", na=False)]
    df["year"] = pd.to_numeric(df.year, errors="coerce")
    df["acres"] = pd.to_numeric(df.Value.astype(str).str.replace(",", ""), errors="coerce")
    df = df.dropna(subset=["year", "acres"]).sort_values("year")
    return df[["year", "acres"]].drop_duplicates("year")


def storage_by_year() -> pd.DataFrame:
    c = pd.read_csv(RAW / "cdec_reservoirs.csv", parse_dates=["date"])
    c = c[(c.storage_af > 1000) & (c.storage_af < MAX_AF)]
    # keep reservoirs with a long, usable record
    counts = c.groupby("station").storage_af.count()
    good = counts[counts > 8000].index
    c = c[c.station.isin(good)]
    daily = c.groupby("date").agg(total_af=("storage_af", "sum"),
                                  n=("station", "nunique")).reset_index()
    daily = daily[daily.n >= 6]
    daily["year"] = daily.date.dt.year
    daily["doy"] = daily.date.dt.dayofyear
    # 1 April: the allocation decision is made on the spring snowpack survey
    apr = daily[(daily.doy >= 88) & (daily.doy <= 98)]
    out = (apr.sort_values("date").groupby("year")
              .agg(total_af=("total_af", "first"), date=("date", "first")).reset_index())
    return out


def ols(y: np.ndarray, X: np.ndarray):
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    dof = len(y) - X.shape[1]
    s2 = resid @ resid / dof
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    r2 = 1 - (resid @ resid) / ((y - y.mean()) @ (y - y.mean()))
    return coef, se, r2


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    key = load_key()
    rice = rice_acreage(key)
    stor = storage_by_year()
    df = rice.merge(stor, on="year", how="inner").dropna()
    df = df[(df.year >= 1990) & (df.acres < 1e6)]
    price_file = RAW / "rice_price.csv"
    if price_file.exists():
        px = pd.read_csv(price_file)
        df = df.merge(px, on="year", how="left")
    df.to_csv(OUT / "water_rice.csv", index=False)
    print(f"years with both rice acreage and storage: {len(df)} "
          f"({df.year.min():.0f}-{df.year.max():.0f})")

    ly = np.log(df.acres.to_numpy(float))
    ls = np.log(df.total_af.to_numpy(float))
    trend = df.year.to_numpy(float) - df.year.mean()

    # 1. raw association
    r_raw = float(np.corrcoef(ls, ly)[0, 1])
    # 2. with a linear trend
    X = np.column_stack([np.ones(len(df)), ls, trend])
    coef, se, r2 = ols(ly, X)
    t_stat = coef[1] / se[1]
    # 3. placebo: next year's storage
    placebo = np.roll(ls, -1)[:-1]
    y_p = ly[:-1]
    Xp = np.column_stack([np.ones(len(y_p)), placebo, trend[:-1]])
    cp, sep, _ = ols(y_p, Xp)

    # price control: acreage responds to price, and price could correlate with water
    if "rice_price" in df and df.rice_price.notna().sum() > 12:
        m = df.dropna(subset=["rice_price"])
        lp = np.log(m.rice_price.to_numpy(float))
        X3 = np.column_stack([np.ones(len(m)), np.log(m.total_af.to_numpy(float)),
                              m.year.to_numpy(float) - m.year.mean(), lp])
        c3, s3, r3 = ols(np.log(m.acres.to_numpy(float)), X3)
        print(f"with trend + price control: elasticity {c3[1]:+.3f} "
              f"(se {s3[1]:.3f}, t {c3[1]/s3[1]:+.2f}), price {c3[3]:+.3f} "
              f"(t {c3[3]/s3[3]:+.2f}), R2 {r3:.3f}, n={len(m)}")
    print(f"\ncorr(log storage, log acres)          {r_raw:+.3f}")
    print(f"with trend: elasticity {coef[1]:+.3f} (se {se[1]:.3f}, t {t_stat:+.2f}), "
          f"R2 {r2:.3f}, n={len(df)}")
    print(f"placebo (next year's storage):        {cp[1]:+.3f} (se {sep[1]:.3f}, "
          f"t {cp[1]/sep[1]:+.2f})")

    fig, ax = plt.subplots(figsize=(7.4, 4.2), dpi=150)
    ax.plot(df.year, df.acres / 1000, "o-", ms=4, color="#1f3b57", label="rice acres (thousand)")
    ax.set_ylabel("planted acres (thousands)", color="#1f3b57")
    ax2 = ax.twinx()
    ax2.plot(df.year, df.total_af / 1e6, "s-", ms=3, color="#c9822b", label="1 Apr storage (MAF)")
    ax2.set_ylabel("reservoir storage, 1 April (million acre-feet)", color="#c9822b")
    ax.set_title("California rice acreage and spring reservoir storage", loc="left", fontsize=10)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "water_rice.png")
    print(f"\nwrote {OUT/'water_rice.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
