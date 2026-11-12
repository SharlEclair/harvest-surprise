"""WASDE history ingest.

USDA publishes the WASDE tables as data files, one per release:

    2010-04 .. 2020-12   https://www.usda.gov/sites/default/files/documents/oce-wasde-report-data-2010-04-to-2015-12.zip
                         https://www.usda.gov/sites/default/files/documents/oce-wasde-report-data-2016-01-to-2020-12.zip
    2021-01 .. now       https://www.usda.gov/sites/default/files/documents/oce-wasde-report-data-YYYY-MM.csv

Each row carries Commodity, Region, Attribute, MarketYear, Value, Unit and — the
point-in-time bit — ReleaseDate and ReleaseTime. That is what makes a leak-free
event study possible without buying a vendor history.

Output: data/raw/wasde_corn.csv, one row per release x market year x attribute.
"""
from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw"
BASE = "https://www.usda.gov/sites/default/files/documents/"
ZIPS = ["oce-wasde-report-data-2010-04-to-2015-12.zip",
        "oce-wasde-report-data-2016-01-to-2020-12.zip"]
FIRST_CSV = (2021, 1)
LAST_CSV = (2026, 12)
UA = {"User-Agent": "Mozilla/5.0 (research; harvest-surprise)"}


def get(url: str, tries: int = 3) -> bytes | None:
    for attempt in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=180)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except Exception as exc:  # noqa: BLE001
            if attempt == tries - 1:
                print(f"  gave up on {url}: {type(exc).__name__}: {exc}", flush=True)
                return None
            time.sleep(2 ** attempt)
    return None


def read_csv_bytes(blob: bytes) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(io.BytesIO(blob), low_memory=False)
    except Exception:  # noqa: BLE001 - some archives are latin-1
        try:
            df = pd.read_csv(io.BytesIO(blob), encoding="latin-1", low_memory=False)
        except Exception:  # noqa: BLE001
            return None
    if "Commodity" not in df.columns:
        return None
    return df


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []

    for name in ZIPS:
        blob = get(BASE + name)
        if blob is None:
            print(f"missing archive {name}", flush=True)
            continue
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
            print(f"{name}: {len(members)} csv members", flush=True)
            for member in members:
                df = read_csv_bytes(zf.read(member))
                if df is not None:
                    frames.append(df)

    for year in range(FIRST_CSV[0], LAST_CSV[0] + 1):
        for month in range(1, 13):
            if (year, month) < FIRST_CSV:
                continue
            url = f"{BASE}oce-wasde-report-data-{year}-{month:02d}.csv"
            blob = get(url)
            if blob is None:
                continue
            df = read_csv_bytes(blob)
            if df is not None:
                frames.append(df)
                print(f"  {year}-{month:02d}: {len(df)} rows", flush=True)

    if not frames:
        raise SystemExit("no WASDE data retrieved")

    all_rows = pd.concat(frames, ignore_index=True)
    all_rows = all_rows.drop_duplicates()
    print(f"total rows: {len(all_rows)}")

    corn = all_rows[
        (all_rows["Commodity"].astype(str).str.strip().str.lower() == "corn")
        & (all_rows["Region"].astype(str).str.strip().str.lower() == "united states")
    ].copy()
    corn["ReleaseDate"] = pd.to_datetime(corn["ReleaseDate"], errors="coerce")
    corn["Value"] = pd.to_numeric(corn["Value"], errors="coerce")
    corn = corn.dropna(subset=["ReleaseDate", "Value"])
    corn = corn.sort_values(["ReleaseDate", "MarketYear", "Attribute"])
    corn.to_csv(OUT / "wasde_corn.csv", index=False)

    print(f"corn US rows: {len(corn)}  releases: {corn.ReleaseDate.nunique()}  "
          f"{corn.ReleaseDate.min().date()} to {corn.ReleaseDate.max().date()}")
    y = corn[corn.Attribute.str.contains("Yield", case=False, na=False)]
    print(f"yield rows: {len(y)}  market years: {sorted(y.MarketYear.astype(str).unique())[-4:]}")
    print(y.sort_values("ReleaseDate").tail(6)[
        ["ReleaseDate", "Attribute", "MarketYear", "Value", "Unit"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
