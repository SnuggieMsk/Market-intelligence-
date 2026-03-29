"""
Future Outlook Agent System.
Generates macro outlook, sector analysis, and market predictions using LLMs.
Standalone from per-stock analysis — covers the whole market.
"""

import json
import time
from datetime import datetime
from agents.llm_providers import llm_pool, parse_agent_response
from data.database import get_connection

OUTLOOK_AGENTS = [
    {
        "name": "Global Macro Strategist",
        "role": "global_macro",
        "prompt": """Analyze the current global macroeconomic environment and its impact on Indian markets.
Cover: US Fed policy, global interest rates, inflation trends, USD/INR, crude oil prices,
geopolitical risks (China, Middle East, Russia-Ukraine), global recession probability,
and capital flows to emerging markets.
Provide a 3-6 month forward outlook with probability-weighted scenarios.""",
    },
    {
        "name": "India Economy Analyst",
        "role": "india_economy",
        "prompt": """Analyze India's current economic situation and near-term outlook.
Cover: GDP growth trajectory, RBI monetary policy, inflation (CPI/WPI), fiscal deficit,
GST collections, industrial production (IIP), PMI data, FII/DII flows,
rupee outlook, current account balance, and government policy initiatives.
Identify which sectors benefit from the current policy environment.""",
    },
    {
        "name": "Sector Rotation Strategist",
        "role": "sector_rotation",
        "prompt": """Based on the current market cycle and macro environment, identify:
1. Top 3 sectors expected to OUTPERFORM in the next 3-6 months (with reasons)
2. Top 3 sectors expected to UNDERPERFORM (with reasons)
3. Sectors at inflection points (transitioning from underperform to outperform or vice versa)
4. Best sector allocation strategy for Indian equity investors right now
Cover: IT, Banking, Pharma, Auto, FMCG, Metals, Energy, Infra, Real Estate, Defence, Chemicals, Textiles.
For each sector, give a conviction rating (HIGH/MEDIUM/LOW).""",
    },
    {
        "name": "Market Technicals Forecaster",
        "role": "market_technicals",
        "prompt": """Analyze the technical outlook for Indian equity markets (Nifty 50, Sensex, Bank Nifty).
Cover: key support/resistance levels, trend direction, breadth indicators,
FII/DII positioning trends, VIX levels, put-call ratios, and seasonal patterns.
Provide specific price targets and risk levels for Nifty 50 over 1-month, 3-month, and 6-month horizons.
Include a probability of bull/bear/range-bound scenarios.""",
    },
    {
        "name": "MF & Investment Flows Analyst",
        "role": "investment_flows",
        "prompt": """Analyze current investment flow trends in Indian mutual funds and equity markets.
Cover: SIP flow trends (monthly data), lump sum vs SIP ratio, NFO activity,
which MF categories are seeing inflows/outflows (small cap, mid cap, large cap, flexi cap, debt),
FII vs DII behavior, retail investor participation trends, and demat account growth.
Identify: which fund categories are likely to perform best given current flows and valuations.
Flag any bubble risks in specific categories (e.g., small cap overheating).""",
    },
]


def generate_market_outlook() -> dict:
    """
    Run all outlook agents and compile a comprehensive market outlook.
    Returns dict with agent analyses and a compiled summary.
    """
    results = {}
    errors = []

    print("\n=== Generating Market Outlook ===")

    for i, agent in enumerate(OUTLOOK_AGENTS):
        name = agent["name"]
        print(f"  [{i+1}/{len(OUTLOOK_AGENTS)}] {name}...")

        prompt = f"""You are a {name} providing analysis for Indian market investors.
Today's date: {datetime.now().strftime('%Y-%m-%d')}.

{agent['prompt']}

Respond in JSON format:
{{
    "headline": "One-line summary of your outlook",
    "outlook": "BULLISH" or "NEUTRAL" or "BEARISH",
    "confidence": 0.0 to 1.0,
    "analysis": "Detailed 3-4 paragraph analysis",
    "key_points": ["point1", "point2", "point3"],
    "risks": ["risk1", "risk2"],
    "opportunities": ["opp1", "opp2"],
    "time_horizon": "3-6 months",
    "sectors_bullish": ["sector1", "sector2"],
    "sectors_bearish": ["sector1", "sector2"]
}}"""

        try:
            response = llm_pool.call_llm(prompt, prefer="gemini_lite")
            parsed = parse_agent_response(response)
            results[agent["role"]] = {
                "name": name,
                "role": agent["role"],
                **parsed,
            }
            outlook = parsed.get("outlook", "?")
            print(f"    -> {outlook} (conf: {parsed.get('confidence', 0):.0%})")
        except Exception as e:
            error_msg = str(e)[:200]
            print(f"    -> ERROR: {error_msg}")
            errors.append({"agent": name, "error": error_msg})
            results[agent["role"]] = {
                "name": name,
                "role": agent["role"],
                "headline": "Analysis unavailable",
                "outlook": "NEUTRAL",
                "confidence": 0,
                "analysis": f"Error: {error_msg}",
                "key_points": [],
                "risks": [],
                "opportunities": [],
            }

        time.sleep(1)  # Rate limit between agents

    # Compile overall outlook
    outlooks = [r.get("outlook", "NEUTRAL") for r in results.values()]
    bull_count = sum(1 for o in outlooks if o == "BULLISH")
    bear_count = sum(1 for o in outlooks if o == "BEARISH")

    if bull_count > bear_count + 1:
        overall = "BULLISH"
    elif bear_count > bull_count + 1:
        overall = "BEARISH"
    else:
        overall = "NEUTRAL"

    # Aggregate sectors
    all_bull_sectors = []
    all_bear_sectors = []
    for r in results.values():
        all_bull_sectors.extend(r.get("sectors_bullish", []))
        all_bear_sectors.extend(r.get("sectors_bearish", []))

    # Count sector mentions
    from collections import Counter
    bull_sectors = [s for s, _ in Counter(all_bull_sectors).most_common(5)]
    bear_sectors = [s for s, _ in Counter(all_bear_sectors).most_common(5)]

    compiled = {
        "overall_outlook": overall,
        "bull_count": bull_count,
        "bear_count": bear_count,
        "neutral_count": len(outlooks) - bull_count - bear_count,
        "top_bullish_sectors": bull_sectors,
        "top_bearish_sectors": bear_sectors,
        "generated_at": datetime.utcnow().isoformat(),
        "agent_results": results,
        "errors": errors,
    }

    # Save to database
    save_outlook(compiled)
    print(f"\n  Overall: {overall} ({bull_count} bull / {bear_count} bear)")
    print("  Outlook saved to database.\n")

    return compiled


def save_outlook(outlook_data: dict):
    """Save outlook to database."""
    conn = get_connection()
    c = conn.cursor()

    # Create table if not exists
    c.execute("""
        CREATE TABLE IF NOT EXISTS market_outlook (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL,
            overall_outlook TEXT NOT NULL,
            outlook_json TEXT NOT NULL
        )
    """)

    c.execute("""
        INSERT INTO market_outlook (generated_at, overall_outlook, outlook_json)
        VALUES (?, ?, ?)
    """, (
        datetime.utcnow().isoformat(),
        outlook_data.get("overall_outlook", "NEUTRAL"),
        json.dumps(outlook_data),
    ))
    conn.commit()
    conn.close()


def get_latest_outlook() -> dict:
    """Get the most recent market outlook."""
    conn = get_connection()

    # Check if table exists
    table_check = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='market_outlook'"
    ).fetchone()
    if not table_check:
        conn.close()
        return None

    row = conn.execute("""
        SELECT * FROM market_outlook
        ORDER BY generated_at DESC LIMIT 1
    """).fetchone()
    conn.close()

    if not row:
        return None

    result = dict(row)
    if result.get("outlook_json"):
        try:
            result["outlook_json"] = json.loads(result["outlook_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    return result
