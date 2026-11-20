"""Frozen grading: a game's quadrant must not change when later results move the opponent."""
import pandas as pd

from cbb import netplus
from cbb.model import solve
from tests.test_model import synthetic_games


def _teams(n):
    return pd.DataFrame({"team_id": range(n)})


def test_frozen_values_do_not_change_with_later_games():
    g, *_ = synthetic_games(rounds=12)
    g["conference_competition"] = False
    early = g[g["game_date"] < "2026-12-07"]
    r_early = solve(early, range(40), "2026-12-07")
    rows_a, _, _ = netplus.build(early, _teams(40), None, r_early)
    r_full = solve(g, range(40), "2027-01-01")
    rows_b, _, _ = netplus.build(g, _teams(40), None, r_full)
    cols = ["game_id", "team_id", "opp_rank_frozen", "quad_frozen", "wab_frozen"]
    a = rows_a[cols].set_index(["game_id", "team_id"])
    b = rows_b[cols].set_index(["game_id", "team_id"]).loc[a.index]
    pd.testing.assert_frame_equal(a, b)
