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
MARGIN_CAP = 25.0
MARGIN_SLOPE = 0.5

# Preseason prior: last season's final ratings, regressed toward average,
# worth PRIOR_GAMES games of data and fading to zero after PRIOR_FADE_GAMES
# games played (Torvik phases his prior out after about 13). (tuned)
PRIOR_GAMES = 6.0
PRIOR_FADE_GAMES = 13
PRIOR_REGRESS = 0.35  # share of the way back to average

# Small ridge penalty so the system stays solvable early in the season.
RIDGE = 0.5

# Win probability = Phi(predicted margin / MARGIN_SD). (tuned)
MARGIN_SD = 11.0

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
