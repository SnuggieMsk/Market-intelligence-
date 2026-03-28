"""
Aggregator: Multiple meta-agents that synthesize all 32+ individual agent analyses
into a cohesive, actionable report for each stock.
"""

import json
import time
from rich.console import Console
from agents.llm_providers import llm_pool, parse_agent_response
from data.database import save_aggregated_report
from research.research_agents import RESEARCH_ROLES
from config.settings import INTER_AGENT_DELAY

console = Console(highlight=False, force_terminal=True)


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
    # Separate base agents from research agents
    base_analyses = [a for a in analyses if a.get("agent_role") not in RESEARCH_ROLES]
    research_analyses = [a for a in analyses if a.get("agent_role") in RESEARCH_ROLES]

    lines = [f"═══ INDIVIDUAL AGENT ANALYSES ({len(base_analyses)} Base + {len(research_analyses)} Research) ═══\n"]

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

    # Add research section if present
    if research_analyses:
        lines.append("\n═══ RESEARCH & NEWS CROSS-REFERENCE ═══\n")
        for a in research_analyses:
            name = a.get("agent_name", "Unknown")
            verdict = a.get("verdict", "?")
            reasoning = a.get("reasoning", "")
            reality_check = a.get("reality_check", "")
            narrative_gap = a.get("narrative_gap", "")
            lines.append(f"── {name} ──")
            lines.append(f"  Verdict: {verdict} | Score: {a.get('score', 5)}/10")
            lines.append(f"  Analysis: {reasoning}")
            if reality_check:
                lines.append(f"  Reality Check: {reality_check}")
            if narrative_gap:
                lines.append(f"  Narrative Gap: {narrative_gap}")
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


def _math_based_aggregation(analyses: list) -> dict:
    """
    Fallback aggregation using pure math when LLM providers are unavailable.
    Computes weighted verdict from agent votes based on confidence scores.
    """
    verdict_scores = {"STRONG_BUY": 10, "BUY": 7.5, "NEUTRAL": 5, "SELL": 2.5, "STRONG_SELL": 0}
    verdict_weights = []
    scores = []
    bull_points = []
    bear_points = []
    risks = []
    catalysts = []

    for a in analyses:
        v = a.get("verdict", "NEUTRAL")
        conf = a.get("confidence", 0.5)
        score = a.get("score", 5.0)
        name = a.get("agent_name", "Unknown")

        # Weighted vote: verdict numeric value × confidence
        v_score = verdict_scores.get(v, 5)
        verdict_weights.append((v_score, conf))
        scores.append(score)

        # Collect bull/bear reasoning
        reasoning = a.get("reasoning", "")
        if v in ("STRONG_BUY", "BUY") and reasoning:
            bull_points.append(f"{name}: {reasoning[:100]}")
        elif v in ("STRONG_SELL", "SELL") and reasoning:
            bear_points.append(f"{name}: {reasoning[:100]}")

        # Collect risks and catalysts (may be JSON strings or lists)
        raw_risks = a.get("risks") or []
        if isinstance(raw_risks, str):
            try:
                raw_risks = json.loads(raw_risks)
            except (json.JSONDecodeError, TypeError):
                raw_risks = []
        for r in raw_risks:
            if isinstance(r, str) and len(r) > 3 and r not in risks:
                risks.append(r)

        raw_cats = a.get("catalysts") or []
        if isinstance(raw_cats, str):
            try:
                raw_cats = json.loads(raw_cats)
            except (json.JSONDecodeError, TypeError):
                raw_cats = []
        for c in raw_cats:
            if isinstance(c, str) and len(c) > 3 and c not in catalysts:
                catalysts.append(c)

    # Weighted average verdict score
    if verdict_weights:
        total_weight = sum(conf for _, conf in verdict_weights)
        if total_weight > 0:
            weighted_avg = sum(v * c for v, c in verdict_weights) / total_weight
        else:
            weighted_avg = 5.0
    else:
        weighted_avg = 5.0

    # Map back to verdict
    if weighted_avg >= 8.5:
        overall_verdict = "STRONG_BUY"
    elif weighted_avg >= 6.5:
        overall_verdict = "BUY"
    elif weighted_avg >= 3.5:
        overall_verdict = "NEUTRAL"
    elif weighted_avg >= 1.5:
        overall_verdict = "SELL"
    else:
        overall_verdict = "STRONG_SELL"

    # Average score
    avg_score = round(sum(scores) / len(scores), 1) if scores else 5.0

    # Verdict distribution for summary
    dist = {}
    for a in analyses:
        v = a.get("verdict", "NEUTRAL")
        dist[v] = dist.get(v, 0) + 1
    dist_str = ", ".join(f"{v}: {c}" for v, c in sorted(dist.items(), key=lambda x: -x[1]))

    consensus = (
        f"Math-based aggregation of {len(analyses)} agents. "
        f"Verdict distribution: {dist_str}. "
        f"Confidence-weighted score: {weighted_avg:.1f}/10."
    )

    # Recommendation
    if overall_verdict in ("STRONG_BUY", "BUY"):
        rec = "Consider buying — majority of agents are bullish."
    elif overall_verdict in ("STRONG_SELL", "SELL"):
        rec = "Consider selling or avoiding — majority of agents are bearish."
    else:
        rec = "Hold or wait — agents are divided, no clear consensus."

    return {
        "overall_verdict": overall_verdict,
        "overall_score": avg_score,
        "consensus_summary": consensus,
        "recommendation": rec,
        "key_risks": risks[:5],
        "key_catalysts": catalysts[:5],
        "bull_case": "; ".join(bull_points[:3]) if bull_points else "Limited bullish sentiment",
        "bear_case": "; ".join(bear_points[:3]) if bear_points else "Limited bearish sentiment",
    }


def aggregate_analyses(ticker: str, scan_id: int, analyses: list, stock_data: dict) -> dict:
    """
    Run meta-aggregator agents to synthesize all individual analyses.
    Returns the final aggregated report.
    """
    console.print(f"\n[bold yellow]=== Aggregating {len(analyses)} analyses for {ticker} ===[/bold yellow]")

    # Fresh health check — agents may have exhausted one provider's rate limits
    console.print("  [dim]Running fresh health check for aggregation...[/dim]")
    llm_pool._demoted_providers.clear()
    llm_pool._consecutive_429s = {"gemini_lite": 0, "gemini": 0, "groq": 0, "openrouter": 0}
    health = llm_pool.check_provider_health()
    alive = [p for p, ok in health.items() if ok]
    console.print(f"  [dim]Alive providers: {', '.join(alive) if alive else 'NONE'}[/dim]")

    analyses_summary = build_analyses_summary(analyses)

    # Step 1: Run the three synthesis agents
    synthesis_results = {}

    for i, meta_agent in enumerate(META_AGENTS[:3]):  # Data, Sentiment, Prediction synthesizers
        if i > 0:
            time.sleep(INTER_AGENT_DELAY)  # Avoid back-to-back rate limits
        console.print(f"  [cyan]Running {meta_agent['name']}...[/cyan]")
        try:
            prompt = SYNTHESIS_PROMPT.format(analyses_summary=analyses_summary)
            raw = llm_pool.call_llm(
                prompt=prompt,
                system_instruction=meta_agent["system_prompt"],
                prefer="gemini_lite",
            )
            synthesis_results[meta_agent["role"]] = parse_agent_response(raw)
            console.print(f"  [green]OK {meta_agent['name']} complete[/green]")
        except Exception as e:
            console.print(f"  [red]FAIL {meta_agent['name']} failed: {e}[/red]")
            synthesis_results[meta_agent["role"]] = {"summary": f"Failed: {e}"}

    # Step 2: Final Verdict from CIO
    time.sleep(INTER_AGENT_DELAY)
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
        console.print(f"  [red]FAIL Final Verdict LLM failed: {e}[/red]")
        console.print(f"  [yellow]Computing math-based aggregation from {len(analyses)} agent votes...[/yellow]")
        final_report = _math_based_aggregation(analyses)

    # Normalize field names — LLMs sometimes use "verdict" instead of "overall_verdict"
    if "overall_verdict" not in final_report and "verdict" in final_report:
        final_report["overall_verdict"] = final_report["verdict"]
    if "overall_score" not in final_report and "score" in final_report:
        final_report["overall_score"] = final_report["score"]
    if "consensus_summary" not in final_report and "reasoning" in final_report:
        final_report["consensus_summary"] = final_report["reasoning"]
    if "key_risks" not in final_report and "risks" in final_report:
        final_report["key_risks"] = final_report["risks"]
    if "key_catalysts" not in final_report and "catalysts" in final_report:
        final_report["key_catalysts"] = final_report["catalysts"]

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
