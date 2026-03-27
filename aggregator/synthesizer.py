"""
Aggregator: Multiple meta-agents that synthesize all 32+ individual agent analyses
into a cohesive, actionable report for each stock.
"""

import json
from rich.console import Console
from agents.llm_providers import llm_pool, parse_agent_response
from data.database import save_aggregated_report

console = Console()


# ── Meta-Aggregator Agents ────────────────────────────────────────────────────
# These agents read ALL individual analyses and produce synthesis reports

META_AGENTS = [
    {
        "name": "Data Synthesizer",
        "role": "data_synthesis",
        "system_prompt": """You are the Data Synthesizer. You aggregate all quantitative data points
from 32+ analyst agents into a coherent data-driven summary.
Focus on: What do the numbers actually say? What's the consensus on valuation?
Where do the quantitative agents agree and disagree?
Output a clear, data-driven summary with specific numbers.""",
    },
    {
        "name": "Sentiment Synthesizer",
        "role": "sentiment_synthesis",
        "system_prompt": """You are the Sentiment Synthesizer. You aggregate all sentiment, behavioral,
and market psychology analyses from the 32+ agents.
Focus on: What's the overall mood? Are agents bullish or bearish? What behavioral biases
are flagged? What does crowd psychology suggest?
Output a clear sentiment summary with specific agent references.""",
    },
    {
        "name": "Prediction Synthesizer",
        "role": "prediction_synthesis",
        "system_prompt": """You are the Prediction Synthesizer. You aggregate all forward-looking views
from the 32+ agents into probability-weighted scenarios.
Focus on: What are the bull/bear/base cases? What probabilities does each deserve?
What catalysts and risks are most cited? What's the expected value?
Output scenario analysis with explicit probabilities.""",
    },
    {
        "name": "Final Verdict Chief",
        "role": "final_verdict",
        "system_prompt": """You are the Chief Investment Officer making the FINAL call.
You have read ALL 32+ analyst opinions and the three synthesis reports.
Your job is to cut through the noise and deliver a clear, actionable verdict.
Be decisive. Weigh the evidence. Explain your reasoning.
Include: verdict, conviction, time horizon, position sizing suggestion, key risks, and triggers.""",
    },
]


def build_analyses_summary(analyses: list) -> str:
    """Format all agent analyses into a readable summary for meta-agents."""
    lines = ["═══ INDIVIDUAL AGENT ANALYSES (32+ Perspectives) ═══\n"]

    # Group by verdict
    verdicts = {}
    for a in analyses:
        v = a.get("verdict", "NEUTRAL")
        if v not in verdicts:
            verdicts[v] = []
        verdicts[v].append(a)

    # Summary stats
    total = len(analyses)
    buy_count = sum(1 for a in analyses if "BUY" in a.get("verdict", ""))
    sell_count = sum(1 for a in analyses if "SELL" in a.get("verdict", ""))
    neutral_count = total - buy_count - sell_count
    avg_score = sum(a.get("score", 5) for a in analyses) / max(total, 1)
    avg_conf = sum(a.get("confidence", 0.5) for a in analyses) / max(total, 1)

    lines.append(f"VERDICT DISTRIBUTION: {buy_count} Buy | {neutral_count} Neutral | {sell_count} Sell")
    lines.append(f"AVERAGE SCORE: {avg_score:.1f}/10 | AVERAGE CONFIDENCE: {avg_conf:.0%}\n")

    # Each agent's analysis
    for a in analyses:
        name = a.get("agent_name", "Unknown")
        verdict = a.get("verdict", "?")
        conf = a.get("confidence", 0)
        score = a.get("score", 5)
        reasoning = a.get("reasoning", "No reasoning provided")
        key_points = a.get("key_points", [])
        risks = a.get("risks", [])
        catalysts = a.get("catalysts", [])

        lines.append(f"── {name} ──")
        lines.append(f"  Verdict: {verdict} | Score: {score}/10 | Confidence: {conf:.0%}")
        lines.append(f"  Reasoning: {reasoning}")
        if key_points:
            lines.append(f"  Key Points: {'; '.join(key_points[:3])}")
        if risks:
            lines.append(f"  Risks: {'; '.join(risks[:2])}")
        if catalysts:
            lines.append(f"  Catalysts: {'; '.join(catalysts[:2])}")
        lines.append("")

    return "\n".join(lines)


SYNTHESIS_PROMPT = """
{analyses_summary}

═══ YOUR SYNTHESIS TASK ═══

You have read analyses from 32+ independent analyst agents, each with a unique perspective.
Now synthesize their collective wisdom from YOUR specific angle.

Respond in this JSON format:
{{
    "summary": "Your detailed 5-8 sentence synthesis",
    "key_agreements": ["What most agents agree on"],
    "key_disagreements": ["Where agents disagree significantly"],
    "strongest_bull_points": ["Top 3 bull arguments"],
    "strongest_bear_points": ["Top 3 bear arguments"],
    "confidence_in_consensus": 0.0 to 1.0,
    "notable_outlier_views": ["Any contrarian views worth highlighting"]
}}
"""


FINAL_VERDICT_PROMPT = """
{analyses_summary}

═══ SYNTHESIS REPORTS ═══

DATA SYNTHESIS:
{data_synthesis}

SENTIMENT SYNTHESIS:
{sentiment_synthesis}

PREDICTION SYNTHESIS:
{prediction_synthesis}

═══ YOUR FINAL VERDICT ═══

As Chief Investment Officer, deliver the FINAL assessment. Cut through the noise.

Respond in this JSON format:
{{
    "overall_verdict": "STRONG_BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG_SELL",
    "overall_score": 1.0 to 10.0,
    "conviction": "low" | "medium" | "high" | "very_high",
    "bull_case": "2-3 sentence bull case",
    "bear_case": "2-3 sentence bear case",
    "consensus_summary": "3-5 sentence overall assessment",
    "agent_agreement_pct": 0 to 100,
    "key_risks": ["Top 3 risks"],
    "key_catalysts": ["Top 3 catalysts"],
    "time_horizon": "1-3 months | 3-6 months | 6-12 months | 1-3 years",
    "position_size": "0% | 1-2% | 2-5% | 5-10% of portfolio",
    "entry_strategy": "Description of how to enter",
    "exit_triggers": ["When to sell"],
    "recommendation": "Final 2-3 sentence recommendation with specific action"
}}
"""


def aggregate_analyses(ticker: str, scan_id: int, analyses: list, stock_data: dict) -> dict:
    """
    Run meta-aggregator agents to synthesize all individual analyses.
    Returns the final aggregated report.
    """
    console.print(f"\n[bold yellow]═══ Aggregating {len(analyses)} analyses for {ticker} ═══[/bold yellow]")

    analyses_summary = build_analyses_summary(analyses)

    # Step 1: Run the three synthesis agents
    synthesis_results = {}

    for meta_agent in META_AGENTS[:3]:  # Data, Sentiment, Prediction synthesizers
        console.print(f"  [cyan]Running {meta_agent['name']}...[/cyan]")
        try:
            prompt = SYNTHESIS_PROMPT.format(analyses_summary=analyses_summary)
            raw = llm_pool.call_llm(
                prompt=prompt,
                system_instruction=meta_agent["system_prompt"],
                prefer="gemini",
            )
            synthesis_results[meta_agent["role"]] = parse_agent_response(raw)
            console.print(f"  [green]✓ {meta_agent['name']} complete[/green]")
        except Exception as e:
            console.print(f"  [red]✗ {meta_agent['name']} failed: {e}[/red]")
            synthesis_results[meta_agent["role"]] = {"summary": f"Failed: {e}"}

    # Step 2: Final Verdict from CIO
    console.print(f"  [cyan]Running Final Verdict Chief...[/cyan]")
    try:
        final_prompt = FINAL_VERDICT_PROMPT.format(
            analyses_summary=analyses_summary,
            data_synthesis=json.dumps(synthesis_results.get("data_synthesis", {}), indent=2),
            sentiment_synthesis=json.dumps(synthesis_results.get("sentiment_synthesis", {}), indent=2),
            prediction_synthesis=json.dumps(synthesis_results.get("prediction_synthesis", {}), indent=2),
        )
        raw = llm_pool.call_llm(
            prompt=final_prompt,
            system_instruction=META_AGENTS[3]["system_prompt"],
            prefer="gemini",
        )
        final_report = parse_agent_response(raw)
    except Exception as e:
        console.print(f"  [red]✗ Final Verdict failed: {e}[/red]")
        final_report = {
            "overall_verdict": "NEUTRAL",
            "overall_score": 5.0,
            "consensus_summary": f"Aggregation failed: {e}",
            "recommendation": "Manual review required",
        }

    # Merge synthesis into final report
    final_report["data_summary"] = synthesis_results.get("data_synthesis", {}).get("summary", "")
    final_report["sentiment_summary"] = synthesis_results.get("sentiment_synthesis", {}).get("summary", "")
    final_report["prediction_summary"] = synthesis_results.get("prediction_synthesis", {}).get("summary", "")
    final_report["synthesis_details"] = synthesis_results

    # Save to database
    save_aggregated_report(scan_id, ticker, final_report)

    verdict = final_report.get("overall_verdict", "?")
    score = final_report.get("overall_score", 0)
    console.print(
        f"\n  [bold]FINAL VERDICT for {ticker}: "
        f"[{'green' if 'BUY' in verdict else 'red' if 'SELL' in verdict else 'yellow'}]"
        f"{verdict}[/] (Score: {score}/10)[/bold]"
    )

    return final_report


def aggregate_all(stocks: list, all_analyses: dict) -> dict:
    """Aggregate analyses for all stocks. Returns {ticker: report}."""
    reports = {}
    for stock in stocks:
        ticker = stock["ticker"]
        analyses = all_analyses.get(ticker, [])
        if analyses:
            report = aggregate_analyses(ticker, stock.get("scan_id"), analyses, stock)
            reports[ticker] = report
    return reports
