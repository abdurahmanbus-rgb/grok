# config.py
# every number on the desk lives here. when you retune, you edit this file and nothing else.

MODEL = "grok-4.7"          # check console.x.ai -> Models if the API rejects it
PAPER = True                # week one: fake fills at real prices. flip only after you read the log

TICKET_USD = 25             # flat. never sized off the last win
MAX_OPEN = 4                # 4 x $25 = $100 in the market, max
MAX_ENTRIES_PER_DAY = 6
DAILY_LOSS_HALT_USD = 50    # realized loss today hits this -> no new entries until tomorrow
COOLDOWN_HOURS = 24         # no re-entry into a token you just left

FACTS = {                   # the rug filter. code only, no model
    "max_risk_score": 40,       # rugcheck score_normalised, 0-100, higher = riskier
    "min_lp_locked_pct": 90,    # biggest pool: LP locked or burned
    "max_top10_pct": 40,        # top 10 holders, pools and lockers excluded
    "max_dev_pct": 5,           # supply still sitting in the creator wallet
    "max_insiders": 10,          # insider-flagged holders + insider graph hits
    "min_liquidity_usd": 15000,
    "max_ticket_share": 0.01,   # your ticket is never more than 1% of the pool
    "min_age_min": 15,          # younger than this, every report is still guessing
    "max_age_hours": 168,
}

MIN_CONFIDENCE = 0.7        # Grok says BUY below this -> treated as SKIP

EXIT = {
    "stop_pct": -35,                        # hard stop from entry
    "ladder": [(100, 0.50), (200, 0.25)],   # +100% sells half, +200% sells a quarter
    "trail_pct": 30,                        # the rest: out when price falls 30% from its peak
    "time_stop_hours": 6,                   # not up 20% after 6 hours -> out, dead money
    "time_stop_min_pct": 20,
    "liq_drop_pct": 40,                     # pool liquidity down 40% from entry -> out now
}

LOG = "checks.csv"
POSITIONS = "positions.json"
TRADES = "trades.csv"