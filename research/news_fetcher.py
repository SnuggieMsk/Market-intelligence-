"""
Fetches news, earnings data, and financial report data from free sources.
Sources: Google News RSS (free, no API), yfinance news + financials.
All data cached locally with 4-hour TTL.
"""

import os
import json
import time
import xml.etree.ElementTree as ET
import requests
import yfinance as yf
import pandas as pd
from typing import Optional

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache", "research")
CACHE_MAX_AGE = 14400  # 4 hours


def _cache_path(ticker: str, kind: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe = ticker.replace(".", "_")
    return os.path.join(CACHE_DIR, f"{safe}_{kind}.json")


def _load_cache(ticker: str, kind: str) -> Optional[dict]:
    path = _cache_path(ticker, kind)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if time.time() - data.get("_cached_at", 0) > CACHE_MAX_AGE:
            return None
        return data
    except Exception:
        return None


def _save_cache(ticker: str, kind: str, data: dict):
    data["_cached_at"] = time.time()
    try:
        with open(_cache_path(ticker, kind), "w") as f:
            json.dump(data, f, default=str)
    except Exception:
        pass


def fetch_google_news(company_name: str, ticker: str, max_articles: int = 10) -> list:
    """Fetch recent news from Google News RSS (free, no API key)."""
    cached = _load_cache(ticker, "news")
    if cached:
        return cached.get("articles", [])

    symbol = ticker.replace(".NS", "").replace(".BO", "")
    query = f"{company_name} OR {symbol} stock India"
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"

    articles = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            source = item.findtext("source", "")
            articles.append({
                "title": title,
                "link": link,
                "published": pub_date,
                "source": source,
            })
            if len(articles) >= max_articles:
                break
    except Exception as e:
        print(f"[News] Google News failed for {ticker}: {e}")

    _save_cache(ticker, "news", {"articles": articles})
    return articles


def fetch_yfinance_news(ticker: str, max_articles: int = 10) -> list:
    """Fetch news from Yahoo Finance via yfinance."""
    cached = _load_cache(ticker, "yf_news")
    if cached:
        return cached.get("articles", [])

    articles = []
    try:
        stock = yf.Ticker(ticker)
        news = stock.news or []
        for item in news[:max_articles]:
            articles.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "publisher": item.get("publisher", ""),
                "published": item.get("providerPublishTime", ""),
            })
    except Exception as e:
        print(f"[News] yfinance news failed for {ticker}: {e}")

    _save_cache(ticker, "yf_news", {"articles": articles})
    return articles


def fetch_earnings_data(ticker: str) -> dict:
    """Fetch quarterly financials and earnings data from yfinance."""
    cached = _load_cache(ticker, "earnings")
    if cached:
        cached.pop("_cached_at", None)
        return cached

    data = {}
    try:
        stock = yf.Ticker(ticker)

        # Quarterly financials
        qf = stock.quarterly_financials
        if qf is not None and not qf.empty:
            data["quarterly_revenue"] = []
            data["quarterly_net_income"] = []
            for col in qf.columns[:4]:  # Last 4 quarters
                rev = qf.loc["Total Revenue", col] if "Total Revenue" in qf.index else None
                ni = qf.loc["Net Income", col] if "Net Income" in qf.index else None
                data["quarterly_revenue"].append({
                    "quarter": str(col.date()),
                    "value": float(rev) if rev is not None else None,
                })
                data["quarterly_net_income"].append({
                    "quarter": str(col.date()),
                    "value": float(ni) if ni is not None else None,
                })

        # Analyst recommendations
        rec = stock.recommendations
        if rec is not None and not rec.empty:
            recent = rec.tail(5)
            data["analyst_recommendations"] = []
            for _, row in recent.iterrows():
                data["analyst_recommendations"].append({
                    "firm": row.get("Firm", ""),
                    "grade": row.get("To Grade", ""),
                    "action": row.get("Action", ""),
                })

    except Exception as e:
        print(f"[Research] Earnings data failed for {ticker}: {e}")

    _save_cache(ticker, "earnings", data)
    return data


def fetch_annual_report_data(ticker: str) -> dict:
    """Fetch annual financials, balance sheet, and cash flow from yfinance."""
    cached = _load_cache(ticker, "annual")
    if cached:
        cached.pop("_cached_at", None)
        return cached

    data = {}
    try:
        stock = yf.Ticker(ticker)

        # Annual financials (last 3 years)
        af = stock.financials
        if af is not None and not af.empty:
            data["annual_financials"] = {}
            for col in af.columns[:3]:
                year = str(col.date())
                data["annual_financials"][year] = {}
                for metric in ["Total Revenue", "Net Income", "Operating Income", "Gross Profit"]:
                    if metric in af.index:
                        val = af.loc[metric, col]
                        data["annual_financials"][year][metric] = float(val) if pd.notna(val) else None

        # Balance sheet
        bs = stock.balance_sheet
        if bs is not None and not bs.empty:
            data["balance_sheet"] = {}
            for col in bs.columns[:3]:
                year = str(col.date())
                data["balance_sheet"][year] = {}
                for metric in ["Total Assets", "Total Debt", "Stockholders Equity", "Cash And Cash Equivalents"]:
                    if metric in bs.index:
                        val = bs.loc[metric, col]
                        data["balance_sheet"][year][metric] = float(val) if pd.notna(val) else None

        # Cash flow
        cf = stock.cashflow
        if cf is not None and not cf.empty:
            data["cash_flow"] = {}
            for col in cf.columns[:3]:
                year = str(col.date())
                data["cash_flow"][year] = {}
                for metric in ["Operating Cash Flow", "Free Cash Flow", "Capital Expenditure"]:
                    if metric in cf.index:
                        val = cf.loc[metric, col]
                        data["cash_flow"][year][metric] = float(val) if pd.notna(val) else None

    except Exception as e:
        print(f"[Research] Annual report data failed for {ticker}: {e}")

    _save_cache(ticker, "annual", data)
    return data


def build_research_context(ticker: str, company_name: str) -> str:
    """
    Build a comprehensive research context string combining all data sources.
    This gets passed to research agents alongside the stock metrics context.
    """
    news = fetch_google_news(company_name, ticker)
    yf_news = fetch_yfinance_news(ticker)
    earnings = fetch_earnings_data(ticker)
    annual = fetch_annual_report_data(ticker)

    lines = ["═══ RESEARCH & NEWS DATA ═══\n"]

    # News headlines
    all_news = news + yf_news
    if all_news:
        lines.append("RECENT NEWS HEADLINES:")
        for i, article in enumerate(all_news[:15], 1):
            title = article.get("title", "")
            source = article.get("source", "") or article.get("publisher", "")
            lines.append(f"  {i}. {title} [{source}]")
        lines.append("")
    else:
        lines.append("RECENT NEWS: No recent news found.\n")

    # Quarterly earnings
    if earnings.get("quarterly_revenue"):
        lines.append("QUARTERLY EARNINGS TREND:")
        for q in earnings["quarterly_revenue"]:
            rev = q["value"]
            rev_str = f"₹{rev/1e7:,.0f} Cr" if rev else "N/A"
            lines.append(f"  {q['quarter']}: Revenue {rev_str}")

    if earnings.get("quarterly_net_income"):
        lines.append("QUARTERLY NET INCOME:")
        for q in earnings["quarterly_net_income"]:
            ni = q["value"]
            ni_str = f"₹{ni/1e7:,.0f} Cr" if ni else "N/A"
            lines.append(f"  {q['quarter']}: Net Income {ni_str}")
        lines.append("")

    # Analyst recommendations
    if earnings.get("analyst_recommendations"):
        lines.append("RECENT ANALYST ACTIONS:")
        for rec in earnings["analyst_recommendations"]:
            lines.append(f"  {rec['firm']}: {rec['action']} → {rec['grade']}")
        lines.append("")

    # Annual financials
    if annual.get("annual_financials"):
        lines.append("ANNUAL FINANCIAL SUMMARY:")
        for year, metrics in annual["annual_financials"].items():
            rev = metrics.get("Total Revenue")
            ni = metrics.get("Net Income")
            rev_str = f"₹{rev/1e7:,.0f} Cr" if rev else "N/A"
            ni_str = f"₹{ni/1e7:,.0f} Cr" if ni else "N/A"
            lines.append(f"  {year}: Revenue {rev_str} | Net Income {ni_str}")
        lines.append("")

    # Balance sheet
    if annual.get("balance_sheet"):
        lines.append("BALANCE SHEET HIGHLIGHTS:")
        for year, metrics in annual["balance_sheet"].items():
            assets = metrics.get("Total Assets")
            debt = metrics.get("Total Debt")
            equity = metrics.get("Stockholders Equity")
            lines.append(f"  {year}: Assets ₹{assets/1e7:,.0f} Cr | Debt ₹{debt/1e7:,.0f} Cr | Equity ₹{equity/1e7:,.0f} Cr" if all([assets, debt, equity]) else f"  {year}: Limited data")
        lines.append("")

    # Cash flow
    if annual.get("cash_flow"):
        lines.append("CASH FLOW HIGHLIGHTS:")
        for year, metrics in annual["cash_flow"].items():
            ocf = metrics.get("Operating Cash Flow")
            fcf = metrics.get("Free Cash Flow")
            lines.append(f"  {year}: Operating CF ₹{ocf/1e7:,.0f} Cr | Free CF ₹{fcf/1e7:,.0f} Cr" if all([ocf, fcf]) else f"  {year}: Limited data")
        lines.append("")

    return "\n".join(lines)
