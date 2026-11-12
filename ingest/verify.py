"""Sanity checks on the NASS pull. Fails loudly rather than printing a story.

Run after `ingest/nass.py`. Exit code 0 means every assertion held.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def load(name: str) -> pd.DataFrame:
    return pd.read_csv(RAW / f"nass_{name}.csv")


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append((label, bool(ok), detail))

    y = load("yield")
    a = load("area_harvested")
    p = load("area_planted")
    c = load("condition")

    # --- shape -------------------------------------------------------------
    for name, df in [("yield", y), ("area_harvested", a), ("area_planted", p), ("condition", c)]:
        check(f"{name}: readable", len(df) > 0, f"{len(df)} rows")

    # --- yield: one row per state-year-period ------------------------------
    grain = y[(y.unit_desc == "BU / ACRE") & (y.state_alpha != "OT")].copy()
    dup = grain.duplicated(["state_alpha", "year", "reference_period_desc"]).sum()
    check("yield: no duplicate state-year-period", dup == 0, f"{dup} duplicates")

    # --- yield: state yields reconcile to the national number --------------
    # An independent check: NASS published 2023 = 177.3 and 2024 = 179.3 bu/ac
    # nationally. Weighting the state rows by harvested acres must reproduce
    # that to within rounding, or the pull is mis-joined.
    ah = a[(a.unit_desc.str.contains("ACRES", na=False)) & (a.state_alpha != "OT")]
    ah = ah[ah.reference_period_desc == "YEAR"][["state_alpha", "year", "value"]]
    ah = ah.rename(columns={"value": "acres"})
    for year, published in [(2023, 177.3), (2024, 179.3)]:
        gy = grain[(grain.year == year) & (grain.reference_period_desc == "YEAR")]
        m = gy.merge(ah[ah.year == year], on=["state_alpha", "year"])
        implied = (m.value * m.acres).sum() / m.acres.sum()
        check(f"yield: {year} states reconcile to {published} bu/ac",
              abs(implied - published) < 1.5,
              f"implied {implied:.1f} from {len(m)} states")

    # --- forecasts: the whole point of the pull ----------------------------
    periods = set(grain.reference_period_desc.unique())
    want = {"YEAR - AUG FORECAST", "YEAR - SEP FORECAST", "YEAR - OCT FORECAST",
            "YEAR - NOV FORECAST"}
    check("yield: all four in-season forecasts present", want <= periods,
          f"missing {want - periods}")

    aug = grain[grain.reference_period_desc == "YEAR - AUG FORECAST"]
    check("yield: Aug forecast covers >= 20 years", aug.year.nunique() >= 20,
          f"{aug.year.nunique()} years, {aug.state_alpha.nunique()} states")

    # revision must be small but non-zero, and must not be identically zero
    merged = aug.merge(
        grain[grain.reference_period_desc == "YEAR"],
        on=["state_alpha", "year"], suffixes=("_aug", "_final"),
    )
    rev = (merged.value_final - merged.value_aug).dropna()
    check("yield: Aug->final revisions are non-trivial", rev.abs().median() > 0.5,
          f"median |rev| {rev.abs().median():.2f} bu/ac, n={len(rev)}")
    check("yield: most Aug forecasts are not exact", (rev != 0).mean() > 0.5,
          f"{(rev != 0).mean():.0%} revised")

    # --- condition: percentages sum to ~100 --------------------------------
    c2 = c[c.state_alpha != "OT"].copy()
    c2["cat"] = c2.short_desc.str.extract(r"PCT ([A-Z ]+)$")[0].str.strip()
    piv = (c2.pivot_table(index=["state_alpha", "year", "week_ending"], columns="cat",
                          values="value", aggfunc="sum"))
    totals = piv.sum(axis=1, min_count=1).dropna()
    check("condition: category percentages sum to 100", 
          totals.between(99, 101).mean() > 0.9,
          f"{(totals.between(99, 101)).mean():.0%} of {len(totals)} state-weeks in [99,101]")

    # --- condition: week_ending parses -------------------------------------
    wk = pd.to_datetime(c2.week_ending, errors="coerce")
    check("condition: week_ending is a date", wk.notna().mean() > 0.99,
          f"{wk.notna().mean():.1%} parse, {wk.min().date()} to {wk.max().date()}")

    # --- area: planted >= harvested ---------------------------------------
    ah = a[(a.unit_desc.str.contains("ACRES", na=False)) & (a.state_alpha != "OT")]
    ap = p[(p.unit_desc.str.contains("ACRES", na=False)) & (p.state_alpha != "OT")]
    m = ah.merge(ap, on=["state_alpha", "year"], suffixes=("_h", "_p"))
    m = m[(m.reference_period_desc_h == "YEAR") & (m.reference_period_desc_p == "YEAR")]
    check("area: planted >= harvested", (m.value_p >= m.value_h * 0.95).mean() > 0.95,
          f"{(m.value_p >= m.value_h * 0.95).mean():.0%} of {len(m)} state-years")

    # --- report ------------------------------------------------------------
    width = max(len(label) for label, _, _ in checks)
    failed = 0
    for label, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {label:<{width}}  {detail}")
        failed += not ok

    print()
    print(f"{len(checks) - failed}/{len(checks)} checks passed")
    if not failed:
        print("samples")
        print(grain[grain.year == 2023]
              .pivot_table(index="state_alpha",
                           columns="reference_period_desc", values="value")
              .loc[["IA", "IL", "NE", "MN", "IN"]]
              .round(1).to_string())
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
