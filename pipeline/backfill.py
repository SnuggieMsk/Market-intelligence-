"""
Backfill pipeline — identifies and fills data gaps without re-running the full pipeline.

Only runs the missing components per stock:
- Quant predictions (pure math, no API calls)
- Research agents (8 LLM calls per stock)
- Aggregation (4 LLM calls per stock)

Usage:
    python -m pipeline.backfill                    # Audit + backfill all gaps
    python -m pipeline.backfill --audit-only       # Just show what's missing
    python -m pipeline.backfill --ticker RELIANCE.NS  # Backfill one stock
    python -m pipeline.backfill --quant-only       # Only fill quant gaps
    python -m pipeline.backfill --research-only    # Only fill research gaps
"""

import sys
import os
import json
import argparse
import time
from rich.console import Console
from rich.table import Table

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import (
    init_db, get_completeness_all, get_completeness_for_ticker,
    get_scan_result_by_id, get_latest_scan_for_ticker,
    save_quant_predictions, get_agent_analyses_for_scan,
)
from quant.engine import run_quant_engine
from agents.executor import run_research_agents_on_stock, run_all_agents_on_stock, run_health_check
from aggregator.synthesizer import aggregate_analyses

console = Console()

EXPECTED_BASE_AGENTS = 36
EXPECTED_RESEARCH_AGENTS = 8


def print_audit(completeness: dict):
    """Print a rich table showing data completeness for all stocks."""
    table = Table(title="Data Completeness Audit", border_style="dim")
    table.add_column("Ticker", style="bold")
    table.add_column("Scan", justify="center")
    table.add_column("Agents", justify="center")
    table.add_column("Research", justify="center")
    table.add_column("Quant", justify="center")
    table.add_column("Report", justify="center")
    table.add_column("Gaps", style="yellow")

    for ticker, c in sorted(completeness.items()):
        gaps = []
        scan_ok = "[green]Y[/]" if c["has_scan"] else "[red]MISSING[/]"
        agent_ok = f"[green]{c['agent_count']}[/]" if c["agent_count"] >= EXPECTED_BASE_AGENTS else f"[red]{c['agent_count']}/{EXPECTED_BASE_AGENTS}[/]"
        research_ok = f"[green]{c['research_count']}[/]" if c["research_count"] >= EXPECTED_RESEARCH_AGENTS else f"[red]{c['research_count']}/{EXPECTED_RESEARCH_AGENTS}[/]"
        quant_ok = "[green]Y[/]" if c["has_quant"] else "[red]MISSING[/]"
        report_ok = "[green]Y[/]" if c["has_report"] else "[red]MISSING[/]"

        if not c["has_scan"]:
            gaps.append("scan")
        if c["agent_count"] < EXPECTED_BASE_AGENTS:
            gaps.append(f"agents({c['agent_count']}/{EXPECTED_BASE_AGENTS})")
        if c["research_count"] < EXPECTED_RESEARCH_AGENTS:
            gaps.append("research")
        if not c["has_quant"]:
            gaps.append("quant")
        if not c["has_report"]:
            gaps.append("report")

        table.add_row(
            ticker, scan_ok, agent_ok, research_ok, quant_ok, report_ok,
            ", ".join(gaps) if gaps else "[green]Complete[/]"
        )

    console.print(table)
    return completeness


def _build_stock_dict_from_scan(scan_row: dict) -> dict:
    """Reconstruct the stock dict that agents expect from a scan_results row."""
    metrics = json.loads(scan_row["metrics_json"]) if isinstance(scan_row["metrics_json"], str) else scan_row["metrics_json"]
    reasons = []
    if scan_row.get("standout_reasons"):
        try:
            reasons = json.loads(scan_row["standout_reasons"]) if isinstance(scan_row["standout_reasons"], str) else scan_row["standout_reasons"]
        except (json.JSONDecodeError, TypeError):
            reasons = []

    return {
        "ticker": scan_row["ticker"],
        "scan_id": scan_row["id"],
        "company_name": scan_row.get("company_name", scan_row["ticker"]),
        "sector": scan_row.get("sector", "Unknown"),
        "industry": "Unknown",
        "current_price": scan_row.get("current_price", 0),
        "market_cap": scan_row.get("market_cap", 0),
        "composite_score": scan_row.get("composite_score", 0),
        "metrics": metrics,
        "standout_reasons": reasons,
    }


def backfill_quant(ticker: str, scan_id: int):
    """Backfill quant predictions for one stock."""
    console.print(f"  [cyan]Running quant engine for {ticker}...[/cyan]")
    try:
        quant = run_quant_engine(ticker)
        if quant and not quant.get("error"):
            save_quant_predictions(scan_id, ticker, quant)
            console.print(f"  [green]Quant saved for {ticker}[/green]")
            return True
        else:
            console.print(f"  [red]Quant failed for {ticker}: {quant.get('error', 'unknown')}[/red]")
            return False
    except Exception as e:
        console.print(f"  [red]Quant error for {ticker}: {e}[/red]")
        return False


def backfill_research(ticker: str, scan_id: int, stock_dict: dict):
    """Backfill research agents for one stock."""
    from research.research_agents import RESEARCH_ROLES, RESEARCH_AGENT_COUNT
    console.print(f"  [cyan]Running {RESEARCH_AGENT_COUNT} research agents for {ticker}...[/cyan]")
    try:
        # Need base analyses for research agents to cross-reference
        base_analyses = get_agent_analyses_for_scan(scan_id)
        # Filter to base agents only (exclude any existing research)
        base_only = [a for a in base_analyses if a.get("agent_role") not in RESEARCH_ROLES]

        research = run_research_agents_on_stock(stock_dict, base_only)
        console.print(f"  [green]Research agents done for {ticker}: {len(research)} results[/green]")
        return True
    except Exception as e:
        console.print(f"  [red]Research error for {ticker}: {e}[/red]")
        return False


def backfill_agents(ticker: str, stock_dict: dict):
    """Backfill base agents for one stock (if fewer than 36)."""
    console.print(f"  [cyan]Running 36 base agents for {ticker}...[/cyan]")
    try:
        analyses = run_all_agents_on_stock(stock_dict)
        console.print(f"  [green]Base agents done for {ticker}: {len(analyses)} results[/green]")
        return analyses
    except Exception as e:
        console.print(f"  [red]Agent error for {ticker}: {e}[/red]")
        return []


def backfill_aggregation(ticker: str, scan_id: int, stock_dict: dict):
    """Re-run aggregation using all available analyses."""
    console.print(f"  [cyan]Re-aggregating {ticker}...[/cyan]")
    try:
        all_analyses = get_agent_analyses_for_scan(scan_id)
        aggregate_analyses(ticker, scan_id, all_analyses, stock_dict)
        console.print(f"  [green]Aggregation done for {ticker}[/green]")
        return True
    except Exception as e:
        console.print(f"  [red]Aggregation error for {ticker}: {e}[/red]")
        return False


def backfill_stock(ticker: str, quant_only=False, research_only=False, agents_only=False):
    """Backfill all gaps for a single stock."""
    c = get_completeness_for_ticker(ticker)

    if not c["has_scan"]:
        console.print(f"[red]{ticker}: No scan data found. Run full analysis first.[/red]")
        return

    # Use the scan that has the most data (best_scan_id) for research cross-referencing,
    # but the latest scan for new operations
    scan = get_latest_scan_for_ticker(ticker)
    stock_dict = _build_stock_dict_from_scan(scan)
    scan_id = scan["id"]
    best_scan_id = c.get("best_scan_id", scan_id)
    did_something = False

    # Quant
    if not quant_only and not research_only and not agents_only:
        # Fill all gaps
        if not c["has_quant"]:
            backfill_quant(ticker, scan_id)
            did_something = True

        if c["agent_count"] < EXPECTED_BASE_AGENTS:
            backfill_agents(ticker, stock_dict)
            did_something = True

        if c["research_count"] < EXPECTED_RESEARCH_AGENTS:
            run_health_check()
            # Use best_scan_id for research (needs base agent data)
            stock_dict_for_research = dict(stock_dict)
            stock_dict_for_research["scan_id"] = best_scan_id
            backfill_research(ticker, best_scan_id, stock_dict_for_research)
            did_something = True

        # Re-aggregate if we added anything, or if report was missing
        if did_something or not c["has_report"]:
            # Aggregate using best_scan_id which has the agent data
            stock_dict_for_agg = dict(stock_dict)
            stock_dict_for_agg["scan_id"] = best_scan_id
            backfill_aggregation(ticker, best_scan_id, stock_dict_for_agg)
    elif quant_only:
        if not c["has_quant"]:
            backfill_quant(ticker, scan_id)
        else:
            console.print(f"  [dim]{ticker}: Quant already exists[/dim]")
    elif research_only:
        if c["research_count"] < EXPECTED_RESEARCH_AGENTS:
            run_health_check()
            stock_dict_for_research = dict(stock_dict)
            stock_dict_for_research["scan_id"] = best_scan_id
            backfill_research(ticker, best_scan_id, stock_dict_for_research)
            # Re-aggregate with research included
            backfill_aggregation(ticker, best_scan_id, stock_dict_for_research)
        else:
            console.print(f"  [dim]{ticker}: Research already complete ({c['research_count']})[/dim]")
    elif agents_only:
        if c["agent_count"] < EXPECTED_BASE_AGENTS:
            backfill_agents(ticker, stock_dict)
            backfill_aggregation(ticker, scan_id, stock_dict)
        else:
            console.print(f"  [dim]{ticker}: Base agents already complete ({c['agent_count']})[/dim]")


def backfill_all(quant_only=False, research_only=False):
    """Backfill all gaps across all stocks in the database."""
    completeness = get_completeness_all()
    if not completeness:
        console.print("[yellow]No stocks in database. Run a full scan first.[/yellow]")
        return

    print_audit(completeness)

    # Count gaps
    stocks_needing_quant = [t for t, c in completeness.items() if not c["has_quant"]]
    stocks_needing_research = [t for t, c in completeness.items() if c["research_count"] < EXPECTED_RESEARCH_AGENTS]
    stocks_needing_agents = [t for t, c in completeness.items() if c["agent_count"] < EXPECTED_BASE_AGENTS]
    stocks_needing_report = [t for t, c in completeness.items() if not c["has_report"]]

    console.print(f"\n[bold]Gaps found:[/bold]")
    console.print(f"  Quant missing:    {len(stocks_needing_quant)} stocks")
    console.print(f"  Agents missing:   {len(stocks_needing_agents)} stocks")
    console.print(f"  Research missing: {len(stocks_needing_research)} stocks")
    console.print(f"  Report missing:   {len(stocks_needing_report)} stocks")

    if quant_only:
        if not stocks_needing_quant:
            console.print("\n[green]All quant data is complete![/green]")
            return
        console.print(f"\n[bold]Backfilling quant for {len(stocks_needing_quant)} stocks...[/bold]")
        for ticker in stocks_needing_quant:
            backfill_stock(ticker, quant_only=True)
            time.sleep(2)
    elif research_only:
        if not stocks_needing_research:
            console.print("\n[green]All research data is complete![/green]")
            return
        console.print(f"\n[bold]Backfilling research for {len(stocks_needing_research)} stocks...[/bold]")
        for ticker in stocks_needing_research:
            backfill_stock(ticker, research_only=True)
    else:
        # Fill everything
        # 1. Quant first (no API calls, fast)
        if stocks_needing_quant:
            console.print(f"\n[bold]Phase 1: Backfilling quant ({len(stocks_needing_quant)} stocks)...[/bold]")
            for ticker in stocks_needing_quant:
                backfill_stock(ticker, quant_only=True)
                time.sleep(2)

        # 2. Research agents (LLM calls)
        if stocks_needing_research:
            console.print(f"\n[bold]Phase 2: Backfilling research ({len(stocks_needing_research)} stocks)...[/bold]")
            for ticker in stocks_needing_research:
                backfill_stock(ticker, research_only=True)

        # 3. Re-aggregate any that changed
        stocks_changed = set(stocks_needing_quant + stocks_needing_research + stocks_needing_report)
        if stocks_changed:
            console.print(f"\n[bold]Phase 3: Re-aggregating {len(stocks_changed)} stocks...[/bold]")
            for ticker in stocks_changed:
                scan = get_latest_scan_for_ticker(ticker)
                if scan:
                    stock_dict = _build_stock_dict_from_scan(scan)
                    backfill_aggregation(ticker, scan["id"], stock_dict)

    # Final audit
    console.print("\n")
    print_audit(get_completeness_all())
    console.print("[bold green]Backfill complete![/bold green]")


def main():
    parser = argparse.ArgumentParser(description="Backfill missing data")
    parser.add_argument("--audit-only", action="store_true", help="Just show what's missing")
    parser.add_argument("--ticker", type=str, help="Backfill a specific ticker (e.g. RELIANCE.NS)")
    parser.add_argument("--quant-only", action="store_true", help="Only backfill quant gaps")
    parser.add_argument("--research-only", action="store_true", help="Only backfill research gaps")
    args = parser.parse_args()

    init_db()

    if args.audit_only:
        completeness = get_completeness_all()
        print_audit(completeness)
        return

    if args.ticker:
        ticker = args.ticker.strip().upper()
        if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
            ticker = f"{ticker}.NS"
        console.print(f"\n[bold]Backfilling {ticker}...[/bold]")
        backfill_stock(ticker, quant_only=args.quant_only, research_only=args.research_only)
    else:
        backfill_all(quant_only=args.quant_only, research_only=args.research_only)


if __name__ == "__main__":
    main()
