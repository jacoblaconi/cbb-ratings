"""Roster-aware preseason prior.

Projects each team's preseason AdjEM from:
  * last season's rating, scaled by how much of last season's production returns
  * transfers in: production share each newcomer had at his old D-I team, and that team's rating
  * high-school recruiting (optional, light weight): data/recruiting/{season}.csv

The projection coefficients are fit by least squares on past seasons
(scripts/fit_prior.py) and stored in config.PRIOR_COEF. The prior is then
blended with game results and fades out as games are played (model.solve).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .data import download, load_games
from .model import Ratings, solve

RECRUIT_DIR = Path(__file__).resolve().parent.parent / "data" / "recruiting"

FEATURES = ["em_ret", "em_prev", "ret", "xfer_em", "xfer_share"]


def player_shares(season: int, refresh: bool = False) -> pd.DataFrame:
    """Each player's share of his team's minutes and production in `season`."""
    p = pd.read_parquet(download("player_box", season, refresh))
    p = p[p["season_type"].isin([2, 3]) & p["athlete_id"].notna() & (p["minutes"].fillna(0) > 0)].copy()
    p["athlete_id"] = p["athlete_id"].astype("int64")
    p["team_id"] = p["team_id"].astype("int64")
    f = lambda c: p[c].fillna(0)  # noqa: E731
    # Hollinger-style game score as a simple production measure.
    p["prod"] = (
        f("points") + 0.4 * f("field_goals_made") - 0.7 * f("field_goals_attempted")
        - 0.4 * (f("free_throws_attempted") - f("free_throws_made")) + 0.7 * f("offensive_rebounds")
        + 0.3 * f("defensive_rebounds") + f("steals") + 0.7 * f("assists") + 0.7 * f("blocks")
        - 0.4 * f("fouls") - f("turnovers")
    )
    agg = p.groupby(["athlete_id", "team_id"], as_index=False)[["minutes", "prod"]].sum()
    tot = agg.groupby("team_id")[["minutes", "prod"]].transform("sum")
    agg["min_share"] = agg["minutes"] / tot["minutes"]
    agg["prod_share"] = (agg["prod"].clip(lower=0)) / agg.groupby("team_id")["prod"].transform(lambda s: s.clip(lower=0).sum())
    agg["share"] = 0.5 * agg["min_share"] + 0.5 * agg["prod_share"].fillna(0)
    return agg[["athlete_id", "team_id", "minutes", "share"]]


def roster(season: int, refresh: bool = False) -> pd.DataFrame:
    r = pd.read_parquet(download("rosters", season, refresh))
    r = r.dropna(subset=["athlete_id", "team_id"])
    r["athlete_id"] = r["athlete_id"].astype("int64")
    r["team_id"] = r["team_id"].astype("int64")
    return r[["athlete_id", "team_id"]].drop_duplicates()


def final_ratings(season: int, prior: pd.DataFrame | None = None) -> Ratings:
    g, _, teams = load_games(season)
    end = (pd.Timestamp(g["game_date"].max()) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return solve(g, teams["team_id"], end, prior)


def features(season: int, prev: Ratings, refresh: bool = False) -> pd.DataFrame:
    """Team features for `season` from last season's ratings, box scores and this season's rosters."""
    shares = player_shares(season - 1, refresh)
    ros = roster(season, refresh)
    em_prev = prev.table["adj_em"] - prev.table["adj_em"].mean()

    # Each rostered player's main team last season (most minutes).
    last = shares.sort_values("minutes", ascending=False).drop_duplicates("athlete_id")
    j = ros.merge(last, on="athlete_id", how="left", suffixes=("", "_old"))
    ret = j[j["team_id_old"] == j["team_id"]].groupby("team_id")["share"].sum()
    xf = j[j["team_id_old"].notna() & (j["team_id_old"] != j["team_id"])].copy()
    xf["old_em"] = em_prev.reindex(xf["team_id_old"].to_numpy()).fillna(em_prev.min()).to_numpy()
    xf["w_em"] = xf["share"] * xf["old_em"]
    xg = xf.groupby("team_id")

    out = pd.DataFrame(index=pd.Index(sorted(ros["team_id"].unique()), name="team_id"))
    out["em_prev"] = em_prev.reindex(out.index)
    out["ret"] = ret.reindex(out.index).fillna(0).clip(upper=1)
    out["em_ret"] = out["em_prev"] * out["ret"]
    out["xfer_em"] = xg["w_em"].sum().reindex(out.index).fillna(0)
    out["xfer_share"] = xg["share"].sum().reindex(out.index).fillna(0)
    # A roster can only use one team's worth of production. When returning
    # players plus transfers add up to more than that, scale the transfer
    # credit down to fill only the room that's left.
    room = (1.0 - out["ret"]).clip(lower=0)
    scale = (room / out["xfer_share"].where(out["xfer_share"] > 0)).clip(upper=1.0).fillna(1.0)
    out["xfer_em"] *= scale
    out["xfer_share"] *= scale
    out["has_prev"] = out["em_prev"].notna()
    out["em_prev"] = out["em_prev"].fillna(0)
    out["em_ret"] = out["em_ret"].fillna(0)
    return out


def recruiting_bump(season: int, team_ids) -> pd.Series:
    """Optional: data/recruiting/{season}.csv with team_id,points (any class-ranking score).

    Converted to z-scores and worth RECRUIT_WEIGHT AdjEM per standard deviation.
    """
    f = RECRUIT_DIR / f"{season}.csv"
    s = pd.Series(0.0, index=pd.Index(team_ids))
    if not f.exists():
        return s
    df = pd.read_csv(f)
    pts = df.set_index("team_id")["points"].astype(float)
    z = (pts - pts.mean()) / (pts.std() or 1.0)
    return s.add(config.RECRUIT_WEIGHT * z, fill_value=0.0).reindex(s.index).fillna(0.0)


def projected_em(feat: pd.DataFrame, coef: dict) -> pd.Series:
    x = sum(coef[k] * feat[k] for k in FEATURES) + coef["intercept"]
    # Teams with no D-I history: a little below average, plus credit for D-I transfers.
    return x.where(feat["has_prev"], config.NEWCOMER_EM + coef["xfer_em"] * feat["xfer_em"])


def build_prior(season: int, refresh: bool = False, coef: dict | None = None) -> pd.DataFrame:
    """Prior table (o_rel, d_rel, t_rel) for `season`, used by model.solve."""
    coef = coef or config.PRIOR_COEF
    prev = final_ratings(season - 1)
    feat = features(season, prev, refresh)
    em = projected_em(feat, coef) + recruiting_bump(season, feat.index)
    base = prev.prior(regress=config.PRIOR_REGRESS).reindex(feat.index)
    # Keep last season's offense/defense tilt, regressed; split projected margin evenly.
    tilt = ((base["o_rel"] + base["d_rel"]) / 2).fillna(0)
    return pd.DataFrame({
        "o_rel": em / 2 + tilt,
        "d_rel": -em / 2 + tilt,
        "t_rel": base["t_rel"].fillna(0),
        "proj_em": em,
        "ret": feat["ret"],
        "xfer_share": feat["xfer_share"],
    })
