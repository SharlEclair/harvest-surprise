"""One figure for the whole tank investigation.

Three instruments were tried against the same ground truth and each failed for a
different reason. Those reasons are in three CSVs and three documents; this puts
them on one page.

    panel A  optical: the signal is below the noise floor at every realistic
             stock change, so the method cannot work rather than did not
    panel B  radar amplitude: within-year correlations near zero, in and out of
             sample
    panel C  radar phase: displacement scales with the perpendicular baseline,
             which no roof motion can do

Output: data/processed/tank_three_failures.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"

INK = "#1f3b57"
WARN = "#b4532a"
GREY = "#8a8a8a"


def main() -> int:
    det = pd.read_csv(OUT / "tank_detectability.csv")
    sar = pd.read_csv(OUT / "cushing_sar_metrics.csv")
    insar = pd.read_csv(OUT / "insar_pairs.csv")

    fig, axes = plt.subplots(1, 3, figsize=(13.2, 3.9), dpi=150)

    # ---- A: optical SNR -------------------------------------------------
    ax = axes[0]
    low = det[det.capacity_scenario == "low"].sort_values("delta_mbbl")
    ax.plot(low.delta_mbbl, low.snr, "o-", color=INK, lw=1.6, ms=5)
    ax.axhline(1.0, color=WARN, ls="--", lw=1.2)
    ax.text(low.delta_mbbl.min(), 1.02, " detection threshold", color=WARN,
            fontsize=7, va="bottom")
    ax.set_yscale("log")
    ax.set_xlabel("hub-wide stock change (million bbl)", fontsize=8)
    ax.set_ylabel("signal-to-noise ratio", fontsize=8)
    ax.set_title("A  optical: below the noise floor", fontsize=9, loc="left")
    ax.tick_params(labelsize=7)
    ax.grid(alpha=0.25, which="both")
    ax.annotate(f"max achievable\nSNR {low.snr.max():.2f}",
                xy=(low.delta_mbbl.max(), low.snr.max()),
                xytext=(-8, 14), textcoords="offset points",
                fontsize=7, color=INK, ha="right")

    # ---- B: radar amplitude --------------------------------------------
    ax = axes[1]
    row = sar[sar.subset == "all"].iloc[0]
    labels = ["2018-21\n(train)", "2022-25\n(held out)"]
    vals = [row.r_within_train, row.r_within_test]
    bars = ax.bar(labels, vals, color=[GREY, INK], width=0.55)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylim(-0.6, 0.6)
    ax.set_ylabel("within-year correlation", fontsize=8)
    ax.set_title("B  radar amplitude: no signal", fontsize=9, loc="left")
    ax.tick_params(labelsize=7)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + (0.03 if v >= 0 else -0.06),
                f"{v:+.3f}", ha="center", fontsize=8, color="black")

    # ---- C: radar phase ------------------------------------------------
    ax = axes[2]
    d = insar.sort_values("baseline_m")
    ax.plot(d.baseline_m, d.median_disp_cm, "o", color=INK, ms=7, zorder=3)
    z = np.polyfit(d.baseline_m, d.median_disp_cm, 1)
    xs = np.linspace(-115, 120, 50)
    ax.plot(xs, np.polyval(z, xs), "-", color=INK, lw=1.1, alpha=0.7, zorder=2)
    ax.axhline(0, color="black", lw=0.8)
    ax.axvline(0, color="black", lw=0.8)
    for _, r in d.iterrows():
        ax.annotate(f"{r.median_disp_cm:+.2f} cm", (r.baseline_m, r.median_disp_cm),
                    textcoords="offset points", xytext=(0, 9),
                    fontsize=7, ha="center", color=INK)
    ax.set_xlabel("perpendicular baseline (m)", fontsize=8)
    ax.set_ylabel("median tank displacement (cm)", fontsize=8)
    ax.set_title("C  radar phase: motion follows geometry", fontsize=9, loc="left")
    ax.tick_params(labelsize=7)
    ax.grid(alpha=0.25)
    ax.annotate("a roof does not know\nhow far apart the orbits were",
                xy=(0, 0), xytext=(0.42, 0.18), textcoords="axes fraction",
                fontsize=7, color=WARN)

    fig.suptitle("Cushing tank fill: three instruments, three independent failures",
                 fontsize=11, x=0.008, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    path = OUT / "tank_three_failures.png"
    fig.savefig(path)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
