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

from cbb import config  # noqa: E402
from cbb.data import load_games  # noqa: E402
from cbb.model import predict, solve  # noqa: E402


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
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("season", type=int)
    ap.add_argument("--grid", action="store_true")
    args = ap.parse_args()

    base_prior = final_ratings(args.season - 1)
    if not args.grid:
        print(run(args.season, base_prior.prior()))
        return
    grid = {
        "PRIOR_GAMES": [3.0, 6.0, 10.0],
        "PRIOR_REGRESS": [0.2, 0.35, 0.5],
        "MARGIN_CAP": [20.0, 25.0, 40.0],
    }
    for combo in itertools.product(*grid.values()):
        for k, v in zip(grid, combo):
            setattr(config, k, v)
        res = run(args.season, base_prior.prior(config.PRIOR_REGRESS))
        print(dict(zip(grid, combo)), {k: round(v, 4) for k, v in res.items()}, flush=True)


if __name__ == "__main__":
    main()
