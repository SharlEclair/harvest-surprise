"""One entry point for the whole study.

    python hsp.py                 # everything, in dependency order
    python hsp.py ingest          # data pulls only
    python hsp.py analyse         # analysis only
    python hsp.py test            # the assertions

Each stage is a module in this repository whose main() returns 0 on success. The
runner stops at the first failure and prints what ran, so a partial pipeline is
never mistaken for a complete one.
"""
from __future__ import annotations

import runpy
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STAGES = {
    "ingest": [
        "ingest/nass.py",
        "ingest/wasde.py",
        "ingest/prices.py",
        "ingest/weather.py",
        "ingest/cdec.py",
    ],
    "measure": [
        "analysis/reservoir_v2.py",
        "analysis/reservoir_v2_validate.py",
    ],
    "analyse": [
        "analysis/gate0.py",
        "analysis/gate1.py",
        "analysis/gate2.py",
        "analysis/water_rice.py",
        "analysis/rice_surprise.py",
        "analysis/chain.py",
        "analysis/mc_propagation.py",
        "analysis/end_to_end.py",
        "analysis/h3_water.py",
        "analysis/dq_catalogue.py",
        "analysis/resolution_filter.py",
    ],
    "test": [
        "ingest/verify.py",
    ],
}


def run(script: str) -> bool:
    path = ROOT / script
    if not path.exists():
        print(f"  MISSING {script}")
        return False
    t0 = time.time()
    print(f"  -> {script}", flush=True)
    try:
        runpy.run_path(str(path), run_name="__main__")
    except SystemExit as exc:
        if exc.code not in (0, None):
            print(f"  FAILED {script} (exit {exc.code})")
            return False
    except Exception as exc:  # noqa: BLE001
        print(f"  FAILED {script}: {type(exc).__name__}: {exc}")
        return False
    print(f"  ok {script} ({time.time() - t0:.0f}s)", flush=True)
    return True


def main(argv: list[str]) -> int:
    wanted = argv[1:] or ["ingest", "measure", "analyse", "test"]
    order = []
    for w in wanted:
        if w not in STAGES:
            print(f"unknown stage {w}; choose from {list(STAGES)}")
            return 2
        order += STAGES[w]

    print(f"running {len(order)} stages\n")
    for script in order:
        if not run(script):
            print("\nstopped: a stage failed")
            return 1
    print("\nall stages completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
