"""NASS Quick Stats ingest — corn, state level, 2000-2025.

Needs a NASS API key in the environment (or in .env):
    NASS_API_KEY=XXXXXXXX-XXXX-...

What it pulls, and why each one matters:

  yields       state corn grain yield, including the USDA's own in-season
               forecasts (reference_period_desc = "YEAR - AUG FORECAST", ...).
               That is the public expectation the model has to beat, and it is
               released with the WASDE on a known date. This is the substitute
               for the paywalled analyst consensus.
  area         planted and harvested acres. Needed because a low canopy can mean
               a bad crop *or* a small one (2019), and the two are different
               trades.
  condition    weekly good/excellent ratings by state. The incumbent public
               signal, and the cheapest baseline a satellite index must beat.

Usage:
    python ingest/nass.py              # writes to data/raw/
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw"
BASE = "https://quickstats.nass.usda.gov/api/api_GET/"
YEARS = (2000, 2025)

COMMON = {
    "commodity_desc": "CORN",
    "agg_level_desc": "STATE",
    "domain_desc": "TOTAL",
}

# NOTE (measured, 2026-11-11): Quick Stats does not honour the range operators
# the way the docs imply. `year__GE=2020&year__LE=2020` returns 31,120 condition
# rows where `year=2020` returns 4,835 — i.e. the range form silently returns
# more than the year it claims to bracket. So: never use __GE/__LE; ask for a
# year explicitly, or ask for everything and filter locally.


def load_key() -> str:
    key = os.environ.get("NASS_API_KEY", "").strip()
    if not key:
        env = ROOT / ".env"
        if env.exists():
            # utf-8-sig: a .env written by a Windows editor often starts with a
            # BOM, which would otherwise stay attached to the first key name and
            # make every startswith() below silently fail.
            for line in env.read_text(encoding="utf-8-sig").splitlines():
                if line.strip().startswith("NASS_API_KEY"):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        raise SystemExit("no NASS_API_KEY in environment or .env")
    return key


def fetch(key: str, **params) -> pd.DataFrame:
    p = {**COMMON, **params, "key": key, "format": "JSON"}
    for attempt in range(4):
        try:
            r = requests.get(BASE, params=p, timeout=180)
            r.raise_for_status()
            payload = r.json()
            if "data" not in payload:
                raise RuntimeError(f"unexpected payload: {str(payload)[:300]}")
            return pd.DataFrame(payload["data"])
        except requests.HTTPError as exc:
            # 4xx is a bad query, not a flaky server: retrying cannot help.
            if exc.response is not None and 400 <= exc.response.status_code < 500:
                raise SystemExit(
                    f"4xx from Quick Stats ({exc.response.status_code}): "
                    f"{exc.response.text[:400]}\nquery: {params}"
                ) from exc
            if attempt == 3:
                raise
            print(f"  retry {attempt + 1}/3 after {type(exc).__name__}: {exc}", flush=True)
            time.sleep(2 ** attempt)
        except Exception as exc:  # noqa: BLE001 - retry then fail loudly
            if attempt == 3:
                raise
            print(f"  retry {attempt + 1}/3 after {type(exc).__name__}: {exc}", flush=True)
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the columns that identify a series, coerce Value to float."""
    keep = [
        "state_alpha", "state_name", "year", "reference_period_desc",
        "week_ending", "short_desc", "statisticcat_desc", "unit_desc",
        "Value", "load_time",
    ]
    out = df[[c for c in keep if c in df.columns]].copy()
    out["value"] = pd.to_numeric(
        out["Value"].astype(str).str.replace(",", "", regex=False), errors="coerce"
    )
    out = out.drop(columns=["Value"])
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    return out.dropna(subset=["year"])


def fetch_years(key: str, start: int, end: int, **params) -> pd.DataFrame:
    """Quick Stats caps a response at 50,000 rows; condition ratings are weekly
    and blow through that, so pull them one year at a time.

    Uses `year=` exactly. Do not swap in year__GE/year__LE — see the note at
    the top of this file, they do not filter the way the docs suggest.
    """
    frames = []
    for year in range(start, end + 1):
        df = fetch(key, year=str(year), **params)
        if len(df):
            frames.append(df)
            print(f"    {year}: {len(df):5d} rows", flush=True)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    key = load_key()
    OUT.mkdir(parents=True, exist_ok=True)

    jobs = {
        # name: query params
        "yield": dict(
            statisticcat_desc="YIELD", util_practice_desc="GRAIN",
            class_desc="ALL CLASSES",
            prodn_practice_desc="ALL PRODUCTION PRACTICES",
        ),
        "area_harvested": dict(
            statisticcat_desc="AREA HARVESTED", util_practice_desc="GRAIN",
            class_desc="ALL CLASSES",
            prodn_practice_desc="ALL PRODUCTION PRACTICES",
        ),
        "area_planted": dict(
            # No util_practice_desc here: planted area is not split by use,
            # and supplying GRAIN makes Quick Stats return 400.
            statisticcat_desc="AREA PLANTED",
            class_desc="ALL CLASSES",
            prodn_practice_desc="ALL PRODUCTION PRACTICES",
        ),
        "condition": dict(statisticcat_desc="CONDITION", freq_desc="WEEKLY"),
    }

    for name, params in jobs.items():
        t0 = time.time()
        if name == "condition":
            # Weekly, ~4.5k rows a year: too big for one 50k-row response.
            raw = fetch_years(key, YEARS[0], YEARS[1], **params)
        else:
            raw = fetch(key, **params)
        df = tidy(raw)
        df.to_csv(OUT / f"nass_{name}.csv", index=False)
        print(f"{name:15s} {len(df):6d} rows  ({time.time() - t0:.0f}s)")

        if name == "yield":
            periods = (
                df[df.state_alpha.ne("OT")]
                .groupby("reference_period_desc").size()
                .sort_values(ascending=False)
            )
            for period, n in periods.items():
                print(f"    {period:22s} {n:5d}")
            states = sorted(df[df.state_alpha.ne("OT")].state_alpha.unique())
            print(f"    states: {len(states)}  years: {df.year.min()}-{df.year.max()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
