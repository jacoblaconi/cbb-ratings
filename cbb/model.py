"""KenPom-style adjusted efficiency and tempo.

Additive model, solved for every team at once by weighted ridge least squares:

    game offensive efficiency (home court removed)
        = national average + team offense term + opponent defense term

AdjO = average + offense term, AdjD = average + defense term, AdjEM = AdjO - AdjD.
Tempo uses the same structure with possessions per 40 minutes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config
from .data import recency_weights


@dataclass
class Ratings:
    table: pd.DataFrame  # index team_id: adj_o, adj_d, adj_em, adj_t, games
    mu: float            # national average efficiency (points per 100 possessions)
    mu_t: float          # national average tempo (possessions per 40 minutes)

    def prior(self, regress: float = config.PRIOR_REGRESS) -> pd.DataFrame:
        """This table as a preseason prior for next season (relative to average)."""
        keep = 1.0 - regress
        return pd.DataFrame(
            {
                "o_rel": keep * (self.table["adj_o"] - self.mu),
                "d_rel": keep * (self.table["adj_d"] - self.mu),
                "t_rel": keep * (self.table["adj_t"] - self.mu_t),
            }
        )


def damp_margins(oe_h: np.ndarray, oe_a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Shrink efficiency margins beyond MARGIN_CAP, keeping the game's average."""
    mid = (oe_h + oe_a) / 2.0
    m = oe_h - oe_a
    excess = np.clip(np.abs(m) - config.MARGIN_CAP, 0, None)
    m2 = np.sign(m) * (np.abs(m) - excess * (1.0 - config.MARGIN_SLOPE))
    return mid + m2 / 2.0, mid - m2 / 2.0


def _accumulate(N: np.ndarray, b: np.ndarray, cols: list[np.ndarray], y: np.ndarray, w: np.ndarray) -> None:
    """Add rows (each the sum of the given unknowns, all coefficient 1) to the normal equations."""
    for ci in cols:
        np.add.at(b, ci, w * y)
        for cj in cols:
            np.add.at(N, (ci, cj), w)


def solve(
    games: pd.DataFrame,
    team_ids,
    as_of: str,
    prior: pd.DataFrame | None = None,
) -> Ratings:
    """Ratings using D-I games played before `as_of` (YYYY-MM-DD)."""
    team_ids = np.asarray(sorted(team_ids), dtype=np.int64)
    n = len(team_ids)
    pos = {t: i for i, t in enumerate(team_ids)}
    g = games[games["d1"] & (games["game_date"] < as_of)]

    gp = np.zeros(n)
    if len(g):
        hi = g["h_team_id"].map(pos).to_numpy()
        ai = g["a_team_id"].map(pos).to_numpy()
        np.add.at(gp, hi, 1)
        np.add.at(gp, ai, 1)

    # Prior pseudo-games: worth PRIOR_GAMES, fading out by PRIOR_FADE_GAMES.
    wp = config.PRIOR_GAMES * np.clip(1.0 - gp / config.PRIOR_FADE_GAMES, 0, None)
    if prior is not None:
        pr = prior.reindex(team_ids)
        # Teams without a prior (new to D-I) start a little below average.
        p_o = pr["o_rel"].fillna(-3.0).to_numpy()
        p_d = pr["d_rel"].fillna(3.0).to_numpy()
        p_t = pr["t_rel"].fillna(0.0).to_numpy()
    else:
        p_o = p_d = p_t = np.zeros(n)
        wp = np.zeros(n)

    # ---- efficiency: unknowns o[0:n], d[n:2n], mu[2n]
    N = np.zeros((2 * n + 1, 2 * n + 1))
    b = np.zeros(2 * n + 1)
    mu_i = 2 * n
    if len(g):
        poss = g["poss"].to_numpy(float)
        oe_h = 100.0 * g["h_team_score"].to_numpy(float) / poss
        oe_a = 100.0 * g["a_team_score"].to_numpy(float) / poss
        oe_h, oe_a = damp_margins(oe_h, oe_a)
        home = (~g["neutral_site"].to_numpy(bool)).astype(float)
        hca_side = home * 100.0 * (config.HCA_POINTS / 2.0) / poss
        w = recency_weights(g["game_date"], as_of)
        mu_col = np.full(len(g), mu_i)
        _accumulate(N, b, [hi, n + ai, mu_col], oe_h - hca_side, w)
        _accumulate(N, b, [ai, n + hi, mu_col], oe_a + hca_side, w)
    idx = np.arange(n)
    N[idx, idx] += wp + config.RIDGE
    b[idx] += wp * p_o
    N[n + idx, n + idx] += wp + config.RIDGE
    b[n + idx] += wp * p_d
    if N[mu_i, mu_i] == 0:  # no games yet: anchor the average
        N[mu_i, mu_i] = 1.0
        b[mu_i] = 104.0
    x = np.linalg.solve(N, b)
    o, d, mu = x[:n], x[n : 2 * n], x[mu_i]
    # Center so average AdjO = average AdjD = mu (prediction-invariant shift).
    mu = mu + o.mean() + d.mean()
    o, d = o - o.mean(), d - d.mean()

    # ---- tempo: unknowns t[0:n], mu_t[n]
    Nt = np.zeros((n + 1, n + 1))
    bt = np.zeros(n + 1)
    if len(g):
        p40 = 40.0 * g["poss"].to_numpy(float) / g["minutes"].to_numpy(float)
        _accumulate(Nt, bt, [hi, ai, np.full(len(g), n)], p40, w)
    Nt[idx, idx] += wp + config.RIDGE
    bt[idx] += wp * p_t
    if Nt[n, n] == 0:
        Nt[n, n] = 1.0
        bt[n] = 68.0
    xt = np.linalg.solve(Nt, bt)
    t, mu_t = xt[:n], xt[n]
    mu_t = mu_t + 2 * t.mean()
    t = t - t.mean()

    table = pd.DataFrame(
        {"adj_o": mu + o, "adj_d": mu + d, "adj_t": mu_t + t, "games": gp},
        index=pd.Index(team_ids, name="team_id"),
    )
    table["adj_em"] = table["adj_o"] - table["adj_d"]
    table["rank"] = table["adj_em"].rank(ascending=False, method="first").astype(int)
    return Ratings(table=table, mu=float(mu), mu_t=float(mu_t))


def phi(z):
    z = np.asarray(z, dtype=float)
    return 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2.0)))


def predict(r: Ratings, h_ids, a_ids, neutral) -> pd.DataFrame:
    """Expected score, margin (home minus away) and home win probability."""
    t = r.table
    h = t.reindex(np.asarray(h_ids))
    a = t.reindex(np.asarray(a_ids))
    tempo = r.mu_t + (h["adj_t"].to_numpy() - r.mu_t) + (a["adj_t"].to_numpy() - r.mu_t)
    home = (~np.asarray(neutral, dtype=bool)).astype(float)
    hca_side = home * 100.0 * (config.HCA_POINTS / 2.0) / tempo
    oe_h = h["adj_o"].to_numpy() + a["adj_d"].to_numpy() - r.mu + hca_side
    oe_a = a["adj_o"].to_numpy() + h["adj_d"].to_numpy() - r.mu - hca_side
    pts_h = oe_h * tempo / 100.0
    pts_a = oe_a * tempo / 100.0
    margin = pts_h - pts_a
    return pd.DataFrame(
        {
            "tempo": tempo,
            "pts_h": pts_h,
            "pts_a": pts_a,
            "margin": margin,
            "p_home": phi(margin / config.MARGIN_SD),
        }
    )
