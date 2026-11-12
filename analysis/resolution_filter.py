"""Physics filter: which of the proposed signals can free imagery actually see?

Most of the 54 "you could track X" comments ignore the only question that matters
first: is X big enough, and does it change often enough, for a free sensor to
resolve it? This turns that into arithmetic instead of vibes.

    fill        = object_area / pixel_area
    snr_detect  = contrast * fill / scene_noise
    snr_agg     = snr_detect * sqrt(objects_per_target)
    countable   = fill >= 0.5 and snr_detect >= 5

`contrast` is the fractional change in reflectance when the object is present.
`scene_noise` is the coefficient of variation of a *single pixel*, which is
dominated by surface heterogeneity rather than sensor noise - about 5% over mixed
urban scenes, about 2% over uniform ones (open water, bare fields, a single tank
roof). Using 2% everywhere is what makes naive analyses conclude that a single
car is detectable; it is not, and the reason is the scene, not the sensor.

The distinction between detecting a thing and counting things is the whole
practical problem: counting needs the object to be about a pixel across, which is
why tank roofs are countable at 30 m and cars are not at 10 m.

Output: research/resolution_grid.csv and two printed tables.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "research"

SENSORS = {          # name: (gsd m, revisit days)
    "Planet 3m": (3.0, 1),
    "Sentinel-2 10m": (10.0, 5),
    "Sentinel-1 10m": (10.0, 6),
    "Landsat 30m": (30.0, 16),
    "MODIS 250m": (250.0, 1),
    "VIIRS 375m": (375.0, 1),
}

# name: (object area m2, contrast, objects per target, timescale days, uniform_bg)
SIGNALS = {
    "car in a parking space": (12.0, 0.35, 400, 1, False),
    "truck trailer parked": (30.0, 0.35, 80, 1, False),
    "shipping container": (29.0, 0.25, 2000, 7, False),
    "new single-family house": (150.0, 0.40, 50, 30, False),
    "oil tank floating roof": (2900.0, 0.20, 40, 30, True),
    "product tanker at berth": (12000.0, 0.25, 1, 1, True),
    "parking lot aggregate": (20000.0, 0.35, 1, 1, False),
    "construction site active": (20000.0, 0.30, 1, 30, False),
    "open pit mine bench": (200000.0, 0.30, 1, 30, True),
    "reservoir surface (per cell)": (1e6, 0.50, 1, 7, True),
    "corn field canopy": (400000.0, 0.30, 1, 16, True),
    "coal / ore stockpile": (50000.0, 0.35, 1, 30, True),
    "gas flare": (200.0, 3.0, 1, 1, True),
    "night-time light (town)": (1e6, 5.0, 1, 1, True),
}


def build() -> pd.DataFrame:
    rows = []
    for name, (area, contrast, n_obj, timescale, uniform) in SIGNALS.items():
        noise = 0.02 if uniform else 0.05
        for sensor, (gsd, revisit) in SENSORS.items():
            if name.startswith("night-time") and sensor not in ("VIIRS 375m",):
                rows.append({"signal": name, "sensor": sensor, "gsd_m": gsd,
                             "fill": 0.0, "snr_detect": 0.0, "snr_agg": 0.0,
                             "countable": False, "revisit_days": revisit,
                             "timescale_days": timescale, "revisit_ok": False,
                             "verdict": "n/a - optical daylight sensor"})
                continue
            fill = min(area / (gsd * gsd), 1.0)
            snr = contrast * fill / noise
            snr_agg = snr * n_obj ** 0.5
            countable = fill >= 0.5 and snr >= 5
            rows.append({
                "signal": name, "sensor": sensor, "gsd_m": gsd,
                "fill": round(fill, 4), "snr_detect": round(snr, 1),
                "snr_agg": round(snr_agg, 1), "countable": countable,
                "revisit_days": revisit, "timescale_days": timescale,
                "revisit_ok": revisit <= timescale,
                "verdict": ("countable" if countable
                            else "aggregate only" if snr_agg >= 2
                            else "not measurable"),
            })
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    df = build()
    df.to_csv(OUT / "resolution_grid.csv", index=False)

    free = df[df.sensor != "Planet 3m"]
    order = ["countable", "aggregate only", "not measurable"]
    pivot = (free.pivot(index="signal", columns="sensor", values="verdict")
                 .reindex(columns=["Sentinel-2 10m", "Sentinel-1 10m",
                                   "Landsat 30m", "MODIS 250m", "VIIRS 375m"]))
    print("Verdict with free sensors (best verdict across the row):\n")
    print(pivot.to_string())

    print("\nRevisit mismatch - the signal moves faster than the free sensor returns:")
    bad = (free[~free.revisit_ok].groupby("signal")
           .agg(revisit=("revisit_days", "min"), timescale=("timescale_days", "first"))
           .sort_values("revisit"))
    print(bad.to_string() if len(bad) else "  none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
