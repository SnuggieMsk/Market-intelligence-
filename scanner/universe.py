"""
Indian Market Stock Universe: Nifty 50 + Sensex 30 + Nifty Next 50.
All tickers are NSE symbols. yfinance uses .NS suffix for NSE.
"""

import pandas as pd
import requests
from io import StringIO
from config.settings import STOCK_UNIVERSE_SOURCES, CUSTOM_WATCHLIST, EXCHANGE_SUFFIX


# ── Hardcoded lists (reliable, no scraping dependency) ────────────────────────

NIFTY_50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BPCL",
    "BHARTIARTL", "BRITANNIA", "CIPLA", "COALINDIA", "DRREDDY",
    "EICHERMOT", "ETERNAL", "GRASIM", "HCLTECH", "HDFCBANK",
    "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK",
    "ITC", "INDUSINDBK", "INFY", "JSWSTEEL", "KOTAKBANK",
    "LT", "M&M", "MARUTI", "NTPC", "NESTLEIND",
    "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN",
    "SUNPHARMA", "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

SENSEX_30 = [
    "ADANIENT", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE",
    "BAJAJFINSV", "BHARTIARTL", "HCLTECH", "HDFCBANK", "HEROMOTOCO",
    "HINDUNILVR", "ICICIBANK", "INDUSINDBK", "INFY", "ITC",
    "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI",
    "NESTLEIND", "NTPC", "POWERGRID", "RELIANCE", "SBIN",
    "SUNPHARMA", "TATAMOTORS", "TATASTEEL", "TCS", "ULTRACEMCO",
]

NIFTY_NEXT_50 = [
    "ABB", "ABBOTINDIA", "ADANIGREEN", "ADANIPOWER", "AMBUJACEM",
    "ATGL", "BANKBARODA", "BOSCHLTD", "CANBK", "CHOLAFIN",
    "COLPAL", "DABUR", "DLF", "DIVISLAB", "GAIL",
    "GODREJCP", "HAVELLS", "HAL", "ICICIPRULI", "IIFL",
    "INDHOTEL", "INDIGO", "IOC", "IRCTC", "IRFC",
    "JIOFIN", "JSWENERGY", "LICI", "LUPIN", "MARICO",
    "MOTHERSON", "NAUKRI", "NHPC", "OBEROIRLTY", "OFSS",
    "PAGEIND", "PAYTM", "PFC", "PIDILITIND", "PNB",
    "RECLTD", "SBICARD", "SHREECEM", "SIEMENS", "TORNTPHARM",
    "TVSMOTOR", "UNIONBANK", "VEDL", "VBL", "ZOMATO",
]

# ── Extra 50 high-interest Indian stocks ──────────────────────────────────────
# Mid-caps, recent IPOs, high momentum, sector leaders
EXTRA_WATCHLIST = [
    "DMART", "POLYCAB", "TATAELXSI", "PERSISTENT", "COFORGE",
    "LTIM", "MPHASIS", "DEEPAKNTR", "PIIND", "ASTRAL",
    "AUROPHARMA", "BIOCON", "IDFCFIRSTB", "FEDERALBNK", "MANAPPURAM",
    "MUTHOOTFIN", "SAIL", "HINDZINC", "NMDC", "TATAPOWER",
    "ADANITRANS", "DIXON", "KAYNES", "COCHINSHIP", "MAZAGONDOCK",
    "BDL", "GRINDWELL", "CUMMINSIND", "THERMAX", "AIAENG",
    "SUNTV", "PVRINOX", "NYKAA", "POLICYBZR", "STARHEALTH",
    "MAXHEALTH", "MEDANTA", "FORTIS", "CGPOWER", "SUZLON",
    "NHPC", "SJVN", "IREDA", "IDEA", "YESBANK",
    "BANDHANBNK", "RBLBANK", "JUBLFOOD", "DEVYANI", "SWIGGY",
]


def _add_suffix(tickers: list) -> list:
    """Add .NS suffix for yfinance NSE lookup."""
    return [f"{t}{EXCHANGE_SUFFIX}" for t in tickers]


def get_nifty50_tickers():
    return _add_suffix(NIFTY_50)


def get_sensex30_tickers():
    return _add_suffix(SENSEX_30)


def get_nifty_next50_tickers():
    return _add_suffix(NIFTY_NEXT_50)


def get_extra_watchlist():
    return _add_suffix(EXTRA_WATCHLIST)


def get_full_universe():
    """Returns deduplicated list of all Indian market tickers to scan."""
    tickers = set()

    fetchers = {
        "nifty50": get_nifty50_tickers,
        "sensex30": get_sensex30_tickers,
        "nifty_next50": get_nifty_next50_tickers,
    }

    for source in STOCK_UNIVERSE_SOURCES:
        if source in fetchers:
            try:
                tickers.update(fetchers[source]())
            except Exception as e:
                print(f"[Universe] Warning: Failed to fetch {source}: {e}")

    # Always include the extra watchlist
    tickers.update(get_extra_watchlist())

    # Add any custom tickers from settings
    if CUSTOM_WATCHLIST:
        tickers.update(_add_suffix(CUSTOM_WATCHLIST))

    return sorted(tickers)
