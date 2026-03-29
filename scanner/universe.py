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

# ── Commodities (MCX India + Global via yfinance) ─────────────────────────────
# MCX-tracked via NSE ETFs + Global futures
COMMODITIES = [
    # Precious Metals
    "GC=F",          # Gold Futures (COMEX)
    "SI=F",          # Silver Futures (COMEX)
    "PL=F",          # Platinum Futures
    # Energy
    "CL=F",          # Crude Oil WTI
    "BZ=F",          # Brent Crude Oil
    "NG=F",          # Natural Gas
    # Base Metals
    "HG=F",          # Copper Futures
    "ALI=F",         # Aluminum Futures
    # Agriculture
    "ZC=F",          # Corn Futures
    "ZW=F",          # Wheat Futures
    "ZS=F",          # Soybean Futures
    "CT=F",          # Cotton Futures
    "KC=F",          # Coffee Futures
    "SB=F",          # Sugar Futures
    # Indian Commodity ETFs (NSE-listed, track MCX prices)
    "GOLDBEES.NS",   # Gold ETF (Nippon India)
    "SILVERBEES.NS", # Silver ETF (Nippon India)
    "CRUDEOIL.NS",   # Crude Oil ETF (if available)
]

COMMODITY_INFO = {
    "GC=F": {"name": "Gold", "category": "Precious Metals", "exchange": "COMEX", "currency": "USD"},
    "SI=F": {"name": "Silver", "category": "Precious Metals", "exchange": "COMEX", "currency": "USD"},
    "PL=F": {"name": "Platinum", "category": "Precious Metals", "exchange": "COMEX", "currency": "USD"},
    "CL=F": {"name": "Crude Oil WTI", "category": "Energy", "exchange": "NYMEX", "currency": "USD"},
    "BZ=F": {"name": "Brent Crude Oil", "category": "Energy", "exchange": "ICE", "currency": "USD"},
    "NG=F": {"name": "Natural Gas", "category": "Energy", "exchange": "NYMEX", "currency": "USD"},
    "HG=F": {"name": "Copper", "category": "Base Metals", "exchange": "COMEX", "currency": "USD"},
    "ALI=F": {"name": "Aluminum", "category": "Base Metals", "exchange": "LME", "currency": "USD"},
    "ZC=F": {"name": "Corn", "category": "Agriculture", "exchange": "CBOT", "currency": "USD"},
    "ZW=F": {"name": "Wheat", "category": "Agriculture", "exchange": "CBOT", "currency": "USD"},
    "ZS=F": {"name": "Soybeans", "category": "Agriculture", "exchange": "CBOT", "currency": "USD"},
    "CT=F": {"name": "Cotton", "category": "Agriculture", "exchange": "ICE", "currency": "USD"},
    "KC=F": {"name": "Coffee", "category": "Agriculture", "exchange": "ICE", "currency": "USD"},
    "SB=F": {"name": "Sugar", "category": "Agriculture", "exchange": "ICE", "currency": "USD"},
    "GOLDBEES.NS": {"name": "Gold ETF India", "category": "Precious Metals", "exchange": "NSE", "currency": "INR"},
    "SILVERBEES.NS": {"name": "Silver ETF India", "category": "Precious Metals", "exchange": "NSE", "currency": "INR"},
    "CRUDEOIL.NS": {"name": "Crude Oil ETF India", "category": "Energy", "exchange": "NSE", "currency": "INR"},
}

def is_commodity(ticker: str) -> bool:
    """Check if a ticker is a commodity."""
    return ticker in COMMODITIES or ticker in COMMODITY_INFO

def get_commodity_info(ticker: str) -> dict:
    """Get commodity metadata."""
    return COMMODITY_INFO.get(ticker, {"name": ticker, "category": "Unknown", "exchange": "Unknown", "currency": "USD"})


# ── Mutual Funds (Indian, via mftool AMFI scheme codes) ──────────────────────
# Top Direct-Growth schemes by AUM/popularity
MUTUAL_FUNDS = [
    "MF:118955",  # HDFC Flexi Cap Fund
    "MF:119598",  # SBI Blue Chip (Large Cap)
    "MF:120586",  # ICICI Prudential Bluechip Fund
    "MF:122639",  # Parag Parikh Flexi Cap Fund
    "MF:118825",  # Mirae Asset Large Cap Fund
    "MF:125497",  # SBI Small Cap Fund
    "MF:118778",  # Nippon India Small Cap Fund
    "MF:120164",  # Kotak Small Cap Fund
    "MF:125354",  # Axis Small Cap Fund
    "MF:120828",  # Quant Small Cap Fund
    "MF:118989",  # HDFC Mid Cap Fund
    "MF:119071",  # DSP Midcap Fund
    "MF:127042",  # Motilal Oswal Midcap Fund
    "MF:120505",  # Axis Midcap Fund
    "MF:120166",  # Kotak Flexicap Fund
    "MF:119609",  # SBI Equity Hybrid Fund
    "MF:145206",  # Tata Small Cap Fund
    "MF:147946",  # Bandhan Small Cap Fund
    "MF:119835",  # SBI Contra Fund
    "MF:118825",  # Mirae Asset Large Cap Fund
]
# Deduplicate
MUTUAL_FUNDS = sorted(set(MUTUAL_FUNDS))

MUTUAL_FUND_INFO = {
    "MF:118955": {"name": "HDFC Flexi Cap Fund", "category": "Flexi Cap", "amc": "HDFC Mutual Fund", "scheme_code": "118955"},
    "MF:119598": {"name": "SBI Blue Chip Fund", "category": "Large Cap", "amc": "SBI Mutual Fund", "scheme_code": "119598"},
    "MF:120586": {"name": "ICICI Prudential Bluechip Fund", "category": "Large Cap", "amc": "ICICI Prudential", "scheme_code": "120586"},
    "MF:122639": {"name": "Parag Parikh Flexi Cap Fund", "category": "Flexi Cap", "amc": "PPFAS Mutual Fund", "scheme_code": "122639"},
    "MF:118825": {"name": "Mirae Asset Large Cap Fund", "category": "Large Cap", "amc": "Mirae Asset", "scheme_code": "118825"},
    "MF:125497": {"name": "SBI Small Cap Fund", "category": "Small Cap", "amc": "SBI Mutual Fund", "scheme_code": "125497"},
    "MF:118778": {"name": "Nippon India Small Cap Fund", "category": "Small Cap", "amc": "Nippon India", "scheme_code": "118778"},
    "MF:120164": {"name": "Kotak Small Cap Fund", "category": "Small Cap", "amc": "Kotak Mahindra", "scheme_code": "120164"},
    "MF:125354": {"name": "Axis Small Cap Fund", "category": "Small Cap", "amc": "Axis Mutual Fund", "scheme_code": "125354"},
    "MF:120828": {"name": "Quant Small Cap Fund", "category": "Small Cap", "amc": "Quant Mutual Fund", "scheme_code": "120828"},
    "MF:118989": {"name": "HDFC Mid Cap Fund", "category": "Mid Cap", "amc": "HDFC Mutual Fund", "scheme_code": "118989"},
    "MF:119071": {"name": "DSP Midcap Fund", "category": "Mid Cap", "amc": "DSP Mutual Fund", "scheme_code": "119071"},
    "MF:127042": {"name": "Motilal Oswal Midcap Fund", "category": "Mid Cap", "amc": "Motilal Oswal", "scheme_code": "127042"},
    "MF:120505": {"name": "Axis Midcap Fund", "category": "Mid Cap", "amc": "Axis Mutual Fund", "scheme_code": "120505"},
    "MF:120166": {"name": "Kotak Flexicap Fund", "category": "Flexi Cap", "amc": "Kotak Mahindra", "scheme_code": "120166"},
    "MF:119609": {"name": "SBI Equity Hybrid Fund", "category": "Hybrid", "amc": "SBI Mutual Fund", "scheme_code": "119609"},
    "MF:145206": {"name": "Tata Small Cap Fund", "category": "Small Cap", "amc": "Tata Mutual Fund", "scheme_code": "145206"},
    "MF:147946": {"name": "Bandhan Small Cap Fund", "category": "Small Cap", "amc": "Bandhan Mutual Fund", "scheme_code": "147946"},
    "MF:119835": {"name": "SBI Contra Fund", "category": "Contra", "amc": "SBI Mutual Fund", "scheme_code": "119835"},
}

def is_mutual_fund(ticker: str) -> bool:
    """Check if a ticker is a mutual fund (MF:scheme_code format)."""
    return ticker.startswith("MF:") or ticker in MUTUAL_FUNDS or ticker in MUTUAL_FUND_INFO

def get_mutual_fund_info(ticker: str) -> dict:
    """Get mutual fund metadata."""
    return MUTUAL_FUND_INFO.get(ticker, {"name": ticker, "category": "Unknown", "amc": "Unknown", "scheme_code": ticker.replace("MF:", "")})

def get_mf_scheme_code(ticker: str) -> str:
    """Extract AMFI scheme code from MF ticker."""
    info = MUTUAL_FUND_INFO.get(ticker)
    if info:
        return info["scheme_code"]
    return ticker.replace("MF:", "")


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
