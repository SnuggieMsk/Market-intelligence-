"""
On-demand single-stock analysis pipeline.
Runs the full pipeline (scan + quant + agents + research + aggregate) for one ticker.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.metrics import compute_all_metrics
from scanner.scanner import compute_composite_score
from quant.engine import run_quant_engine
from agents.executor import run_all_agents_on_stock, run_research_agents_on_stock, run_health_check
from aggregator.synthesizer import aggregate_analyses
from data.database import init_db, save_scan_result


def analyze_single_stock(ticker: str, progress_callback=None):
    """
    Run full analysis pipeline on a single stock.
    progress_callback(step, total, message) is called to report progress.
    Returns dict with all results.
    """
    init_db()
    results = {"ticker": ticker, "error": None}

    def report(step, total, msg):
        if progress_callback:
            progress_callback(step, total, msg)

    try:
        # Step 1: Compute metrics
        report(1, 6, f"Computing 32+ metrics for {ticker}...")
        stock_data = compute_all_metrics(ticker)
        if not stock_data:
            results["error"] = f"Could not fetch data for {ticker}"
            return results

        # Score the stock
        stock_data["composite_score"] = compute_composite_score(stock_data["metrics"])
        results["stock"] = stock_data
        results["metrics"] = stock_data["metrics"]

        # Step 2: Save scan result
        report(2, 6, "Saving scan result...")
        scan_id = save_scan_result(
            ticker=stock_data["ticker"],
            composite_score=stock_data["composite_score"],
            metrics=stock_data["metrics"],
            standout_reasons=stock_data.get("standout_reasons", []),
            company_name=stock_data.get("company_name", ticker),
            sector=stock_data.get("sector", ""),
            market_cap=stock_data.get("market_cap", 0),
            current_price=stock_data.get("current_price", 0),
        )
        stock_data["scan_id"] = scan_id
        results["scan_id"] = scan_id

        # Step 3: Run quant engine
        report(3, 6, "Running quantitative prediction engine...")
        try:
            quant = run_quant_engine(ticker, scan_id)
            results["quant"] = quant
        except Exception as e:
            results["quant_error"] = str(e)

        # Step 4: Health check & run agents
        report(4, 6, "Running 36 AI analyst agents...")
        run_health_check()
        analyses = run_all_agents_on_stock(stock_data)
        results["analyses"] = analyses

        # Step 5: Research agents
        report(5, 6, "Running 8 research verification agents...")
        try:
            research = run_research_agents_on_stock(stock_data, analyses)
            results["research"] = research
        except Exception as e:
            results["research_error"] = str(e)

        # Step 6: Aggregate
        report(6, 6, "Aggregating all analyses into final verdict...")
        all_analyses = analyses + (results.get("research") or [])
        aggregate_analyses(ticker, scan_id, all_analyses, stock_data)

        results["success"] = True
    except Exception as e:
        results["error"] = str(e)
        results["success"] = False

    return results
