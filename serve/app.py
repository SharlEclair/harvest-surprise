"""Read-only API over the H3 water layer and the water-rice panel.

Small on purpose: four endpoints, no database, no auth, data loaded once at
startup. The point is that the numbers in the report can be queried rather than
just read, which is the difference between a notebook and a product.

Run:  uvicorn serve.app:app --port 8000
Then: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"

app = FastAPI(title="Harvest Surprise", version="1.0",
              description="H3 water accessibility and the water-rice panel")


@lru_cache(maxsize=1)
def layer() -> pd.DataFrame:
    f = OUT / "h3_water.parquet"
    if not f.exists():
        raise FileNotFoundError("h3_water.parquet not built; run python hsp.py analyse")
    return pd.read_parquet(f)


@lru_cache(maxsize=1)
def county_panel() -> pd.DataFrame:
    return pd.read_csv(OUT / "county_water.csv")


@lru_cache(maxsize=1)
def validation() -> pd.DataFrame:
    return pd.read_csv(OUT / "reservoir_v2_validation.csv")


def years() -> list[int]:
    return sorted(int(c) for c in layer().columns if c.isdigit())


@app.get("/health")
def health() -> dict:
    try:
        df = layer()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok", "cells": int(len(df)), "years": years()}


@app.get("/water/{year}")
def water(year: int, limit: int = Query(10, ge=1, le=200)) -> dict:
    df = layer()
    col = str(year)
    if col not in df:
        raise HTTPException(status_code=404, detail=f"no data for {year}")
    top = df.nlargest(limit, col)[["h3", "lat", "lon", col]]
    # name=None: a column called "2025" is not a valid identifier for itertuples
    cells = [
        {"h3": h3, "lat": round(float(lat), 4), "lon": round(float(lon), 4),
         "accessibility_af": round(float(v), 0)}
        for h3, lat, lon, v in top.itertuples(index=False, name=None)
    ]
    return {"year": year, "unit": "acre-feet of linearly-decayed reservoir access",
            "cells": cells}


@app.get("/county/{name}")
def county(name: str) -> dict:
    p = county_panel()
    d = p[p.county.str.upper() == name.upper()]
    if d.empty:
        raise HTTPException(status_code=404, detail=f"county {name!r} not in the panel")
    d = d.sort_values("year")
    return {
        "county": d.county.iloc[0],
        "exposure": round(float(d.exposure.iloc[0]), 3),
        "years": [
            {"year": int(r.year), "acres": float(r.acres)}
            for r in d[["year", "acres"]].itertuples(index=False)
        ],
    }


@app.get("/reservoirs")
def reservoirs() -> dict:
    v = validation()
    return {
        "validated": [
            {"reservoir": r.reservoir, "spearman": float(r.spearman),
             "rmse_ft": float(r.rmse_isotonic_ft),
             "baseline_ft": float(r.baseline_rmse_ft),
             "scenes": int(r.n_scored)}
            for r in v.itertuples(index=False)
        ]
    }
