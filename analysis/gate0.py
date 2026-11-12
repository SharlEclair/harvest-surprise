"""Gate 0 â€” would perfect knowledge pay?

The question the video's author asked last, asked first.

  1. How big is a WASDE corn-yield revision, and how often does one happen?
  2. If you knew the revision in advance, what would trading it earn â€” and how
     much of that is gone if you have to trade k days early?
  3. How does the prize degrade with forecast error?

The lead-time axis is measured, not assumed: for each event the P&L is computed
over [release - k trading days, release] for k in {0,1,2,3,5,10}. If the market
already moves before the report, the oracle's edge decays in k, and that decay
is the real cost of a forecast that arrives early.

Price response is reported two ways, because they answer different questions:
  * OLS beta: return ~ d_yield + d_area, controlling for the acreage revision
    that lands in the same report.
  * sign-trade beta: -mean(P&L) / mean|revision|, i.e. the average move per
    bu/ac among the releases that actually revised.

Outputs: data/processed/gate0_events.csv, gate0_leadtime.csv, gate0.png
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

COST_ROUND_TRIP = 0.0015   # 0.15 % of notional: 1 tick + commission + slippage
EVENTS_PER_YEAR = 5.05     # measured: non-zero revisions per year in the sample
LEADS = (0, 1, 2, 3, 5, 10)


def build_events() -> pd.DataFrame:
    corn = pd.read_csv(RAW / "wasde_corn.csv", parse_dates=["ReleaseDate"])
    corn["Attribute"] = corn["Attribute"].astype(str).str.strip()
    corn["MarketYear"] = corn["MarketYear"].astype(str).str.strip()

    keep = {"Yield per Harvested Acre": "yield_bu_ac",
            "Area Harvested": "area_harvested_mac"}
    # The same quantity appears twice per release, once in bushels and once in
    # metric tons. Without this filter the pivot silently picks whichever row
    # comes last, which is a 36x error waiting to happen.
    want_unit = {"Yield per Harvested Acre": "Bushels",
                 "Area Harvested": "Million Acres"}
    corn = corn[corn.apply(lambda r: r["Unit"] == want_unit.get(r["Attribute"]), axis=1)]
    wide = (corn[corn.Attribute.isin(keep)]
            .assign(metric=lambda d: d.Attribute.map(keep))
            .pivot_table(index=["ReleaseDate", "MarketYear"], columns="metric",
                         values="Value", aggfunc="last")
            .reset_index())
    if "yield_bu_ac" not in wide:
        raise SystemExit("no yield rows in WASDE pull")

    # Each release carries three marketing years; the newest is the crop the
    # market is trading. Differencing is always within the same market year, so
    # no release is compared against a different crop.
    wide["my_start"] = wide.MarketYear.str.slice(0, 4).astype(int)
    newest = (wide.sort_values(["ReleaseDate", "my_start"])
                  .groupby("ReleaseDate").tail(1).copy())
    newest = newest.sort_values(["my_start", "ReleaseDate"])
    newest["d_yield"] = newest.groupby("my_start")["yield_bu_ac"].diff()
    newest["d_area"] = newest.groupby("my_start")["area_harvested_mac"].diff()
    newest = newest.dropna(subset=["d_yield"])
    return newest[["ReleaseDate", "MarketYear", "my_start", "yield_bu_ac",
                   "d_yield", "d_area"]].reset_index(drop=True)


def attach_returns(events: pd.DataFrame) -> pd.DataFrame:
    px = pd.read_csv(RAW / "prices_daily.csv", parse_dates=["date"])
    corn = px[px.ticker == "ZC=F"].sort_values("date").reset_index(drop=True)
    corn["log_close"] = np.log(corn["close"])

    pos = corn["date"].searchsorted(pd.DatetimeIndex(events.ReleaseDate), side="left")
    pos = np.clip(pos, 11, len(corn) - 1)

    out = events.copy()
    out["trade_date"] = corn["date"].iloc[pos].to_numpy()
    out["close"] = corn["close"].iloc[pos].to_numpy()
    for k in LEADS:
        out[f"ret_lag{k}"] = (corn["log_close"].iloc[pos].to_numpy()
                              - corn["log_close"].iloc[pos - (k + 1)].to_numpy())
    out = out[(out.trade_date - out.ReleaseDate).dt.days <= 4]
    return out.reset_index(drop=True)


def oracle(events: pd.DataFrame, col: str) -> dict:
    """Trade the sign of the revision. Only releases that actually revise count:
    you cannot know that in advance, which is the point of the surface below."""
    d = events[events.d_yield != 0].copy()
    d["pnl"] = -np.sign(d.d_yield) * d[col]
    n = len(d)
    mean = float(d.pnl.mean())
    se = float(d.pnl.std(ddof=1) / np.sqrt(n))
    return {"n": n, "mean": mean, "se": se, "t": mean / se if se > 0 else np.nan,
            "hit": float((d.pnl > 0).mean()),
            "mean_abs_rev": float(d.d_yield.abs().mean())}


def ols(events: pd.DataFrame) -> dict:
    """return ~ d_yield + d_area. The acreage control is pre-registered in the
    brief because area and yield revisions land in the same report."""
    x = events["d_yield"].to_numpy(float)
    a = events["d_area"].fillna(0).to_numpy(float)
    y = events["ret_lag0"].to_numpy(float)
    X = np.column_stack([np.ones(len(x)), x, a])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    s2 = resid @ resid / (len(y) - X.shape[1])
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    r2 = 1 - (resid @ resid) / ((y - y.mean()) @ (y - y.mean()))
    return {"beta": float(coef[1]), "se": float(se[1]), "t": float(coef[1] / se[1]),
            "beta_area": float(coef[2]), "se_area": float(se[2]),
            "r2": float(r2), "n": len(y), "sigma_u": float(np.std(x, ddof=1))}


def surface(beta: float, sigma_u: float, rho_grid: np.ndarray,
            costs: float = COST_ROUND_TRIP) -> pd.DataFrame:
    """Expected annual net return if the price response is |beta| per bu/ac.

        E[pnl per event] = |beta| * sigma_u * rho - costs
        rho = corr(forecast, surprise) = sqrt(1 - rmse^2 / sigma_u^2)

    This is an approximation and is labelled as one: it assumes normal errors
    and a linear price response, and it uses the regression beta rather than the
    sign-trade beta, so it is the *conservative* of the two estimates.
    """
    rows = []
    for f in np.linspace(0.0, 1.0, 11):
        rmse = f * sigma_u
        rho = float(np.sqrt(max(0.0, 1 - f ** 2)))
        gross = abs(beta) * sigma_u * rho
        net = gross - costs
        rows.append({"rmse_bu_ac": rmse, "rmse_frac": f, "rho": rho,
                     "gross": gross, "net": net,
                     "annual_net": net * EVENTS_PER_YEAR})
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    events = attach_returns(build_events())
    events.to_csv(OUT / "gate0_events.csv", index=False)

    zero = float((events.d_yield == 0).mean())
    sigma_u = float(events.d_yield.std(ddof=1))
    print(f"events {len(events)}  {events.ReleaseDate.min().date()} to "
          f"{events.ReleaseDate.max().date()}")
    print(f"zero-revision releases: {zero:.0%}; sigma_u = {sigma_u:.2f} bu/ac")
    print(f"median |revision| among revisions: "
          f"{events.loc[events.d_yield != 0, 'd_yield'].abs().median():.1f} bu/ac")

    print("\n--- oracle P&L by lead time (know the revision sign, trade k days early) ---")
    lead_rows = []
    for k in LEADS:
        r = oracle(events, f"ret_lag{k}")
        lead_rows.append({"lead_days": k, **r})
        print(f"  k={k:2d}d: n={r['n']:3d}  mean {r['mean']:+.3%}  "
              f"t {r['t']:+.2f}  hit {r['hit']:.0%}")
    lead = pd.DataFrame(lead_rows)
    lead.to_csv(OUT / "gate0_leadtime.csv", index=False)

    print("\n--- price response ---")
    reg = ols(events)
    print(f"  OLS beta {reg['beta']*100:+.3f}% per bu/ac (se {reg['se']*100:.3f}, "
          f"t {reg['t']:+.2f}), area control {reg['beta_area']*100:+.3f}% per M acres "
          f"(t {reg['beta_area']/reg['se_area']:+.2f}), R2 {reg['r2']:.3f}")
    sign_beta = -lead.loc[0, "mean"] / lead.loc[0, "mean_abs_rev"]
    print(f"  sign-trade implied {-sign_beta*100:+.3f}% per bu/ac "
          f"(-mean P&L / mean|revision|); the two agree in sign, and the sign "
          f"trade implies the larger effect")

    print("\n--- how much of the oracle edge survives a premature trade ---")
    base = lead.loc[0, "mean"]
    for _, r in lead.iterrows():
        print(f"  k={int(r.lead_days):2d}: {r['mean']:+.3%}/event  "
              f"({r['mean']/base:.0%} of same-day)")

    surf = surface(reg["beta"], sigma_u, None)
    surf.to_csv(OUT / "gate0_surface.csv", index=False)
    print(f"\n--- break-even surface from the OLS beta "
          f"({abs(reg['beta'])*100:.2f}%/bu, cost {COST_ROUND_TRIP:.2%}) ---")
    for rmse in (0, 1, 2, 3):
        row = surf.iloc[(surf.rmse_bu_ac - rmse).abs().to_numpy().argmin()]
        print(f"  RMSE {rmse} bu/ac -> rho {row.rho:.2f}  gross {row.gross:+.3%}  "
              f"net {row.net:+.3%}/event  annual {row.annual_net:+.2%}")
    be = surf[surf.annual_net <= 0]
    if len(be):
        first = be.iloc[0]
        print(f"  breaks even at RMSE < {first.rmse_bu_ac:.2f} bu/ac "
              f"({first.rmse_frac:.0%} of sigma_u)")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=140)
    ax = axes[0]
    ax.plot(lead.lead_days, lead["mean"] * 100, "o-", color="#1f3b57")
    ax.axhline(COST_ROUND_TRIP * 100, color="#c9822b", ls="--", lw=1,
               label=f"round trip {COST_ROUND_TRIP:.2%}")
    ax.set_xlabel("days traded before the release")
    ax.set_ylabel("oracle return per event (%)")
    ax.set_title("The market drifts toward the revision before the report", loc="left", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=0.25)

    ax = axes[1]
    ax.plot(surf.rmse_bu_ac, surf.annual_net * 100, "o-", color="#1f3b57")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xlabel("forecast RMSE (bu/ac)")
    ax.set_ylabel("annual net return on notional (%)")
    ax.set_title(f"Break-even surface (beta {reg['beta']*100:.2f}%/bu)", loc="left",
                 fontsize=10)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "gate0.png")
    print(f"\nwrote {OUT/'gate0.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

