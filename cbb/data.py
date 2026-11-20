"""Download and shape hoopR (ESPN) data into one row per game."""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

RELEASES = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
FILES = {
    "team_box": "espn_mens_college_basketball_team_boxscores/team_box_{season}.parquet",
    "schedule": "espn_mens_college_basketball_schedules/mbb_schedule_{season}.parquet",
}

RAW_DIR = Path(os.environ.get("CBB_RAW_DIR", Path(__file__).resolve().parent.parent / "data" / "raw"))


def download(kind: str, season: int, refresh: bool = False) -> Path:
    """Fetch one hoopR parquet file into data/raw (cached unless refresh)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rel = FILES[kind].format(season=season)
    dest = RAW_DIR / rel.split("/")[-1]
    if dest.exists() and not refresh:
        return dest
    tmp = dest.with_suffix(".tmp")
    req = urllib.request.Request(f"{RELEASES}/{rel}", headers={"User-Agent": "cbb-ratings"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(tmp, "wb") as fh:
        fh.write(resp.read())
    tmp.replace(dest)
    return dest


def load_schedule(season: int, refresh: bool = False) -> pd.DataFrame:
    s = pd.read_parquet(download("schedule", season, refresh))
    s = s[s["season_type"].isin([2, 3])].copy()
    s["game_id"] = s["id"].astype("int64")
    # Local (Eastern) calendar date of tip-off.
    tip = pd.to_datetime(s["date"], utc=True, errors="coerce")
    s["tip_utc"] = tip
    s["game_date"] = tip.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    return s.drop_duplicates("game_id")


def d1_teams(schedule: pd.DataFrame) -> pd.DataFrame:
    """Teams with a D-I conference id in the schedule, with display info."""
    cols = {
        "id": "team_id", "display_name": "name", "location": "short", "abbreviation": "abbr",
        "color": "color", "logo": "logo", "conference_id": "conf_id",
    }
    parts = []
    for side in ("home", "away"):
        p = schedule[[f"{side}_{c}" for c in cols]].copy()
        p.columns = list(cols.values())
        parts.append(p)
    t = pd.concat(parts).dropna(subset=["conf_id"]).drop_duplicates("team_id")
    t["team_id"] = t["team_id"].astype("int64")
    t["conf_id"] = t["conf_id"].astype("int64")
    conf_names = (
        schedule[schedule["conference_competition"] == True]  # noqa: E712
        .dropna(subset=["groups_id"])
        .drop_duplicates("groups_id")
        .set_index("groups_id")["groups_short_name"]
    )
    t["conf"] = t["conf_id"].map(conf_names).fillna("")
    return t.sort_values("name").reset_index(drop=True)


def _possessions(box: pd.DataFrame) -> pd.Series:
    return (
        box["field_goals_attempted"]
        - box["offensive_rebounds"]
        + box["total_turnovers"]
        + config.FT_FACTOR * box["free_throws_attempted"]
    )


def load_games(season: int, refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (games, upcoming, teams).

    games: one row per completed game between two teams with box scores,
    oriented home/away (neutral games keep ESPN's listed home team).
    upcoming: scheduled games not yet played.
    teams: D-I teams.
    """
    sched = load_schedule(season, refresh)
    teams = d1_teams(sched)
    d1 = set(teams["team_id"])

    box = pd.read_parquet(download("team_box", season, refresh))
    box = box[box["season_type"].isin([2, 3])].copy()
    box["poss"] = _possessions(box)
    keep = [
        "game_id", "team_id", "team_home_away", "team_score", "poss",
        "field_goals_made", "field_goals_attempted", "three_point_field_goals_made",
        "free_throws_attempted", "free_throws_made", "offensive_rebounds", "defensive_rebounds",
        "total_turnovers",
    ]
    box = box[keep].dropna(subset=["team_score", "poss"])
    home = box[box["team_home_away"] == "home"].drop(columns="team_home_away").add_prefix("h_")
    away = box[box["team_home_away"] == "away"].drop(columns="team_home_away").add_prefix("a_")
    g = home.merge(away, left_on="h_game_id", right_on="a_game_id").rename(columns={"h_game_id": "game_id"})
    g = g.drop(columns="a_game_id")

    meta = sched[["game_id", "game_date", "neutral_site", "status_period", "season_type", "conference_competition"]]
    g = g.merge(meta, on="game_id", how="left")
    g = g[g["h_team_score"].notna() & (g["h_team_score"] + g["a_team_score"] > 0)].copy()
    g["neutral_site"] = g["neutral_site"].fillna(False).astype(bool)
    g["conference_competition"] = g["conference_competition"].fillna(False).astype(bool)
    periods = g["status_period"].fillna(2).clip(lower=2)
    g["minutes"] = 40 + 5 * (periods - 2)
    g["poss"] = (g["h_poss"] + g["a_poss"]) / 2.0
    g["h_team_id"] = g["h_team_id"].astype("int64")
    g["a_team_id"] = g["a_team_id"].astype("int64")
    g["d1"] = g["h_team_id"].isin(d1) & g["a_team_id"].isin(d1)
    g = g[g["poss"] > 30].sort_values(["game_date", "game_id"]).reset_index(drop=True)

    played = set(g["game_id"])
    up = sched[~sched["game_id"].isin(played) & (sched["status_type_completed"] != True)]  # noqa: E712
    up = up[["game_id", "game_date", "tip_utc", "neutral_site", "home_id", "away_id"]].dropna(subset=["home_id", "away_id"])
    up = up.rename(columns={"home_id": "h_team_id", "away_id": "a_team_id"})
    up["h_team_id"] = up["h_team_id"].astype("int64")
    up["a_team_id"] = up["a_team_id"].astype("int64")
    up["neutral_site"] = up["neutral_site"].fillna(False).astype(bool)
    up = up[up["h_team_id"].isin(d1) & up["a_team_id"].isin(d1)].sort_values("tip_utc").reset_index(drop=True)
    return g, up, teams


def recency_weights(game_dates: pd.Series, as_of: str) -> np.ndarray:
    age = (pd.Timestamp(as_of) - pd.to_datetime(game_dates)).dt.days.to_numpy(dtype=float)
    w = 1.0 - config.RECENCY_DECAY_PER_DAY * np.clip(age - config.RECENCY_FULL_DAYS, 0, None)
    return np.clip(w, config.RECENCY_FLOOR, 1.0)
