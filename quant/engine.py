"""
Quantitative Prediction Engine — orchestrates all math models.
Pure Python, zero LLM calls. Reuses scanner's data fetch (with retry + fallback).
"""

import os
import json
import time
from rich.console import Console

from quant.valuation import compute_all_valuations
from quant.levels import compute_support_resistance
from quant.predictions import compute_all_predictions
from scanner.metrics import _fetch_stock_data, enrich_fundamentals  # Reuse scanner's fetch + enrichment

console = Console()

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache", "quant")
CACHE_MAX_AGE = 14400  # 4 hours


def _cache_path(ticker: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe = ticker.replace(".", "_")
    return os.path.join(CACHE_DIR, f"{safe}_quant.json")


def _load_cache(ticker: str):
    path = _cache_path(ticker)
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


def _save_cache(ticker: str, data: dict):
    data["_cached_at"] = time.time()
    try:
        with open(_cache_path(ticker), "w") as f:
            json.dump(data, f, default=str)
    except Exception:
        pass


def run_quant_engine(ticker: str) -> dict:
    """
    Run all quantitative models for a single stock.
    Uses scanner's _fetch_stock_data which has retry + Yahoo/Google fallback.
    If fundamental data is missing, enriches via yfinance financials.
    """
    # Check cache
    cached = _load_cache(ticker)
    if cached:
        cached.pop("_cached_at", None)
        return cached

    result = {"ticker": ticker, "error": None}

    try:
        # Reuse scanner's fetch function — has yfinance retry + Yahoo direct + Google fallback
        hist, info = _fetch_stock_data(ticker)

        if hist.empty or len(hist) < 50:
            result["error"] = "Insufficient historical data"
            return result

        # Enrich fundamentals if missing (critical for valuations)
        info = enrich_fundamentals(ticker, info)

        current_price = float(hist["Close"].iloc[-1])

        # 1. Valuations
        console.print(f"  [dim]{ticker}: Computing valuations...[/dim]")
        result["valuations"] = compute_all_valuations(current_price, info)

        # 2. Support/Resistance levels
        console.print(f"  [dim]{ticker}: Computing support/resistance...[/dim]")
        result["levels"] = compute_support_resistance(hist)

        # 3. Predictions (Bollinger, Monte Carlo, Mean Reversion)
        console.print(f"  [dim]{ticker}: Running prediction models...[/dim]")
        result["predictions"] = compute_all_predictions(hist)

        # Summary
        mc = result["predictions"].get("monte_carlo", {})
        val = result["valuations"]
        result["summary"] = {
            "current_price": current_price,
            "fair_value_composite": val.get("composite_fair_value"),
            "upside_to_fair_value": val.get("composite_upside"),
            "monte_carlo_median": mc.get("median_price"),
            "monte_carlo_expected_return": mc.get("expected_return"),
            "prob_positive_30d": mc.get("prob_positive"),
            "bollinger_signal": result["predictions"].get("bollinger", {}).get("signal"),
            "mean_reversion_signal": result["predictions"].get("mean_reversion", {}).get("signal"),
        }

        _save_cache(ticker, result)

    except Exception as e:
        result["error"] = str(e)
        console.print(f"  [red]{ticker}: Quant engine error: {e}[/red]")

    return result


def run_quant_engine_for_stocks(stocks: list) -> dict:
    """Run quant engine on all standout stocks. Returns {ticker: quant_results}."""
    console.print(f"\n[bold cyan]Running Quant Engine on {len(stocks)} stocks...[/bold cyan]")

    results = {}
    for i, stock in enumerate(stocks):
        ticker = stock["ticker"]
        results[ticker] = run_quant_engine(ticker)
        # Small delay between stocks to avoid yfinance rate limits
        if i < len(stocks) - 1:
            time.sleep(2)

    # Print summary
    console.print("\n[bold]Quant Engine Results:[/bold]")
    for ticker, data in results.items():
        if data.get("error"):
            console.print(f"  [red]{ticker}: Error - {data['error']}[/red]")
        else:
            summary = data.get("summary", {})
            fair = summary.get("fair_value_composite")
            upside = summary.get("upside_to_fair_value")
            prob = summary.get("prob_positive_30d")
            fair_str = f"₹{fair:.2f}" if fair else "N/A"
            upside_str = f"{upside:+.1f}%" if upside else "N/A"
            prob_str = f"{prob:.0f}%" if prob else "N/A"
            console.print(f"  [green]{ticker}: Fair Value {fair_str} | Upside {upside_str} | P(up 30d) {prob_str}[/green]")

    return results
