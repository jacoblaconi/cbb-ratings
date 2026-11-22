import numpy as np
import pandas as pd

from cbb import config, netplus, sim, tracker
from cbb.export import team_stats, watch_score
from cbb.model import solve
from cbb.players import STATS, player_ratings
from tests.test_model import synthetic_games


def _league(n_teams=96, rounds=10):
    g, o, d, mu = synthetic_games(n_teams=n_teams, rounds=rounds)
    for side in ("h", "a"):
        for c in ("field_goals_made", "field_goals_attempted", "three_point_field_goals_made",
                  "free_throws_attempted", "offensive_rebounds", "defensive_rebounds", "total_turnovers"):
            g[f"{side}_{c}"] = 10.0
    g["conference_competition"] = (g["h_team_id"] % 8) == (g["a_team_id"] % 8)
    g["season_type"] = 2
    teams = pd.DataFrame({"team_id": range(n_teams), "conf": [f"C{i % 8}" for i in range(n_teams)],
                          "name": [f"T{i}" for i in range(n_teams)]})
    return g, teams


def test_watch_score_prefers_good_close_games():
    close_good = watch_score(25, 25, 0.5)
    lopsided = watch_score(25, 25, 0.95)
    close_bad = watch_score(-5, -5, 0.5)
    assert close_good > lopsided and close_good > close_bad
    assert 0 <= watch_score(-30, -30, 0.99) <= watch_score(40, 40, 0.5) <= 100


def test_bracket_order_pairs_top_seed_with_lowest():
    order = sim._bracket_order(16)
    assert sorted(order) == list(range(16))
    pairs = [(order[i], order[i + 1]) for i in range(0, 16, 2)]
    assert all(a + b == 15 for a, b in pairs)


def test_simulation_fills_a_68_team_field():
    g, teams = _league()
    r = solve(g, teams["team_id"], "2027-01-01")
    _, summ, _ = netplus.build(g, teams, None, r)
    stats = team_stats(g, teams, r)
    up = pd.DataFrame({"game_id": [10_000], "game_date": ["2027-01-02"], "h_team_id": [0], "a_team_id": [1],
                       "neutral_site": [False]})
    schedule = pd.DataFrame({"game_id": [10_000], "notes_headline": [""], "conference_competition": [True],
                             "season_type": [2], "game_date": ["2027-01-02"]})
    odds, br = sim.simulate(r, teams, stats, summ, up, schedule, g, n=200, seed=1)
    assert abs(odds["p_field"].sum() - 68) < 1e-6
    assert abs(odds["p_auto"].sum() - 8) < 1e-6
    assert abs(odds["p_champ"].sum() - 1) < 1e-6
    assert abs(odds["p_r64"].sum() - 64) < 1e-6
    assert (odds["p_s16"] <= odds["p_r32"] + 1e-9).all()
    assert len(br["seeds"]) == 68
    # Better teams make the field more often.
    top = r.table["adj_em"].idxmax()
    assert odds.at[top, "p_field"] > 0.95


def test_conf_tourney_detection_ignores_early_events():
    s = pd.DataFrame({
        "notes_headline": ["Players Era 8 - Championship", "SEC Tournament - Final", "Big 12 Tournament - Final"],
        "conference_competition": [True, True, False],
        "season_type": [2, 2, 2],
        "game_date": ["2026-11-19", "2027-03-15", "2027-03-14"],
    })
    assert sim.conf_tourney_games(s).tolist() == [False, True, False]


def test_tracker_grades_against_the_spread():
    g, teams = _league(n_teams=20, rounds=4)
    snaps = {}
    r = solve(g, teams["team_id"], "2027-01-01")
    netplus.build(g, teams, None, r, snapshots=snaps)
    lines = pd.DataFrame({"home_spread": [-100.0, 100.0], "total": [1.0, 1000.0], "provider": ["X", "X"]},
                         index=pd.Index(g["game_id"].iloc[-2:].to_numpy(), name="game_id"))
    d = tracker.pregame(g, snaps, lines)
    assert len(d) == len(g)
    last = d.set_index("game_id").loc[lines.index]
    # Home -100: the model takes the away side and the home team didn't cover.
    assert last["ats"].iloc[0] == "W"
    # Home +100: the model takes home, home covers easily.
    assert last["ats"].iloc[1] == "W"
    # Totals: model expects over 1 and under 1000.
    assert last["ou"].tolist() == ["W", "W"]
    rep = tracker.report(d, "2027-01-01")
    assert rep["overall"]["games"] == len(g) and rep["overall"]["lined"] == 2


def test_player_usage_averages_to_100():
    rng = np.random.default_rng(3)
    rows = []
    for gid in range(6):
        for team, opp in ((1, 2), (2, 1)):
            mins = np.array([36, 34, 32, 30, 28, 20, 12, 8], float)
            for i, mp in enumerate(mins):
                fga = rng.integers(2, 15)
                fgm = rng.integers(0, fga + 1)
                fg3 = rng.integers(0, fgm + 1)
                fta = rng.integers(0, 8)
                ftm = rng.integers(0, fta + 1)
                rows.append({"game_id": gid, "team_id": team, "athlete_id": team * 100 + i,
                             "athlete_display_name": f"P{i}", "athlete_position_abbreviation": "G",
                             "athlete_jersey": str(i), "minutes": mp,
                             "field_goals_made": fgm, "field_goals_attempted": fga,
                             "three_point_field_goals_made": fg3, "three_point_field_goals_attempted": fg3 + 2,
                             "free_throws_made": ftm, "free_throws_attempted": fta,
                             "offensive_rebounds": rng.integers(0, 4), "defensive_rebounds": rng.integers(0, 7),
                             "assists": rng.integers(0, 5), "steals": 1, "blocks": 0,
                             "turnovers": rng.integers(0, 4), "fouls": 2,
                             "points": 2 * (fgm - fg3) + 3 * fg3 + ftm})
    p = pd.DataFrame(rows)
    for c in STATS:
        p[c] = p[c].astype(float)
    out = player_ratings(p, [1, 2], 105.0)
    for team, grp in out.groupby("team_id"):
        # Five players on the floor: minutes-weighted usage adds up to 100%.
        assert abs((grp["usg"] * grp["min_pct"]).sum() / 100 - 100) < 1e-6
        assert abs(grp["min_pct"].sum() - 500) < 1e-6
    assert out["ortg"].between(40, 200).all()
