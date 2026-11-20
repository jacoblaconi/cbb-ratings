import numpy as np
import pandas as pd

from cbb import config
from cbb.model import damp_margins, predict, solve
from cbb.netplus import quadrant


def synthetic_games(n_teams=40, rounds=12, seed=1):
    rng = np.random.default_rng(seed)
    o = rng.normal(0, 6, n_teams)
    d = rng.normal(0, 6, n_teams)
    mu, poss = 105.0, 70.0
    rows, gid = [], 0
    for r in range(rounds):
        perm = rng.permutation(n_teams)
        for h, a in zip(perm[::2], perm[1::2]):
            hca = 100 * (config.HCA_POINTS / 2) / poss
            oe_h = mu + o[h] + d[a] + hca
            oe_a = mu + o[a] + d[h] - hca
            rows.append({
                "game_id": gid, "game_date": f"2026-12-{r + 1:02d}", "h_team_id": h, "a_team_id": a,
                "h_team_score": oe_h * poss / 100, "a_team_score": oe_a * poss / 100,
                "poss": poss, "minutes": 40.0, "neutral_site": False, "d1": True,
            })
            gid += 1
    return pd.DataFrame(rows), o, d, mu


def test_solver_recovers_true_ratings():
    g, o, d, mu = synthetic_games()
    r = solve(g, range(40), "2027-01-01")
    em_true = o - d
    em_fit = r.table["adj_em"].to_numpy()
    assert np.corrcoef(em_true, em_fit)[0, 1] > 0.99
    assert abs(r.mu - mu) < 1.0


def test_prediction_includes_home_court():
    g, *_ = synthetic_games()
    r = solve(g, range(40), "2027-01-01")
    home = predict(r, [0], [1], [False])["margin"].iloc[0]
    neutral = predict(r, [0], [1], [True])["margin"].iloc[0]
    assert abs((home - neutral) - config.HCA_POINTS) < 0.01


def test_damp_margins_keeps_average_and_caps():
    h, a = damp_margins(np.array([160.0]), np.array([80.0]))
    assert abs((h + a)[0] - 240.0) < 1e-9
    assert (h - a)[0] < 80.0


def test_quadrant_cutoffs():
    assert quadrant(30, "home") == 1 and quadrant(31, "home") == 2
    assert quadrant(50, "neutral") == 1 and quadrant(201, "neutral") == 4
    assert quadrant(75, "away") == 1 and quadrant(240, "away") == 3 and quadrant(241, "away") == 4
