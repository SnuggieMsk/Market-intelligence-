"""
On-demand single-stock analysis pipeline.
Runs the full pipeline (scan + quant + agents + research + aggregate) for one ticker.
Supports cancellation via a stop_flag (threading.Event).
"""

import sys
import os
import threading
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.metrics import compute_all_metrics
from scanner.scanner import compute_composite_score
from quant.engine import run_quant_engine
from agents.executor import run_all_agents_on_stock, run_research_agents_on_stock, run_health_check
from aggregator.synthesizer import aggregate_analyses
from data.database import (
    init_db, save_scan_result, save_quant_predictions,
    save_aggregated_report,
)


class AnalysisCancelled(Exception):
    """Raised when the user cancels the analysis."""
    pass


def _fallback_aggregation(ticker, scan_id, analyses):
    """
    If LLM-based aggregation fails, compute a math-based verdict from agent votes.
    This ensures we ALWAYS have an aggregated report in the DB.
    """
    print(f"  [FALLBACK] Computing math-based aggregation for {ticker}...")

    verdict_scores = {"STRONG_BUY": 10, "BUY": 7.5, "NEUTRAL": 5, "SELL": 2.5, "STRONG_SELL": 0}
    scores = []
    verdicts = []

    for a in analyses:
        v = (a.get("verdict") or "").upper().replace(" ", "_")
        if v in verdict_scores:
            verdicts.append(v)
            s = a.get("score")
            if s is not None:
                scores.append(float(s))
            else:
                scores.append(verdict_scores[v])

    if not verdicts:
        return None

    avg_score = sum(scores) / len(scores) if scores else 5.0
    # Determine verdict from average score
    if avg_score >= 8:
        overall = "STRONG_BUY"
    elif avg_score >= 6:
        overall = "BUY"
    elif avg_score >= 4:
        overall = "NEUTRAL"
    elif avg_score >= 2:
        overall = "SELL"
    else:
        overall = "STRONG_SELL"

    from collections import Counter
    vote_counts = Counter(verdicts)
    top_verdict = vote_counts.most_common(1)[0]

    report = {
        "overall_verdict": overall,
        "overall_score": round(avg_score, 1),
        "consensus_summary": (
            f"Math-based aggregation from {len(verdicts)} agent votes. "
            f"Most common verdict: {top_verdict[0]} ({top_verdict[1]} votes). "
            f"Average score: {avg_score:.1f}/10."
        ),
        "recommendation": f"Based on {len(verdicts)} agents: {overall} with score {avg_score:.1f}/10",
        "key_risks": [],
        "key_catalysts": [],
        "data_summary": "",
        "sentiment_summary": "",
        "prediction_summary": "",
    }

    save_aggregated_report(scan_id, ticker, report)
    print(f"  [FALLBACK] Saved: {overall} ({avg_score:.1f}/10)")
    return report


def analyze_single_stock(ticker: str, progress_callback=None, stop_flag: threading.Event = None):
    """
    Run full analysis pipeline on a single stock.
    progress_callback(step, total, message) is called to report progress.
    stop_flag: if set, the analysis will stop at the next checkpoint.
    Returns dict with all results.
    """
    init_db()
    results = {"ticker": ticker, "error": None}

    def check_stop():
        if stop_flag and stop_flag.is_set():
            raise AnalysisCancelled("Analysis stopped by user")

    def report(step, total, msg):
        check_stop()
        print(f"  [Pipeline] Step {step}/{total}: {msg}")  # Always log to stdout
        if progress_callback:
            progress_callback(step, total, msg)

    try:
        # Step 1: Compute metrics
        report(1, 7, f"Computing 32+ metrics for {ticker}...")
        stock_data = compute_all_metrics(ticker)
        if not stock_data:
            results["error"] = f"Could not fetch data for {ticker}"
            return results

        # Score the stock
        stock_data["composite_score"] = compute_composite_score(stock_data["metrics"])
        results["stock"] = stock_data
        results["metrics"] = stock_data["metrics"]

        check_stop()

        # Step 2: Save scan result
        report(2, 7, "Saving scan result...")
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
        print(f"  [Pipeline] scan_id={scan_id} saved for {ticker}")

        # Step 3: Run quant engine
        report(3, 7, "Running quantitative prediction engine...")
        try:
            quant = run_quant_engine(ticker)
            if quant and not quant.get("error"):
                save_quant_predictions(scan_id, ticker, quant)
                print(f"  [Pipeline] Quant predictions saved for {ticker}")
            results["quant"] = quant
        except AnalysisCancelled:
            raise
        except Exception as e:
            print(f"  [Pipeline] Quant error (non-fatal): {e}")
            results["quant_error"] = str(e)

        check_stop()

        # Step 4: Health check & run agents
        report(4, 7, "Running 36 AI analyst agents...")
        run_health_check()
        analyses = run_all_agents_on_stock(stock_data, stop_flag=stop_flag)
        results["analyses"] = analyses
        print(f"  [Pipeline] {len(analyses)} agents completed for {ticker}")

        check_stop()

        # Step 5: Research agents
        report(5, 7, "Running 11 research verification agents...")
        try:
            research = run_research_agents_on_stock(stock_data, analyses, stop_flag=stop_flag)
            results["research"] = research
            print(f"  [Pipeline] {len(research)} research agents completed for {ticker}")
        except AnalysisCancelled:
            raise
        except Exception as e:
            print(f"  [Pipeline] Research error (non-fatal): {e}")
            results["research_error"] = str(e)

        check_stop()

        # Step 6: Aggregate — THIS IS CRITICAL, use fallback if LLM fails
        report(6, 7, "Aggregating all analyses into final verdict...")
        all_analyses = analyses + (results.get("research") or [])

        try:
            aggregate_analyses(ticker, scan_id, all_analyses, stock_data)
            print(f"  [Pipeline] LLM aggregation saved for {ticker}")
        except Exception as e:
            print(f"  [Pipeline] LLM aggregation FAILED: {e}")
            print(f"  [Pipeline] {traceback.format_exc()}")
            # FALLBACK: math-based aggregation — ensures we always have a report
            fallback = _fallback_aggregation(ticker, scan_id, all_analyses)
            if not fallback:
                print(f"  [Pipeline] Even fallback aggregation failed for {ticker}")

        # Step 7: Done
        report(7, 7, "Analysis complete!")
        results["success"] = True
        print(f"  [Pipeline] SUCCESS: {ticker} analysis complete")

    except AnalysisCancelled:
        results["error"] = "Analysis stopped by user"
        results["success"] = False
        results["cancelled"] = True
        print(f"  [Pipeline] CANCELLED: {ticker}")
    except Exception as e:
        print(f"  [Pipeline] FATAL ERROR for {ticker}: {e}")
        print(f"  [Pipeline] {traceback.format_exc()}")
        results["error"] = str(e)
        results["success"] = False

    return results
