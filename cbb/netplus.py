"""NET+: a NET-style resume where every game is graded once, on the day it is played.

Each morning's rankings are saved as a snapshot. A game's quadrant, opponent
rank and wins-above-bubble value come from the snapshot taken the morning of
the game, and never change afterwards. The same grading against today's
rankings ("live") is kept alongside for comparison.

Rank source for snapshots: our own AdjEM rank, unless official NCAA NET ranks
for a date are provided as data/official_net/YYYY-MM-DD.csv (columns
team_id,rank, ESPN team ids). The newest file on or before a game date wins.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .model import Ratings, phi, solve

OFFICIAL_NET_DIR = Path(__file__).resolve().parent.parent / "data" / "official_net"


def quadrant(rank, location: str) -> int:
    q1, q2, q3 = config.QUADRANTS[location]
    if rank <= q1:
        return 1
    if rank <= q2:
        return 2
    if rank <= q3:
        return 3
    return 4


def _official_ranks() -> dict[str, pd.Series]:
    out = {}
    if OFFICIAL_NET_DIR.exists():
        for f in sorted(OFFICIAL_NET_DIR.glob("*.csv")):
            df = pd.read_csv(f)
            out[f.stem] = df.set_index("team_id")["rank"].astype(int)
    return out


def _bubble_prob(r: Ratings, opp_ids: np.ndarray, loc: np.ndarray) -> np.ndarray:
    """Chance a bubble-rank team wins this game. loc: +1 bubble home, 0 neutral, -1 away."""
    t = r.table.sort_values("rank")
    bub = t.iloc[min(config.BUBBLE_RANK, len(t)) - 1]
    o = t.reindex(opp_ids)
    tempo = r.mu_t + (bub["adj_t"] - r.mu_t) + (o["adj_t"].to_numpy() - r.mu_t)
    hca = loc * 100.0 * (config.HCA_POINTS / 2.0) / tempo
    oe_b = bub["adj_o"] + o["adj_d"].to_numpy() - r.mu + hca
    oe_o = o["adj_o"].to_numpy() + bub["adj_d"] - r.mu - hca
    margin = (oe_b - oe_o) * tempo / 100.0
    return phi(margin / config.MARGIN_SD)


def _team_rows(g: pd.DataFrame) -> pd.DataFrame:
    """Two rows per game: one from each team's side."""
    base = {
        "game_id": g["game_id"], "game_date": g["game_date"], "neutral": g["neutral_site"],
        "conf_game": g["conference_competition"], "d1": g["d1"], "poss": g["poss"],
    }
    h = pd.DataFrame({**base, "team_id": g["h_team_id"], "opp_id": g["a_team_id"],
                      "pts": g["h_team_score"], "opp_pts": g["a_team_score"], "side": "home"})
    a = pd.DataFrame({**base, "team_id": g["a_team_id"], "opp_id": g["h_team_id"],
                      "pts": g["a_team_score"], "opp_pts": g["h_team_score"], "side": "away"})
    rows = pd.concat([h, a], ignore_index=True)
    rows["location"] = np.where(rows["neutral"], "neutral", rows["side"])
    rows["win"] = (rows["pts"] > rows["opp_pts"]).astype(int)
    return rows.sort_values(["game_date", "game_id"]).reset_index(drop=True)


def build(games: pd.DataFrame, teams: pd.DataFrame, prior: pd.DataFrame | None, current: Ratings,
          snapshots: dict | None = None):
    """Return (game_rows, team_summary, rank_history).

    If `snapshots` is a dict, each morning's Ratings are stored in it by date
    (the prediction tracker reuses them)."""
    ids = teams["team_id"]
    official = _official_ranks()
    official_dates = sorted(official)

    rows = _team_rows(games)
    d1 = rows[rows["d1"]].copy()
    loc_num = d1["location"].map({"home": 1.0, "neutral": 0.0, "away": -1.0}).to_numpy()

    frozen_rank = np.zeros(len(d1), dtype=int)
    frozen_p = np.zeros(len(d1))
    source = np.empty(len(d1), dtype=object)
    history = {}
    for day, idx in d1.groupby("game_date").indices.items():
        snap = solve(games, ids, day, prior)
        if snapshots is not None:
            snapshots[day] = snap
        history[day] = snap.table["rank"]
        ranks = snap.table["rank"]
        src = "model"
        usable = [d for d in official_dates if d <= day]
        if usable:
            ranks = official[usable[-1]].reindex(ranks.index).fillna(ranks).astype(int)
            src = "net"
        opp = d1["opp_id"].to_numpy()[idx]
        frozen_rank[idx] = ranks.reindex(opp).to_numpy()
        frozen_p[idx] = _bubble_prob(snap, opp, loc_num[idx])
        source[idx] = src

    d1["opp_rank_frozen"] = frozen_rank
    d1["rank_source"] = source
    d1["opp_rank_live"] = current.table["rank"].reindex(d1["opp_id"]).to_numpy().astype(int)
    d1["quad_frozen"] = [quadrant(r, l) for r, l in zip(d1["opp_rank_frozen"], d1["location"])]
    d1["quad_live"] = [quadrant(r, l) for r, l in zip(d1["opp_rank_live"], d1["location"])]
    d1["wab_frozen"] = d1["win"] - frozen_p
    d1["wab_live"] = d1["win"] - _bubble_prob(current, d1["opp_id"].to_numpy(), loc_num)

    out = rows.merge(
        d1[["game_id", "team_id", "opp_rank_frozen", "opp_rank_live", "quad_frozen", "quad_live",
            "wab_frozen", "wab_live", "rank_source"]],
        on=["game_id", "team_id"], how="left",
    )

    summ = pd.DataFrame(index=pd.Index(ids, name="team_id"))
    grp = d1.groupby("team_id")
    summ["wab_frozen"] = grp["wab_frozen"].sum()
    summ["wab_live"] = grp["wab_live"].sum()
    for kind in ("frozen", "live"):
        for q in (1, 2, 3, 4):
            sel = d1[d1[f"quad_{kind}"] == q].groupby("team_id")["win"]
            summ[f"q{q}_{kind}_w"] = sel.sum()
            summ[f"q{q}_{kind}_l"] = sel.count() - sel.sum()
    summ = summ.fillna(0)
    for c in summ.columns:
        if c.startswith("q"):
            summ[c] = summ[c].astype(int)

    em = current.table["adj_em"].reindex(summ.index)
    z = lambda s: (s - s.mean()) / (s.std() or 1.0)  # noqa: E731
    w = config.NETPLUS_RESULTS_WEIGHT
    summ["netplus_score"] = w * z(summ["wab_frozen"]) + (1 - w) * z(em)
    summ["netplus_rank"] = summ["netplus_score"].rank(ascending=False, method="first").astype(int)
    summ["netstyle_score"] = w * z(summ["wab_live"]) + (1 - w) * z(em)
    summ["netstyle_rank"] = summ["netstyle_score"].rank(ascending=False, method="first").astype(int)

    hist = pd.DataFrame(history).T.sort_index()
    return out, summ, hist
