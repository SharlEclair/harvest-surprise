"""Score the SAR series against EIA stocks, with the same held-out discipline.

Same three metrics as the optical work: levels, within-year levels, and 4-week
changes, each split into 2018-21 and 2022-25. Ascending and descending orbits see
the tanks from different angles, so they are also scored separately - a real
geometric signal should be consistent across both.

Output: data/processed/cushing_sar_metrics.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"


def within_year_r(x: np.ndarray, y: np.ndarray, years: np.ndarray) -> float:
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10:
        return np.nan
    xd = x[ok] - pd.Series(x[ok]).groupby(years[ok]).transform("mean").to_numpy()
    yd = y[ok] - pd.Series(y[ok]).groupby(years[ok]).transform("mean").to_numpy()
    if np.std(xd) == 0 or np.std(yd) == 0:
        return np.nan
    return float(np.corrcoef(xd, yd)[0, 1])


def changes(dates: pd.Series, x: np.ndarray, y: np.ndarray, gap=21, tol=45):
    order = np.argsort(dates.to_numpy())
    d = dates.to_numpy()[order]
    xs, ys = x[order], y[order]
    dx, dy, yr = [], [], []
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
        yr.append(pd.Timestamp(d[i]).year)
    return np.array(dx), np.array(dy), np.array(yr)


def main() -> int:
    f = OUT / "cushing_sar.csv"
    if not f.exists():
        raise SystemExit("no SAR series yet")
    df = pd.read_csv(f, parse_dates=["date"]).sort_values("date")
    eia = pd.read_csv(RAW / "eia_cushing_weekly.csv", parse_dates=["date"]).sort_values("date")
    df["stocks"] = np.interp(df.date.astype("int64"), eia.date.astype("int64"), eia.stocks_kbbl)
    years = df.date.dt.year.to_numpy()
    print(f"SAR scenes {len(df)}, {df.date.min().date()} to {df.date.max().date()}")

    rows = []
    for name, sub in [("all", df),
                      ("ascending", df[df.orbit == "ascending"]),
                      ("descending", df[df.orbit == "descending"])]:
        if len(sub) < 30:
            continue
        s = sub.sort_values("date")
        x, y, yr = s.ratio_db.to_numpy(float), s.stocks.to_numpy(float), s.date.dt.year.to_numpy()
        r_lvl = float(np.corrcoef(x, y)[0, 1])
        tr, te = yr <= 2021, yr >= 2022
        dx, dy, dyr = changes(s.date, x, y)
        rows.append({
            "subset": name, "n": len(s),
            "r_levels": round(r_lvl, 3),
            "r_within_train": round(within_year_r(x[tr], y[tr], yr[tr]), 3),
            "r_within_test": round(within_year_r(x[te], y[te], yr[te]), 3),
            "r_change_train": round(within_year_r(dx[dyr <= 2021], dy[dyr <= 2021],
                                                  dyr[dyr <= 2021]), 3) if len(dx) > 30 else np.nan,
            "r_change_test": round(within_year_r(dx[dyr >= 2022], dy[dyr >= 2022],
                                                 dyr[dyr >= 2022]), 3) if len(dx) > 30 else np.nan,
            "n_changes": len(dx),
        })
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "cushing_sar_metrics.csv", index=False)
    print("\n" + out.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
