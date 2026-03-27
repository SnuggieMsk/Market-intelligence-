"""
Fetches the stock universe (S&P 500, NASDAQ 100) from Wikipedia.
No API key needed.
"""

import pandas as pd
import requests
from io import StringIO
from config.settings import STOCK_UNIVERSE_SOURCES, CUSTOM_WATCHLIST


def get_sp500_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    resp = requests.get(url, timeout=30)
    tables = pd.read_html(StringIO(resp.text))
    df = tables[0]
    return df["Symbol"].str.replace(".", "-", regex=False).tolist()


def get_nasdaq100_tickers():
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    resp = requests.get(url, timeout=30)
    tables = pd.read_html(StringIO(resp.text))
    # The main table has a "Ticker" column
    for table in tables:
        if "Ticker" in table.columns:
            return table["Ticker"].str.replace(".", "-", regex=False).tolist()
        if "Symbol" in table.columns:
            return table["Symbol"].str.replace(".", "-", regex=False).tolist()
    return []


def get_full_universe():
    """Returns deduplicated list of all tickers to scan."""
    tickers = set()

    fetchers = {
        "sp500": get_sp500_tickers,
        "nasdaq100": get_nasdaq100_tickers,
    }

    for source in STOCK_UNIVERSE_SOURCES:
        if source in fetchers:
            try:
                tickers.update(fetchers[source]())
            except Exception as e:
                print(f"[Universe] Warning: Failed to fetch {source}: {e}")

    tickers.update(CUSTOM_WATCHLIST)
    return sorted(tickers)
