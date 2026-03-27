"""
Quick test script to validate the entire setup.
Run: python test_setup.py
Tests each component independently so you can debug one at a time.
"""

import sys
import os
import time

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

passed = 0
failed = 0


def test(name, fn):
    global passed, failed
    print(f"\n{BOLD}[TEST] {name}{RESET}")
    try:
        fn()
        print(f"  {GREEN}PASS{RESET}")
        passed += 1
    except Exception as e:
        print(f"  {RED}FAIL: {e}{RESET}")
        failed += 1


# ── Test 1: Config & Environment ─────────────────────────────────────────────

def test_config():
    from config.settings import GEMINI_API_KEYS, GROQ_API_KEYS, OPENROUTER_API_KEY
    assert len(GEMINI_API_KEYS) > 0, "No GEMINI_API_KEYS in .env"
    print(f"  Gemini keys: {len(GEMINI_API_KEYS)}")
    assert len(GROQ_API_KEYS) > 0, "No GROQ_API_KEYS in .env"
    print(f"  Groq keys: {len(GROQ_API_KEYS)}")
    assert OPENROUTER_API_KEY, "No OPENROUTER_API_KEY in .env"
    print(f"  OpenRouter key: {'*' * 10}...{OPENROUTER_API_KEY[-6:]}")

test("Config & API Keys loaded from .env", test_config)


# ── Test 2: Database ─────────────────────────────────────────────────────────

def test_database():
    from data.database import init_db, get_connection
    init_db()
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    conn.close()
    table_names = [t["name"] for t in tables]
    print(f"  Tables: {table_names}")
    assert "scan_results" in table_names
    assert "agent_analyses" in table_names
    assert "aggregated_reports" in table_names

test("Database initialization", test_database)


# ── Test 3: Stock Universe ───────────────────────────────────────────────────

def test_universe():
    from scanner.universe import get_full_universe
    tickers = get_full_universe()
    print(f"  Total tickers: {len(tickers)}")
    assert len(tickers) >= 100, f"Expected 100+ tickers, got {len(tickers)}"
    assert "RELIANCE.NS" in tickers, "RELIANCE.NS missing"
    assert "TCS.NS" in tickers, "TCS.NS missing"
    assert "HDFCBANK.NS" in tickers, "HDFCBANK.NS missing"
    print(f"  Sample: {tickers[:5]}")

test("Stock universe (Nifty 50 + Next 50 + extras)", test_universe)


# ── Test 4: yfinance Data Fetch ──────────────────────────────────────────────

def test_yfinance():
    from scanner.metrics import _fetch_stock_data
    hist, info = _fetch_stock_data("RELIANCE.NS")
    assert not hist.empty, "No price data returned for RELIANCE.NS"
    price = hist["Close"].iloc[-1]
    print(f"  RELIANCE.NS latest close: ₹{price:.2f}")
    print(f"  Company: {info.get('shortName', 'N/A')}")
    print(f"  Market Cap: ₹{info.get('marketCap', 0):,.0f}")
    print(f"  Data source: yfinance or direct Yahoo API (auto-fallback)")

test("Stock data fetch with fallback (RELIANCE.NS)", test_yfinance)


# ── Test 5: Metrics Computation ──────────────────────────────────────────────

def test_metrics():
    from scanner.metrics import compute_all_metrics
    result = compute_all_metrics("TCS.NS")
    assert result is not None, "Failed to compute metrics for TCS.NS"
    metrics = result["metrics"]
    print(f"  Metrics computed: {len(metrics)}")
    assert len(metrics) >= 30, f"Expected 30+ metrics, got {len(metrics)}"
    print(f"  Price: ₹{result['current_price']:.2f}")
    print(f"  RSI: {metrics.get('rsi', 'N/A')}")
    print(f"  P/E: {metrics.get('pe_ratio_vs_sector', 'N/A')}")
    print(f"  Reasons: {result['standout_reasons'][:2]}")

test("Metrics computation (TCS.NS)", test_metrics)


# ── Test 6: Gemini API ───────────────────────────────────────────────────────

def test_gemini():
    from agents.llm_providers import llm_pool
    resp = llm_pool.call_gemini("Reply with exactly: GEMINI_OK", "You are a test bot.")
    print(f"  Response: {resp.strip()[:80]}")
    assert len(resp.strip()) > 0, "Empty response"

test("Gemini API call", test_gemini)


# ── Test 7: Groq API ─────────────────────────────────────────────────────────

def test_groq():
    from agents.llm_providers import llm_pool
    resp = llm_pool.call_groq("Reply with exactly: GROQ_OK", "You are a test bot.")
    print(f"  Response: {resp.strip()[:80]}")
    assert len(resp.strip()) > 0, "Empty response"

test("Groq API call", test_groq)


# ── Test 8: OpenRouter API ───────────────────────────────────────────────────

def test_openrouter():
    from agents.llm_providers import llm_pool
    resp = llm_pool.call_openrouter("Reply with exactly: OPENROUTER_OK", "You are a test bot.")
    print(f"  Response: {resp.strip()[:80]}")
    assert len(resp.strip()) > 0, "Empty response"

test("OpenRouter API call", test_openrouter)


# ── Test 9: LLM Fallback Chain ───────────────────────────────────────────────

def test_fallback():
    from agents.llm_providers import llm_pool
    resp = llm_pool.call_llm(
        "Reply with a JSON object: {\"status\": \"ok\"}",
        "You are a test bot. Reply ONLY with valid JSON.",
        prefer="gemini"
    )
    print(f"  Response: {resp.strip()[:80]}")
    assert len(resp.strip()) > 0, "Empty response"

test("LLM fallback chain (gemini→groq→openrouter)", test_fallback)


# ── Test 10: JSON Parsing ────────────────────────────────────────────────────

def test_json_parsing():
    from agents.llm_providers import parse_agent_response

    # Test clean JSON
    result = parse_agent_response('{"verdict": "BUY", "score": 8.0}')
    assert result["verdict"] == "BUY"

    # Test JSON in markdown
    result = parse_agent_response('```json\n{"verdict": "SELL", "score": 3.0}\n```')
    assert result["verdict"] == "SELL"

    # Test garbage input (should return fallback)
    result = parse_agent_response("This is not JSON at all")
    assert result["verdict"] == "NEUTRAL"
    print("  Clean JSON: OK | Markdown JSON: OK | Fallback: OK")

test("JSON response parsing", test_json_parsing)


# ── Test 11: Agent Personalities ─────────────────────────────────────────────

def test_personalities():
    from agents.personalities import AGENT_PERSONALITIES
    print(f"  Total agents: {len(AGENT_PERSONALITIES)}")
    assert len(AGENT_PERSONALITIES) >= 32, f"Expected 32+ agents, got {len(AGENT_PERSONALITIES)}"
    names = [a["name"] for a in AGENT_PERSONALITIES]
    print(f"  First 5: {names[:5]}")
    # Check all have required fields
    for agent in AGENT_PERSONALITIES:
        assert "name" in agent, f"Agent missing name"
        assert "role" in agent, f"Agent missing role: {agent.get('name')}"
        assert "system_prompt" in agent, f"Agent missing system_prompt: {agent.get('name')}"

test("Agent personalities (32+)", test_personalities)


# ── Test 12: Single Agent Run ────────────────────────────────────────────────

def test_single_agent():
    from agents.executor import run_single_agent
    from agents.personalities import AGENT_PERSONALITIES

    # Use a mock stock for testing
    mock_stock = {
        "ticker": "RELIANCE.NS",
        "company_name": "Reliance Industries",
        "sector": "Energy",
        "industry": "Oil & Gas Refining & Marketing",
        "market_cap": 17_000_000_000_000,
        "current_price": 1350.00,
        "metrics": {
            "price_vs_52w_low": 15.0, "price_vs_52w_high": 20.0,
            "daily_return": 1.5, "weekly_return": 3.2,
            "monthly_return": -2.1, "gap_percentage": 0.5,
            "intraday_range": 2.1, "price_vs_sma200": -5.0,
            "volume_surge": 2.3, "relative_volume": 1.8,
            "volume_price_trend": 0.6, "accumulation_distribution": 1,
            "on_balance_volume_trend": 1, "historical_volatility": 28.0,
            "atr_percentage": 2.1, "bollinger_squeeze": 8.0,
            "iv_percentile": 65.0, "rsi": 42.0,
            "macd_signal": -1, "stochastic_crossover": 1,
            "momentum_score": 5.0, "rate_of_change": -1.5,
            "pe_ratio_vs_sector": 22.5, "pb_ratio": 2.1,
            "debt_to_equity": 45.0, "revenue_growth": 12.0,
            "earnings_surprise": 8.0, "free_cash_flow_yield": 4.2,
            "short_interest": 1.2, "insider_buying": 65.0,
            "analyst_rating_change": 1.8, "sector_relative_strength": 3.0,
        },
        "standout_reasons": ["Volume surge: 2.3x average", "RSI approaching oversold"],
    }

    agent = AGENT_PERSONALITIES[0]  # Warren - Deep Value Investor
    print(f"  Running: {agent['name']}")
    result = run_single_agent(agent, mock_stock)
    print(f"  Verdict: {result.get('verdict', 'N/A')}")
    print(f"  Score: {result.get('score', 'N/A')}/10")
    print(f"  Confidence: {result.get('confidence', 'N/A')}")
    print(f"  Reasoning: {result.get('reasoning', 'N/A')[:100]}...")
    assert result.get("verdict") != "ERROR", f"Agent failed: {result.get('reasoning')}"

test("Single agent analysis (Warren on mock Reliance data)", test_single_agent)


# ── Summary ──────────────────────────────────────────────────────────────────

print(f"\n{'='*60}")
print(f"{BOLD}TEST RESULTS: {GREEN}{passed} passed{RESET}, {RED if failed else GREEN}{failed} failed{RESET}")
print(f"{'='*60}")

if failed == 0:
    print(f"\n{GREEN}{BOLD}All tests passed! You're ready to run:{RESET}")
    print(f"  python main.py              # Single scan + analysis")
    print(f"  python main.py --continuous  # Run every 30 minutes")
    print(f"  streamlit run dashboard/app.py  # Launch dashboard")
else:
    print(f"\n{YELLOW}Fix the failing tests above, then re-run: python test_setup.py{RESET}")

sys.exit(0 if failed == 0 else 1)
