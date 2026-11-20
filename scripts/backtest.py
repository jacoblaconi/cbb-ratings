"""Back-test predictions: each day, rate teams on games before that day and predict that day's games.

Usage: python scripts/backtest.py 2026 [--grid]
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cbb import config  # noqa: E402
from cbb.data import load_games  # noqa: E402
from cbb.model import predict, solve  # noqa: E402
from cbb.prior import build_prior  # noqa: E402


def final_ratings(season: int, prior=None):
    g, _, teams = load_games(season)
    end = (pd.Timestamp(g["game_date"].max()) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return solve(g, teams["team_id"], end, prior)


def run(season: int, prior_table, start_after: str | None = None) -> dict:
    g, _, teams = load_games(season)
    g = g[g["d1"]]
    rows = []
    for day, today in g.groupby("game_date"):
        if start_after and day <= start_after:
            continue
        r = solve(g, teams["team_id"], day, prior_table)
        p = predict(r, today["h_team_id"], today["a_team_id"], today["neutral_site"])
        actual = (today["h_team_score"] - today["a_team_score"]).to_numpy(float)
        rows.append(pd.DataFrame({"date": day, "pred": p["margin"].to_numpy(), "p": p["p_home"].to_numpy(), "act": actual}))
    d = pd.concat(rows)
    err = d["pred"] - d["act"]
    won = (d["act"] > 0).astype(float)
    return {
        "games": len(d),
        "mae": float(err.abs().mean()),
        "rmse": float(np.sqrt((err**2).mean())),
        "winner_pct": float(((d["pred"] > 0) == (d["act"] > 0)).mean()),
        "brier": float(((d["p"] - won) ** 2).mean()),
        "resid_sd": float(err.std()),
        # Before mid-December, when the prior matters most.
        "mae_early": float(err[d["date"].to_numpy() < f"{season - 1}-12-15"].abs().mean()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("season", type=int)
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--prior", choices=["roster", "last"], default="roster")
    ap.add_argument("--fit-seasons", default=None,
                    help="refit prior coefficients on these seasons first, e.g. 2025 (avoids testing on fit data)")
    args = ap.parse_args()

    coef = None
    if args.fit_seasons:
        from fit_prior import dataset  # noqa: E402
        from cbb.prior import FEATURES
        d = pd.concat([dataset(int(s)) for s in args.fit_seasons.split(",")])
        X = np.column_stack([d[k] for k in FEATURES] + [np.ones(len(d))])
        beta, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
        coef = dict(zip(FEATURES + ["intercept"], beta))

    def make_prior():
        if args.prior == "roster":
            return build_prior(args.season, coef=coef)
        return final_ratings(args.season - 1).prior(config.PRIOR_REGRESS)

    if not args.grid:
        print(run(args.season, make_prior()))
        return
    grid = {
        "PRIOR_GAMES": [4.0, 6.0, 9.0, 12.0],
        "PRIOR_FADE_GAMES": [10, 13, 18],
    }
    for combo in itertools.product(*grid.values()):
        for k, v in zip(grid, combo):
            setattr(config, k, v)
        res = run(args.season, make_prior())
        print(dict(zip(grid, combo)), {k: round(v, 4) for k, v in res.items()}, flush=True)


if __name__ == "__main__":
    main()
