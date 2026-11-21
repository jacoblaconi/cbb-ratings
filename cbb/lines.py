"""Betting lines for completed games, for the prediction tracker.

Source: the ESPN game summaries that sportsdataverse mirrors in hoopR-mbb-raw
(the same feed the box scores come from). Each finished game's summary has a
"pickcenter" block with the sportsbook line ESPN showed (DraftKings), which is
at or near the closing line. Only lines are kept: provider, home spread, total.

Fetched lines are cached in data/cache/lines_{season}.csv so each night only
newly finished games are downloaded. The nightly workflow keeps that file
between runs with actions/cache.
"""

from __future__ import annotations

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(os.environ.get("CBB_CACHE_DIR", Path(__file__).resolve().parent.parent / "data" / "cache"))
COLS = ["game_id", "provider", "home_spread", "total"]


def _fetch(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "cbb-ratings"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            d = json.loads(resp.read())
    except Exception:  # noqa: BLE001  (missing or partial summary: try again tomorrow)
        return None
    pc = d.get("pickcenter") or []
    pc = [p for p in pc if p.get("spread") is not None]
    if not pc:
        return {"provider": None, "home_spread": None, "total": None}
    p = sorted(pc, key=lambda p: (p.get("provider") or {}).get("priority", 99))[0]
    return {
        "provider": (p.get("provider") or {}).get("name"),
        "home_spread": float(p["spread"]),  # negative = home team favored
        "total": p.get("overUnder"),
    }




def load_lines(season: int, schedule: pd.DataFrame, game_ids, max_fetch: int = 3000,
               offline: bool = False) -> pd.DataFrame:
    """Lines for the given completed games (cached; fetches what's missing).

    Games checked with no line on file are cached as empty and not fetched again.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"lines_{season}.csv"
    cache = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=COLS)
    have = set(cache["game_id"].astype("int64"))
    want = [int(g) for g in game_ids if int(g) not in have]
    urls = schedule.set_index("game_id")["game_json_url"] if "game_json_url" in schedule else pd.Series(dtype=str)
    todo = [(g, urls.get(g)) for g in want if isinstance(urls.get(g), str)][:max_fetch]
    if todo and not offline:
        with ThreadPoolExecutor(16) as ex:
            got = list(ex.map(lambda t: _fetch(t[1]), todo))
        new = [{"game_id": g, **r} for (g, _), r in zip(todo, got) if r is not None]
        if new:
            cache = pd.concat([cache, pd.DataFrame(new, columns=COLS)], ignore_index=True)
            cache.to_csv(path, index=False)
    cache["game_id"] = cache["game_id"].astype("int64")
    return cache.dropna(subset=["home_spread"]).drop_duplicates("game_id", keep="last").set_index("game_id")
