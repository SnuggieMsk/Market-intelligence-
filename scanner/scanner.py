"""
Main scanner: fetches universe, computes metrics, scores and ranks stocks,
returns top standout candidates for agent analysis.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from config.settings import (
    METRIC_WEIGHTS, TOP_STOCKS_TO_ANALYZE, MIN_MARKET_CAP, MIN_VOLUME
)
from scanner.universe import get_full_universe
from scanner.metrics import compute_all_metrics
from data.database import save_scan_result

console = Console()


def compute_composite_score(metrics: dict) -> float:
    """
    Weighted composite score. Higher = more standout.
    Metrics are normalized and combined using configured weights.
    """
    score = 0.0
    max_possible = 0.0

    for metric_name, weight in METRIC_WEIGHTS.items():
        value = metrics.get(metric_name, 0)
        max_possible += weight * 10

        # Normalize each metric to a 0-10 scale based on its type
        if metric_name == "price_vs_52w_low":
            # Lower = more interesting (closer to 52w low)
            normalized = max(0, 10 - (value / 5))  # 0% from low = 10, 50% = 0
        elif metric_name == "price_vs_52w_high":
            # Higher = more beaten down
            normalized = min(10, value / 5)
        elif metric_name in ("daily_return", "gap_percentage"):
            # Absolute magnitude matters
            normalized = min(10, abs(value) / 2)
        elif metric_name in ("weekly_return", "monthly_return", "rate_of_change"):
            normalized = min(10, abs(value) / 5)
        elif metric_name == "price_vs_sma200":
            # Below SMA is more interesting
            normalized = min(10, max(0, -value / 5))
        elif metric_name == "volume_surge":
            normalized = min(10, (value - 1) * 3)  # 1x = 0, 4x+ = 10
        elif metric_name == "relative_volume":
            normalized = min(10, (value - 1) * 5)
        elif metric_name in ("volume_price_trend", "accumulation_distribution", "on_balance_volume_trend"):
            normalized = 5 + value * 5  # -1 to 1 -> 0 to 10
        elif metric_name == "historical_volatility":
            normalized = min(10, value / 10)
        elif metric_name == "atr_percentage":
            normalized = min(10, value * 2)
        elif metric_name == "bollinger_squeeze":
            # Lower bandwidth = tighter squeeze = more interesting
            normalized = max(0, 10 - value)
        elif metric_name == "iv_percentile":
            normalized = value / 10
        elif metric_name == "rsi":
            # Extremes are interesting (oversold or overbought)
            normalized = max(0, 10 - abs(value - 50) / 5)
            # Flip: extreme RSI = high score
            normalized = 10 - normalized
        elif metric_name in ("macd_signal", "stochastic_crossover"):
            normalized = 5 + value * 5
        elif metric_name == "momentum_score":
            normalized = value  # Already 0-10
        elif metric_name == "pe_ratio_vs_sector":
            normalized = max(0, 10 - (value / 5)) if value > 0 else 5
        elif metric_name == "pb_ratio":
            normalized = max(0, 10 - value * 2) if value > 0 else 5
        elif metric_name == "debt_to_equity":
            normalized = max(0, 10 - (value / 50)) if value > 0 else 5
        elif metric_name == "revenue_growth":
            normalized = min(10, value / 5) if value > 0 else 0
        elif metric_name == "earnings_surprise":
            normalized = min(10, abs(value) / 5)
        elif metric_name == "free_cash_flow_yield":
            normalized = min(10, max(0, value))
        elif metric_name == "short_interest":
            normalized = min(10, value / 3)
        elif metric_name == "insider_buying":
            normalized = min(10, value / 5)
        elif metric_name == "analyst_rating_change":
            normalized = max(0, 10 - (value - 1) * 2.5)  # 1=10, 5=0
        elif metric_name == "sector_relative_strength":
            normalized = min(10, max(0, value / 3 + 5))
        else:
            normalized = 5

        score += weight * max(0, min(10, normalized))

    return (score / max_possible) * 100 if max_possible > 0 else 0


def scan_market() -> list:
    """
    Full market scan pipeline:
    1. Get stock universe
    2. Compute metrics for each stock (parallel)
    3. Score and rank
    4. Return top standouts
    """
    console.print("\n[bold cyan]═══ Market Intelligence Scanner ═══[/bold cyan]\n")

    # Step 1: Get universe
    console.print("[yellow]Fetching stock universe...[/yellow]")
    tickers = get_full_universe()
    console.print(f"[green]Universe: {len(tickers)} stocks[/green]")

    # Step 2: Compute metrics (parallel with progress bar)
    results = []
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
    ) as progress:
        task = progress.add_task("Scanning stocks...", total=len(tickers))

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(compute_all_metrics, t): t for t in tickers}

            for future in as_completed(futures):
                progress.advance(task)
                result = future.result()
                if result:
                    # Apply filters
                    mcap = result.get("market_cap", 0) or 0
                    if mcap >= MIN_MARKET_CAP:
                        results.append(result)
                else:
                    failed += 1

    console.print(f"[green]Scanned: {len(results)} stocks passed filters | {failed} failed[/green]")

    # Step 3: Score and rank
    for r in results:
        r["composite_score"] = compute_composite_score(r["metrics"])

    results.sort(key=lambda x: x["composite_score"], reverse=True)

    # Step 4: Take top standouts
    top = results[:TOP_STOCKS_TO_ANALYZE]

    console.print(f"\n[bold green]Top {len(top)} Standout Stocks:[/bold green]")
    for i, stock in enumerate(top, 1):
        reasons = ", ".join(stock["standout_reasons"][:3]) if stock["standout_reasons"] else "Composite score"
        console.print(
            f"  {i:2d}. [bold]{stock['ticker']:15s}[/bold] "
            f"Score: {stock['composite_score']:.1f} | "
            f"₹{stock['current_price']:.2f} | "
            f"{stock['company_name']} | "
            f"[dim]{reasons}[/dim]"
        )

    # Save to database
    scan_ids = {}
    for stock in top:
        scan_id = save_scan_result(
            ticker=stock["ticker"],
            composite_score=stock["composite_score"],
            metrics=stock["metrics"],
            standout_reasons=stock["standout_reasons"],
            company_name=stock["company_name"],
            sector=stock["sector"],
            market_cap=stock["market_cap"],
            current_price=stock["current_price"],
        )
        scan_ids[stock["ticker"]] = scan_id
        stock["scan_id"] = scan_id

    return top
