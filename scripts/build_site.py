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
from cbb.data import load_games  # noqa: E402
from cbb.export import export  # noqa: E402
from cbb.model import solve  # noqa: E402
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
    rows, summ, hist = netplus.build(games, teams, prior, current)
    export(Path(args.out), args.season, as_of, games, upcoming, teams, current, rows, summ, hist, prior)

    top = current.table.sort_values("rank").head(5).join(teams.set_index("team_id")["short"])
    print(f"season {args.season} as of {as_of}: {int(games['d1'].sum())} D-I games, "
          f"{len(upcoming)} upcoming, built in {time.time() - t0:.1f}s")
    print(top[["short", "adj_em", "adj_o", "adj_d", "adj_t"]].round(1).to_string())


if __name__ == "__main__":
    main()
