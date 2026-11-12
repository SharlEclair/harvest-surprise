"""Daily futures prices for the event study.

Source is Yahoo via yfinance. This is a **continuous front-month series**, not
CME settlement data: it splices contracts on the vendor's own roll rule and the
roll dates are not documented. For a one-day event study around a 12:00 ET
release that is acceptable and is disclosed; it is not acceptable for settling a
published P&L, which is why the report says so.

Output: data/raw/prices_daily.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw"
TICKERS = {"ZC=F": "corn", "ZS=F": "soybean", "ZW=F": "wheat"}
START = "2009-01-01"


def main() -> int:
    import yfinance as yf

    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for ticker, name in TICKERS.items():
        df = yf.download(ticker, start=START, progress=False, auto_adjust=False)
        if df.empty:
            print(f"{ticker}: no data")
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df["ticker"] = ticker
        df["name"] = name
        frames.append(df)
        print(f"{ticker:6s} {len(df):5d} rows  {df.Date.min().date()} to {df.Date.max().date()}")

    if not frames:
        raise SystemExit("no price data")

    out = pd.concat(frames, ignore_index=True)
    out.columns = [str(c).lower().replace(" ", "_") for c in out.columns]
    out.to_csv(OUT / "prices_daily.csv", index=False)
    print(f"wrote {OUT / 'prices_daily.csv'} ({len(out)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
