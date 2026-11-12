"""Close the chain: satellite storage error -> acreage forecast error.

Two questions:

1. How wrong is the satellite storage estimate, in the units the economic model
   actually uses (acre-feet, not feet of elevation)?
2. If you substitute it for the gauge, how much worse is the rice-acreage
   forecast?

The second is just error propagation: the acreage elasticity is ~0.41, so a
storage error of X% becomes an acreage error of about 0.41 * X%. That is the
honest way to close the chain on five years of satellite data, rather than
pretending five observations can fit a 36-year relationship.

Also reports the June acreage report reaction in rough rice futures, descriptively,
with the sample size stated.

Output: data/processed/chain_propagation.csv, rice_event.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
ELASTICITY = 0.407          # from analysis/water_rice.py, trend-controlled, n=36


def propagation() -> pd.DataFrame:
    m = pd.read_csv(OUT / "reservoir_v2_matched.csv", parse_dates=["date"])
    rows = []
    for name, g in m.groupby("reservoir"):
        g = g.sort_values("area_m2").reset_index(drop=True)
        if len(g) < 10:
            continue
        x = g.area_m2.to_numpy(float)
        y = g.elevation_ft.to_numpy(float)
        pred = np.empty_like(y)
        for i in range(len(x)):
            mask = np.arange(len(x)) != i
            iso = IsotonicRegression(out_of_bounds="clip").fit(x[mask], y[mask])
            pred[i] = float(iso.predict([x[i]])[0])

        # map both to storage through the gauge's own curve
        curv = g.sort_values("elevation_ft")
        st_obs = np.interp(y, curv.elevation_ft, curv.storage_af,
                           left=np.nan, right=np.nan)
        st_pred = np.interp(pred, curv.elevation_ft, curv.storage_af,
                            left=np.nan, right=np.nan)
        ok = np.isfinite(st_obs) & np.isfinite(st_pred) & (st_obs > 0)
        if ok.sum() < 8:
            continue
        pct = (st_pred[ok] - st_obs[ok]) / st_obs[ok] * 100
        rows.append({
            "reservoir": name,
            "n": int(ok.sum()),
            "median_abs_storage_err_pct": round(float(np.median(np.abs(pct))), 1),
            "p90_abs_storage_err_pct": round(float(np.percentile(np.abs(pct), 90)), 1),
            "acreage_err_pct": round(float(np.median(np.abs(pct))) * abs(ELASTICITY), 1),
        })
    return pd.DataFrame(rows)


def rice_event() -> pd.DataFrame:
    px = pd.read_csv(RAW / "rice_price.csv") if (RAW / "rice_price.csv").exists() else None
    if px is None:
        raise SystemExit("no rice price file")
    d = pd.read_csv(OUT / "rice_surprise.csv")
    # daily bars cached by a one-off pull; yfinance 1.8.0 is broken in this venv
    raw = pd.read_csv(RAW / "rice_daily.csv", parse_dates=["date"])
    raw["ret"] = np.log(raw.close).diff()

    rows = []
    for _, r in d.iterrows():
        target = pd.Timestamp(year=int(r.year), month=6, day=30)
        after = raw[raw.date >= target]
        if after.empty:
            continue
        day = after.iloc[0]
        rows.append({"year": int(r.year), "report_day": day.date,
                     "ret": float(day.ret),
                     "rev_pct": float(r.rev_pct),
                     "mar_acres": float(r["YEAR - MAR ACREAGE"]),
                     "jun_acres": float(r["YEAR - JUN ACREAGE"])})
    ev = pd.DataFrame(rows).dropna(subset=["ret"])
    return ev


def main() -> int:
    prop = propagation()
    prop.to_csv(OUT / "chain_propagation.csv", index=False)
    print("satellite storage error, propagated to acreage\n")
    print(prop.to_string(index=False))
    if len(prop):
        med = float(prop.median_abs_storage_err_pct.median())
        print(f"\nmedian storage error {med:.1f}% -> acreage error "
              f"{med * abs(ELASTICITY):.1f}%")
        print("for context, the trend+price model explains R2 0.52, so a "
              f"{med * abs(ELASTICITY):.1f}% acreage error is small against the "
              "residual variation it is trying to explain")

    ev = rice_event()
    ev.to_csv(OUT / "rice_event.csv", index=False)
    print(f"\nJune acreage report reaction, rough rice futures: n={len(ev)}")
    if len(ev) >= 4:
        c = np.corrcoef(ev.rev_pct, ev.ret)[0, 1]
        print(f"  corr(revision %, report-day return) = {c:+.3f}")
        print(f"  mean |return| on report day = {ev.ret.abs().mean():.2%}")
        print("  n is tiny and rough rice is thin; this is descriptive, not a test")
        print(ev.assign(ret=lambda d: (d.ret * 100).round(2),
                        rev_pct=lambda d: (d.rev_pct * 100).round(1)).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
