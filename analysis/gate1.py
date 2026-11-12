"""Gate 1 - does free data forecast the corn crop better than the alternatives?

Prediction date is 1 August. Every feature must exist by then:

  weather    NASA POWER daily, windows ending 31 July (asof_* columns)
  satellite  MODIS 13Q1 composites that *begin* on or before 20 July
             (day-of-year 177 and 193), never the late-July composite, whose
             pixels run into August
  yield      NASS, the target only

Two evaluation schemes, and the difference between them is the finding:

  loyo       train on every other year. Measures model skill, and is what most
             projects report.
  expanding  train only on years before the target. Measures what a trader could
             actually have done, and is the scheme Gate 2 relies on.

Models:
  B0  trend only
  B1  trend + weather
  B2  trend + weather + NDVI
  B3  NASS published August forecast (reference, not a model)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
SPIKE = ROOT / "spike" / "data" / "years"

STATES = ["IA", "IL", "NE", "MN", "IN", "KS", "MO", "ND", "SD", "WI",
          "OH", "MI", "TX", "CO", "KY", "TN", "AR", "PA"]
WEATHER = ["asof_gdd", "asof_edd", "asof_heat_days", "asof_precip",
           "asof_precip_jul", "asof_tmax_jul"]
ALPHAS = np.logspace(0, 3, 7)


def load_yield() -> pd.DataFrame:
    y = pd.read_csv(RAW / "nass_yield.csv")
    y = y[(y.unit_desc == "BU / ACRE") & (y.reference_period_desc == "YEAR")]
    y = y[y.state_alpha.isin(STATES) & y.year.between(2000, 2025)]
    return y[["state_alpha", "year", "value"]].rename(columns={"value": "yield"})


def load_aug_forecast() -> pd.DataFrame:
    f = pd.read_csv(RAW / "nass_yield.csv")
    f = f[(f.unit_desc == "BU / ACRE")
          & (f.reference_period_desc == "YEAR - AUG FORECAST")]
    f = f[f.state_alpha.isin(STATES)]
    return f[["state_alpha", "year", "value"]].rename(columns={"value": "aug_fcst"})


def load_weather() -> pd.DataFrame:
    w = pd.read_csv(RAW / "weather_state_year.csv")
    return w[["state_alpha", "year"] + WEATHER]


def load_ndvi() -> pd.DataFrame:
    """One regional index per year.

    Eight collinear tile columns destabilise a ridge fitted on six years, and a
    per-state split was tried and abandoned: 18 states resolve to only 4 MODIS
    tiles, so any "state" column was a copy of a tile column. The honest input is
    a single Corn Belt index, and that is what is used.
    """
    frames = [pd.read_csv(f) for f in sorted(SPIKE.glob("ndvi_*.csv"))]
    if not frames:
        raise SystemExit("no NDVI files in spike/data/years")
    df = pd.concat(frames, ignore_index=True)
    df["doy"] = df["item"].str.split(".").str[1].str[-3:].astype(int)
    df = df[df.doy.isin([177, 193])]
    per_date = (df.assign(w=df.ndvi * df.n_pixels)
                  .groupby(["year", "doy"])
                  .apply(lambda g: g.w.sum() / g.n_pixels.sum(), include_groups=False)
                  .rename("ndvi").reset_index())
    wide = per_date.pivot(index="year", columns="doy", values="ndvi")
    return pd.DataFrame({"year": wide.index,
                         "ndvi_mean": wide.mean(axis=1).to_numpy()})


def load_area() -> pd.DataFrame:
    a = pd.read_csv(RAW / "nass_area_harvested.csv")
    a = a[(a.unit_desc.str.contains("ACRES", na=False))
          & (a.reference_period_desc == "YEAR") & a.state_alpha.isin(STATES)]
    out = a[["state_alpha", "year", "value"]].rename(columns={"value": "acres"})
    # Census-of-Agriculture years carry two acreage records per state-year.
    return out.drop_duplicates(["state_alpha", "year"])


def panel() -> pd.DataFrame:
    y = load_yield()
    df = (y.merge(load_weather(), on=["state_alpha", "year"], how="left")
           .merge(load_ndvi(), on="year", how="left")
           .merge(load_aug_forecast(), on=["state_alpha", "year"], how="left"))
    return df.sort_values(["state_alpha", "year"]).reset_index(drop=True)


def design(train: pd.DataFrame, test: pd.DataFrame, feats: list[str]):
    """Standardise with training-fold statistics only.

    Weather is centred and scaled within state, so a hot year in Texas is judged
    against Texas. The statistics come from the training years and are then
    applied to the held-out year; computing them on the test year would leak,
    and with one observation per state it would divide by a standard deviation of
    zero.
    """
    tr, te = train.copy(), test.copy()
    cols = []
    for f in feats:
        if f.startswith("asof"):
            g = (tr.groupby("state_alpha")[f].agg(["mean", "std"])
                   .rename(columns={"mean": "_m", "std": "_s"}))
            tr = tr.join(g, on="state_alpha")
            te = te.join(g, on="state_alpha")
            tr[f"{f}_z"] = (tr[f] - tr["_m"]) / tr["_s"]
            te[f"{f}_z"] = (te[f] - te["_m"]) / te["_s"]
            tr = tr.drop(columns=["_m", "_s"])
            te = te.drop(columns=["_m", "_s"])
        else:
            m, s = tr[f].mean(), tr[f].std()
            tr[f"{f}_z"] = (tr[f] - m) / s
            te[f"{f}_z"] = (te[f] - m) / s
        cols.append(f"{f}_z")
    return (tr[cols].fillna(0.0).to_numpy(float),
            te[cols].fillna(0.0).to_numpy(float))


def run(df: pd.DataFrame, feats: list[str], scheme: str = "loyo",
        min_train: int = 6) -> pd.DataFrame:
    preds = []
    for held in sorted(df.year.unique()):
        if scheme == "loyo":
            train = df[df.year != held]
        else:
            train = df[df.year < held]
            if train.year.nunique() < min_train:
                continue
        test = df[df.year == held].copy()
        if train.empty or test.empty:
            continue

        coefs, tr_rows, te_rows = {}, [], []
        for state, g in train.groupby("state_alpha"):
            b = np.polyfit(g.year.to_numpy(float), g["yield"].to_numpy(float), 1)
            coefs[state] = b
            tr_rows.append(pd.DataFrame({"state_alpha": state,
                                         "year": g.year.to_numpy(),
                                         "trend": np.polyval(b, g.year.to_numpy(float))}))
            tt = test[test.state_alpha == state]
            if len(tt):
                te_rows.append(pd.DataFrame({"state_alpha": state,
                                             "year": tt.year.to_numpy(),
                                             "trend": np.polyval(b, tt.year.to_numpy(float))}))
        if not te_rows:
            continue
        train = train.merge(pd.concat(tr_rows, ignore_index=True),
                            on=["state_alpha", "year"], how="left")
        test = test.merge(pd.concat(te_rows, ignore_index=True),
                          on=["state_alpha", "year"], how="left")
        train["resid"] = train["yield"] - train.trend
        test["resid"] = test["yield"] - test.trend

        if feats:
            Xtr, Xte = design(train, test, feats)
            model = RidgeCV(alphas=ALPHAS, fit_intercept=True)
            model.fit(Xtr, train["resid"].to_numpy(float))
            test["resid_hat"] = model.predict(Xte)
            test["alpha"] = float(model.alpha_)
        else:
            test["resid_hat"] = 0.0
            test["alpha"] = np.nan
        test["pred"] = test.trend + test.resid_hat
        preds.append(test)
    return pd.concat(preds, ignore_index=True) if preds else pd.DataFrame()


def metrics(p: pd.DataFrame) -> dict:
    e = (p["yield"] - p.pred).dropna()
    return {"n": len(e), "rmse": float(np.sqrt((e ** 2).mean())),
            "mae": float(e.abs().mean()), "bias": float(e.mean()),
            "r2": float(1 - (e ** 2).sum()
                        / ((p["yield"] - p["yield"].mean()) ** 2).sum())}


def national(preds: dict, area: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (scheme, name), p in preds.items():
        m = p.merge(area, on=["state_alpha", "year"], how="left")
        g = (m.assign(wp=m.pred * m.acres, wy=m["yield"] * m.acres)
               .groupby("year")
               .apply(lambda d: pd.Series({"pred": d.wp.sum() / d.acres.sum(),
                                           "actual": d.wy.sum() / d.acres.sum()}),
                      include_groups=False)
               .reset_index())
        g["model"] = f"{scheme}|{name}"
        rows.append(g)
    return pd.concat(rows, ignore_index=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    df = panel()
    print(f"panel: {len(df)} state-years, {df.state_alpha.nunique()} states, "
          f"{df.year.min():.0f}-{df.year.max():.0f}")
    print(f"missing yield {df['yield'].isna().sum()}, "
          f"weather {df[WEATHER].isna().any(axis=1).sum()}, "
          f"ndvi {df.ndvi_mean.isna().sum()}")

    preds, results = {}, {}
    for scheme in ("loyo", "expanding"):
        for name, feats in [("B0", []), ("B1", WEATHER),
                            ("B2", WEATHER + ["ndvi_mean"])]:
            p = run(df, feats, scheme=scheme)
            p["model"], p["scheme"] = name, scheme
            preds[(scheme, name)] = p
            results[(scheme, name)] = metrics(p)
            m = results[(scheme, name)]
            print(f"{scheme:9s} {name}: n={m['n']} rmse={m['rmse']:.3f} "
                  f"mae={m['mae']:.3f} bias={m['bias']:+.3f} r2={m['r2']:.3f}")

    b3 = df.dropna(subset=["aug_fcst"]).copy()
    b3["pred"], b3["model"], b3["scheme"] = b3["aug_fcst"], "B3", "usda"
    m3 = metrics(b3)
    results[("usda", "B3")] = m3
    print(f"{'usda':9s} B3: n={m3['n']} rmse={m3['rmse']:.3f} "
          f"mae={m3['mae']:.3f} bias={m3['bias']:+.3f} r2={m3['r2']:.3f}")

    print("\nis weather+NDVI better than weather alone? (year-block bootstrap)")
    for scheme in ("loyo", "expanding"):
        b1, b2 = preds[(scheme, "B1")], preds[(scheme, "B2")]
        j = b1[["state_alpha", "year", "pred"]].merge(
            b2[["state_alpha", "year", "pred"]], on=["state_alpha", "year"],
            suffixes=("_b1", "_b2"))
        j = j.merge(df[["state_alpha", "year", "yield"]],
                    on=["state_alpha", "year"])
        j["d2"] = (j["yield"] - j.pred_b2) ** 2 - (j["yield"] - j.pred_b1) ** 2
        years = j.year.unique()
        rng = np.random.default_rng(0)
        boots = []
        for _ in range(2000):
            pick = rng.choice(years, size=len(years), replace=True)
            boots.append(float(pd.concat([j[j.year == y] for y in pick]).d2.mean()))
        obs = float(j.d2.mean())
        lo, hi = np.percentile(boots, [2.5, 97.5])
        verdict = "excludes zero" if lo > 0 else "includes zero, not distinguishable"
        print(f"  {scheme:9s} reduction {obs:+.2f} (95% CI {lo:+.2f} to {hi:+.2f}); "
              f"{verdict}")

    pd.concat(preds.values(), ignore_index=True).to_csv(
        OUT / "gate1_predictions.csv", index=False)
    pd.DataFrame({f"{k[0]}|{k[1]}": v for k, v in results.items()}).T.to_csv(
        OUT / "gate1_metrics.csv")

    area = load_area()
    nat = national(preds, area)
    nat.to_csv(OUT / "gate1_national.csv", index=False)
    print("\nnational aggregate (harvested-acre weighted):")
    for name, g in nat.groupby("model"):
        err = g.pred - g.actual
        print(f"  {name:18s} RMSE {np.sqrt((err ** 2).mean()):5.2f}  "
              f"MAE {err.abs().mean():5.2f}  bias {err.mean():+.2f}  n={len(g)}")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=140)
    ax = axes[0]
    for (scheme, name), p in preds.items():
        if scheme != "loyo":
            continue
        e = (p["yield"] - p.pred).dropna()
        ax.hist(e, bins=30, alpha=0.55,
                label=f"{name} (RMSE {np.sqrt((e ** 2).mean()):.1f})")
    e3 = (b3["yield"] - b3.pred).dropna()
    ax.hist(e3, bins=30, alpha=0.45,
            label=f"B3 NASS Aug (RMSE {np.sqrt((e3 ** 2).mean()):.1f})")
    ax.set_xlabel("prediction error (bu/ac)")
    ax.set_title("State yield error, leave-one-year-out", loc="left", fontsize=10)
    ax.legend(fontsize=7, frameon=False)

    ax = axes[1]
    for name, g in nat.groupby("model"):
        ax.plot(g.year, g.pred - g.actual, marker="o", ms=3, lw=1, label=name)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("national error (bu/ac)")
    ax.set_title("National aggregate error by year", loc="left", fontsize=10)
    ax.legend(fontsize=7, frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "gate1.png")
    print(f"\nwrote {OUT/'gate1.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
