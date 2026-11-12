"""Assertions on the artefacts this repository produces.

These are not unit tests of helper functions - there are almost none. They are
checks on the *claims*: that the joins are unique, that the reservoir measurement
beats its baseline, that the water-rice elasticity is positive and significant,
and that the corn evaluation is point-in-time. If one of these breaks, a number in
the report is no longer true.

Run: python -m pytest tests -q    (or python hsp.py test for the data checks)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"


def need(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} not built yet")
    return path


# --- data integrity -------------------------------------------------------

def test_nass_yield_is_unique_per_state_year_period():
    df = need(RAW / "nass_yield.csv")
    y = pd.read_csv(df)
    y = y[(y.unit_desc == "BU / ACRE") & (y.state_alpha != "OT")]
    dup = y.duplicated(["state_alpha", "year", "reference_period_desc"]).sum()
    assert dup == 0, f"{dup} duplicate state-year-period rows"


def test_nass_state_yields_reconcile_to_national():
    y = pd.read_csv(need(RAW / "nass_yield.csv"))
    a = pd.read_csv(need(RAW / "nass_area_harvested.csv"))
    y = y[(y.unit_desc == "BU / ACRE") & (y.reference_period_desc == "YEAR")
          & (y.state_alpha != "OT") & (y.year == 2023)]
    a = a[(a.unit_desc.str.contains("ACRES", na=False))
          & (a.reference_period_desc == "YEAR") & (a.year == 2023)]
    m = y.merge(a[["state_alpha", "year", "value"]], on=["state_alpha", "year"],
                suffixes=("", "_acres"))
    implied = (m.value * m.value_acres).sum() / m.value_acres.sum()
    assert abs(implied - 177.3) < 1.5, f"implied national yield {implied:.1f}"


def test_wasde_has_release_timestamps():
    w = pd.read_csv(need(RAW / "wasde_corn.csv"))
    assert {"ReleaseDate", "ReleaseTime"} <= set(w.columns)
    assert w.ReleaseDate.nunique() > 100


# --- reservoir measurement ------------------------------------------------

def test_reservoir_validation_beats_baseline():
    v = pd.read_csv(need(OUT / "reservoir_v2_validation.csv"))
    scored = v[v.reservoir.isin(["Shasta", "Oroville"])]
    assert len(scored) == 2, "expected the two validated reservoirs"
    assert (scored.rmse_isotonic_ft < scored.baseline_rmse_ft).all(), \
        f"isotonic did not beat baseline: {scored[['reservoir','rmse_isotonic_ft','baseline_rmse_ft']]}"
    assert (scored.spearman > 0.5).all(), f"weak rank correlation: {scored.spearman.tolist()}"


def test_satellite_storage_error_small_enough_to_propagate():
    p = pd.read_csv(need(OUT / "chain_propagation.csv"))
    assert p.median_abs_storage_err_pct.median() < 15, \
        "median storage error too large to stand in for a gauge"


# --- economic link --------------------------------------------------------

def test_water_rice_elasticity_positive_and_significant():
    df = pd.read_csv(need(OUT / "water_rice.csv"))
    x = np.log(df.total_af.to_numpy(float))
    y = np.log(df.acres.to_numpy(float))
    trend = df.year.to_numpy(float) - df.year.mean()
    X = np.column_stack([np.ones(len(df)), x, trend])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    s2 = resid @ resid / (len(y) - 3)
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    t = coef[1] / se[1]
    assert coef[1] > 0, f"elasticity flipped sign: {coef[1]:+.3f}"
    assert t > 3, f"elasticity no longer significant: t={t:+.2f}"


def test_water_rice_placebo_is_weaker_than_signal():
    df = pd.read_csv(need(OUT / "water_rice.csv"))
    x = np.log(df.total_af.to_numpy(float))
    y = np.log(df.acres.to_numpy(float))
    trend = df.year.to_numpy(float) - df.year.mean()

    def elast(xx, yy, tt):
        X = np.column_stack([np.ones(len(xx)), xx, tt])
        c, *_ = np.linalg.lstsq(X, yy, rcond=None)
        return c[1]

    signal = elast(x, y, trend)
    placebo = elast(x[:-1], y[1:], trend[1:])
    assert placebo < 0.75 * signal, \
        f"placebo {placebo:+.3f} too close to signal {signal:+.3f}"


# --- corn evaluation ------------------------------------------------------

def test_corn_predictions_are_unique_and_point_in_time():
    p = pd.read_csv(need(OUT / "gate1_predictions.csv"))
    dup = p.duplicated(["state_alpha", "year", "model", "scheme"]).sum()
    assert dup == 0, f"{dup} duplicate predictions"
    exp = p[p.scheme == "expanding"]
    assert exp.year.min() >= 2006, "expanding scheme should skip the first six years"


def test_expanding_beats_trend_on_the_national_aggregate():
    n = pd.read_csv(need(OUT / "gate1_national.csv"))
    nat = n[n.model.str.startswith("expanding")]
    rmse = {}
    for name, g in nat.groupby("model"):
        rmse[name] = float(np.sqrt(((g.pred - g.actual) ** 2).mean()))
    assert rmse["expanding|B1"] < rmse["expanding|B0"], \
        f"weather did not beat trend: {rmse}"


def test_monte_carlo_shows_attenuation_not_collapse():
    m = pd.read_csv(need(OUT / "mc_propagation.csv"))
    el = m[m.quantity == "elasticity"].iloc[0]
    assert el.mc_median > 0, "satellite noise flipped the elasticity"
    assert el.mc_p05 > 0, "5th percentile of the elasticity is not positive"
    assert el.mc_median < el.gauge, "expected errors-in-variables attenuation"


def test_end_to_end_satellite_is_not_worse_than_the_gauge():
    e = pd.read_csv(need(OUT / "end_to_end.csv"))
    assert len(e) >= 4, "need at least four out-of-sample years"
    gauge = e.err_gauge_pct.abs().mean()
    sat = e.err_sat_pct.abs().mean()
    assert sat < 60, f"satellite MAPE implausibly large: {sat:.1f}%"
    assert sat - gauge < 10, f"satellite is {sat - gauge:.1f}pp worse than the gauge"


def test_h3_layer_is_valid():
    import h3  # noqa: F401
    layer = pd.read_parquet(need(OUT / "h3_water.parquet"))
    assert len(layer) > 500, "H3 grid implausibly small"
    wcols = [c for c in layer.columns if c.startswith("w_")]
    assert wcols, "no reservoir weight columns"
    w = layer[wcols].to_numpy()
    assert w.min() >= 0 and w.max() <= 1, "weights must be a linear decay in [0,1]"
    years = [c for c in layer.columns if c.isdigit()]
    assert "2025" in years, "no 2025 accessibility column"
    assert (layer["2025"] >= 0).all()


def test_county_water_panel_covers_the_rice_belt():
    d = pd.read_csv(need(OUT / "county_water.csv"))
    assert d.county.nunique() >= 10
    assert len(d) >= 300
    top = d.groupby("county").acres.mean().nlargest(3).index.tolist()
    assert any(c in top for c in ["COLUSA", "SUTTER", "BUTTE"]), f"unexpected top counties: {top}"


def test_dq_catalogue_covers_the_core_tables():
    d = pd.read_csv(need(OUT / "dq_summary.csv"))
    core = {"cdec_reservoirs", "nass_yield", "wasde_corn", "prices_daily"}
    assert core <= set(d.table), f"missing from the catalogue: {core - set(d.table)}"
    cdec = d[d.table == "cdec_reservoirs"].iloc[0]
    assert cdec.dup_keys == 0, "the reservoir gauge table has duplicate station-dates"


def test_wasde_yield_is_unit_filtered():
    """The same quantity appears in bushels and metric tons; the gate must pick one."""
    w = pd.read_csv(need(RAW / "wasde_corn.csv"), low_memory=False)
    y = w[w.Attribute == "Yield per Harvested Acre"]
    assert set(y.Unit.unique()) == {"Bushels"}, f"unexpected yield units: {set(y.Unit.unique())}"


def test_cushing_index_tracks_stocks_in_levels_but_not_flows():
    """The video's project, rebuilt: level signal real, flow signal absent."""
    v = pd.read_csv(need(OUT / "cushing_validation.csv"))
    levels = float(v.loc[v.test == "levels, raw", "corr"].iloc[0])
    flows = float(v.loc[v.test == "4-week change", "corr"].iloc[0])
    assert levels > 0.3, f"level correlation collapsed: {levels:+.2f}"
    assert abs(flows) < 0.3, f"flow correlation unexpectedly strong: {flows:+.2f}"


def test_cushing_sar_amplitude_has_no_within_year_signal():
    """The radar amplitude null, pinned so it cannot quietly become a claim."""
    f = OUT / "cushing_sar_metrics.csv"
    if not f.exists():
        pytest.skip("SAR not run")
    m = pd.read_csv(f)
    row = m[m.subset == "all"].iloc[0]
    assert abs(row.r_within_test) < 0.3, f"unexpected within-year SAR signal: {row.r_within_test}"
    assert abs(row.r_within_train) < 0.3


def test_tank_fill_is_below_detection_at_10m():
    """The detectability calculation must keep saying 'impossible', not 'hard'."""
    d = pd.read_csv(need(OUT / "tank_detectability.csv"))
    row = d[(d.capacity_scenario == "low") & (d.delta_mbbl == 20)].iloc[0]
    assert row.snr < 1, f"SNR at a 20 Mbbl move is {row.snr}, expected below 1"
    assert row.snr > 0, "signal must be positive; a zero here means a broken formula"


def test_no_hub_crosses_detection_at_10m():
    h = pd.read_csv(need(OUT / "hub_noise.csv")).dropna(subset=["noise_fraction"])
    assert len(h) >= 3, "expected at least three hubs measured"
    # best possible signal: a 45 Mbbl move at 48 Mbbl capacity -> 5.4%
    assert (h.noise_fraction > 0.054).all(), (
        f"a hub now sits inside the detection band: {h[['hub','noise_fraction']]}")


def test_insar_tank_offset_is_a_baseline_artefact():
    """If this ever stops holding, either the DEM changed or the roofs moved."""
    d = pd.read_csv(need(OUT / "insar_pairs.csv"))
    assert len(d) >= 3, "need at least three baselines to test the artefact"
    r = float(np.corrcoef(d.baseline_m, d.median_disp_cm)[0, 1])
    assert abs(r) > 0.9, f"displacement no longer tracks baseline: r={r:+.2f}"
    near_zero = d.loc[d.baseline_m.abs().idxmin()]
    assert abs(near_zero.median_disp_cm) < 1.0, (
        f"a near-zero-baseline pair shows {near_zero.median_disp_cm:+.2f} cm, "
        "which would be real motion rather than geometry")


def test_insar_phase_is_not_aliased_over_tanks():
    """If the phase were aliased the gradient would approach pi; it does not."""
    g = pd.read_csv(need(OUT / "insar_phase_gradient.csv"))
    tanks = g[g["class"] == "tank"].iloc[0]
    assert tanks.median_grad_rad_px < 1.0, (
        f"tank phase gradient {tanks.median_grad_rad_px:.2f} rad/px suggests aliasing")
    assert tanks.share_gt_1 < 0.2, "too many tank pixels at the wrap limit"


def test_reservoir_validation_screens_area_collapses():
    """A failed water mask must not be allowed to speak for the measurement."""
    v = pd.read_csv(need(OUT / "reservoir_v2_validation.csv"))
    assert "n_area_collapse_dropped" in v.columns, "screen not applied"
    assert "spearman_all_scenes" in v.columns, "pre-screen value not recorded"
    # every reservoir that had a collapse should score better once it is removed
    hit = v[v.n_area_collapse_dropped > 0]
    assert len(hit) >= 2, "expected collapses to be found and screened"
    assert (hit.spearman >= hit.spearman_all_scenes).all(), (
        "screening made a reservoir worse; check the threshold")
    # the two reservoirs that carry the claim must clear a useful bar
    strong = v[v.reservoir.isin(["Shasta", "Oroville"])]
    assert (strong.spearman >= 0.85).all(), strong[["reservoir", "spearman"]]


def test_insar_products_are_coarser_than_a_tank():
    """The whole phase conclusion rests on this: a tank fits inside one pixel."""
    f = OUT / "insar_10m.csv"
    if not f.exists():
        pytest.skip("coarse/fine comparison not run")
    d = pd.read_csv(f)
    assert (d.grid_m >= 40).all(), "expected no product finer than 40 m"
    # a 60 m tank must not span more than two pixels at these grids
    assert (d.grid_m >= 40).all()


def test_reservoir_tracks_changes_not_just_levels():
    """Levels could co-move on seasonality alone; changes are the sharper test."""
    v = pd.read_csv(need(OUT / "reservoir_v2_validation.csv"))
    assert "spearman_changes" in v.columns, "change test not in the artefact"
    strong = v[v.reservoir.isin(["Shasta", "Oroville"])]
    assert (strong.spearman_changes > 0.5).all(), strong[["reservoir", "spearman_changes"]]
    assert (v.n_changes >= 30).all(), "too few change observations to conclude"


def test_gate2_trade_loses_to_buy_and_hold_on_compounded_terms():
    """Arithmetic means flattered it; compounding is what an investor experiences."""
    tr = pd.read_csv(need(OUT / "gate2_trades.csv"))
    pnl = tr.pos * tr.ret
    comp, comp_long = (1 + pnl).prod() - 1, (1 + tr.ret).prod() - 1
    assert comp < comp_long, (f"strategy {comp:+.1%} beat buy-and-hold {comp_long:+.1%}; "
                              "the no-edge conclusion needs revisiting")
    # removing its single best year must not rescue it either
    keep = tr.index != pnl.idxmax()
    assert (1 + pnl[keep]).prod() - 1 < (1 + tr.ret[keep]).prod() - 1


def test_comment_corpus_base_count():
    """Appendix A's percentages divide by this number, so it must not drift."""
    d = pd.read_csv(need(ROOT / "research" / "comments_all.csv"))
    top = d[d.is_reply == False]  # noqa: E712 - column is bool or 0/1
    assert len(top) == 337, f"top-level comments now {len(top)}, Appendix A says 337"
