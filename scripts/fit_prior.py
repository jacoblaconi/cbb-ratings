"""Fit the roster-aware prior: predict each team's final AdjEM from preseason information.

Usage: python scripts/fit_prior.py 2025 2026
Prints coefficients to paste into cbb/config.py (PRIOR_COEF) and the fit quality.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cbb.prior import FEATURES, features, final_ratings  # noqa: E402


def dataset(season: int) -> pd.DataFrame:
    prev = final_ratings(season - 1)
    cur = final_ratings(season)
    f = features(season, prev)
    y = cur.table["adj_em"] - cur.table["adj_em"].mean()
    f = f[f.index.isin(y.index) & f["has_prev"]].copy()
    f["y"] = y.reindex(f.index)
    f["season"] = season
    return f


def main() -> None:
    seasons = [int(s) for s in sys.argv[1:]] or [2025, 2026]
    d = pd.concat([dataset(s) for s in seasons])
    X = np.column_stack([d[k] for k in FEATURES] + [np.ones(len(d))])
    beta, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
    coef = dict(zip(FEATURES + ["intercept"], np.round(beta, 3)))
    pred = X @ beta
    for s in seasons:
        m = d["season"].to_numpy() == s
        y = d["y"].to_numpy()[m]
        naive = 0.8 * d["em_prev"].to_numpy()[m]
        print(f"{s}: teams {m.sum()}  roster model MAE {np.abs(pred[m] - y).mean():.2f}  "
              f"last-season-only MAE {np.abs(naive - y).mean():.2f}")
    print("PRIOR_COEF =", {k: float(v) for k, v in coef.items()})


if __name__ == "__main__":
    main()
