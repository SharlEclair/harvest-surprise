"""Gate 2 Ã¢â‚¬â€ does the model know something the USDA's August forecast does not?

The state-yield model does not beat the USDA on level (Gate 1: RMSE 12.9 vs
9.5). That is the wrong test for tradability. The tradeable question is whether
the model's *disagreement* with the USDA predicts the *revision* the USDA will
subsequently publish.

    d   = model prediction (1 Aug)  -  NASS August forecast
    rev = final state yield        -  NASS August forecast

If corr(d, rev) > 0, a model that says "better than USDA" tends to be followed
by upward revisions, which is information the August report did not contain.

Then the trading version: hold corn from the August WASDE to the January final
in the direction of the national disagreement, and compare with the null.

Outputs: data/processed/gate2_state.csv, gate2_national.csv, gate2.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
MODEL = "B2"
SCHEME = "expanding"   # point-in-time: train only on years before the target
COST = 0.0015          # round trip, charged once per trade


def state_frame() -> pd.DataFrame:
    p = pd.read_csv(OUT / "gate1_predictions.csv")
    p = p[(p.model == MODEL) & (p.scheme == SCHEME)].copy()
    p = p.dropna(subset=["pred", "aug_fcst", "yield"])
    p["d"] = p.pred - p.aug_fcst
    p["rev"] = p["yield"] - p.aug_fcst
    return p


def wasde_dates() -> pd.DataFrame:
    """First/last release in each calendar year, plus the August and January ones."""
    w = pd.read_csv(RAW / "wasde_corn.csv", parse_dates=["ReleaseDate"])
    w = w[w.Attribute.str.contains("Yield", na=False)]
    d = (w.assign(year=w.ReleaseDate.dt.year, month=w.ReleaseDate.dt.month)
          .groupby("year")["ReleaseDate"]
          .agg(first_release="min", last_release="max")
          .reset_index())
    aug = (w[w.ReleaseDate.dt.month == 8]
           .assign(year=w.ReleaseDate.dt.year)
           .groupby("year")["ReleaseDate"].min().rename("aug_release").reset_index())
    jan = (w[w.ReleaseDate.dt.month == 1]
           .assign(year=w.ReleaseDate.dt.year)
           .groupby("year")["ReleaseDate"].min().rename("jan_release").reset_index())
    return d.merge(aug, on="year", how="left").merge(jan, on="year", how="left")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    st = state_frame()
    print(f"state-years with model, forecast and final: {len(st)}")

    n = len(st)
    r = np.corrcoef(st.d, st.rev)[0, 1]
    # block bootstrap by year: events within a year are not independent
    years = st.year.unique()
    boot = []
    rng = np.random.default_rng(0)
    for _ in range(2000):
        pick = rng.choice(years, size=len(years), replace=True)
        s = pd.concat([st[st.year == y] for y in pick])
        if s.d.std() > 0 and s.rev.std() > 0:
            boot.append(np.corrcoef(s.d, s.rev)[0, 1])
    lo, hi = np.percentile(boot, [2.5, 97.5])

    slope = np.polyfit(st.d, st.rev, 1)[0]
    print(f"corr(model - USDA August, final - USDA August) = {r:+.3f}")
    print(f"  year-block bootstrap 95% CI: [{lo:+.3f}, {hi:+.3f}]  (n_boot={len(boot)})")
    print(f"  slope: 1 bu/ac of disagreement -> {slope:+.2f} bu/ac of revision")
    print(f"  share of revisions in the direction of the disagreement: "
          f"{(np.sign(st.d) == np.sign(st.rev)).mean():.0%}")

    st["tercile"] = pd.qcut(st.d, 3, labels=["model low", "middle", "model high"])
    tab = st.groupby("tercile", observed=True).agg(
        n=("rev", "size"), mean_rev=("rev", "mean"), mean_d=("d", "mean"),
        share_up=("rev", lambda s: (s > 0).mean()))
    print("\nmean subsequent revision by disagreement tercile:")
    print(tab.round(3).to_string())
    st.to_csv(OUT / "gate2_state.csv", index=False)

    # --- national aggregate -------------------------------------------------
    area = pd.read_csv(RAW / "nass_area_harvested.csv")
    area = area[(area.unit_desc.str.contains("ACRES", na=False))
                & (area.reference_period_desc == "YEAR")]
    area = area[["state_alpha", "year", "value"]].rename(columns={"value": "acres"})
    # Census-of-Agriculture years carry two acreage records per state-year.
    area = area.drop_duplicates(["state_alpha", "year"])
    m = st.merge(area, on=["state_alpha", "year"], how="left")
    nat = (m.assign(pd=m.pred * m.acres, fd=m.aug_fcst * m.acres,
                    yd=m["yield"] * m.acres)
             .groupby("year")
             .apply(lambda d: pd.Series({
                 "pred": d.pd.sum() / d.acres.sum(),
                 "aug": d.fd.sum() / d.acres.sum(),
                 "final": d.yd.sum() / d.acres.sum()}), include_groups=False)
             .reset_index())
    nat["d"] = nat.pred - nat.aug
    nat["rev"] = nat.final - nat.aug
    cn = np.corrcoef(nat.d, nat.rev)[0, 1] if nat.d.std() > 0 else np.nan
    print(f"\nnational: corr(disagreement, revision) = {cn:+.3f}  n={len(nat)}")
    print(nat.round(2).to_string(index=False))
    nat.to_csv(OUT / "gate2_national.csv", index=False)

    # --- trading version ----------------------------------------------------
    px = pd.read_csv(RAW / "prices_daily.csv", parse_dates=["date"])
    corn = px[px.ticker == "ZC=F"].sort_values("date").set_index("date")
    dates = wasde_dates()
    trades = []
    for _, row in nat.iterrows():
        yr = int(row.year)
        d0 = dates[dates.year == yr]
        if d0.empty or pd.isna(d0.aug_release.iloc[0]):
            continue
        # Enter on the August WASDE, exit on the January WASDE that publishes
        # the final crop. That is exactly the window the revision is measured in.
        start = d0.aug_release.iloc[0]
        nxt = dates[dates.year == yr + 1]
        if nxt.empty:
            continue
        # 2019 and 2021 have no January release in the archive (the 2019 report
        # was cancelled, the 2021 file is missing); fall back to the first
        # release of the year rather than dropping the observation silently.
        end = nxt.jan_release.iloc[0] if not pd.isna(nxt.jan_release.iloc[0]) \
            else nxt.first_release.iloc[0]
        s = corn.index.searchsorted(start, side="left")
        e = corn.index.searchsorted(end, side="left")
        if s >= len(corn) or e >= len(corn) or e <= s:
            continue
        r_hold = np.log(corn.close.iloc[e] / corn.close.iloc[s]) - COST
        trades.append({"year": yr, "start": start, "end": end,
                       "p_start": float(corn.close.iloc[s]),
                       "p_end": float(corn.close.iloc[e]),
                       "d": row.d, "rev": row.rev, "ret": r_hold})
    tr = pd.DataFrame(trades)
    if len(tr) > 3:
        tr["pos"] = -np.sign(tr.d)   # bigger crop than USDA => short
        tr["pnl"] = tr.pos * tr.ret
        mean, se = tr.pnl.mean(), tr.pnl.std(ddof=1) / np.sqrt(len(tr))
        print(f"\nhold Aug->Jan in the direction of the disagreement: "
              f"n={len(tr)}  mean {mean:+.2%}  se {se:.2%}  "
              f"t {mean/se:+.2f}  hit {(tr.pnl > 0).mean():.0%}")
        # Directional benchmark: if corn simply fell over this window, a short
        # book would look profitable without any skill. Report both.
        print(f"  always long {tr.ret.mean():+.2%}/yr; always short "
              f"{-tr.ret.mean():+.2%}/yr; strategy {mean:+.2%}/yr")

        # Arithmetic means hide compounding, and compounding is what a backtest is
        # supposed to be about. Report terminal wealth, a bootstrap interval, and
        # how much of the result rests on a single year.
        comp = float(np.prod(1 + tr.pnl) - 1)
        comp_long = float(np.prod(1 + tr.ret) - 1)
        rng_c = np.random.default_rng(3)
        cbs = np.array([np.prod(1 + rng_c.choice(tr.pnl.to_numpy(float), len(tr),
                                                 replace=True)) - 1
                        for _ in range(5000)])
        print(f"  compounded: strategy {comp:+.1%} vs always long {comp_long:+.1%} "
              f"over {len(tr)} years")
        print(f"  compounded bootstrap 95% CI [{np.percentile(cbs, 2.5):+.0%}, "
              f"{np.percentile(cbs, 97.5):+.0%}]")
        print(f"  strategy beats always-long in "
              f"{int((tr.pnl > tr.ret).sum())}/{len(tr)} years")
        worst = int(tr.pnl.idxmax())
        keep = tr.index != worst
        print(f"  without {int(tr.loc[worst, 'year'])} (its best year, "
              f"{tr.loc[worst, 'pnl']:+.1%}): strategy "
              f"{np.prod(1 + tr.loc[keep, 'pnl']) - 1:+.1%} vs always long "
              f"{np.prod(1 + tr.loc[keep, 'ret']) - 1:+.1%}")

        # Null: permute the position vector across years. This keeps the return
        # distribution and the sign balance, and destroys only the pairing.
        rng = np.random.default_rng(1)
        pos = tr.pos.to_numpy(float)
        rets = tr.ret.to_numpy(float)
        null = np.array([float(np.mean(rng.permutation(pos) * rets)) for _ in range(10000)])
        p = float((null >= mean).mean())
        print(f"  permutation null (10,000 shuffles of the position vector): "
              f"median {np.median(null):+.2%}, p = {p:.3f}")
        tr.to_csv(OUT / "gate2_trades.csv", index=False)

        fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)
        ax.hist(null, bins=50, color="#999", alpha=0.7, label="shuffled positions (10k)")
        ax.axvline(mean, color="#c9822b", lw=2, label=f"strategy {mean:+.2%}")
        ax.set_xlabel("mean annual return, 1 unit notional")
        ax.set_title("Gate 2: the disagreement trade against a permutation null",
                     loc="left", fontsize=10)
        ax.legend(fontsize=8, frameon=False)
        fig.tight_layout()
        fig.savefig(OUT / "gate2.png")
        print(f"  wrote {OUT/'gate2.png'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())




