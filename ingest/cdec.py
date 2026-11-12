"""California reservoir ground truth from CDEC.

The California Data Exchange Center publishes daily reservoir elevation and
storage for every major reservoir, free and without a key. That is what makes
this signal testable: a satellite water-area measurement can be checked against
a gauge that runs every day, unlike almost every other "track X from space" idea
in the comment thread.

Sensors used:
    6   reservoir elevation, feet
    15  reservoir storage, acre-feet

Output: data/raw/cdec_reservoirs.csv
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw"
BASE = "https://cdec.water.ca.gov/dynamicapp/req/JSONDataServlet"

STATIONS = {
    "SHA": "Shasta",
    "ORO": "Oroville",
    "DNP": "Don Pedro",
    "FOL": "Folsom",
    "NML": "New Melones",
    "HTH": "Hetch Hetchy",
    "EXC": "Exchequer",
    "SNL": "San Luis",
    "ISB": "Isabella",
    "PNF": "Pine Flat",
}
SENSORS = {"6": "elevation_ft", "15": "storage_af"}
START, END = "1990-01-01", "2025-12-31"   # 35 years: enough to test against rice acreage


def fetch(station: str, sensor: str) -> pd.DataFrame:
    params = {"Stations": station, "SensorNums": sensor, "dur_code": "D",
              "start": START, "end": END}
    for attempt in range(3):
        try:
            r = requests.get(BASE, params=params, timeout=120,
                             headers={"User-Agent": "Mozilla/5.0 research"})
            r.raise_for_status()
            rows = r.json()
            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d %H:%M",
                                        errors="coerce")
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            return df[["date", "value"]].dropna()
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                print(f"  {station}/{sensor} failed: {type(exc).__name__}: {exc}")
                return pd.DataFrame()
            time.sleep(2 * (attempt + 1))
    return pd.DataFrame()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for station in STATIONS:
        for sensor, name in SENSORS.items():
            df = fetch(station, sensor)
            if df.empty:
                print(f"{station} {name}: no data")
                continue
            df = df.rename(columns={"value": name})
            df["station"] = station
            frames.append(df)
            print(f"{station} {name}: {len(df)} rows "
                  f"{df.date.min().date()} to {df.date.max().date()}")
            time.sleep(0.3)

    if not frames:
        raise SystemExit("no CDEC data")
    wide = pd.concat(frames).groupby(["station", "date"]).first().reset_index()
    wide["reservoir"] = wide.station.map(STATIONS)
    wide.to_csv(OUT / "cdec_reservoirs.csv", index=False)
    print(f"\nwrote {OUT/'cdec_reservoirs.csv'} ({len(wide)} station-days)")
    print(wide.groupby("reservoir").agg(
        n=("date", "size"), elev_min=("elevation_ft", "min"),
        elev_max=("elevation_ft", "max")).round(1).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
