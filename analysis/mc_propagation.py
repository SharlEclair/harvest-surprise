"""Monte Carlo: what does using the satellite cost the acreage forecast?

The analytic propagation in analysis/chain.py says a 5.2% median storage error
becomes a 2.1% acreage error. That uses the median and ignores the tail, and the
tail is the whole story with optical satellites: the p90 storage error is ~47%
because a cloudy year has few usable scenes.

This runs 10,000 draws from the *empirical* error distribution measured against
the CDEC gauges - not a Gaussian - and reports the distribution of the elasticity
and of the acreage forecast error.

Output: data/processed/mc_propagation.csv, mc_propagation.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"
N_DRAWS = 10_000


def empirical_errors() -> np.ndarray:
    """Per-scene storage percentage errors, pooled across reservoirs."""
    m = pd.read_csv(OUT / "reservoir_v2_matched.csv", parse_dates=["date"])
    errs = []
    for name, g in m.groupby("reservoir"):
        g = g.sort_values("area_m2").reset_index(drop=True)
        if len(g) < 10:
            continue
        x = g.area_m2.to_numpy(float)
        y = g.elevation_ft.to_numpy(float)
        pred = np.empty_like(y)
        for i in range(len(x)):
            mask = np.arange(len(x)) != i
            iso = IsotonicRegression(out_of_bounds="clip").fit(x[mask], y[mask])
            pred[i] = float(iso.predict([x[i]])[0])
        curv = g.sort_values("elevation_ft")
        obs = np.interp(y, curv.elevation_ft, curv.storage_af, left=np.nan, right=np.nan)
        prd = np.interp(pred, curv.elevation_ft, curv.storage_af, left=np.nan, right=np.nan)
        ok = np.isfinite(obs) & np.isfinite(prd) & (obs > 0)
        errs.append((prd[ok] - obs[ok]) / obs[ok])
    return np.concatenate(errs) if errs else np.array([])


def fit_elasticity(storage: np.ndarray, acres: np.ndarray, year: np.ndarray):
    x = np.log(storage)
    y = np.log(acres)
    t = year - year.mean()
    X = np.column_stack([np.ones(len(x)), x, t])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coef
    return coef[1], pred, y


def main() -> int:
    panel = pd.read_csv(OUT / "water_rice.csv").dropna(subset=["total_af", "acres"])
    errs = empirical_errors()
    if len(errs) < 50:
        raise SystemExit("not enough measured errors")
    panel = panel.sort_values("year")
    storage = panel.total_af.to_numpy(float)
    acres = panel.acres.to_numpy(float)
    year = panel.year.to_numpy(float)

    base_el, base_pred, y = fit_elasticity(storage, acres, year)
    base_rmse = float(np.sqrt(np.mean((base_pred - y) ** 2)))
    print(f"empirical storage error: n={len(errs)}, median {np.median(np.abs(errs)):.1%}, "
          f"p90 {np.percentile(np.abs(errs), 90):.1%}")
    print(f"gauge model: elasticity {base_el:+.3f}, in-sample log-RMSE {base_rmse:.3f}")

    rng = np.random.default_rng(42)
    els, rmses = [], []
    for _ in range(N_DRAWS):
        draw = rng.choice(errs, size=len(storage), replace=True)
        noisy = storage * (1 + draw)
        noisy = np.clip(noisy, storage.min() * 0.2, None)
        el, pred, _ = fit_elasticity(noisy, acres, year)
        els.append(el)
        rmses.append(float(np.sqrt(np.mean((pred - y) ** 2))))

    els = np.array(els)
    rmses = np.array(rmses)
    out = pd.DataFrame({
        "quantity": ["elasticity", "acreage_log_rmse"],
        "gauge": [base_el, base_rmse],
        "mc_median": [float(np.median(els)), float(np.median(rmses))],
        "mc_p05": [float(np.percentile(els, 5)), float(np.percentile(rmses, 5))],
        "mc_p95": [float(np.percentile(els, 95)), float(np.percentile(rmses, 95))],
        "share_positive": [float((els > 0).mean()), np.nan],
    })
    out.to_csv(OUT / "mc_propagation.csv", index=False)
    print("\nmonte carlo with satellite-grade storage:\n")
    print(out.to_string(index=False))

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), dpi=140)
    axes[0].hist(els, bins=60, color="#1f3b57")
    axes[0].axvline(base_el, color="#c9822b", lw=2, label=f"gauge {base_el:+.3f}")
    axes[0].set_title("elasticity under measured storage error", fontsize=9, loc="left")
    axes[0].legend(fontsize=8, frameon=False)
    axes[1].hist(rmses, bins=60, color="#1f3b57")
    axes[1].axvline(base_rmse, color="#c9822b", lw=2, label=f"gauge {base_rmse:.3f}")
    axes[1].set_title("acreage log-RMSE under measured storage error", fontsize=9, loc="left")
    axes[1].legend(fontsize=8, frameon=False)
    for ax in axes:
        ax.grid(alpha=0.25)
        ax.tick_params(labelsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "mc_propagation.png")
    print(f"\nwrote {OUT/'mc_propagation.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
