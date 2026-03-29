"""
Computes 32+ metrics for each stock to identify standout opportunities.
Primary: yfinance. Fallback: Yahoo Finance direct API via requests.
Mutual funds: mftool (AMFI NAV data).
Caches data locally to avoid redundant downloads.
"""

import os
import json
import time
import numpy as np
import pandas as pd
import yfinance as yf
import requests
from typing import Optional
from datetime import datetime, timedelta

# ── Local Cache ───────────────────────────────────────────────────────────────
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache")
CACHE_MAX_AGE = 14400  # 4 hours — markets are open ~6.5h, keeps data fresh enough
YFINANCE_MAX_RETRIES = 3
YFINANCE_RETRY_DELAY = 5  # seconds


def _cache_path(ticker: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe_name = ticker.replace(".", "_").replace("/", "_")
    return os.path.join(CACHE_DIR, f"{safe_name}.json")


def _load_cache(ticker: str) -> Optional[dict]:
    path = _cache_path(ticker)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            cached = json.load(f)
        age = time.time() - cached.get("_cached_at", 0)
        if age > CACHE_MAX_AGE:
            return None  # Stale
        return cached
    except Exception:
        return None


def _save_cache(ticker: str, data: dict):
    path = _cache_path(ticker)
    data["_cached_at"] = time.time()
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception:
        pass  # Non-critical


def _fetch_yahoo_direct(ticker: str) -> tuple:
    """
    Fallback: fetch data directly from Yahoo Finance API via requests.
    Tries query2 (newer) then query1 (legacy).
    Returns (hist_df, info_dict) or raises on failure.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    period2 = int(time.time())
    period1 = period2 - (365 * 24 * 3600)  # 1 year

    # Try multiple Yahoo Finance API hosts
    base_urls = [
        "https://query2.finance.yahoo.com",
        "https://query1.finance.yahoo.com",
    ]

    data = None
    last_err = None
    for base in base_urls:
        url = f"{base}/v8/finance/chart/{ticker}?period1={period1}&period2={period2}&interval=1d"
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            last_err = e
            continue

    if data is None:
        raise RuntimeError(f"Yahoo direct API unreachable: {last_err}")

    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    ohlcv = result["indicators"]["quote"][0]

    hist = pd.DataFrame({
        "Open": ohlcv["open"],
        "High": ohlcv["high"],
        "Low": ohlcv["low"],
        "Close": ohlcv["close"],
        "Volume": ohlcv["volume"],
    }, index=pd.to_datetime(timestamps, unit="s"))
    hist.dropna(inplace=True)

    # Fetch info/fundamentals
    info = {}
    try:
        meta = result.get("meta", {})
        info["shortName"] = meta.get("shortName", ticker.split(".")[0])
        info["marketCap"] = meta.get("marketCap", 0)
        info["regularMarketPrice"] = meta.get("regularMarketPrice", 0)

        # Try quoteSummary for fundamentals
        for base in base_urls:
            try:
                info_url = (
                    f"{base}/v10/finance/quoteSummary/{ticker}"
                    f"?modules=defaultKeyStatistics,financialData,summaryDetail,assetProfile"
                )
                info_resp = requests.get(info_url, headers=headers, timeout=30)
                if info_resp.status_code == 200:
                    modules = info_resp.json().get("quoteSummary", {}).get("result", [{}])[0]

                    profile = modules.get("assetProfile", {})
                    info["sector"] = profile.get("sector", "Unknown")
                    info["industry"] = profile.get("industry", "Unknown")

                    stats = modules.get("defaultKeyStatistics", {})
                    info["trailingPE"] = stats.get("trailingPE", {}).get("raw")
                    info["forwardPE"] = stats.get("forwardPE", {}).get("raw")
                    info["priceToBook"] = stats.get("priceToBook", {}).get("raw")
                    info["shortPercentOfFloat"] = stats.get("shortPercentOfFloat", {}).get("raw")
                    info["heldPercentInsiders"] = stats.get("heldPercentInsiders", {}).get("raw")

                    fin = modules.get("financialData", {})
                    info["debtToEquity"] = fin.get("debtToEquity", {}).get("raw")
                    info["revenueGrowth"] = fin.get("revenueGrowth", {}).get("raw")
                    info["earningsGrowth"] = fin.get("earningsGrowth", {}).get("raw")
                    info["freeCashflow"] = fin.get("freeCashflow", {}).get("raw")
                    info["operatingCashflow"] = fin.get("operatingCashflows", {}).get("raw")
                    info["totalRevenue"] = fin.get("totalRevenue", {}).get("raw")
                    info["recommendationMean"] = fin.get("recommendationMean", {}).get("raw")

                    summary = modules.get("summaryDetail", {})
                    info["marketCap"] = summary.get("marketCap", {}).get("raw", info.get("marketCap", 0))
                    info["trailingPE"] = info.get("trailingPE") or summary.get("trailingPE", {}).get("raw")
                    info["dividendYield"] = summary.get("dividendYield", {}).get("raw")
                    info["payoutRatio"] = summary.get("payoutRatio", {}).get("raw")

                    # Quant-critical fields from defaultKeyStatistics
                    info["trailingEps"] = stats.get("trailingEps", {}).get("raw")
                    info["forwardEps"] = stats.get("forwardEps", {}).get("raw")
                    info["bookValue"] = stats.get("bookValue", {}).get("raw")
                    info["sharesOutstanding"] = stats.get("sharesOutstanding", {}).get("raw")
                    info["earningsQuarterlyGrowth"] = stats.get("earningsQuarterlyGrowth", {}).get("raw")
                    info["netIncomeToCommon"] = stats.get("netIncomeToCommon", {}).get("raw")
                    info["enterpriseValue"] = stats.get("enterpriseValue", {}).get("raw")

                    break  # Got fundamentals, stop trying
            except Exception:
                continue
    except Exception:
        pass  # Partial info is fine

    return hist, info


def _fetch_google_finance(ticker: str) -> tuple:
    """
    Third fallback: scrape Google Finance for basic price data.
    Limited to recent price + basic info, no full 1-year history.
    Returns (hist_df, info_dict) or raises on failure.
    """
    from bs4 import BeautifulSoup

    # Convert ticker: RELIANCE.NS → RELIANCE:NSE
    symbol = ticker.replace(".NS", "").replace(".BO", "")
    exchange = "NSE" if ".NS" in ticker or not ".BO" in ticker else "BOM"

    url = f"https://www.google.com/finance/quote/{symbol}:{exchange}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract current price
    price_div = soup.find("div", {"class": "YMlKec fxKbKc"})
    if not price_div:
        raise RuntimeError(f"Could not find price on Google Finance for {symbol}")

    price_text = price_div.text.strip().replace("₹", "").replace(",", "").strip()
    current_price = float(price_text)

    # Build minimal history from current price (enough for basic metrics)
    # Google Finance doesn't give full historical data easily, so we create
    # a synthetic 1-day frame and rely on cache for subsequent runs
    now = pd.Timestamp.now()
    hist = pd.DataFrame({
        "Open": [current_price],
        "High": [current_price * 1.01],
        "Low": [current_price * 0.99],
        "Close": [current_price],
        "Volume": [0],
    }, index=[now])

    info = {
        "shortName": symbol,
        "regularMarketPrice": current_price,
        "sector": "Unknown",
        "industry": "Unknown",
        "marketCap": 0,
    }

    print(f"[GoogleFinance] {ticker}: ₹{current_price:.2f}")
    return hist, info


def _fetch_mf_data(ticker: str) -> tuple:
    """
    Fetch mutual fund NAV data via mftool.
    Returns (hist_df, info_dict) in the same format as stock data.
    """
    from scanner.universe import get_mf_scheme_code, get_mutual_fund_info
    from mftool import Mftool

    scheme_code = get_mf_scheme_code(ticker)
    mf_info = get_mutual_fund_info(ticker)
    mf = Mftool()

    # Get NAV history
    df = mf.get_scheme_historical_nav(scheme_code, as_Dataframe=True)
    if df is None or df.empty:
        raise RuntimeError(f"No NAV data for scheme {scheme_code}")

    # Convert: mftool returns nav as string, index as DD-MM-YYYY strings
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df.index = pd.to_datetime(df.index, format="%d-%m-%Y")
    df = df.sort_index()

    # Keep only last 1 year
    one_year_ago = df.index.max() - pd.Timedelta(days=365)
    df = df[df.index >= one_year_ago]

    # Build a hist DataFrame matching yfinance format (NAV-based, no volume)
    hist = pd.DataFrame({
        "Open": df["nav"],
        "High": df["nav"],
        "Low": df["nav"],
        "Close": df["nav"],
        "Volume": 0,
    }, index=df.index)

    # Get scheme details
    details = mf.get_scheme_details(scheme_code)

    info = {
        "shortName": mf_info.get("name", details.get("scheme_name", ticker)),
        "regularMarketPrice": float(df["nav"].iloc[-1]),
        "sector": mf_info.get("category", details.get("scheme_category", "Mutual Fund")),
        "industry": mf_info.get("amc", details.get("fund_house", "Unknown")),
        "marketCap": 0,
        "scheme_category": details.get("scheme_category", ""),
        "fund_house": details.get("fund_house", ""),
        "scheme_name": details.get("scheme_name", ""),
    }

    print(f"[mftool] {ticker}: NAV Rs.{info['regularMarketPrice']:.2f} ({len(hist)} days)")
    return hist, info


def _fetch_stock_data(ticker: str) -> tuple:
    """
    Fetch stock data with 3-level fallback + raw data caching.
    1. Check raw data cache first (avoids re-fetching for quant engine)
    2. yfinance (with retry for rate limits)
    3. Direct Yahoo Finance API (query2/query1)
    4. Google Finance scraper (basic price only)
    Returns (hist_df, info_dict).
    """
    # Check raw data cache first — shared by scanner + quant engine
    raw_cache_dir = os.path.join(CACHE_DIR, "raw")
    os.makedirs(raw_cache_dir, exist_ok=True)
    safe_name = ticker.replace(".", "_")
    raw_cache_path = os.path.join(raw_cache_dir, f"{safe_name}_raw.json")

    try:
        if os.path.exists(raw_cache_path):
            with open(raw_cache_path) as f:
                cached = json.load(f)
            if time.time() - cached.get("_cached_at", 0) < CACHE_MAX_AGE:
                hist = pd.DataFrame(cached["hist"])
                hist.index = pd.to_datetime(hist.index)
                return hist, cached["info"]
    except Exception:
        pass  # Cache miss or corrupt, fetch fresh

    errors = []

    # Level 1: yfinance with retries
    for attempt in range(YFINANCE_MAX_RETRIES):
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            if not hist.empty:
                info = stock.info
                # Cache raw data for quant engine reuse
                _save_raw_cache(raw_cache_path, hist, info)
                return hist, info
            elif attempt == 0:
                print(f"[yfinance] {ticker} returned empty data, retrying in 2s...")
                time.sleep(2)
                continue
        except Exception as e:
            err = str(e).lower()
            if "rate" in err or "429" in err or "too many" in err:
                wait = YFINANCE_RETRY_DELAY * (attempt + 1)
                print(f"[yfinance] {ticker} rate limited, waiting {wait}s (attempt {attempt+1})")
                time.sleep(wait)
            else:
                errors.append(f"yfinance: {e}")
                break

    # Level 2: Direct Yahoo Finance API (query2 + query1)
    print(f"[yfinance] {ticker} falling back to direct Yahoo API...")
    try:
        hist, info = _fetch_yahoo_direct(ticker)
        _save_raw_cache(raw_cache_path, hist, info)
        return hist, info
    except Exception as e2:
        errors.append(f"yahoo_direct: {e2}")

    # Level 3: Google Finance scraper (basic price data)
    print(f"[Yahoo] {ticker} also failed, trying Google Finance...")
    try:
        hist, info = _fetch_google_finance(ticker)
        _save_raw_cache(raw_cache_path, hist, info)
        return hist, info
    except Exception as e3:
        errors.append(f"google_finance: {e3}")

    raise RuntimeError(f"All data sources failed for {ticker}: {'; '.join(errors)}")


def _save_raw_cache(path: str, hist, info: dict):
    """Save raw hist + info to JSON cache for reuse by quant engine."""
    try:
        import numpy as np
        # Convert hist DataFrame to JSON-safe dict
        hist_dict = hist.to_dict()
        # Convert Timestamp keys to strings
        for col in hist_dict:
            hist_dict[col] = {str(k): (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                              for k, v in hist_dict[col].items()}
        # Convert numpy values in info
        clean_info = {}
        for k, v in info.items():
            if isinstance(v, (np.floating, np.integer)):
                clean_info[k] = float(v)
            elif isinstance(v, (str, int, float, bool, type(None))):
                clean_info[k] = v
            else:
                clean_info[k] = str(v)

        with open(path, "w") as f:
            json.dump({"hist": hist_dict, "info": clean_info, "_cached_at": time.time()}, f)
    except Exception:
        pass  # Non-critical


def enrich_fundamentals(ticker: str, info: dict) -> dict:
    """
    If critical fundamental fields are missing from the info dict, try fetching
    them via yfinance financials (balance sheet, income stmt, cash flow).
    This ensures valuation metrics (P/E, P/B, D/E, revenue growth, etc.) are populated
    even when yfinance's .info endpoint returns minimal data.
    """
    critical_fields = ["trailingEps", "forwardEps", "bookValue", "freeCashflow", "sharesOutstanding"]
    has_any = any(info.get(f) for f in critical_fields)
    if has_any:
        return info  # Already have data

    print(f"  [{ticker}] Fundamental data missing — enriching from yfinance financials...")

    try:
        stock = yf.Ticker(ticker)
        yf_info = {}

        # First try stock.info (may fail due to rate limits)
        try:
            yf_info = stock.info or {}
        except Exception:
            pass  # Rate limited or unavailable

        if yf_info and len(yf_info) > 5:
            # Good data from .info — merge missing fields
            for field in ["trailingEps", "forwardEps", "bookValue", "freeCashflow",
                          "sharesOutstanding", "earningsGrowth", "earningsQuarterlyGrowth",
                          "revenueGrowth", "totalRevenue", "netIncomeToCommon",
                          "operatingCashflow", "totalDebt", "totalCash",
                          "dividendYield", "payoutRatio", "debtToEquity",
                          "trailingPE", "forwardPE", "priceToBook",
                          "sector", "industry"]:
                if not info.get(field) and yf_info.get(field):
                    info[field] = yf_info[field]
            return info

        # Fallback: pull from financial statements directly
        try:
            bs = stock.quarterly_balance_sheet
            inc = stock.quarterly_income_stmt
            cf = stock.quarterly_cashflow

            shares = info.get("sharesOutstanding") or (yf_info.get("sharesOutstanding") if yf_info else None)

            if inc is not None and not inc.empty:
                # EPS from income statement
                for label in ["Net Income", "Net Income Common Stockholders"]:
                    if label in inc.index and len(inc.columns) >= 4:
                        annual_ni = float(inc.loc[label].iloc[:4].sum())
                        if shares and shares > 0:
                            info["trailingEps"] = round(annual_ni / shares, 2)
                        info["netIncomeToCommon"] = annual_ni
                        break

                # Revenue + growth
                for label in ["Total Revenue", "Revenue"]:
                    if label in inc.index:
                        info["totalRevenue"] = float(inc.loc[label].iloc[0])
                        if len(inc.columns) >= 5:
                            recent = float(inc.loc[label].iloc[:4].sum())
                            older = float(inc.loc[label].iloc[4:8].sum())
                            if older > 0:
                                info["revenueGrowth"] = round((recent - older) / older, 4)
                        break

                # Earnings growth
                for label in ["Net Income", "Net Income Common Stockholders"]:
                    if label in inc.index and len(inc.columns) >= 5:
                        recent = float(inc.loc[label].iloc[:4].sum())
                        older = float(inc.loc[label].iloc[4:8].sum())
                        if older > 0:
                            info["earningsGrowth"] = round((recent - older) / older, 4)
                        break

            if bs is not None and not bs.empty:
                # Book value per share
                for label in ["Total Stockholder Equity", "Stockholders Equity",
                              "Total Equity Gross Minority Interest"]:
                    if label in bs.index:
                        equity = float(bs.loc[label].iloc[0])
                        if shares and shares > 0:
                            info["bookValue"] = round(equity / shares, 2)
                            # Price to book
                            price = info.get("regularMarketPrice", 0)
                            if price and info["bookValue"] > 0:
                                info["priceToBook"] = round(price / info["bookValue"], 2)
                        break

                # Debt to equity
                for debt_label in ["Total Debt", "Long Term Debt"]:
                    if debt_label in bs.index:
                        debt = float(bs.loc[debt_label].iloc[0])
                        info["totalDebt"] = debt
                        for eq_label in ["Total Stockholder Equity", "Stockholders Equity",
                                         "Total Equity Gross Minority Interest"]:
                            if eq_label in bs.index:
                                eq = float(bs.loc[eq_label].iloc[0])
                                if eq > 0:
                                    info["debtToEquity"] = round((debt / eq) * 100, 2)
                                break
                        break

            if cf is not None and not cf.empty:
                opcf = None
                capex = None
                for label in ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]:
                    if label in cf.index:
                        opcf = float(cf.loc[label].iloc[0])
                        break
                for label in ["Capital Expenditure", "Capital Expenditures"]:
                    if label in cf.index:
                        capex = float(cf.loc[label].iloc[0])
                        break
                if opcf:
                    info["operatingCashflow"] = opcf
                    info["freeCashflow"] = opcf + capex if capex else opcf * 0.7

            # Compute P/E if we got EPS
            eps = info.get("trailingEps")
            price = info.get("regularMarketPrice", 0)
            if eps and eps > 0 and price and price > 0:
                info["trailingPE"] = round(price / eps, 2)

        except Exception as e:
            print(f"  [{ticker}] Financial statement enrichment failed: {e}")

    except Exception as e:
        print(f"  [{ticker}] yfinance enrichment failed: {e}")

    return info


def compute_all_metrics(ticker: str) -> Optional[dict]:
    """
    Compute all 32+ metrics for a given ticker.
    Uses local cache, yfinance with retry, and direct Yahoo API fallback.
    Enriches fundamentals from yfinance financials if missing.
    Returns None if data is insufficient.
    """
    # Check cache first
    cached = _load_cache(ticker)
    if cached:
        cached.pop("_cached_at", None)
        return cached

    try:
        from scanner.universe import is_mutual_fund as _check_mf
        if _check_mf(ticker):
            hist, info = _fetch_mf_data(ticker)
        else:
            hist, info = _fetch_stock_data(ticker)

        if hist.empty or len(hist) < 50:
            return None

        # Enrich fundamentals if yfinance returned minimal data
        info = enrich_fundamentals(ticker, info)

        close = hist["Close"]
        volume = hist["Volume"]
        high = hist["High"]
        low = hist["Low"]
        latest_close = close.iloc[-1]
        latest_volume = volume.iloc[-1]

        metrics = {}
        reasons = []

        # ══════════════════════════════════════════════════════════════════════
        # PRICE ACTION (8 metrics)
        # ══════════════════════════════════════════════════════════════════════

        # 1. Price vs 52-week low (how close to the bottom)
        low_52w = close.min()
        metrics["price_vs_52w_low"] = ((latest_close - low_52w) / low_52w) * 100
        if metrics["price_vs_52w_low"] < 10:
            reasons.append(f"Trading within 10% of 52-week low (₹{low_52w:.2f})")

        # 2. Price vs 52-week high (how far from top)
        high_52w = close.max()
        metrics["price_vs_52w_high"] = ((high_52w - latest_close) / high_52w) * 100
        if metrics["price_vs_52w_high"] > 40:
            reasons.append(f"Down {metrics['price_vs_52w_high']:.0f}% from 52-week high")

        # 3. Daily return
        metrics["daily_return"] = ((close.iloc[-1] / close.iloc[-2]) - 1) * 100 if len(close) >= 2 else 0
        if abs(metrics["daily_return"]) > 5:
            reasons.append(f"Big daily move: {metrics['daily_return']:+.1f}%")

        # 4. Weekly return
        metrics["weekly_return"] = ((close.iloc[-1] / close.iloc[-5]) - 1) * 100 if len(close) >= 5 else 0

        # 5. Monthly return
        metrics["monthly_return"] = ((close.iloc[-1] / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

        # 6. Gap percentage (today's open vs yesterday's close)
        if len(hist) >= 2:
            today_open = hist["Open"].iloc[-1]
            prev_close = close.iloc[-2]
            metrics["gap_percentage"] = ((today_open - prev_close) / prev_close) * 100
            if abs(metrics["gap_percentage"]) > 3:
                reasons.append(f"Gap {'up' if metrics['gap_percentage'] > 0 else 'down'}: {metrics['gap_percentage']:+.1f}%")
        else:
            metrics["gap_percentage"] = 0

        # 7. Intraday range (% of price)
        metrics["intraday_range"] = ((high.iloc[-1] - low.iloc[-1]) / latest_close) * 100

        # 8. Price vs 200-day SMA
        if len(close) >= 200:
            sma200 = close.rolling(200).mean().iloc[-1]
            metrics["price_vs_sma200"] = ((latest_close - sma200) / sma200) * 100
            if metrics["price_vs_sma200"] < -20:
                reasons.append(f"Trading {abs(metrics['price_vs_sma200']):.0f}% below 200-day SMA")
        else:
            sma200 = close.rolling(len(close)).mean().iloc[-1]
            metrics["price_vs_sma200"] = ((latest_close - sma200) / sma200) * 100

        # ══════════════════════════════════════════════════════════════════════
        # VOLUME (5 metrics)
        # ══════════════════════════════════════════════════════════════════════

        avg_volume_20 = volume.rolling(20).mean().iloc[-1]

        # 9. Volume surge (today vs 20-day avg)
        metrics["volume_surge"] = (latest_volume / avg_volume_20) if avg_volume_20 > 0 else 1
        if metrics["volume_surge"] > 3:
            reasons.append(f"Volume surge: {metrics['volume_surge']:.1f}x average")

        # 10. Relative volume (5-day avg vs 20-day avg)
        avg_vol_5 = volume.tail(5).mean()
        metrics["relative_volume"] = (avg_vol_5 / avg_volume_20) if avg_volume_20 > 0 else 1

        # 11. Volume-Price Trend
        vpt = ((close.ffill().pct_change() * volume).cumsum())
        metrics["volume_price_trend"] = vpt.iloc[-1] / vpt.abs().max() if vpt.abs().max() > 0 else 0

        # 12. Accumulation/Distribution
        mfm = ((close - low) - (high - close)) / (high - low + 1e-10)
        ad_line = (mfm * volume).cumsum()
        ad_recent = ad_line.tail(10).mean()
        ad_prior = ad_line.tail(30).head(20).mean()
        metrics["accumulation_distribution"] = 1 if ad_recent > ad_prior else -1

        # 13. OBV trend (rising or falling)
        obv = (np.sign(close.diff()) * volume).cumsum()
        obv_sma = obv.rolling(20).mean()
        metrics["on_balance_volume_trend"] = 1 if obv.iloc[-1] > obv_sma.iloc[-1] else -1

        # ══════════════════════════════════════════════════════════════════════
        # VOLATILITY (4 metrics)
        # ══════════════════════════════════════════════════════════════════════

        returns = close.ffill().pct_change().dropna()

        # 14. Historical volatility (annualized)
        metrics["historical_volatility"] = returns.tail(30).std() * np.sqrt(252) * 100

        # 15. ATR as percentage of price
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr_14 = tr.rolling(14).mean().iloc[-1]
        metrics["atr_percentage"] = (atr_14 / latest_close) * 100

        # 16. Bollinger Band squeeze (bandwidth)
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_upper = sma20 + 2 * std20
        bb_lower = sma20 - 2 * std20
        bandwidth = ((bb_upper - bb_lower) / sma20 * 100).iloc[-1]
        metrics["bollinger_squeeze"] = bandwidth
        if bandwidth < 5:
            reasons.append("Bollinger Band squeeze detected — breakout imminent")

        # 17. IV percentile (approximated from historical vol percentile)
        rolling_vol = returns.rolling(20).std() * np.sqrt(252) * 100
        current_vol = rolling_vol.iloc[-1]
        metrics["iv_percentile"] = (rolling_vol < current_vol).mean() * 100

        # ══════════════════════════════════════════════════════════════════════
        # MOMENTUM (5 metrics)
        # ══════════════════════════════════════════════════════════════════════

        # 18. RSI (14-period)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        rsi = (100 - (100 / (1 + rs))).iloc[-1]
        metrics["rsi"] = rsi
        if rsi < 30:
            reasons.append(f"RSI oversold: {rsi:.0f}")
        elif rsi > 70:
            reasons.append(f"RSI overbought: {rsi:.0f}")

        # 19. MACD signal
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        metrics["macd_signal"] = 1 if macd_line.iloc[-1] > signal_line.iloc[-1] else -1
        if macd_line.iloc[-2] < signal_line.iloc[-2] and macd_line.iloc[-1] > signal_line.iloc[-1]:
            reasons.append("MACD bullish crossover")

        # 20. Stochastic crossover
        low_14 = low.rolling(14).min()
        high_14 = high.rolling(14).max()
        k_line = ((close - low_14) / (high_14 - low_14 + 1e-10)) * 100
        d_line = k_line.rolling(3).mean()
        metrics["stochastic_crossover"] = 1 if k_line.iloc[-1] > d_line.iloc[-1] else -1

        # 21. Composite momentum score
        sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else close.mean()
        above_sma50 = 1 if latest_close > sma_50 else 0
        metrics["momentum_score"] = (
            (1 if metrics["macd_signal"] > 0 else 0) +
            (1 if rsi > 50 else 0) +
            above_sma50 +
            (1 if metrics["stochastic_crossover"] > 0 else 0)
        ) / 4 * 10

        # 22. Rate of change (10-day)
        metrics["rate_of_change"] = ((close.iloc[-1] / close.iloc[-10]) - 1) * 100 if len(close) >= 10 else 0

        # ══════════════════════════════════════════════════════════════════════
        # FUNDAMENTALS (6 metrics) — skip for commodities and mutual funds
        # ══════════════════════════════════════════════════════════════════════
        from scanner.universe import is_commodity as _is_commodity, is_mutual_fund as _is_mf
        _is_comm = _is_commodity(ticker)
        _is_mutual_fund = _is_mf(ticker)

        if _is_comm or _is_mutual_fund:
            # Commodities don't have P/E, P/B, D/E, revenue, earnings, FCF
            metrics["pe_ratio_vs_sector"] = 0
            metrics["pb_ratio"] = 0
            metrics["debt_to_equity"] = 0
            metrics["revenue_growth"] = 0
            metrics["earnings_surprise"] = 0
            metrics["free_cash_flow_yield"] = 0
            if _is_mutual_fund:
                reasons.append("Mutual fund - use NAV/returns metrics instead of company fundamentals")
            else:
                reasons.append("Commodity asset - fundamentals N/A, focus on supply/demand & technicals")
        else:
            # 23. P/E ratio vs sector average (simplified: just raw PE)
            pe = info.get("trailingPE") or info.get("forwardPE")
            metrics["pe_ratio_vs_sector"] = pe if pe and pe > 0 else 0
            if pe and 0 < pe < 10:
                reasons.append(f"Very low P/E: {pe:.1f}")

            # 24. Price-to-Book ratio
            pb = info.get("priceToBook")
            metrics["pb_ratio"] = pb if pb and pb > 0 else 0
            if pb and 0 < pb < 1:
                reasons.append(f"Trading below book value (P/B: {pb:.2f})")

            # 25. Debt-to-Equity
            de = info.get("debtToEquity")
            metrics["debt_to_equity"] = de if de else 0

            # 26. Revenue growth
            rg = info.get("revenueGrowth")
            metrics["revenue_growth"] = (rg * 100) if rg else 0
            if rg and rg > 0.25:
                reasons.append(f"Strong revenue growth: {rg*100:.0f}%")

            # 27. Earnings surprise (approximated from earnings growth)
            eg = info.get("earningsGrowth")
            metrics["earnings_surprise"] = (eg * 100) if eg else 0
            if eg and eg > 0.30:
                reasons.append(f"Strong earnings growth: {eg*100:.0f}%")

            # 28. Free cash flow yield
            fcf = info.get("freeCashflow")
            mcap = info.get("marketCap")
            if fcf and mcap and mcap > 0:
                metrics["free_cash_flow_yield"] = (fcf / mcap) * 100
            else:
                metrics["free_cash_flow_yield"] = 0

        # ══════════════════════════════════════════════════════════════════════
        # SENTIMENT & MARKET (4 metrics)
        # ══════════════════════════════════════════════════════════════════════

        # 29. Short interest (% of float)
        short_pct = info.get("shortPercentOfFloat")
        metrics["short_interest"] = (short_pct * 100) if short_pct else 0
        if short_pct and short_pct > 0.15:
            reasons.append(f"High short interest: {short_pct*100:.0f}% of float")

        # 30. Insider buying (net insider transactions)
        # yfinance gives insiderTransactions — use buy ratio
        insider_buy = info.get("heldPercentInsiders")
        metrics["insider_buying"] = (insider_buy * 100) if insider_buy else 0

        # 31. Analyst rating change
        rec = info.get("recommendationMean")  # 1=strong buy, 5=sell
        metrics["analyst_rating_change"] = rec if rec else 3.0
        if rec and rec < 1.8:
            reasons.append(f"Strong analyst buy consensus ({rec:.1f}/5)")

        # 32. Sector relative strength (simplified: stock return vs SPY)
        metrics["sector_relative_strength"] = metrics.get("monthly_return", 0)

        # ══════════════════════════════════════════════════════════════════════
        # METADATA
        # ══════════════════════════════════════════════════════════════════════

        # Set metadata — use commodity/MF info if applicable
        if _is_comm:
            from scanner.universe import get_commodity_info
            _comm_info = get_commodity_info(ticker)
            _company_name = _comm_info.get("name", info.get("shortName", ticker))
            _sector = _comm_info.get("category", "Commodities")
            _industry = f"{_comm_info.get('exchange', '')} Futures"
            _market_cap = 0
            _asset_type = "commodity"
        elif _is_mutual_fund:
            from scanner.universe import get_mutual_fund_info
            _mf_info = get_mutual_fund_info(ticker)
            _company_name = _mf_info.get("name", ticker)
            _sector = _mf_info.get("category", "Mutual Fund")
            _industry = _mf_info.get("amc", "Unknown AMC")
            _market_cap = 0
            _asset_type = "mutual_fund"
        else:
            _company_name = info.get("shortName", ticker)
            _sector = info.get("sector", "Unknown")
            _industry = info.get("industry", "Unknown")
            _market_cap = info.get("marketCap", 0)
            _asset_type = "stock"

        result = {
            "ticker": ticker,
            "company_name": _company_name,
            "sector": _sector,
            "industry": _industry,
            "market_cap": _market_cap,
            "current_price": float(latest_close),
            "metrics": {k: float(v) if isinstance(v, (np.floating, np.integer)) else v for k, v in metrics.items()},
            "standout_reasons": reasons,
            "asset_type": _asset_type,
        }

        # Cache for re-runs
        _save_cache(ticker, result)
        return result

    except Exception as e:
        print(f"[Metrics] Error computing metrics for {ticker}: {e}")
        return None
