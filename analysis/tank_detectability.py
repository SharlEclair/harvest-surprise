"""Was tank fill ever detectable at 10 m? A signal-to-noise calculation.

Two empirical nulls (optical and SAR amplitude) do not explain themselves. This
computes the signal the method could possibly see, from geometry, and compares it
to the noise actually measured in the archive.

Signal model for one tank, viewed at solar elevation theta:

    roof diameter d, height H, stock change delta_s, total hub capacity C
    roof drop            dh = H * delta_s / C
    shadow length        L  = dh / tan(theta)
    shadowed fraction    g  = min(L, d) / d          (never exceeds one diameter)
    brightness change    dI = g * contrast

Noise is measured, not assumed: the standard deviation of a tank's brightness
after removing the scene mean, i.e. everything that is not shared illumination.

Output: data/processed/tank_detectability.csv, printed SNR table.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

# Cushing working storage capacity. EIA has reported roughly 90 million barrels
# in recent years; 48 Mbbl was the 2011 figure quoted alongside the satellite
# coverage. Both are used to bracket the answer.
CAPACITY_MBBL = {"low": 48.0, "high": 90.0}
TANK_D_M = 60.0          # typical large floating-roof tank, metres
TANK_H_M = 20.0
SOLAR_ELEV_DEG = 60.0    # Sentinel-2 overpass is mid-morning, not noon
CONTRAST = 0.30          # roof reflectance minus shadowed roof, fractional


def signal_per_mbbl(capacity_mbbl: float, delta_mbbl: float) -> dict:
    dh = TANK_H_M * delta_mbbl / capacity_mbbl
    L = dh / np.tan(np.radians(SOLAR_ELEV_DEG))
    g = min(L, TANK_D_M) / TANK_D_M
    return {"delta_mbbl": delta_mbbl, "roof_drop_m": dh, "shadow_m": L,
            "shadowed_fraction": g, "brightness_change": g * CONTRAST}


def main() -> int:
    z = np.load(OUT / "cushing_tank_matrix.npz", allow_pickle=True)
    B, V = z["brightness"], z["valid"]
    Bm = np.where(V > 0, B, np.nan)
    # remove the scene mean: this is the part of a tank's brightness that is not
    # explained by illumination and atmosphere, i.e. the noise floor
    R = Bm - np.nanmean(Bm, axis=1, keepdims=True)
    tank_sd = np.nanstd(R, axis=0)
    tank_sd = tank_sd[np.isfinite(tank_sd)]
    median_tank_sd = float(np.median(tank_sd))
    mean_level = float(np.nanmedian(Bm))
    noise_frac = median_tank_sd / mean_level
    print(f"tanks {len(tank_sd)}, median per-tank brightness after scene removal: "
          f"{median_tank_sd:.1f} DN on a level of {mean_level:.0f} "
          f"({noise_frac:.1%})")

    rows = []
    for label, cap in CAPACITY_MBBL.items():
        for delta in (1, 5, 10, 20, 45):
            s = signal_per_mbbl(cap, delta)
            s["capacity_scenario"] = label
            s["snr"] = s["brightness_change"] / noise_frac
            rows.append(s)
    df = pd.DataFrame(rows)
    df["noise_fraction"] = noise_frac
    df.to_csv(OUT / "tank_detectability.csv", index=False)

    print("\nsignal for a hub-wide stock change, at 10 m and solar elevation 60 deg\n")
    print(df[["capacity_scenario", "delta_mbbl", "roof_drop_m", "shadow_m",
              "shadowed_fraction", "brightness_change", "snr"]]
          .round(4).to_string(index=False))

    # what change would be needed to reach SNR 2?
    for label, cap in CAPACITY_MBBL.items():
        need = 2 * noise_frac * cap / CONTRAST  # in Mbbl, from g=dI/contrast and dh proportional
        # invert properly: dI = (dh/tan/d)*contrast, dh = H*ds/cap
        ds_needed = (2 * noise_frac / CONTRAST) * (TANK_D_M * np.tan(np.radians(SOLAR_ELEV_DEG))) * cap / TANK_H_M
        print(f"\ncapacity {cap:.0f} Mbbl: SNR 2 needs a stock move of "
              f"{ds_needed:.1f} Mbbl, about {ds_needed / cap:.0%} of capacity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
