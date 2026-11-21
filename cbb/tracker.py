"""Prediction tracker: every D-I game, predicted the morning it was played.

Each pick comes from the ratings snapshot taken the morning of the game
(games before that date only, same code and constants as today's ratings).
Picks are rebuilt every night rather than logged, so they are exactly what the
current model would have said before tip-off. Where a betting line is on file
(see lines.py), the pick is also scored against the spread and the total.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .model import Ratings, predict

EDGE = 3.0  # points of disagreement with the spread for the "big edge" split


def pregame(games: pd.DataFrame, snapshots: dict[str, Ratings], lines: pd.DataFrame | None = None) -> pd.DataFrame:
    g = games[games["d1"]]
    parts = []
    for day, today in g.groupby("game_date"):
        snap = snapshots.get(day)
        if snap is None:
            continue
        p = predict(snap, today["h_team_id"], today["a_team_id"], today["neutral_site"])
        parts.append(pd.DataFrame({
            "game_id": today["game_id"].to_numpy(), "game_date": day,
            "h_team_id": today["h_team_id"].to_numpy(), "a_team_id": today["a_team_id"].to_numpy(),
            "neutral_site": today["neutral_site"].to_numpy(),
            "h_score": today["h_team_score"].to_numpy(), "a_score": today["a_team_score"].to_numpy(),
            "pts_h": p["pts_h"].to_numpy(), "pts_a": p["pts_a"].to_numpy(),
            "margin": p["margin"].to_numpy(), "p_home": p["p_home"].to_numpy(),
        }))
    if not parts:
        return pd.DataFrame()
    d = pd.concat(parts, ignore_index=True)
    d["act_margin"] = d["h_score"] - d["a_score"]
    d["act_total"] = d["h_score"] + d["a_score"]
    d["pred_total"] = d["pts_h"] + d["pts_a"]
    d["correct"] = (d["margin"] > 0) == (d["act_margin"] > 0)
    if lines is not None and len(lines):
        d = d.join(lines[["home_spread", "total", "provider"]].rename(columns={"total": "line_total"}), on="game_id")
    else:
        d["home_spread"] = np.nan
        d["line_total"] = np.nan
        d["provider"] = None
    # Against the spread: model takes home if it expects home to beat the line.
    vegas = -d["home_spread"]
    d["ats_edge"] = d["margin"] - vegas
    cover = d["act_margin"] - vegas
    d["ats"] = np.where(d["home_spread"].isna() | (d["ats_edge"] == 0), None,
                        np.where(cover == 0, "P", np.where((cover > 0) == (d["ats_edge"] > 0), "W", "L")))
    ou = d["act_total"] - d["line_total"]
    d["ou_edge"] = d["pred_total"] - d["line_total"]
    d["ou"] = np.where(d["line_total"].isna() | (d["ou_edge"] == 0), None,
                       np.where(ou == 0, "P", np.where((ou > 0) == (d["ou_edge"] > 0), "W", "L")))
    return d


def _rec(s: pd.Series) -> dict:
    s = s.dropna()
    return {"w": int((s == "W").sum()), "l": int((s == "L").sum()), "p": int((s == "P").sum())}


def summarize(d: pd.DataFrame) -> dict:
    if d.empty:
        return {"games": 0}
    won = (d["act_margin"] > 0).astype(float)
    p = d["p_home"].clip(1e-6, 1 - 1e-6)
    lined = d[d["home_spread"].notna()]
    out = {
        "games": int(len(d)),
        "su_w": int(d["correct"].sum()), "su_l": int((~d["correct"]).sum()),
        "mae": float((d["margin"] - d["act_margin"]).abs().mean()),
        "rmse": float(np.sqrt(((d["margin"] - d["act_margin"]) ** 2).mean())),
        "brier": float(((d["p_home"] - won) ** 2).mean()),
        "log_loss": float(-(won * np.log(p) + (1 - won) * np.log(1 - p)).mean()),
        "total_mae": float((d["pred_total"] - d["act_total"]).abs().mean()),
        "lined": int(len(lined)),
        "ats": _rec(d["ats"]),
        "ats_big": _rec(d.loc[d["ats_edge"].abs() >= EDGE, "ats"]),
        "ou": _rec(d["ou"]),
    }
    if len(lined):
        vm = -lined["home_spread"]
        out["model_mae_lined"] = float((lined["margin"] - lined["act_margin"]).abs().mean())
        out["vegas_mae"] = float((vm - lined["act_margin"]).abs().mean())
        fav = vm != 0
        out["vegas_su_w"] = int(((vm[fav] > 0) == (lined["act_margin"][fav] > 0)).sum())
        out["vegas_su_n"] = int(fav.sum())
        out["model_su_w_lined"] = int(lined.loc[fav, "correct"].sum())
    return out


def report(d: pd.DataFrame, as_of: str, recent_days: int = 14) -> dict:
    if d.empty:
        return {"overall": {"games": 0}, "last7": {"games": 0}, "weeks": [], "calibration": [], "games": []}
    last7 = (pd.Timestamp(as_of) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    dt = pd.to_datetime(d["game_date"])
    wk = (dt - pd.to_timedelta(dt.dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")  # Monday
    weeks = [{"week": w, **summarize(x)} for w, x in d.groupby(wk)]
    # Calibration: favorite's predicted chance vs how often favorites won.
    fav_p = np.maximum(d["p_home"], 1 - d["p_home"])
    fav_won = np.where(d["p_home"] >= 0.5, d["act_margin"] > 0, d["act_margin"] < 0)
    bins = np.array([0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0001])
    b = np.digitize(fav_p, bins) - 1
    cal = [{"lo": float(bins[i]), "hi": float(min(bins[i + 1], 1.0)), "n": int((b == i).sum()),
            "pred": float(fav_p[b == i].mean()), "actual": float(fav_won[b == i].mean())}
           for i in range(len(bins) - 1) if (b == i).sum()]
    cutoff = (pd.Timestamp(as_of) - pd.Timedelta(days=recent_days)).strftime("%Y-%m-%d")
    return {
        "overall": summarize(d),
        "last7": summarize(d[d["game_date"] >= last7]),
        "weeks": weeks,
        "calibration": cal,
        "games": d[d["game_date"] >= cutoff].sort_values(["game_date", "game_id"], ascending=[False, True]),
    }
