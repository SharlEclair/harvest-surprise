"""End to end: pixels -> storage -> planted acreage, no gauge in the loop.

The chain tested here:

    Sentinel-2 water area -> rating curve -> storage -> acreage model -> acres

compared against the same model fed the CDEC gauge. If the satellite path is a
real substitute, the difference in acreage error should be small.

Two honest caveats, stated rather than buried:

* The rating curve per reservoir is fitted on all of its scenes, including the
  ones used to predict. It is a property of the reservoir's bathymetry, not of the
  year, but it is not out-of-sample.
* Only three reservoirs are measured by satellite. Their storage is scaled to the
  ten-reservoir total by a ratio estimated from the gauges, so the test depends on
  that ratio being stable.

Output: data/processed/end_to_end.csv, end_to_end.png
"""
from __future__ import annotations

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


def gauge_totals() -> pd.DataFrame:
    c = pd.read_csv(RAW / "cdec_reservoirs.csv", parse_dates=["date"])
    c = c[(c.storage_af > 1000) & (c.storage_af < 6e6)]
    counts = c.groupby("station").storage_af.count()
    c = c[c.station.isin(counts[counts > 8000].index)]
    c["doy"] = c.date.dt.day_of_year
    c["year"] = c.date.dt.year
    apr = c[c.doy.between(88, 98)]
    near3 = apr[apr.station.isin(["SHA", "ORO", "DNP"])]
    tot = apr.groupby(["year", "date"]).agg(total10=("storage_af", "sum")).reset_index()
    three = near3.groupby(["year", "date"]).agg(total3=("storage_af", "sum")).reset_index()
    out = tot.merge(three, on=["year", "date"], how="left")
    out = (out.sort_values("date").groupby("year")
              .agg(total10=("total10", "first"), total3=("total3", "first")).reset_index())
    return out.dropna().query("year >= 1990")


def satellite_storage() -> pd.DataFrame:
    """One satellite-derived storage estimate per reservoir-year, near 1 April."""
    m = pd.read_csv(OUT / "reservoir_v2_matched.csv", parse_dates=["date"])
    m["year"] = m.date.dt.year
    m["doy"] = m.date.dt.day_of_year
    m["dist"] = (m.doy - 91).abs()
    rows = []
    for (name, year), g in m.groupby(["reservoir", "year"]):
        g = g.sort_values("area_m2").reset_index(drop=True)
        iso = IsotonicRegression(out_of_bounds="clip").fit(g.area_m2, g.elevation_ft)
        curv = g.sort_values("elevation_ft")
        pick = g.loc[g.dist.idxmin()]
        if pick.dist > 30:
            continue
        elev = float(iso.predict([pick.area_m2])[0])
        stor = float(np.interp(elev, curv.elevation_ft, curv.storage_af,
                               left=np.nan, right=np.nan))
        rows.append({"reservoir": name, "year": int(year),
                     "scene_date": pick.date, "days_from_apr1": int(pick.dist),
                     "elev_pred_ft": elev, "storage_pred_af": stor})
    return pd.DataFrame(rows)


def main() -> int:
    g = gauge_totals()
    ratio = float((g.total3 / g.total10).mean())
    print(f"3-of-10 reservoir ratio: {ratio:.3f} (sd {(g.total3/g.total10).std():.3f})")

    sat = satellite_storage()
    if sat.empty:
        raise SystemExit("no satellite estimates near 1 April")
    sat_year = (sat.groupby("year").agg(sat3=("storage_pred_af", "sum"),
                                        n=("reservoir", "size")).reset_index())
    sat_year["sat10"] = sat_year.sat3 / ratio
    print(f"satellite years: {sat_year.year.tolist()}, "
          f"reservoirs per year: {sat_year.n.unique().tolist()}")

    panel = pd.read_csv(OUT / "water_rice.csv")
    df = panel.merge(g[["year", "total10"]], on="year", how="inner")
    df = df.merge(sat_year[["year", "sat10"]], on="year", how="left")

    # fit the acreage model on the gauge, 1990-2020, then predict 2021-2025 both ways
    train = df[(df.year <= 2020)]
    x = np.log(train.total10.to_numpy(float))
    y = np.log(train.acres.to_numpy(float))
    t = train.year.to_numpy(float) - 2005.0
    X = np.column_stack([np.ones(len(train)), x, t])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    print(f"model fitted on 1990-2020: elasticity {coef[1]:+.3f}, "
          f"trend {coef[2]:+.4f}/yr")

    test = df[(df.year >= 2021)].dropna(subset=["sat10"]).copy()
    if test.empty:
        raise SystemExit("no overlap between satellite years and acreage")

    def predict(storage):
        Xt = np.column_stack([np.ones(len(test)), np.log(storage),
                              test.year.to_numpy(float) - 2005.0])
        return np.exp(Xt @ coef)

    test["pred_gauge"] = predict(test.total10.to_numpy(float))
    test["pred_sat"] = predict(test.sat10.to_numpy(float))
    test["err_gauge_pct"] = (test.pred_gauge / test.acres - 1) * 100
    test["err_sat_pct"] = (test.pred_sat / test.acres - 1) * 100
    test.to_csv(OUT / "end_to_end.csv", index=False)

    print("\nyear  actual    gauge    sat     err_gauge%  err_sat%")
    for _, r in test.iterrows():
        print(f"{int(r.year)}  {r.acres:7.0f} {r.pred_gauge:7.0f} {r.pred_sat:7.0f}  "
              f"{r.err_gauge_pct:+9.1f}  {r.err_sat_pct:+8.1f}")
    print(f"\nMAPE gauge {test.err_gauge_pct.abs().mean():.1f}%, "
          f"satellite {test.err_sat_pct.abs().mean():.1f}%")

    fig, ax = plt.subplots(figsize=(7.2, 4), dpi=150)
    ax.plot(test.year, test.acres / 1000, "o-", color="#111", label="actual")
    ax.plot(test.year, test.pred_gauge / 1000, "s--", color="#c9822b", label="gauge-fed")
    ax.plot(test.year, test.pred_sat / 1000, "^--", color="#2f7d6d", label="satellite-fed")
    ax.set_ylabel("rice acres (thousands)")
    ax.set_title("Pixels to acreage: satellite vs gauge in the loop", loc="left", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "end_to_end.png")
    print(f"wrote {OUT/'end_to_end.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
