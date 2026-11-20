"""Team stats and JSON export for the static site."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .model import Ratings, predict


def _sides(g: pd.DataFrame) -> pd.DataFrame:
    """Per-team box rows (offense = this team, defense = opponent)."""
    stats = ["team_score", "field_goals_made", "field_goals_attempted", "three_point_field_goals_made",
             "free_throws_attempted", "offensive_rebounds", "defensive_rebounds", "total_turnovers"]
    out = []
    for me, op in (("h", "a"), ("a", "h")):
        d = pd.DataFrame({"team_id": g[f"{me}_team_id"], "opp_id": g[f"{op}_team_id"], "poss": g["poss"],
                          "minutes": g["minutes"], "game_date": g["game_date"],
                          "conf_game": g["conference_competition"], "d1": g["d1"]})
        for s in stats:
            d[f"o_{s}"] = g[f"{me}_{s}"].to_numpy()
            d[f"d_{s}"] = g[f"{op}_{s}"].to_numpy()
        out.append(d)
    return pd.concat(out, ignore_index=True)


def team_stats(games: pd.DataFrame, teams: pd.DataFrame, current: Ratings) -> pd.DataFrame:
    s = _sides(games)
    all_g = s.groupby("team_id")
    rec = pd.DataFrame({
        "wins": all_g.apply(lambda x: int((x["o_team_score"] > x["d_team_score"]).sum()), include_groups=False),
        "losses": all_g.apply(lambda x: int((x["o_team_score"] < x["d_team_score"]).sum()), include_groups=False),
    })
    conf = s[s["conf_game"]].groupby("team_id")
    rec["conf_wins"] = conf.apply(lambda x: int((x["o_team_score"] > x["d_team_score"]).sum()), include_groups=False)
    rec["conf_losses"] = conf.apply(lambda x: int((x["o_team_score"] < x["d_team_score"]).sum()), include_groups=False)

    d = s[s["d1"]].copy()
    t = d.groupby("team_id").sum(numeric_only=True)
    out = pd.DataFrame(index=pd.Index(teams["team_id"], name="team_id"))
    out = out.join(rec)
    out["raw_o"] = 100 * t["o_team_score"] / t["poss"]
    out["raw_d"] = 100 * t["d_team_score"] / t["poss"]
    out["raw_t"] = 40 * t["poss"] / t["minutes"]
    for side in ("o", "d"):
        other = "d" if side == "o" else "o"
        out[f"{side}_efg"] = 100 * (t[f"{side}_field_goals_made"] + 0.5 * t[f"{side}_three_point_field_goals_made"]) / t[f"{side}_field_goals_attempted"]
        out[f"{side}_to"] = 100 * t[f"{side}_total_turnovers"] / t["poss"]
        out[f"{side}_or"] = 100 * t[f"{side}_offensive_rebounds"] / (t[f"{side}_offensive_rebounds"] + t[f"{other}_defensive_rebounds"])
        out[f"{side}_ftr"] = 100 * t[f"{side}_free_throws_attempted"] / t[f"{side}_field_goals_attempted"]

    # Luck: actual win % minus expected win % from game-by-game efficiencies (D-I games).
    oe = 100 * d["o_team_score"] / d["poss"]
    de = 100 * d["d_team_score"] / d["poss"]
    x = 10.25
    d["pyth"] = oe**x / (oe**x + de**x)
    d["won"] = (d["o_team_score"] > d["d_team_score"]).astype(float)
    lg = d.groupby("team_id")
    out["luck"] = lg["won"].mean() - lg["pyth"].mean()

    # Strength of schedule: average current rating of D-I opponents.
    r = current.table
    d["opp_em"] = r["adj_em"].reindex(d["opp_id"]).to_numpy()
    d["opp_o"] = r["adj_o"].reindex(d["opp_id"]).to_numpy()
    d["opp_d"] = r["adj_d"].reindex(d["opp_id"]).to_numpy()
    sg = d.groupby("team_id")
    out["sos_em"] = sg["opp_em"].mean()
    out["sos_o"] = sg["opp_o"].mean()
    out["sos_d"] = sg["opp_d"].mean()
    out["ncsos_em"] = d[~d["conf_game"]].groupby("team_id")["opp_em"].mean()
    for c in ("wins", "losses", "conf_wins", "conf_losses"):
        out[c] = out[c].fillna(0).astype(int)
    return out


def _clean(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) else round(f, 3)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")))


def export(out_dir: Path, season: int, as_of: str, games, upcoming, teams, current: Ratings,
           game_rows, netplus, history, prior: pd.DataFrame | None = None) -> None:
    stats = team_stats(games, teams, current)
    info = teams.set_index("team_id")
    r = current.table

    rank_cols = {"adj_o": False, "adj_d": True, "adj_t": False, "sos_em": False, "luck": False}
    table = info[["name", "short", "abbr", "conf", "color", "logo"]].join(r).join(stats).join(
        netplus[["netplus_rank", "netstyle_rank", "netplus_score", "wab_frozen", "wab_live"]])
    if prior is not None:
        pr = prior[["proj_em", "ret", "xfer_share"]].rename(columns={"proj_em": "pre_em", "ret": "pre_ret", "xfer_share": "pre_xfer"})
        table = table.join(pr)
        table["pre_rank"] = table["pre_em"].rank(ascending=False, method="min")
        gp = table["games"].fillna(0)
        table["prior_fade"] = config.PRIOR_FADE_GAMES
        table["prior_weight"] = config.PRIOR_GAMES * (1 - gp / config.PRIOR_FADE_GAMES).clip(lower=0)
    for c, asc in rank_cols.items():
        table[f"{c}_rank"] = table[c].rank(ascending=asc, method="min")
    table = table.sort_values("rank").reset_index()
    _write(out_dir / "ratings.json", _records(table))

    np_cols = [c for c in netplus.columns if c.startswith("q")] + [
        "netplus_rank", "netstyle_rank", "netplus_score", "wab_frozen", "wab_live"]
    npt = info[["name", "short", "conf", "logo"]].join(netplus[np_cols]).join(r[["rank", "adj_em"]]).join(
        stats[["wins", "losses"]]).sort_values("netplus_rank").reset_index()
    _write(out_dir / "netplus.json", _records(npt))

    # Per-team pages: game log, upcoming games, rank history.
    names = info["short"].to_dict()
    up = upcoming.copy()
    if len(up):
        p = predict(current, up["h_team_id"], up["a_team_id"], up["neutral_site"])
        up = pd.concat([up.reset_index(drop=True), p], axis=1)
    hist_dates = list(history.index)
    for tid in info.index:
        mine = game_rows[game_rows["team_id"] == tid].copy()
        mine["opp"] = mine["opp_id"].map(names).fillna("Non-D-I")
        log = mine[["game_date", "game_id", "opp_id", "opp", "location", "pts", "opp_pts", "win", "poss", "d1",
                    "opp_rank_frozen", "opp_rank_live", "quad_frozen", "quad_live", "wab_frozen", "wab_live",
                    "rank_source"]]
        nxt = []
        if len(up):
            u = up[(up["h_team_id"] == tid) | (up["a_team_id"] == tid)]
            for _, g in u.iterrows():
                home = g["h_team_id"] == tid
                opp = g["a_team_id"] if home else g["h_team_id"]
                nxt.append({
                    "game_date": g["game_date"], "opp_id": int(opp), "opp": names.get(opp, ""),
                    "location": "neutral" if g["neutral_site"] else ("home" if home else "away"),
                    "pts": _clean(g["pts_h"] if home else g["pts_a"]),
                    "opp_pts": _clean(g["pts_a"] if home else g["pts_h"]),
                    "win_prob": _clean(g["p_home"] if home else 1 - g["p_home"]),
                    "opp_rank": int(r.at[opp, "rank"]),
                })
        _write(out_dir / "teams" / f"{tid}.json", {
            "team": _records(table[table["team_id"] == tid])[0],
            "netplus": _records(netplus.loc[[tid]].reset_index())[0],
            "games": _records(log),
            "upcoming": nxt,
            "rank_history": {"dates": hist_dates, "ranks": [int(x) for x in history[tid].tolist()]}
            if tid in history.columns else None,
        })

    # Upcoming games, next 7 days.
    if len(up):
        last = (pd.Timestamp(as_of) + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        week = up[(up["game_date"] >= as_of) & (up["game_date"] <= last)].copy()
        week["home"] = week["h_team_id"].map(names)
        week["away"] = week["a_team_id"].map(names)
        week["h_rank"] = r["rank"].reindex(week["h_team_id"]).to_numpy()
        week["a_rank"] = r["rank"].reindex(week["a_team_id"]).to_numpy()
        week["tip"] = week["tip_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        cols = ["game_id", "game_date", "tip", "neutral_site", "h_team_id", "a_team_id", "home", "away",
                "h_rank", "a_rank", "pts_h", "pts_a", "margin", "p_home", "tempo"]
        _write(out_dir / "games.json", _records(week[cols]))
    else:
        _write(out_dir / "games.json", [])

    _write(out_dir / "meta.json", {
        "season": season,
        "season_label": f"{season - 1}-{str(season)[-2:]}",
        "as_of": as_of,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "games_rated": int(games["d1"].sum()),
        "national_avg_eff": round(current.mu, 2),
        "national_avg_tempo": round(current.mu_t, 2),
        "constants": {k: getattr(config, k) for k in (
            "HCA_POINTS", "FT_FACTOR", "MARGIN_SD", "PRIOR_GAMES", "PRIOR_FADE_GAMES",
            "PRIOR_REGRESS", "MARGIN_CAP", "BUBBLE_RANK", "NETPLUS_RESULTS_WEIGHT")},
        "rank_sources": sorted(set(game_rows["rank_source"].dropna())),
    })
