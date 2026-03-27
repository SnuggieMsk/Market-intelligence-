"""
On-demand single-stock analysis pipeline.
Runs the full analysis (metrics → quant → agents → research → aggregation)
for any user-specified ticker, callable from the dashboard.
"""

import time
from rich.console import Console

from scanner.metrics import compute_all_metrics
from scanner.scanner import compute_composite_score
from quant.engine import run_quant_engine
from data.database import save_scan_result, save_quant_predictions

console = Console()


def analyze_single_stock(ticker: str, progress_callback=None) -> dict:
    """
    Run the full analysis pipeline on a single stock.

    Args:
        ticker: NSE ticker (e.g. "RELIANCE.NS")
        progress_callback: optional callable(step: str, detail: str) for UI updates

    Returns:
        dict with keys: success, error, stock, quant, analyses, research, report
    """
    result = {
        "success": False,
        "error": None,
        "stock": None,
        "quant": None,
        "analyses": [],
        "research": [],
        "report": None,
    }

    def _progress(step, detail=""):
        if progress_callback:
            progress_callback(step, detail)

    # ── Step 1: Compute metrics ──────────────────────────────────────────────
    _progress("metrics", f"Scanning {ticker}...")
    try:
        stock_data = compute_all_metrics(ticker)
        if not stock_data:
            result["error"] = f"Could not fetch data for {ticker}. Check the ticker symbol."
            return result
    except Exception as e:
        result["error"] = f"Metrics computation failed: {e}"
        return result

    # Compute composite score
    stock_data["composite_score"] = compute_composite_score(stock_data.get("metrics", {}))

    # Save scan result to DB
    scan_id = save_scan_result(
        ticker=stock_data["ticker"],
        composite_score=stock_data["composite_score"],
        metrics=stock_data["metrics"],
        standout_reasons=stock_data.get("standout_reasons", []),
        company_name=stock_data.get("company_name", ticker),
        sector=stock_data.get("sector", "Unknown"),
        market_cap=stock_data.get("market_cap", 0),
        current_price=stock_data.get("current_price", 0),
    )
    stock_data["scan_id"] = scan_id
    result["stock"] = stock_data

    _progress("metrics", f"Scan complete — {stock_data.get('company_name', ticker)}")

    # ── Step 2: Quant Engine ─────────────────────────────────────────────────
    _progress("quant", "Running quantitative models...")
    try:
        quant = run_quant_engine(ticker)
        result["quant"] = quant
        if scan_id and not quant.get("error"):
            save_quant_predictions(scan_id, ticker, quant)
        _progress("quant", "Quant engine complete")
    except Exception as e:
        _progress("quant", f"Quant engine error: {e}")

    # ── Step 3: AI Agents (36 base) ──────────────────────────────────────────
    _progress("agents", "Running 36 AI agents (this takes a few minutes)...")
    try:
        from agents.executor import run_all_agents_on_stock, run_health_check

        alive = run_health_check()
        if not alive:
            _progress("agents", "No LLM providers available — skipping agents")
        else:
            analyses = run_all_agents_on_stock(stock_data)
            result["analyses"] = analyses

            success = sum(1 for a in analyses if a.get("verdict") != "ERROR")
            _progress("agents", f"{success}/{len(analyses)} agents completed")
    except Exception as e:
        _progress("agents", f"Agent execution error: {e}")

    # ── Step 4: Research Agents (8) ──────────────────────────────────────────
    if result["analyses"]:
        _progress("research", "Running 8 research agents...")
        try:
            from agents.executor import run_research_agents_on_stock

            research = run_research_agents_on_stock(stock_data, result["analyses"])
            result["research"] = research
            # Note: run_research_agents_on_stock already saves to DB internally

            _progress("research", f"{len(research)} research agents complete")
        except Exception as e:
            _progress("research", f"Research agents error: {e}")

    # ── Step 5: Aggregation ──────────────────────────────────────────────────
    all_analyses = result["analyses"] + result["research"]
    if all_analyses:
        _progress("aggregate", "Synthesizing all analyses...")
        try:
            from aggregator.synthesizer import aggregate_analyses

            report = aggregate_analyses(
                ticker=ticker,
                scan_id=scan_id,
                analyses=all_analyses,
                stock_data=stock_data,
            )
            result["report"] = report
            _progress("aggregate", "Final report generated")
        except Exception as e:
            _progress("aggregate", f"Aggregation error: {e}")

    result["success"] = True
    return result


def ensure_ticker_suffix(ticker: str) -> str:
    """Ensure ticker has .NS suffix for NSE stocks."""
    ticker = ticker.strip().upper()
    if not ticker.endswith((".NS", ".BO")):
        ticker += ".NS"
    return ticker
