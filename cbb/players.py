"""Player ratings from box scores.

Offensive rating is Dean Oliver's individual ORtg (points produced per 100
possessions used), computed from season totals the way Basketball-Reference
documents it. Usage, minutes share and the rate stats follow KenPom's player
glossary. Team totals come from the same player box scores, so a player's
numbers and his team's always add up.

"Off. value" is a single sortable number: points per 100 team possessions a
player adds over a D-I average offense using the same possessions,
(ORtg - national average) x usage x minutes share.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data import download

STATS = ["minutes", "field_goals_made", "field_goals_attempted", "three_point_field_goals_made",
         "three_point_field_goals_attempted", "free_throws_made", "free_throws_attempted",
         "offensive_rebounds", "defensive_rebounds", "assists", "steals", "blocks", "turnovers",
         "fouls", "points"]


def load_player_box(season: int, game_ids, refresh: bool = False) -> pd.DataFrame:
    p = pd.read_parquet(download("player_box", season, refresh))
    p = p[p["season_type"].isin([2, 3]) & p["athlete_id"].notna() & p["game_id"].isin(set(game_ids))].copy()
    p["athlete_id"] = p["athlete_id"].astype("int64")
    p["team_id"] = p["team_id"].astype("int64")
    p["game_id"] = p["game_id"].astype("int64")
    for c in STATS:
        p[c] = p[c].fillna(0).astype(float)
    return p


def player_ratings(p: pd.DataFrame, team_ids, mu: float) -> pd.DataFrame:
    """Season player table for players on `team_ids`. mu: national average efficiency."""
    if p.empty:
        return pd.DataFrame()
    tg = p.groupby(["game_id", "team_id"], as_index=False)[STATS].sum()
    opp = tg.rename(columns={"team_id": "opp_id", **{c: f"opp_{c}" for c in STATS}})
    tg = tg.merge(opp, on="game_id")
    tg = tg[tg["team_id"] != tg["opp_id"]]
    team = tg.groupby("team_id")[STATS + ["opp_offensive_rebounds", "opp_defensive_rebounds"]].sum()
    team = team.add_prefix("tm_")
    games_played = p[p["minutes"] > 0].groupby(["athlete_id", "team_id"])["game_id"].nunique()

    pl = p.groupby(["athlete_id", "team_id"], as_index=False).agg(
        name=("athlete_display_name", "last"), pos=("athlete_position_abbreviation", "last"),
        jersey=("athlete_jersey", "last"), **{c: (c, "sum") for c in STATS})
    pl = pl[pl["team_id"].isin(set(team_ids)) & (pl["minutes"] > 0)]
    pl["g"] = games_played.reindex(pd.MultiIndex.from_frame(pl[["athlete_id", "team_id"]])).to_numpy()
    d = pl.merge(team, left_on="team_id", right_index=True)

    MP, FG, FGA, FG3 = d["minutes"], d["field_goals_made"], d["field_goals_attempted"], d["three_point_field_goals_made"]
    FT, FTA, ORB, DRB = d["free_throws_made"], d["free_throws_attempted"], d["offensive_rebounds"], d["defensive_rebounds"]
    AST, TOV, PTS = d["assists"], d["turnovers"], d["points"]
    T = lambda c: d[f"tm_{c}"]  # noqa: E731
    tMP, tFG, tFGA, tFG3 = T("minutes"), T("field_goals_made"), T("field_goals_attempted"), T("three_point_field_goals_made")
    tFT, tFTA, tORB, tAST = T("free_throws_made"), T("free_throws_attempted"), T("offensive_rebounds"), T("assists")
    tTOV, tPTS, tDRB = T("turnovers"), T("points"), T("defensive_rebounds")
    oORB, oDRB = T("opp_offensive_rebounds"), T("opp_defensive_rebounds")

    with np.errstate(divide="ignore", invalid="ignore"):
        share = MP / (tMP / 5)
        qAST = share * (1.14 * ((tAST - AST) / tFG)) + (
            ((tAST / tMP) * MP * 5 - AST) / ((tFG / tMP) * MP * 5 - FG)) * (1 - share)
        ft_rate = np.where(FTA > 0, FT / FTA, 0.0)
        two_ratio = np.where(FGA > 0, (PTS - FT) / (2 * FGA), 0.0)
        fg_part = FG * (1 - 0.5 * two_ratio * qAST)
        ast_part = 0.5 * (((tPTS - tFT) - (PTS - FT)) / (2 * (tFGA - FGA))) * AST
        ft_part = (1 - (1 - ft_rate) ** 2) * 0.4 * FTA
        t_sc_poss = tFG + (1 - (1 - tFT / tFTA) ** 2) * tFTA * 0.4
        t_orb_pct = tORB / (tORB + oDRB)
        t_play = t_sc_poss / (tFGA + tFTA * 0.4 + tTOV)
        t_orb_w = ((1 - t_orb_pct) * t_play) / ((1 - t_orb_pct) * t_play + t_orb_pct * (1 - t_play))
        orb_part = ORB * t_orb_w * t_play
        sc_poss = (fg_part + ast_part + ft_part) * (1 - (tORB / t_sc_poss) * t_orb_w * t_play) + orb_part
        fgx = (FGA - FG) * (1 - 1.07 * t_orb_pct)
        ftx = ((1 - ft_rate) ** 2) * 0.4 * FTA
        tot_poss = sc_poss + fgx + ftx + TOV
        pp_fg = 2 * (FG + 0.5 * FG3) * (1 - 0.5 * two_ratio * qAST)
        pp_ast = 2 * ((tFG - FG + 0.5 * (tFG3 - FG3)) / (tFG - FG)) * ast_part
        pp_orb = ORB * t_orb_w * t_play * (tPTS / t_sc_poss)
        pprod = (pp_fg + pp_ast + FT) * (1 - (tORB / t_sc_poss) * t_orb_w * t_play) + pp_orb

        out = pd.DataFrame({
            "athlete_id": d["athlete_id"], "team_id": d["team_id"], "name": d["name"], "pos": d["pos"],
            "jersey": d["jersey"], "g": d["g"], "mpg": MP / d["g"],
            "ppg": PTS / d["g"], "rpg": (ORB + DRB) / d["g"], "apg": AST / d["g"],
            "min_pct": 100 * share,
            "ortg": 100 * pprod / tot_poss,
            "usg": 100 * (FGA + 0.44 * FTA + TOV) * (tMP / 5) / (MP * (tFGA + 0.44 * tFTA + tTOV)),
            "efg": 100 * (FG + 0.5 * FG3) / FGA,
            "ts": 100 * PTS / (2 * (FGA + 0.44 * FTA)),
            "three_pct": 100 * FG3 / d["three_point_field_goals_attempted"],
            "three_a": d["three_point_field_goals_attempted"],
            "ft_pct": 100 * FT / FTA,
            "ast_rate": 100 * AST / (share * tFG - FG),
            "to_rate": 100 * TOV / (FGA + 0.44 * FTA + TOV),
            "or_pct": 100 * ORB * (tMP / 5) / (MP * (tORB + oDRB)),
            "dr_pct": 100 * DRB * (tMP / 5) / (MP * (tDRB + oORB)),
        })
    out = out.replace([np.inf, -np.inf], np.nan)
    out["off_value"] = (out["ortg"] - mu) * (out["usg"] / 100) * (out["min_pct"] / 100)
    # Rates are meaningless on a handful of minutes.
    rates = ["ortg", "usg", "efg", "ts", "three_pct", "ft_pct", "ast_rate", "to_rate", "or_pct", "dr_pct", "off_value"]
    out.loc[out["min_pct"] < 10, rates] = np.nan
    # ORtg is noisy on tiny samples: leave it blank under 40 possessions used.
    small = tot_poss.to_numpy() < 40
    out.loc[small, ["ortg", "off_value"]] = np.nan
    return out.sort_values(["team_id", "min_pct"], ascending=[True, False]).reset_index(drop=True)
