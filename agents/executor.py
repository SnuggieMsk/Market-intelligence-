"""
Agent executor: runs all 32+ analyst agents against each standout stock.
Distributes across Gemini and Groq with rate limiting and retries.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from config.settings import MAX_CONCURRENT_AGENTS, AGENT_TIMEOUT_SECONDS, INTER_AGENT_DELAY
from agents.personalities import AGENT_PERSONALITIES
from agents.llm_providers import llm_pool, parse_agent_response
from data.database import save_agent_analysis

console = Console()


def build_stock_context(stock: dict) -> str:
    """Build a detailed context string about the stock/commodity for agents to analyze."""
    from scanner.universe import is_commodity, get_commodity_info

    metrics = stock.get("metrics", {})
    reasons = stock.get("standout_reasons", [])
    ticker = stock["ticker"]

    # Detect if this is a commodity
    if is_commodity(ticker):
        return _build_commodity_context(stock, metrics, reasons)

    context = f"""
=== STOCK ANALYSIS REQUEST ===

Company: {stock.get('company_name', ticker)}
Ticker: {ticker}
Sector: {stock.get('sector', 'Unknown')} | Industry: {stock.get('industry', 'Unknown')}
Current Price: {_format_price(stock.get('current_price', 0), ticker)}
Market Cap: {_format_price(stock.get('market_cap', 0), ticker)}
Exchange: NSE (National Stock Exchange of India)

=== WHY THIS STANDS OUT ===
{chr(10).join(f'  - {r}' for r in reasons) if reasons else '  - High composite score across multiple metrics'}

=== DETAILED METRICS ===

PRICE ACTION:
  - Price vs 52-week low: {metrics.get('price_vs_52w_low', 0):.1f}% above
  - Price vs 52-week high: {metrics.get('price_vs_52w_high', 0):.1f}% below
  - Daily return: {metrics.get('daily_return', 0):+.2f}%
  - Weekly return: {metrics.get('weekly_return', 0):+.2f}%
  - Monthly return: {metrics.get('monthly_return', 0):+.2f}%
  - Gap percentage: {metrics.get('gap_percentage', 0):+.2f}%
  - Intraday range: {metrics.get('intraday_range', 0):.2f}%
  - Price vs 200-SMA: {metrics.get('price_vs_sma200', 0):+.2f}%

VOLUME:
  - Volume surge (vs 20d avg): {metrics.get('volume_surge', 1):.1f}x
  - Relative volume (5d vs 20d): {metrics.get('relative_volume', 1):.1f}x
  - Volume-price trend: {metrics.get('volume_price_trend', 0):+.2f}
  - Accumulation/Distribution: {'Accumulating' if metrics.get('accumulation_distribution', 0) > 0 else 'Distributing'}
  - OBV trend: {'Rising' if metrics.get('on_balance_volume_trend', 0) > 0 else 'Falling'}

VOLATILITY:
  - Historical volatility (ann.): {metrics.get('historical_volatility', 0):.1f}%
  - ATR as % of price: {metrics.get('atr_percentage', 0):.2f}%
  - Bollinger bandwidth: {metrics.get('bollinger_squeeze', 0):.1f}%
  - IV percentile: {metrics.get('iv_percentile', 0):.0f}%

MOMENTUM:
  - RSI (14): {metrics.get('rsi', 50):.1f}
  - MACD: {'Bullish' if metrics.get('macd_signal', 0) > 0 else 'Bearish'}
  - Stochastic: {'Bullish crossover' if metrics.get('stochastic_crossover', 0) > 0 else 'Bearish crossover'}
  - Momentum score: {metrics.get('momentum_score', 5):.1f}/10
  - Rate of change (10d): {metrics.get('rate_of_change', 0):+.2f}%

FUNDAMENTALS:
  - P/E ratio: {metrics.get('pe_ratio_vs_sector', 0):.1f}
  - P/B ratio: {metrics.get('pb_ratio', 0):.2f}
  - Debt/Equity: {metrics.get('debt_to_equity', 0):.1f}
  - Revenue growth: {metrics.get('revenue_growth', 0):+.1f}%
  - Earnings growth: {metrics.get('earnings_surprise', 0):+.1f}%
  - FCF yield: {metrics.get('free_cash_flow_yield', 0):.2f}%

SENTIMENT & MARKET:
  - Short interest: {metrics.get('short_interest', 0):.1f}% of float
  - Insider ownership: {metrics.get('insider_buying', 0):.1f}%
  - Analyst rating: {metrics.get('analyst_rating_change', 3):.1f}/5 (1=strong buy)
  - Sector relative strength: {metrics.get('sector_relative_strength', 0):+.1f}%
"""
    return context


def _format_price(price, ticker=""):
    """Format price with correct currency symbol."""
    from scanner.universe import is_commodity, get_commodity_info
    if is_commodity(ticker):
        info = get_commodity_info(ticker)
        sym = "$" if info.get("currency") == "USD" else "Rs."
        return f"{sym}{price:,.2f}"
    return f"Rs.{price:,.2f}"


def _build_commodity_context(stock: dict, metrics: dict, reasons: list) -> str:
    """Build context string specifically for commodity analysis."""
    from scanner.universe import get_commodity_info

    ticker = stock["ticker"]
    info = get_commodity_info(ticker)
    currency_sym = "$" if info.get("currency") == "USD" else "Rs."

    context = f"""
=== COMMODITY ANALYSIS REQUEST ===

Commodity: {info.get('name', ticker)}
Ticker: {ticker}
Category: {info.get('category', 'Unknown')}
Exchange: {info.get('exchange', 'Unknown')}
Current Price: {currency_sym}{stock.get('current_price', 0):,.2f}
Currency: {info.get('currency', 'USD')}
Asset Type: COMMODITY (Not a stock — no P/E, no earnings, no management)

=== WHY THIS COMMODITY STANDS OUT ===
{chr(10).join(f'  - {r}' for r in reasons) if reasons else '  - Significant price/volume activity detected'}

=== PRICE & TECHNICAL METRICS ===

PRICE ACTION:
  - Price vs 52-week low: {metrics.get('price_vs_52w_low', 0):.1f}% above
  - Price vs 52-week high: {metrics.get('price_vs_52w_high', 0):.1f}% below
  - Daily return: {metrics.get('daily_return', 0):+.2f}%
  - Weekly return: {metrics.get('weekly_return', 0):+.2f}%
  - Monthly return: {metrics.get('monthly_return', 0):+.2f}%
  - Gap percentage: {metrics.get('gap_percentage', 0):+.2f}%
  - Intraday range: {metrics.get('intraday_range', 0):.2f}%
  - Price vs 200-SMA: {metrics.get('price_vs_sma200', 0):+.2f}%

VOLUME & OPEN INTEREST:
  - Volume surge (vs 20d avg): {metrics.get('volume_surge', 1):.1f}x
  - Relative volume (5d vs 20d): {metrics.get('relative_volume', 1):.1f}x
  - Volume-price trend: {metrics.get('volume_price_trend', 0):+.2f}
  - Accumulation/Distribution: {'Accumulating' if metrics.get('accumulation_distribution', 0) > 0 else 'Distributing'}
  - OBV trend: {'Rising' if metrics.get('on_balance_volume_trend', 0) > 0 else 'Falling'}

VOLATILITY:
  - Historical volatility (ann.): {metrics.get('historical_volatility', 0):.1f}%
  - ATR as % of price: {metrics.get('atr_percentage', 0):.2f}%
  - Bollinger bandwidth: {metrics.get('bollinger_squeeze', 0):.1f}%
  - IV percentile: {metrics.get('iv_percentile', 0):.0f}%

MOMENTUM:
  - RSI (14): {metrics.get('rsi', 50):.1f}
  - MACD: {'Bullish' if metrics.get('macd_signal', 0) > 0 else 'Bearish'}
  - Stochastic: {'Bullish crossover' if metrics.get('stochastic_crossover', 0) > 0 else 'Bearish crossover'}
  - Momentum score: {metrics.get('momentum_score', 5):.1f}/10
  - Rate of change (10d): {metrics.get('rate_of_change', 0):+.2f}%

=== COMMODITY-SPECIFIC ANALYSIS CONTEXT ===
(Use your domain knowledge for the following — data above is technical only)

KEY FACTORS TO CONSIDER:
  - Supply/demand fundamentals for {info.get('name', ticker)}
  - Geopolitical risks affecting this commodity
  - Seasonal patterns and weather impacts
  - USD/DXY correlation (inverse for most commodities)
  - Central bank policy impact (especially on precious metals)
  - India-specific: import dependency, MCX trends, government policy
  - Inventory levels at major exchanges (LME/COMEX/SHFE)
  - Contango/backwardation structure implications

NOTE: Fundamental metrics (P/E, P/B, D/E, revenue, earnings, FCF) are NOT applicable.
Focus on: technicals, supply-demand, macro drivers, positioning, and seasonal patterns.
"""
    return context


ANALYSIS_PROMPT_TEMPLATE = """
{stock_context}

=== YOUR ANALYSIS TASK ===

Analyze this asset from YOUR unique perspective. Be BRUTAL and HONEST.
Do NOT sugarcoat. If it's garbage, say it's garbage. If it's gold, explain why.

You MUST respond in this exact JSON format:
{{
    "verdict": "STRONG_BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG_SELL",
    "confidence": 0.0 to 1.0,
    "score": 1.0 to 10.0,
    "reasoning": "Your detailed 3-5 sentence analysis from your unique perspective",
    "key_points": ["point 1", "point 2", "point 3"],
    "risks": ["risk 1", "risk 2"],
    "catalysts": ["catalyst 1", "catalyst 2"],
    "time_horizon": "short_term | medium_term | long_term",
    "conviction_level": "low | medium | high | very_high"
}}

Remember: You are {agent_name}. Stay in character. Be specific and data-driven.
"""


def run_single_agent(agent: dict, stock: dict) -> dict:
    """Run a single agent analysis on a stock."""
    stock_context = build_stock_context(stock)
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        stock_context=stock_context,
        agent_name=agent["name"],
    )

    try:
        raw_response = llm_pool.call_llm(
            prompt=prompt,
            system_instruction=agent["system_prompt"],
            prefer=agent.get("prefer_provider", "gemini_lite"),
        )
        analysis = parse_agent_response(raw_response)
        analysis["agent_name"] = agent["name"]
        analysis["agent_role"] = agent["role"]
        return analysis
    except Exception as e:
        return {
            "agent_name": agent["name"],
            "agent_role": agent["role"],
            "verdict": "ERROR",
            "confidence": 0,
            "score": 5.0,
            "reasoning": f"Agent failed: {str(e)}",
            "key_points": [],
            "risks": [],
            "catalysts": [],
        }


def run_health_check() -> list:
    """
    Run provider health check once. Returns list of alive providers.
    Results are cached — call this at startup before running agents.
    """
    global _health_check_done, _alive_providers
    if _health_check_done:
        return _alive_providers

    console.print("\n[bold yellow]Health Check: Testing LLM providers (1 call each)...[/bold yellow]")
    health = llm_pool.check_provider_health()

    _alive_providers = [p for p, ok in health.items() if ok]
    _health_check_done = True

    for p, ok in health.items():
        status = "[bold green]ALIVE[/bold green]" if ok else "[bold red]DEAD — will skip[/bold red]"
        console.print(f"  {p:15s} {status}")

    if not _alive_providers:
        console.print("[bold red]WARNING: No LLM providers available! All agents will fail.[/bold red]")
    else:
        console.print(f"[green]Active providers: {', '.join(_alive_providers)}[/green]")

    return _alive_providers


# Module-level state — health check runs once per session
_health_check_done = False
_alive_providers = []


def run_all_agents_on_stock(stock: dict, stop_flag=None) -> list:
    """
    Run all 36 agents against a single stock.
    Runs sequentially with delays to respect free tier rate limits.
    Only uses providers that passed health check — zero wasted calls.
    stop_flag: threading.Event — if set, stops at the next agent boundary.
    """
    ticker = stock["ticker"]
    scan_id = stock.get("scan_id")

    console.print(f"\n[bold magenta]Running {len(AGENT_PERSONALITIES)} agents on {ticker}...[/bold magenta]")

    # Ensure health check has been done
    healthy = run_health_check()
    if healthy:
        console.print(f"[dim]Routing to: {', '.join(healthy)}[/dim]")
        # All agents prefer the highest-priority alive provider (gemini_lite > gemini > groq).
        # Fallback to other providers happens per-call inside call_llm.
        from config.settings import PROVIDER_PRIORITY
        primary = next((p for p in PROVIDER_PRIORITY if p in healthy), healthy[0])
        for agent in AGENT_PERSONALITIES:
            agent["prefer_provider"] = primary

    analyses = []
    success_count = 0
    error_count = 0
    consecutive_errors = 0
    current_delay = INTER_AGENT_DELAY  # Adaptive delay — increases on rate limit errors

    for i, agent in enumerate(AGENT_PERSONALITIES):
        # Check stop flag before each agent
        if stop_flag and stop_flag.is_set():
            console.print(f"\n  [yellow]Stopped by user after {success_count} agents[/yellow]")
            break

        agent_num = i + 1
        total = len(AGENT_PERSONALITIES)

        # If we've had consecutive rate-limit errors, pause for a full window reset
        if consecutive_errors >= 3:
            cooldown = 60
            console.print(
                f"  [yellow]PAUSE {consecutive_errors} consecutive errors — cooling down {cooldown}s for rate limits to reset...[/yellow]"
            )
            time.sleep(cooldown)
            consecutive_errors = 0  # Reset counter after cooldown
            current_delay = INTER_AGENT_DELAY  # Reset delay too

        try:
            analysis = run_single_agent(agent, stock)
            analyses.append(analysis)

            # Save to DB
            if scan_id:
                save_agent_analysis(
                    scan_id=scan_id,
                    ticker=ticker,
                    agent_name=analysis["agent_name"],
                    agent_role=analysis["agent_role"],
                    analysis=analysis,
                )

            verdict = analysis.get("verdict", "?")
            conf = analysis.get("confidence", 0)
            is_error = verdict == "ERROR"

            if is_error:
                error_count += 1
                consecutive_errors += 1
                # Increase delay when hitting errors (likely rate limited)
                current_delay = min(current_delay + 3, 30)
                console.print(
                    f"  [{agent_num:2d}/{total}] [red]{analysis['agent_name']:40s} -> ERROR[/red]"
                )
            else:
                success_count += 1
                consecutive_errors = 0  # Reset on success
                current_delay = max(current_delay - 1, INTER_AGENT_DELAY)  # Ease back down
                console.print(
                    f"  [{agent_num:2d}/{total}] [dim]{analysis['agent_name']:40s}[/dim] -> "
                    f"[{'green' if 'BUY' in verdict else 'red' if 'SELL' in verdict else 'yellow'}]"
                    f"{verdict:12s}[/] (conf: {conf:.0%})"
                )

        except Exception as e:
            error_count += 1
            consecutive_errors += 1
            current_delay = min(current_delay + 3, 30)
            console.print(f"  [{agent_num:2d}/{total}] [red]{agent['name']}: Failed - {e}[/red]")

        # Adaptive delay between agents
        if agent_num < total:
            time.sleep(current_delay)

    console.print(
        f"\n  [bold]Done: {success_count} succeeded, {error_count} errors[/bold]"
    )
    return analyses


def run_agents_on_all_stocks(stocks: list) -> dict:
    """
    Run all agents on all standout stocks.
    Returns dict: {ticker: [analyses]}
    """
    all_results = {}

    for i, stock in enumerate(stocks, 1):
        console.print(f"\n[bold cyan]=== Stock {i}/{len(stocks)}: {stock['ticker']} ===[/bold cyan]")
        analyses = run_all_agents_on_stock(stock)
        all_results[stock["ticker"]] = analyses

        # Brief pause between stocks to avoid rate limits
        if i < len(stocks):
            time.sleep(2)

    return all_results


# ── Research Agents ──────────────────────────────────────────────────────────

RESEARCH_PROMPT_TEMPLATE = """
{stock_context}

{research_context}

═══ EXISTING AGENT ANALYSIS SUMMARY ═══
{existing_verdicts}

═══ YOUR RESEARCH ANALYSIS TASK ═══

You have access to BOTH the stock's quantitative metrics AND real-world research data
(news, earnings, annual reports, regulatory developments). Cross-reference them.

Your job is to verify whether the other agents' analysis matches reality.
Look for gaps between what the numbers say and what's actually happening in the real world.
Consider regulatory, governance, and policy developments that may create tailwinds or headwinds.

Respond in this exact JSON format:
{{
    "verdict": "STRONG_BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG_SELL",
    "confidence": 0.0 to 1.0,
    "score": 1.0 to 10.0,
    "reasoning": "Your detailed 3-5 sentence analysis cross-referencing research data with metrics",
    "key_points": ["point 1", "point 2", "point 3"],
    "risks": ["risk from research data"],
    "catalysts": ["catalyst from research data"],
    "reality_check": "Does the company narrative match the numbers? Explain.",
    "narrative_gap": "What are other agents missing that the news/data reveals?"
}}

Remember: You are {agent_name}. Stay in character. Be specific and data-driven.
"""


def _build_existing_verdicts_summary(analyses: list) -> str:
    """Summarize base 36 agents' verdicts for research agents to cross-reference."""
    if not analyses:
        return "No prior analyses available."

    buy_count = sum(1 for a in analyses if "BUY" in a.get("verdict", ""))
    sell_count = sum(1 for a in analyses if "SELL" in a.get("verdict", ""))
    neutral_count = len(analyses) - buy_count - sell_count
    avg_score = sum(a.get("score", 5) for a in analyses) / max(len(analyses), 1)

    lines = [
        f"Total agents: {len(analyses)} | Buy: {buy_count} | Neutral: {neutral_count} | Sell: {sell_count}",
        f"Average score: {avg_score:.1f}/10",
        "",
        "Top bull/bear views:",
    ]

    # Top 3 highest and lowest scores
    sorted_analyses = sorted(analyses, key=lambda a: a.get("score", 5), reverse=True)
    for a in sorted_analyses[:3]:
        lines.append(f"  BULL: {a.get('agent_name', '?')} — {a.get('verdict', '?')} ({a.get('score', 0)}/10): {a.get('reasoning', '')[:100]}")
    for a in sorted_analyses[-3:]:
        lines.append(f"  BEAR: {a.get('agent_name', '?')} — {a.get('verdict', '?')} ({a.get('score', 0)}/10): {a.get('reasoning', '')[:100]}")

    return "\n".join(lines)


def run_research_agents_on_stock(stock: dict, base_analyses: list, stop_flag=None) -> list:
    """
    Run 11 research agents that cross-reference news/earnings/reports/regulations
    against the base 36 agents' analysis. Returns list of research analyses.
    """
    from research.news_fetcher import build_research_context
    from research.research_agents import RESEARCH_AGENT_PERSONALITIES

    ticker = stock["ticker"]
    scan_id = stock.get("scan_id")
    company_name = stock.get("company_name", ticker)

    console.print(f"\n[bold blue]Running {len(RESEARCH_AGENT_PERSONALITIES)} research agents on {ticker}...[/bold blue]")

    # Build contexts
    stock_context = build_stock_context(stock)
    research_context = build_research_context(ticker, company_name)
    existing_verdicts = _build_existing_verdicts_summary(base_analyses)

    # Ensure health check done — all research agents prefer primary provider
    healthy = run_health_check()
    if healthy:
        from config.settings import PROVIDER_PRIORITY
        primary = next((p for p in PROVIDER_PRIORITY if p in healthy), healthy[0])
        for agent in RESEARCH_AGENT_PERSONALITIES:
            agent["prefer_provider"] = primary

    analyses = []
    success_count = 0
    error_count = 0
    consecutive_errors = 0
    current_delay = INTER_AGENT_DELAY

    for i, agent in enumerate(RESEARCH_AGENT_PERSONALITIES):
        # Check stop flag before each research agent
        if stop_flag and stop_flag.is_set():
            console.print(f"\n  [yellow]Stopped by user after {success_count} research agents[/yellow]")
            break

        agent_num = i + 1
        total = len(RESEARCH_AGENT_PERSONALITIES)

        # Cooldown after consecutive errors
        if consecutive_errors >= 2:
            cooldown = 60
            console.print(
                f"  [yellow]PAUSE {consecutive_errors} consecutive errors — cooling down {cooldown}s...[/yellow]"
            )
            time.sleep(cooldown)
            consecutive_errors = 0
            current_delay = INTER_AGENT_DELAY

        prompt = RESEARCH_PROMPT_TEMPLATE.format(
            stock_context=stock_context,
            research_context=research_context,
            existing_verdicts=existing_verdicts,
            agent_name=agent["name"],
        )

        try:
            raw_response = llm_pool.call_llm(
                prompt=prompt,
                system_instruction=agent["system_prompt"],
                prefer=agent.get("prefer_provider", "gemini_lite"),
            )
            analysis = parse_agent_response(raw_response)
            analysis["agent_name"] = agent["name"]
            analysis["agent_role"] = agent["role"]
            analyses.append(analysis)

            if scan_id:
                save_agent_analysis(
                    scan_id=scan_id,
                    ticker=ticker,
                    agent_name=analysis["agent_name"],
                    agent_role=analysis["agent_role"],
                    analysis=analysis,
                )

            verdict = analysis.get("verdict", "?")
            conf = analysis.get("confidence", 0)
            if verdict == "ERROR":
                error_count += 1
                consecutive_errors += 1
                current_delay = min(current_delay + 3, 30)
                console.print(f"  [R{agent_num}/{total}] [red]{analysis['agent_name']:40s} -> ERROR[/red]")
            else:
                success_count += 1
                consecutive_errors = 0
                current_delay = max(current_delay - 1, INTER_AGENT_DELAY)
                console.print(
                    f"  [R{agent_num}/{total}] [dim]{analysis['agent_name']:40s}[/dim] -> "
                    f"[{'green' if 'BUY' in verdict else 'red' if 'SELL' in verdict else 'yellow'}]"
                    f"{verdict:12s}[/] (conf: {conf:.0%})"
                )

        except Exception as e:
            error_count += 1
            consecutive_errors += 1
            current_delay = min(current_delay + 3, 30)
            console.print(f"  [R{agent_num}/{total}] [red]{agent['name']}: Failed - {e}[/red]")

        if agent_num < total:
            time.sleep(current_delay)

    console.print(f"\n  [bold]Research agents: {success_count} succeeded, {error_count} errors[/bold]")
    return analyses


def run_research_on_all_stocks(stocks: list, all_base_analyses: dict) -> dict:
    """Run research agents on all stocks. Returns {ticker: [research_analyses]}."""
    all_research = {}

    for i, stock in enumerate(stocks, 1):
        ticker = stock["ticker"]
        base = all_base_analyses.get(ticker, [])
        console.print(f"\n[bold blue]=== Research {i}/{len(stocks)}: {ticker} ===[/bold blue]")
        research = run_research_agents_on_stock(stock, base)
        all_research[ticker] = research

        if i < len(stocks):
            time.sleep(2)

    return all_research
