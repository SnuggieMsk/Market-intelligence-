"""
Central configuration for Market Intelligence System.
All settings, API keys, and constants live here.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────────
# Add your keys to a .env file in the project root
GEMINI_API_KEYS = [
    k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()
]
GROQ_API_KEYS = [
    k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()
]

# ── Scanner Settings ──────────────────────────────────────────────────────────
SCAN_INTERVAL_MINUTES = 30          # How often to run the full scan
TOP_STOCKS_TO_ANALYZE = 15          # How many standout stocks to send to agents
MIN_MARKET_CAP = 1_000_000_000     # $1B minimum market cap (filter penny stocks)
MIN_VOLUME = 500_000                # Minimum daily volume

# Universe: S&P 500 + NASDAQ 100 + additional watchlist
STOCK_UNIVERSE_SOURCES = [
    "sp500",
    "nasdaq100",
]
CUSTOM_WATCHLIST = []  # Add tickers manually, e.g. ["TSLA", "NVDA"]

# ── Agent Settings ────────────────────────────────────────────────────────────
MAX_CONCURRENT_AGENTS = 5           # Parallel agent calls (respect rate limits)
AGENT_TIMEOUT_SECONDS = 120         # Max time per agent analysis
GEMINI_RPM_LIMIT = 15               # Requests per minute per key
GROQ_RPM_LIMIT = 30                 # Requests per minute per key

# ── LLM Model Selection ──────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.0-flash"        # Free tier model
GROQ_MODEL = "llama-3.3-70b-versatile"   # Free tier model

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "market_intel.db")

# ── Dashboard ─────────────────────────────────────────────────────────────────
DASHBOARD_PORT = 8501
DASHBOARD_REFRESH_SECONDS = 300     # Auto-refresh every 5 minutes

# ── Scoring Weights for Scanner Metrics ───────────────────────────────────────
# Higher weight = more important for identifying standout stocks
METRIC_WEIGHTS = {
    # Price Action (8 metrics)
    "price_vs_52w_low": 3.0,
    "price_vs_52w_high": 2.0,
    "daily_return": 2.5,
    "weekly_return": 2.0,
    "monthly_return": 1.5,
    "gap_percentage": 3.0,
    "intraday_range": 1.5,
    "price_vs_sma200": 2.5,

    # Volume (5 metrics)
    "volume_surge": 3.5,
    "relative_volume": 3.0,
    "volume_price_trend": 2.0,
    "accumulation_distribution": 2.0,
    "on_balance_volume_trend": 1.5,

    # Volatility (4 metrics)
    "historical_volatility": 1.5,
    "atr_percentage": 1.5,
    "bollinger_squeeze": 2.5,
    "iv_percentile": 2.0,

    # Momentum (5 metrics)
    "rsi": 2.5,
    "macd_signal": 2.0,
    "stochastic_crossover": 2.0,
    "momentum_score": 2.0,
    "rate_of_change": 1.5,

    # Fundamentals (6 metrics)
    "pe_ratio_vs_sector": 2.0,
    "pb_ratio": 1.5,
    "debt_to_equity": 1.5,
    "revenue_growth": 2.5,
    "earnings_surprise": 3.0,
    "free_cash_flow_yield": 2.0,

    # Sentiment & Market (4 metrics)
    "short_interest": 2.5,
    "insider_buying": 3.0,
    "analyst_rating_change": 2.0,
    "sector_relative_strength": 1.5,
}
