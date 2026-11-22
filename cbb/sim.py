"""Season simulation: projected records, conference titles and bracketology.

Each simulation:
  1. draws every team's "true" strength around its current AdjEM
     (SIM_RATING_SD), so a sim season can run hot or cold for a team;
  2. plays every remaining scheduled game with the model's margin plus game noise;
  3. plays each conference tournament, seeded by simulated conference record
     (conference tournament games already played are respected: losers are out,
     a completed final locks the auto bid);
  4. picks the field: 31 automatic bids plus the best at-large teams by a
     NET+-style selection score (wins above bubble, frozen as graded on game
     day, blended with AdjEM), seeds the 68 on an S-curve, and
  5. plays the NCAA tournament (First Four included) on neutral courts.

Simplifications: every conference team enters its tournament, conference
tournaments are plain single elimination on neutral courts, and the bracket
ignores the committee's conference separation rules. Teams that are not yet
eligible (transitioning to D-I) are not filtered out.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import config
from .model import Ratings, phi
from .netplus import _bubble_prob

TOURNEY_RE = re.compile(r"Tournament|Championship|Playoffs", re.I)
FINAL_RE = re.compile(r" - (Final|Championship|Championship Game)$", re.I)
ROUNDS = ["r64", "r32", "s16", "e8", "f4", "final", "champ"]
REGION_SEED_ORDER = [1, 16, 8, 9, 5, 12, 4, 13, 6, 11, 3, 14, 7, 10, 2, 15]


def _bracket_order(p: int) -> list[int]:
    """Seed positions (0-based) for a single-elimination bracket of size p (power of 2)."""
    order = [0]
    while len(order) < p:
        m = len(order) * 2
        order = [x for s in order for x in (s, m - 1 - s)]
    return order


def conf_tourney_games(schedule: pd.DataFrame) -> pd.Series:
    """Boolean mask over schedule rows: conference tournament games.

    ESPN flags some in-season event games between league rivals as conference
    games with "Championship" in the headline, so only late-season games count.
    """
    h = schedule["notes_headline"].fillna("")
    md = schedule["game_date"].astype(str).str[5:]
    return ((md >= "02-25") & (md <= "03-31")
            & schedule["conference_competition"].fillna(False).astype(bool)
            & (schedule["season_type"] == 2) & h.str.contains(TOURNEY_RE) & ~h.str.contains("NCAA"))


class Sim:
    def __init__(self, r: Ratings, team_ids, n: int, rng: np.random.Generator):
        self.ids = np.asarray(team_ids, dtype=np.int64)
        self.pos = {t: i for i, t in enumerate(self.ids)}
        t = r.table.reindex(self.ids)
        self.em = t["adj_em"].to_numpy()
        self.tempo = t["adj_t"].to_numpy()
        self.mu_t = r.mu_t
        self.n, self.rng = n, rng
        k = len(self.ids)
        # True strength per sim (AdjEM units).
        self.true_em = self.em[None, :] + rng.normal(0, config.SIM_RATING_SD, (n, k))
        # Game noise left after rating noise, so total error matches MARGIN_SD.
        rating_pts = config.SIM_RATING_SD * r.mu_t / 100.0
        self.game_sd = float(np.sqrt(max(config.MARGIN_SD**2 - 2 * rating_pts**2, 25.0)))
        # Chance the bubble team beats each team at a neutral site (for WAB).
        self.bub_neutral = _bubble_prob(r, self.ids, np.zeros(k))
        self.hca = config.HCA_POINTS

    def play(self, a: np.ndarray, b: np.ndarray, a_home: np.ndarray | float = 0.0) -> np.ndarray:
        """Does team a beat team b? a, b: [n, m] team positions (sims x games). a_home: +1/0/-1."""
        rows = np.arange(self.n)[:, None]
        tempo = self.tempo[a] + self.tempo[b] - self.mu_t
        margin = (self.true_em[rows, a] - self.true_em[rows, b]) * tempo / 100.0 + np.asarray(a_home) * self.hca
        return margin + self.rng.normal(0, self.game_sd, margin.shape) > 0


def simulate(r: Ratings, teams: pd.DataFrame, stats: pd.DataFrame, netplus: pd.DataFrame,
             upcoming: pd.DataFrame, schedule: pd.DataFrame, games: pd.DataFrame,
             n: int | None = None, seed: int = 0) -> tuple[pd.DataFrame, dict]:
    """Return (per-team odds table, projected bracket dict)."""
    n = n or config.SIM_COUNT
    rng = np.random.default_rng(seed)
    ids = teams["team_id"].to_numpy(np.int64)
    sim = Sim(r, ids, n, rng)
    k = len(ids)
    conf = teams.set_index("team_id")["conf"].reindex(ids).fillna("").to_numpy()
    pos = sim.pos
    rows = np.arange(n)[:, None]

    st = stats.reindex(ids)
    wins = np.tile(st["wins"].fillna(0).to_numpy(float), (n, 1))
    losses = np.tile(st["losses"].fillna(0).to_numpy(float), (n, 1))
    cw = np.tile(st["conf_wins"].fillna(0).to_numpy(float), (n, 1))
    cl = np.tile(st["conf_losses"].fillna(0).to_numpy(float), (n, 1))
    wab = np.tile(netplus["wab_frozen"].reindex(ids).fillna(0).to_numpy(float), (n, 1))

    # ---- remaining regular season (conference tournament games are simulated separately)
    ct_ids = set(schedule.loc[conf_tourney_games(schedule), "game_id"].astype("int64"))
    sched_conf = schedule.set_index("game_id")["conference_competition"].fillna(False).astype(bool)
    up = upcoming[~upcoming["game_id"].isin(ct_ids)]
    up = up[up["h_team_id"].isin(pos) & up["a_team_id"].isin(pos)]
    if len(up):
        h = up["h_team_id"].map(pos).to_numpy()
        a = up["a_team_id"].map(pos).to_numpy()
        home = np.where(up["neutral_site"].to_numpy(bool), 0.0, 1.0)
        is_conf = sched_conf.reindex(up["game_id"]).fillna(False).to_numpy(bool)
        H, A = np.tile(h, (n, 1)), np.tile(a, (n, 1))
        hw = sim.play(H, A, home[None, :])
        # Bubble odds for each side's opponent, as the game would be graded today.
        bp_h = _bubble_prob(r, ids[a], home)   # bubble team in the home team's spot
        bp_a = _bubble_prob(r, ids[h], -home)
        for side, opp_win, bp in ((h, hw, bp_h), (a, ~hw, bp_a)):
            w = opp_win.astype(float)
            np.add.at(wins.T, side, w.T)
            np.add.at(losses.T, side, 1 - w.T)
            np.add.at(wab.T, side, (w - bp[None, :]).T)
            np.add.at(cw.T, side[is_conf], w[:, is_conf].T)
            np.add.at(cl.T, side[is_conf], 1 - w[:, is_conf].T)

    # Regular-season conference title (share of first place).
    cpct = cw / np.maximum(cw + cl, 1)
    reg_title = np.zeros(k)
    confs = sorted(c for c in set(conf) if c)
    for c in confs:
        m = np.where(conf == c)[0]
        best = cpct[:, m].max(axis=1, keepdims=True)
        reg_title[m] = (cpct[:, m] >= best - 1e-9).mean(axis=0)

    # ---- conference tournaments
    done = games.merge(schedule[["game_id", "notes_headline"]], on="game_id", how="left")
    done_ct = done[conf_tourney_games(done)]
    eliminated, locked = set(), {}
    for _, g in done_ct.iterrows():
        loser = g["a_team_id"] if g["h_team_score"] > g["a_team_score"] else g["h_team_id"]
        winner = g["h_team_id"] if loser == g["a_team_id"] else g["a_team_id"]
        eliminated.add(int(loser))
        if FINAL_RE.search(str(g["notes_headline"])):
            if int(winner) in pos:
                locked[conf[pos[int(winner)]]] = pos[int(winner)]

    auto = np.full((n, len(confs)), -1)
    for ci, c in enumerate(confs):
        if c in locked:
            auto[:, ci] = locked[c]
            continue
        m = np.array([i for i in np.where(conf == c)[0] if ids[i] not in eliminated])
        if len(m) == 0:
            continue
        if len(m) == 1:
            auto[:, ci] = m[0]
            continue
        # Seed by simulated conference win pct, rating as tiebreak.
        key = cpct[:, m] + 1e-4 * sim.true_em[:, m]
        seeded = m[np.argsort(-key, axis=1)]  # [n, len(m)]
        size = 1 << int(np.ceil(np.log2(len(m))))
        slots = np.full((n, size), -1)
        order = _bracket_order(size)
        for p, s in enumerate(order):
            if s < len(m):
                slots[:, p] = seeded[:, s]
        while slots.shape[1] > 1:
            x, y = slots[:, 0::2], slots[:, 1::2]
            both = (x >= 0) & (y >= 0)
            xw = np.where(both, sim.play(np.maximum(x, 0), np.maximum(y, 0)), x >= 0)
            win = np.where(xw, x, y)
            lose = np.where(xw, y, x)
            r_ = np.broadcast_to(rows, win.shape)[both]
            wi, li = win[both], lose[both]
            np.add.at(wins, (r_, wi), 1)
            np.add.at(losses, (r_, li), 1)
            np.add.at(wab, (r_, wi), 1 - sim.bub_neutral[li])
            np.add.at(wab, (r_, li), -sim.bub_neutral[wi])
            slots = win
        auto[:, ci] = slots[:, 0]

    # ---- selection
    z = lambda x: (x - x.mean(axis=1, keepdims=True)) / (x.std(axis=1, keepdims=True) + 1e-9)  # noqa: E731
    w = config.NETPLUS_RESULTS_WEIGHT
    score = w * z(wab) + (1 - w) * z(sim.true_em)
    is_auto = np.zeros((n, k), bool)
    valid = auto >= 0
    is_auto[np.broadcast_to(rows, auto.shape)[valid], auto[valid]] = True
    n_at = 68 - is_auto.sum(axis=1)
    at_score = np.where(is_auto, -np.inf, score)
    at_rank = np.argsort(np.argsort(-at_score, axis=1), axis=1)
    is_at = at_rank < n_at[:, None]
    in_field = is_auto | is_at

    # S-curve with First Four: last four at-large and four lowest auto bids play in.
    seed_line = np.zeros((n, k), int)
    ff = np.zeros((n, k), bool)
    rd = {name: np.zeros(k) for name in ROUNDS}
    curve = REGION_SEED_ORDER
    for s in range(n):
        f = np.where(in_field[s])[0]
        f = f[np.argsort(-score[s, f])]
        autos = [t for t in f if is_auto[s, t]]
        ats = [t for t in f if not is_auto[s, t]]
        ff_auto, ff_at = autos[-4:], ats[-4:]
        partner = {}
        for grp in (ff_at, ff_auto):
            if len(grp) == 4:
                partner[grp[0]], partner[grp[1]] = grp[3], grp[2]
        drop = set(partner.values())
        slots = [t for t in f if t not in drop][:64]
        # bracket[region][seed] = team (or play-in pair)
        region_slots = [[None] * 17 for _ in range(4)]
        for i, t in enumerate(slots):
            line, p = divmod(i, 4)
            reg = p if line % 2 == 0 else 3 - p
            region_slots[reg][line + 1] = t
            seed_line[s, t] = line + 1
            if t in partner:
                seed_line[s, partner[t]] = line + 1
                ff[s, t] = ff[s, partner[t]] = True
        # First Four
        field = []
        for reg in (0, 3, 1, 2):  # overall 1 meets overall 4 in the national semis
            for sd in curve:
                t = region_slots[reg][sd]
                if t in partner:
                    o = partner[t]
                    t = t if _play_one(sim, s, np.array([t]), np.array([o]))[0] else o
                field.append(t)
        bracket = np.array(field)
        for t in bracket:
            rd["r64"][t] += 1
        for name in ROUNDS[1:]:
            x, y = bracket[0::2], bracket[1::2]
            xw = _play_one(sim, s, x, y)
            bracket = np.where(xw, x, y)
            for t in bracket:
                rd[name][t] += 1

    out = pd.DataFrame(index=pd.Index(ids, name="team_id"))
    out["proj_w"] = wins.mean(axis=0)
    out["proj_l"] = losses.mean(axis=0)
    out["proj_cw"] = cw.mean(axis=0)
    out["proj_cl"] = cl.mean(axis=0)
    out["p_reg_title"] = reg_title
    out["p_auto"] = is_auto.mean(axis=0)
    out["p_at_large"] = is_at.mean(axis=0)
    out["p_field"] = in_field.mean(axis=0)
    out["p_first_four"] = ff.mean(axis=0)
    with np.errstate(invalid="ignore"):
        out["avg_seed"] = np.where(in_field, seed_line, 0).sum(axis=0) / in_field.sum(axis=0)
    for name in ROUNDS:
        out[f"p_{name}"] = rd[name] / n
    out["sel_score"] = score.mean(axis=0)
    out["proj_wab"] = wab.mean(axis=0)
    out["conf"] = conf
    return out, projected_bracket(out)


def _play_one(sim: Sim, s: int, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    tempo = sim.tempo[x] + sim.tempo[y] - sim.mu_t
    margin = (sim.true_em[s, x] - sim.true_em[s, y]) * tempo / 100.0
    return margin + sim.rng.normal(0, sim.game_sd, margin.shape) > 0


def projected_bracket(odds: pd.DataFrame) -> dict:
    """One bracket from the sim averages: likeliest auto bid per conference, then the
    best at-large teams by average selection score, seeded on an S-curve."""
    o = odds.copy()
    confs = [c for c in o["conf"].unique() if c]
    autos = [o[o["conf"] == c]["p_auto"].idxmax() for c in confs]
    pool = o.drop(index=autos).sort_values("sel_score", ascending=False)
    n_at = 68 - len(autos)
    ats = list(pool.index[:n_at])
    field = o.loc[autos + ats].sort_values("sel_score", ascending=False)
    a_sorted = [t for t in field.index if t in set(autos)]
    t_sorted = [t for t in field.index if t in set(ats)]
    ff_at, ff_auto = t_sorted[-4:], a_sorted[-4:]
    partner = {}
    for grp in (ff_at, ff_auto):
        if len(grp) == 4:
            partner[grp[0]], partner[grp[1]] = grp[3], grp[2]
    drop = set(partner.values())
    slots = [t for t in field.index if t not in drop][:64]
    seeds = []
    for i, t in enumerate(slots):
        line, p = divmod(i, 4)
        reg = p if line % 2 == 0 else 3 - p
        for tt in ([t, partner[t]] if t in partner else [t]):
            seeds.append({"team_id": int(tt), "seed": line + 1, "region": reg, "overall": i + 1,
                          "auto": tt in set(autos), "first_four": tt in partner or tt in drop})
    rest = pool.index[n_at:]
    return {
        "seeds": seeds,
        "last_four_byes": [int(t) for t in t_sorted[-8:-4]],
        "last_four_in": [int(t) for t in ff_at],
        "first_four_out": [int(t) for t in rest[:4]],
        "next_four_out": [int(t) for t in rest[4:8]],
    }
