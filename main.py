"""
Market Intelligence System — Main Orchestrator

Usage:
    python main.py              # Run once
    python main.py --continuous # Run continuously on schedule
    python main.py --dashboard  # Launch dashboard only
"""

import sys
import time
import argparse
from datetime import datetime
from rich.console import Console
from rich.panel import Panel

from config.settings import SCAN_INTERVAL_MINUTES
from data.database import init_db
from scanner.scanner import scan_market
from agents.executor import run_agents_on_all_stocks, run_health_check
from aggregator.synthesizer import aggregate_all

console = Console()


def print_banner():
    console.print(Panel.fit(
        "[bold cyan]Market Intelligence System[/bold cyan]\n"
        "[dim]32+ Metrics Scanner | 32+ AI Analyst Agents | Synthesis Dashboard[/dim]\n"
        f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
        border_style="cyan",
    ))


def run_pipeline():
    """Run the full scan → analyze → aggregate pipeline."""
    start = time.time()

    # Step 0: Health check — find which LLM providers are alive
    alive = run_health_check()
    if not alive:
        console.print("[bold red]No LLM providers available. Aborting.[/bold red]")
        console.print("[dim]Wait for rate limits to reset, or check your API keys in .env[/dim]")
        return

    agent_count = 36
    console.print(f"\n[bold]Ready: {len(alive)} provider(s) alive → "
                  f"{agent_count} agents will use {', '.join(alive)}[/bold]")

    # Step 1: Scan the market
    console.print("\n[bold]STEP 1/3: Scanning Market[/bold]")
    standout_stocks = scan_market()

    if not standout_stocks:
        console.print("[yellow]No standout stocks found this scan.[/yellow]")
        return

    # Step 2: Run all agents
    console.print("\n[bold]STEP 2/3: Running AI Agents[/bold]")
    all_analyses = run_agents_on_all_stocks(standout_stocks)

    # Step 3: Aggregate
    console.print("\n[bold]STEP 3/3: Aggregating Results[/bold]")
    reports = aggregate_all(standout_stocks, all_analyses)

    elapsed = time.time() - start
    console.print(Panel.fit(
        f"[bold green]Pipeline Complete![/bold green]\n"
        f"Stocks analyzed: {len(standout_stocks)}\n"
        f"Agent analyses: {sum(len(v) for v in all_analyses.values())}\n"
        f"Reports generated: {len(reports)}\n"
        f"Time: {elapsed/60:.1f} minutes\n\n"
        f"[dim]View results: streamlit run dashboard/app.py[/dim]",
        border_style="green",
    ))


def run_continuous():
    """Run pipeline on a daily schedule."""
    hours = SCAN_INTERVAL_MINUTES / 60
    console.print(f"[bold]Running continuously every {hours:.0f} hours[/bold]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    while True:
        try:
            run_pipeline()
            console.print(
                f"\n[dim]Next scan in {SCAN_INTERVAL_MINUTES} minutes "
                f"(at {datetime.now().strftime('%H:%M')}+{SCAN_INTERVAL_MINUTES}min)...[/dim]"
            )
            time.sleep(SCAN_INTERVAL_MINUTES * 60)
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]Pipeline error: {e}[/red]")
            console.print(f"[dim]Retrying in 5 minutes...[/dim]")
            time.sleep(300)


def launch_dashboard():
    """Launch the Streamlit dashboard."""
    import subprocess
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        "dashboard/app.py",
        "--server.port", "8501",
        "--server.headless", "true",
    ])


def main():
    parser = argparse.ArgumentParser(description="Market Intelligence System")
    parser.add_argument("--continuous", action="store_true", help="Run continuously on schedule")
    parser.add_argument("--dashboard", action="store_true", help="Launch dashboard only")
    parser.add_argument("--scan-only", action="store_true", help="Run scanner only (no agents)")
    args = parser.parse_args()

    print_banner()
    init_db()

    if args.dashboard:
        launch_dashboard()
    elif args.scan_only:
        scan_market()
    elif args.continuous:
        run_continuous()
    else:
        run_pipeline()


if __name__ == "__main__":
    main()
