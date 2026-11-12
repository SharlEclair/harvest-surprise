"""Daily weather for the corn states, from NASA POWER.

POWER is free, keyless and covers 1981->present on a 0.5 x 0.625 degree grid.
Three points are sampled per state (centre plus two offsets) so a state's number
is not a single grid cell, and the daily series is reduced to season aggregates
that have physical meaning for corn: growing degree days, extreme degree days
(heat above 29 C), and May-July precipitation.

The reduction is deliberately explicit rather than "whatever a model likes":
corn yield responds to heat during silking and to water through grain fill, so
the windows are fixed by the crop calendar, not fitted.

Output: data/raw/weather_state_year.csv
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CACHE = RAW / "power_cache"
# Census gazetteer URLs 404 as of 2026-11-11, so state geometry comes from a
# public GeoJSON and the sampler uses each state's bounding-box centre. That is
# accurate enough for 0.5 degree weather: the bbox centre lands in the state,
# and three offset points per state cover the spread.
STATES_GEOJSON = ("https://raw.githubusercontent.com/PublicaMundi/MappingAPI/"
                  "master/data/geojson/us-states.json")
POWER = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = ["T2M_MAX", "T2M_MIN", "PRECTOTCORR"]

NAME_TO_USPS = {
    "Iowa": "IA", "Illinois": "IL", "Nebraska": "NE", "Minnesota": "MN",
    "Indiana": "IN", "Kansas": "KS", "Missouri": "MO", "North Dakota": "ND",
    "South Dakota": "SD", "Wisconsin": "WI", "Ohio": "OH", "Michigan": "MI",
    "Texas": "TX", "Colorado": "CO", "Kentucky": "KY", "Tennessee": "TN",
    "Arkansas": "AR", "Pennsylvania": "PA",
}

# Main corn states; a state not in this list is simply not modelled.
STATES = list(NAME_TO_USPS.values())
# Offsets (deg lat, deg lon) from the state's centre.
OFFSETS = [(0.0, 0.0), (0.9, 0.0), (-0.9, 0.9)]


def _ring_points(geom: dict):
    def walk(coords):
        if isinstance(coords[0], (int, float)):
            yield coords
        else:
            for c in coords:
                yield from walk(c)

    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    else:
        polys = geom["coordinates"]
    for poly in polys:
        for ring in poly:
            yield from (p for p in ring if len(p) >= 2)


def centroids() -> dict[str, tuple[float, float]]:
    """Bounding-box centre of each state, from the GeoJSON."""
    cache = CACHE / "state_bbox.json"
    CACHE.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        return {k: tuple(v) for k, v in json.loads(cache.read_text()).items()}
    r = requests.get(STATES_GEOJSON, timeout=120,
                     headers={"User-Agent": "Mozilla/5.0 research"})
    r.raise_for_status()
    out: dict[str, tuple[float, float]] = {}
    for feat in r.json()["features"]:
        usps = NAME_TO_USPS.get(feat["properties"].get("name", "").strip())
        if not usps:
            continue
        pts = list(_ring_points(feat["geometry"]))
        lons = [p[0] for p in pts]
        lats = [p[1] for p in pts]
        out[usps] = (round((min(lats) + max(lats)) / 2, 3),
                     round((min(lons) + max(lons)) / 2, 3))
    cache.write_text(json.dumps(out))
    return out


def fetch_point(lat: float, lon: float, start: str, end: str) -> pd.DataFrame | None:
    params = {
        "parameters": ",".join(PARAMS), "community": "AG",
        "latitude": round(lat, 3), "longitude": round(lon, 3),
        "start": start, "end": end, "format": "JSON",
    }
    for attempt in range(3):
        try:
            r = requests.get(POWER, params=params, timeout=120,
                             headers={"User-Agent": "Mozilla/5.0 research"})
            r.raise_for_status()
            payload = r.json()
            p = payload["properties"]["parameter"]
            df = pd.DataFrame(p)
            df.index = pd.to_datetime(df.index, format="%Y%m%d")
            df = df.replace(-999.0, np.nan).astype(float)
            return df
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                print(f"  failed {lat},{lon}: {type(exc).__name__}: {exc}", flush=True)
                return None
            time.sleep(3 * (attempt + 1))
    return None


def season_stats(daily: pd.DataFrame, year: int) -> dict:
    """Fixed crop-calendar windows, not fitted ones.

    The `asof_` columns stop at 31 July, which is the information set for a
    prediction made on 1 August. The full-season columns are kept for later
    use but must not be used in an August model.
    """
    d = daily[daily.index.year == year]
    if d.empty:
        return {}
    gdd = ((d.T2M_MAX.clip(upper=30) + d.T2M_MIN.clip(upper=30)) / 2 - 10).clip(lower=0)
    edd = (d.T2M_MAX - 29).clip(lower=0)          # extreme degree days
    may_jul = d.loc[f"{year}-05-01":f"{year}-07-31"]
    jul = d.loc[f"{year}-07-01":f"{year}-07-31"]
    jul_aug = d.loc[f"{year}-07-01":f"{year}-08-31"]
    return {
        # --- available on 1 August -----------------------------------------
        "asof_gdd": float(gdd.loc[f"{year}-04-15":f"{year}-07-31"].sum()),
        "asof_edd": float(edd.loc[f"{year}-06-15":f"{year}-07-31"].sum()),
        "asof_heat_days": float((jul.T2M_MAX > 32).sum()),
        "asof_precip": float(d.loc[f"{year}-04-15":f"{year}-07-31"].PRECTOTCORR.sum()),
        "asof_precip_jul": float(jul.PRECTOTCORR.sum()),
        "asof_tmax_jul": float(jul.T2M_MAX.mean()),
        # --- full season, for reference only --------------------------------
        "gdd_may_jul": float(gdd.loc[f"{year}-05-01":f"{year}-07-31"].sum()),
        "gdd_season": float(gdd.loc[f"{year}-04-15":f"{year}-09-30"].sum()),
        "edd_jul_aug": float(edd.loc[f"{year}-07-01":f"{year}-08-31"].sum()),
        "heat_days_32_jul_aug": float((jul_aug.T2M_MAX > 32).sum()),
        "precip_may_jul": float(may_jul.PRECTOTCORR.sum()),
        "precip_jul_aug": float(jul_aug.PRECTOTCORR.sum()),
        "precip_season": float(d.loc[f"{year}-04-15":f"{year}-09-30"].PRECTOTCORR.sum()),
        "tmax_jul_mean": float(jul_aug.T2M_MAX.mean()),
    }


def main() -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    cents = centroids()
    print(f"centroids for {len(cents)} states")
    missing = [s for s in STATES if s not in cents]
    if missing:
        print(f"  no centroid: {missing}")

    rows = []
    for state, (lat, lon) in cents.items():
        points = []
        for dlat, dlon in OFFSETS:
            cache = CACHE / f"{state}_{dlat:+.1f}_{dlon:+.1f}.csv"
            if cache.exists():
                daily = pd.read_csv(cache, index_col=0, parse_dates=True)
            else:
                daily = fetch_point(lat + dlat, lon + dlon, "20000101", "20251231")
                if daily is None:
                    continue
                daily.to_csv(cache)
                time.sleep(0.5)
            points.append(daily)
        if not points:
            continue
        for year in range(2000, 2026):
            stats = [season_stats(p, year) for p in points]
            stats = [s for s in stats if s]
            if not stats:
                continue
            rec = {"state_alpha": state, "year": year,
                   "n_points": len(stats)}
            for k in stats[0]:
                rec[k] = float(np.mean([s[k] for s in stats]))
            rows.append(rec)
        print(f"  {state}: {len(points)} points, "
              f"{len([r for r in rows if r['state_alpha'] == state])} state-years",
              flush=True)

    if not rows:
        raise SystemExit("no weather retrieved")
    df = pd.DataFrame(rows).sort_values(["state_alpha", "year"])
    df.to_csv(RAW / "weather_state_year.csv", index=False)
    print(f"wrote {RAW/'weather_state_year.csv'} ({len(df)} rows)")
    print(df.describe().T[["mean", "min", "max"]].round(1).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

