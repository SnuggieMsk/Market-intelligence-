"""
Central configuration for Market Intelligence System.
Focused on Indian Market (NSE/BSE).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────────
GEMINI_API_KEYS = [
    k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()
]
GROQ_API_KEYS = [
    k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()
]
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

# Gemini 2.5 Flash Lite — Tier 1 paid key (4K RPM, 4M TPM — the workhorse)
GEMINI_LITE_API_KEY = os.getenv("GEMINI_LITE_API_KEY", "").strip()

# ── Market ────────────────────────────────────────────────────────────────────
MARKET = "INDIA"                    # INDIA or US
CURRENCY_SYMBOL = "₹"
EXCHANGE_SUFFIX = ".NS"             # .NS for NSE, .BO for BSE

# ── Scanner Settings ──────────────────────────────────────────────────────────
SCAN_INTERVAL_MINUTES = 1440         # Once per day (24 hours)
TOP_STOCKS_TO_ANALYZE = 5           # Start small: 5 stocks x 36 agents = 180 calls
MIN_MARKET_CAP = 5_000_000_000     # ₹500 Cr minimum (~₹5B)
MIN_VOLUME = 200_000               # Minimum daily volume

# Universe: Nifty 50 + Sensex 30 + Nifty Next 50 + custom
STOCK_UNIVERSE_SOURCES = [
    "nifty50",
    "sensex30",
    "nifty_next50",
]
CUSTOM_WATCHLIST = []  # Add NSE tickers manually, e.g. ["ZOMATO", "PAYTM"]

# ── Agent Settings ────────────────────────────────────────────────────────────
MAX_CONCURRENT_AGENTS = 1           # Sequential: 1 at a time to avoid rate limits
AGENT_TIMEOUT_SECONDS = 120         # Max time per agent analysis
GEMINI_LITE_RPM = 2000               # Tier 1 paid: 4K RPM limit, 2K conservative
GEMINI_RPM_PER_KEY = 10              # gemini-2.5-flash free: 15 RPM, 10 conservative for TPM headroom
GROQ_RPM_PER_KEY = 5                # Groq free: 6000 TPM / ~1800 tokens/call ~ 3 calls/min
OPENROUTER_RPM = 3                  # OpenRouter free: ~3-5 RPM realistic
INTER_AGENT_DELAY = 2               # 2s gap — Gemini Lite Tier 1 has 4K RPM, no need for long waits

# Provider priority: gemini_lite is #1 (paid Tier 1, 4K RPM, 4M TPM).
# Free Gemini keys are backup. Groq and OpenRouter are last-resort.
PROVIDER_PRIORITY = ["gemini_lite", "gemini", "groq", "openrouter"]
PROVIDER_DEMOTE_AFTER_FAILURES = 2  # Consecutive 429s before demoting a provider

# ── LLM Model Selection ──────────────────────────────────────────────────────
GEMINI_LITE_MODEL = "gemini-2.5-flash-lite"  # Tier 1 paid: fastest, cheapest, 4K RPM
GEMINI_MODEL = "gemini-2.5-flash"            # Free tier backup: 15 RPM per key
GROQ_MODEL = "llama-3.3-70b-versatile"
OPENROUTER_MODEL = "nousresearch/hermes-3-llama-3.1-405b:free"  # 405B param, best free option

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "market_intel.db")

# ── Dashboard ─────────────────────────────────────────────────────────────────
DASHBOARD_PORT = 8501
DASHBOARD_REFRESH_SECONDS = 300

# ── Scoring Weights for Scanner Metrics ───────────────────────────────────────
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
