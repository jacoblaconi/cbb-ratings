"""Model constants. Values marked "tuned" were chosen by scripts/backtest.py."""

# Possessions: FGA - ORB + TO + FT_FACTOR * FTA (KenPom glossary)
FT_FACTOR = 0.475

# Home-court advantage in points per game (KenPom's current flat value)
HCA_POINTS = 3.75

# Recency weighting, Torvik's published schedule: full weight for 40 days,
# then -1% per day until a floor of 60% at 80 days.
RECENCY_FULL_DAYS = 40
RECENCY_DECAY_PER_DAY = 0.01
RECENCY_FLOOR = 0.60

# Blowout damping: game efficiency margins (per 100 possessions) beyond
# MARGIN_CAP count at MARGIN_SLOPE of their size. (tuned)
MARGIN_CAP = 40.0
MARGIN_SLOPE = 0.5

# Preseason prior: last season's final ratings, regressed toward average,
# worth PRIOR_GAMES games of data and fading to zero after PRIOR_FADE_GAMES
# games played (tuned; Torvik phases his prior out after about 13).
PRIOR_GAMES = 6.0
PRIOR_FADE_GAMES = 18
PRIOR_REGRESS = 0.20  # share of the way back to average

# Roster-aware prior projection (scripts/fit_prior.py on 2024-25 and 2025-26).
# Projected AdjEM (vs average) = sum(coef * feature) + intercept, where
#   em_prev: last season's AdjEM, ret: share of last season's production returning,
#   em_ret: em_prev * ret, xfer_em: transfers' production share x old team's AdjEM,
#   xfer_share: transfers' total production share at their old teams, capped so
#   ret + xfer_share is at most one roster.
PRIOR_COEF = {"em_ret": 0.433, "em_prev": 0.581, "ret": 8.174, "xfer_em": 0.648,
              "xfer_share": 11.233, "intercept": -4.213}

# Optional recruiting input (data/recruiting/{season}.csv): AdjEM per standard
# deviation of class score. Kept light on purpose.
RECRUIT_WEIGHT = 1.0

# Small ridge penalty so the system stays solvable early in the season.
RIDGE = 0.5

# Win probability = Phi(predicted margin / MARGIN_SD). (tuned)
MARGIN_SD = 11.9

# NET quadrant cutoffs by location: upper rank bound for Q1, Q2, Q3.
QUADRANTS = {
    "home": (30, 75, 160),
    "neutral": (50, 100, 200),
    "away": (75, 135, 240),
}

# Bubble team for wins-above-bubble: this rank in the snapshot.
BUBBLE_RANK = 45

# NET+ blend: results part (frozen WAB) and efficiency part (AdjEM),
# mirroring NET's results + efficiency structure.
NETPLUS_RESULTS_WEIGHT = 0.5

# Season simulation (bracketology, conference odds).
SIM_COUNT = 2000
# NCAA tournament field: 76 teams. The 12 lowest-seeded auto bids and the 12
# lowest-seeded at-large teams play a 12-game opening round; six of each reach
# the round of 64.
FIELD_SIZE = 76
OPENING_ROUND_AUTO = 12
OPENING_ROUND_AT_LARGE = 12
# Spread of each team's "true" AdjEM around its current rating in a simulated
# season. Game noise is reduced so total error still matches MARGIN_SD.
SIM_RATING_SD = 3.0
