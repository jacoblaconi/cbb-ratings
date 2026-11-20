# CBB Ratings + NET+

KenPom-style adjusted efficiency ratings for D-I men's college basketball, plus **NET+**: a NET-style resume where every game is graded once, using the opponent's rank on the day the game was played.

The site is static. A GitHub Actions job rebuilds the data every morning and deploys `site/` to GitHub Pages.

## Pages

- **Ratings**: AdjEM, AdjO, AdjD, AdjT, luck, SOS, Four Factors, raw efficiency
- **NET+**: frozen quadrant records and wins above bubble, next to the same resume graded with today's ranks
- **Team**: game log with opponent rank and quadrant at game time vs today, rank by day, upcoming predictions
- **Games**: projected scores and win chances for the next 7 days
- **Method**: how it all works

## Run locally

```bash
pip install -r requirements.txt
python scripts/build_site.py            # downloads hoopR data, writes site/data/
python -m http.server -d site 8000      # open http://localhost:8000
python -m pytest -q
python scripts/backtest.py 2026         # predict every 2025-26 game using only earlier games
python scripts/backtest.py 2026 --grid  # re-tune the open constants
```

`--as-of YYYY-MM-DD` rebuilds the site as it would have looked on that morning.

## Layout

| Path | What it does |
| --- | --- |
| `cbb/data.py` | Downloads hoopR (ESPN) box scores and schedules, builds one row per game |
| `cbb/model.py` | Additive adjusted efficiency + tempo solver, predictions |
| `cbb/netplus.py` | Daily rank snapshots, frozen quadrants, wins above bubble, NET+ score |
| `cbb/export.py` | Team stats (Four Factors, luck, SOS) and JSON for the site |
| `cbb/config.py` | All model constants |
| `site/` | Static website (no build step) |

## Official NET (optional)

NET+ freezes our own AdjEM rank by default. To freeze the official NCAA NET instead, add `data/official_net/YYYY-MM-DD.csv` files with `team_id,rank` (ESPN team ids). From each file's date on, NET+ uses it.

## Data

ESPN data via [sportsdataverse/hoopR-mbb-data](https://github.com/sportsdataverse/hoopR-mbb-data). KenPom, Torvik and Haslam are used only as published-method references; nothing is scraped from them.
