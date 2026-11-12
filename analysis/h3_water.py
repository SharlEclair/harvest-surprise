"""An H3 water-accessibility layer, and a test of whether exposure amplifies response.

Two pieces, matching the idiom of the transit-desert platform:

1. **The layer.** An H3 resolution-6 grid over California, each cell scored by
   linearly-decayed access to the ten major reservoirs:
       A_i(t) = sum_j max(0, 1 - d_ij / D_MAX) * storage_j(t)
   That is the same linear-decay accessibility used for transit stops, with
   reservoirs in place of stations and acre-feet in place of service frequency.
2. **The test.** Counties whose rice acreage is more exposed to reservoir storage
   should respond more strongly to a good or bad water year. That is an
   interaction, `exposure_c x log(storage_t)`, which is identified with county
   fixed effects because the interaction varies over time.

Output: data/processed/h3_water.parquet, county_water.csv, printed regression.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import h3
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
COUNTY_GEOJSON = ("https://raw.githubusercontent.com/plotly/datasets/master/"
                  "geojson-counties-fips.json")
D_MAX_KM = 300.0
RES_H3 = 6

# reservoir centres, from the bounding boxes used for the Sentinel-2 work
RESERVOIRS = {
    "Shasta": (40.75, -122.37), "Oroville": (39.56, -121.45),
    "Don Pedro": (37.71, -120.41), "Folsom": (38.71, -121.16),
    "New Melones": (37.95, -120.52), "Hetch Hetchy": (37.95, -119.79),
    "Exchequer": (37.58, -119.99), "San Luis": (37.06, -121.07),
    "Isabella": (35.67, -118.47), "Pine Flat": (36.83, -119.32),
}


def haversine(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def counties() -> pd.DataFrame:
    cache = RAW / "counties_ca.json"
    if not cache.exists():
        r = requests.get(COUNTY_GEOJSON, timeout=180,
                         headers={"User-Agent": "Mozilla/5.0 research"})
        r.raise_for_status()
        cache.write_text(r.text, encoding="utf-8")
    feats = json.loads(cache.read_text(encoding="utf-8"))["features"]
    rows = []
    for f in feats:
        fips = str(f.get("id") or "")
        if not fips.startswith("06"):
            continue
        pts = []

        def walk(c):
            if isinstance(c[0], (int, float)):
                pts.append(c)
            else:
                for x in c:
                    walk(x)

        walk(f["geometry"]["coordinates"])
        lats = [p[1] for p in pts]
        lons = [p[0] for p in pts]
        rows.append({
            "fips": fips,
            "county": f["properties"]["NAME"].upper(),
            "lat": (min(lats) + max(lats)) / 2,
            "lon": (min(lons) + max(lons)) / 2,
        })
    return pd.DataFrame(rows)


def h3_layer(ca: pd.DataFrame) -> pd.DataFrame:
    cells = set()
    for _, r in ca.iterrows():
        # sample the state on a coarse lattice and keep cells near a county centre
        for dlat in np.arange(-1.2, 1.21, 0.35):
            for dlon in np.arange(-1.2, 1.21, 0.35):
                cells.add(h3.latlng_to_cell(r.lat + dlat, r.lon + dlon, RES_H3))
    rows = []
    for c in cells:
        lat, lon = h3.cell_to_latlng(c)
        rec = {"h3": c, "lat": lat, "lon": lon}
        for name, (rlat, rlon) in RESERVOIRS.items():
            d = haversine(lat, lon, rlat, rlon)
            rec[f"w_{name}"] = max(0.0, 1 - d / D_MAX_KM)
        rows.append(rec)
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ca = counties()
    print(f"CA counties: {len(ca)}")
    layer = h3_layer(ca)
    print(f"H3 res-{RES_H3} cells: {len(layer)}")

    cdec = pd.read_csv(RAW / "cdec_reservoirs.csv", parse_dates=["date"])
    cdec = cdec[(cdec.storage_af > 1000) & (cdec.storage_af < 6e6)]
    cdec["year"] = cdec.date.dt.year
    cdec["doy"] = cdec.date.dt.day_of_year
    apr = cdec[cdec.doy.between(88, 98)]
    by_res = (apr.groupby(["year", "station"]).storage_af.first().unstack("station"))
    name_map = {"SHA": "Shasta", "ORO": "Oroville", "DNP": "Don Pedro", "FOL": "Folsom",
                "NML": "New Melones", "HTH": "Hetch Hetchy", "EXC": "Exchequer",
                "SNL": "San Luis", "ISB": "Isabella", "PNF": "Pine Flat"}
    by_res = by_res.rename(columns=name_map)
    by_res = by_res.dropna(axis=1, how="all").fillna(0.0)

    wcols = [c for c in layer.columns if c.startswith("w_")]
    # accessibility per cell per year
    acc = {}
    for year, row in by_res.iterrows():
        s = np.array([row.get(c[2:], 0.0) for c in wcols])
        acc[int(year)] = layer[wcols].to_numpy() @ s
    acc_df = pd.DataFrame(acc)
    acc_df.insert(0, "h3", layer.h3)
    # one table: geometry, decay weights, and the accessibility time series
    full = layer.merge(acc_df, on="h3", how="left")
    full.to_parquet(OUT / "h3_water.parquet", index=False)
    print(f"accessibility matrix: {acc_df.shape}")

    # county-level exposure weight: mean of its nearest cells
    rows = []
    for _, r in ca.iterrows():
        d = [haversine(r.lat, r.lon, la, lo) for la, lo in zip(layer.lat, layer.lon)]
        idx = int(np.argmin(d))
        rows.append({"county": r.county, "fips": r.fips,
                     "exposure": float(layer[wcols].iloc[idx].sum())})
    expo = pd.DataFrame(rows)
    print(f"county exposure range: {expo.exposure.min():.2f} to {expo.exposure.max():.2f}")

    rice = pd.read_csv(RAW / "nass_rice_county.csv")
    rice = rice[~rice.county_name.str.contains("OTHER", na=False)]
    rice = rice.rename(columns={"county_name": "county"})
    rice["year"] = pd.to_numeric(rice.year, errors="coerce")
    panel = rice.merge(expo, on="county", how="inner")
    panel = panel[panel.year.between(1990, 2025)]
    panel.to_csv(OUT / "county_water.csv", index=False)
    print(f"panel: {len(panel)} county-years, {panel.county.nunique()} counties, "
          f"{panel.year.min():.0f}-{panel.year.max():.0f}")

    # DuckDB demo query over the H3 layer
    con = duckdb.connect()
    con.execute("CREATE TABLE h3_water AS SELECT * FROM read_parquet(?)", [str(OUT / "h3_water.parquet")])
    top = con.execute("""
        SELECT h3, ROUND("2025", 0) AS af_2025, ROUND("2015", 0) AS af_2015
        FROM h3_water ORDER BY "2025" DESC LIMIT 5
    """).df()
    print("\ntop H3 cells by 2025 water access (DuckDB):")
    print(top.to_string(index=False))

    # interaction test
    d = panel.dropna(subset=["acres", "exposure"]).copy()
    d = d[d.acres > 500]
    d["ly"] = np.log(d.acres)
    S = by_res.sum(axis=1)
    d["ls"] = np.log(d.year.map(S))
    d["inter"] = d.exposure * d.ls
    dummies = pd.get_dummies(d.county, drop_first=True).astype(float)
    X = np.column_stack([np.ones(len(d)), dummies.to_numpy(), d.ls.to_numpy(),
                         d.inter.to_numpy(), (d.year - d.year.mean()).to_numpy()])
    y = d.ly.to_numpy()
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    dof = len(y) - X.shape[1]
    s2 = resid @ resid / dof
    se = np.sqrt(np.diag(s2 * np.linalg.pinv(X.T @ X)))
    k = 1 + dummies.shape[1]
    b, s = coef[k + 1], se[k + 1]
    # A null is only informative if the design could have seen something. At 80%
    # power and two-sided 5%, the smallest detectable coefficient is about 2.8 se.
    mde = 2.80 * s
    print(f"\npanel regression n={len(d)} counties={d.county.nunique()}")
    print(f"  log storage            {coef[k]:+.3f} (se {se[k]:.3f}, t {coef[k]/se[k]:+.2f})")
    print(f"  exposure x log storage {coef[k+1]:+.3f} (se {se[k+1]:.3f}, "
          f"t {coef[k+1]/se[k+1]:+.2f})")
    print(f"    95% CI [{b - 1.96 * s:+.3f}, {b + 1.96 * s:+.3f}]; "
          f"minimum detectable |beta| at 80% power = {mde:.3f}")
    print(f"    the null rules out exposure effects larger than {mde:.2f}, "
          f"not smaller ones")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
