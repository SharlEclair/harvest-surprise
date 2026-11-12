"""CAISO day-ahead prices, free and keyless - working version.

Three findings from the attempt log, all measured:

* `queryname=PRC_LMP` with `market_run_id=DAM` works, but the request window must
  be **28 days or less**. A 31-day window returns a 1 KB error document that still
  carries HTTP 200, so the failure is silent unless you check for `ERR_DESC`.
* OASIS rate-limits at roughly one request per second; bursts return 429.
* The response is a ZIP containing an OASISReport XML, not a CSV. The useful rows
  are `DATA_ITEM` elements with `RESOURCE_NAME`, `INTERVAL_START_GMT` and `VALUE`.

Output: data/raw/caiso_dam.csv (hourly, both hubs, 2018-2025).
"""
from __future__ import annotations

import io
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw"
URL = "http://oasis.caiso.com/oasisapi/SingleZip"
HUBS = {"TH_NP15_GEN-APND": "NP15", "TH_SP15_GEN-APND": "SP15"}
START, END = pd.Timestamp("2018-01-01"), pd.Timestamp("2025-12-31")
WINDOW_DAYS = 28


def tag(e: ET.Element) -> str:
    return e.tag.split("}")[-1]


def chunks():
    start = START
    while start <= END:
        end = min(start + pd.Timedelta(days=WINDOW_DAYS - 1), END)
        yield start, end
        start = end + pd.Timedelta(days=1)


def parse(blob: bytes, hub: str) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        member = [n for n in zf.namelist() if n.lower().endswith(".xml")][0]
        data = zf.read(member)
    root = ET.fromstring(data)
    if any(tag(e) == "ERR_DESC" for e in root.iter()):
        desc = next((e.text for e in root.iter() if tag(e) == "ERR_DESC"), "unknown")
        raise RuntimeError(f"OASIS error: {desc}")
    rows = []
    for item in root.iter():
        if tag(item) != "DATA_ITEM":
            continue
        fields = {tag(c): (c.text or "").strip() for c in item}
        if fields.get("DATA_ITEM") != "LMP_PRC":
            continue
        rows.append({
            "hub": hub,
            "timestamp": fields.get("INTERVAL_START_GMT"),
            "lmp": fields.get("VALUE"),
        })
    return rows


def fetch(start: pd.Timestamp, end: pd.Timestamp, node: str, hub: str):
    params = {
        "queryname": "PRC_LMP",
        "startdatetime": start.strftime("%Y%m%dT00:00-0000"),
        "enddatetime": end.strftime("%Y%m%dT23:59-0000"),
        "market_run_id": "DAM",
        "version": "1",
        "node": node,
    }
    for attempt in range(4):
        try:
            r = requests.get(URL, params=params, timeout=120,
                             headers={"User-Agent": "Mozilla/5.0 research"})
            if r.status_code == 429:
                raise RuntimeError("429")
            r.raise_for_status()
            return parse(r.content, hub)
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                print(f"  {hub} {start:%Y-%m-%d}: {type(exc).__name__}: {exc}")
                return []
            wait = 30 if "429" in str(exc) else 3 * (attempt + 1)
            time.sleep(wait)
    return []


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    allrows, t0 = [], time.time()
    plan = [(s, e, node, hub) for s, e in chunks() for node, hub in HUBS.items()]
    for i, (s, e, node, hub) in enumerate(plan):
        rows = fetch(s, e, node, hub)
        allrows += rows
        if i % 10 == 0:
            print(f"{i}/{len(plan)} windows, {len(allrows)} rows "
                  f"({time.time()-t0:.0f}s)", flush=True)
        time.sleep(1.2)

    if not allrows:
        raise SystemExit("no CAISO data")
    df = pd.DataFrame(allrows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["lmp"] = pd.to_numeric(df["lmp"], errors="coerce")
    df = df.dropna(subset=["timestamp", "lmp"]).drop_duplicates(["hub", "timestamp"])
    df = df.sort_values(["hub", "timestamp"])
    df.to_csv(OUT / "caiso_dam.csv", index=False)

    local = df.timestamp.dt.tz_convert("America/Los_Angeles")
    daily = (df.assign(date=local.dt.normalize(), hour=local.dt.hour)
               .groupby(["hub", "date"]).agg(lmp_mean=("lmp", "mean"),
                                             lmp_peak=("lmp", lambda s: s.max())).reset_index())
    daily.to_csv(OUT / "caiso_daily.csv", index=False)
    print(f"\nwrote {OUT/'caiso_dam.csv'} ({len(df)} hourly rows) "
          f"{df.timestamp.min().date()} to {df.timestamp.max().date()}")
    print(daily.groupby("hub").agg(days=("date", "size"),
                                   mean=("lmp_mean", "mean"),
                                   p95=("lmp_peak", lambda s: s.quantile(0.95))).round(1).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
