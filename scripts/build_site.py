"""Nightly build: download data, compute ratings and NET+, write site/data/*.json.

Usage: python scripts/build_site.py [--season 2027] [--as-of YYYY-MM-DD] [--refresh]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cbb import netplus  # noqa: E402
from cbb import sim, tracker  # noqa: E402
from cbb.data import load_games, load_schedule  # noqa: E402
from cbb.export import export, team_stats  # noqa: E402
from cbb.lines import load_lines  # noqa: E402
from cbb.model import solve  # noqa: E402
from cbb.players import load_player_box, player_ratings  # noqa: E402
from cbb.prior import build_prior  # noqa: E402


def current_season(today: datetime) -> int:
    return today.year + 1 if today.month >= 8 else today.year


def main() -> None:
    today = datetime.now(ZoneInfo("America/New_York"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=current_season(today))
    ap.add_argument("--as-of", default=None, help="rate games before this date (default: today, US Eastern)")
    ap.add_argument("--refresh", action="store_true", help="re-download data files")
    ap.add_argument("--out", default=str(ROOT / "site" / "data"))
    ap.add_argument("--sims", type=int, default=None, help="season simulations (default config.SIM_COUNT)")
    ap.add_argument("--no-lines", action="store_true", help="don't download betting lines (use the cache only)")
    args = ap.parse_args()
    t0 = time.time()

    # Preseason prior: last season's ratings adjusted for returning production,
    # transfers in and (optional) recruiting. Fades out as games are played.
    prior = build_prior(args.season, refresh=args.refresh)

    games, upcoming, teams = load_games(args.season, refresh=args.refresh)
    as_of = args.as_of or today.strftime("%Y-%m-%d")
    games = games[games["game_date"] < as_of]
    upcoming = upcoming[upcoming["game_date"] >= as_of]

    current = solve(games, teams["team_id"], as_of, prior)
    snaps: dict = {}
    rows, summ, hist = netplus.build(games, teams, prior, current, snapshots=snaps)
    stats = team_stats(games, teams, current)
    t1 = time.time()

    # Prediction tracker: morning-of picks for every game, scored vs results and lines.
    schedule = load_schedule(args.season)
    lines = load_lines(args.season, schedule, games.loc[games["d1"], "game_id"], offline=args.no_lines)
    picks = tracker.pregame(games, snaps, lines)
    track = tracker.report(picks, as_of)
    t2 = time.time()

    # Players.
    pbox = load_player_box(args.season, games["game_id"], refresh=args.refresh)
    players = player_ratings(pbox, teams["team_id"], current.mu)

    # Season simulation and bracketology (seeded by date so a rebuild is reproducible).
    odds, bracket = sim.simulate(current, teams, stats, summ, upcoming, schedule, games,
                                 n=args.sims, seed=int(as_of.replace("-", "")))
    t3 = time.time()

    export(Path(args.out), args.season, as_of, games, upcoming, teams, current, rows, summ, hist, prior,
           stats=stats, players=players, tracker=track, odds=odds, bracket=bracket)
    o = track["overall"]
    if o.get("games"):
        print(f"tracker: {o['games']} games, {o['su_w']}-{o['su_l']} straight up, MAE {o['mae']:.2f}, "
              f"{o['lined']} with lines, ATS {o['ats']['w']}-{o['ats']['l']}-{o['ats']['p']} ({t2 - t1:.1f}s)")
    print(f"players: {len(players)}; simulation: {t3 - t2:.1f}s")

    top = current.table.sort_values("rank").head(5).join(teams.set_index("team_id")["short"])
    print(f"season {args.season} as of {as_of}: {int(games['d1'].sum())} D-I games, "
          f"{len(upcoming)} upcoming, built in {time.time() - t0:.1f}s")
    print(top[["short", "adj_em", "adj_o", "adj_d", "adj_t"]].round(1).to_string())


if __name__ == "__main__":
    main()
