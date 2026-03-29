"""
Market Intelligence Dashboard — Professional Grade
Finance-bro meets cafe-girl aesthetic: warm tones, clean data, espresso vibes.
"""

import json
import sys
import os

# Fix Windows charmap encoding — set env var before any imports touch stdout
os.environ["PYTHONIOENCODING"] = "utf-8"

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.universe import NIFTY_50, SENSEX_30, NIFTY_NEXT_50, EXTRA_WATCHLIST, COMMODITIES, COMMODITY_INFO, is_commodity, MUTUAL_FUNDS, MUTUAL_FUND_INFO, is_mutual_fund
from research.research_agents import RESEARCH_AGENT_COUNT

from data.database import (
    init_db, get_latest_scan_results, get_latest_reports,
    get_report_for_ticker, get_all_analyses_for_ticker,
    get_agent_analyses_for_scan, get_quant_predictions_for_ticker,
    get_research_analyses_for_ticker, get_completeness_for_ticker,
)

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Market Intelligence",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=300_000, key="auto_refresh")
except ImportError:
    pass

init_db()

# ── Custom CSS: Warm espresso + cream palette ────────────────────────────────
st.markdown("""
<style>
/* Import fonts */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=DM+Serif+Display&family=JetBrains+Mono:wght@400;500&display=swap');

/* Root variables */
:root {
    --espresso: #2C1810;
    --dark-roast: #1A1A2E;
    --cream: #FAF3E0;
    --latte: #D4A574;
    --rose-gold: #B76E79;
    --sage: #87A878;
    --mint: #98D4BB;
    --warm-gray: #8B8589;
    --soft-white: #FFF8F0;
    --caramel: #C68B59;
    --blush: #E8C4C4;
}

/* Main background */
.stApp {
    background: linear-gradient(135deg, #1A1A2E 0%, #16213E 50%, #1A1A2E 100%);
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1E1E30 0%, #2C1810 100%) !important;
    border-right: 1px solid rgba(212, 165, 116, 0.15);
}

section[data-testid="stSidebar"] .stRadio label {
    font-family: 'DM Sans', sans-serif !important;
    color: #FAF3E0 !important;
    font-weight: 500;
    padding: 8px 12px;
    border-radius: 8px;
    transition: all 0.2s ease;
}

section[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(212, 165, 116, 0.1);
}

/* Headers */
h1, h2, h3 {
    font-family: 'DM Serif Display', serif !important;
    color: #FAF3E0 !important;
}

h1 { letter-spacing: -0.5px; }

/* Body text */
p, li, span, div {
    font-family: 'DM Sans', sans-serif !important;
}

/* Metric cards */
div[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(44, 24, 16, 0.6) 0%, rgba(30, 30, 48, 0.6) 100%);
    border: 1px solid rgba(212, 165, 116, 0.2);
    border-radius: 12px;
    padding: 16px 20px;
    backdrop-filter: blur(10px);
}

div[data-testid="stMetric"] label {
    color: #D4A574 !important;
    font-size: 0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 500;
}

div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    color: #FAF3E0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 500;
}

/* Expander styling */
details {
    background: rgba(44, 24, 16, 0.3) !important;
    border: 1px solid rgba(212, 165, 116, 0.15) !important;
    border-radius: 12px !important;
    margin-bottom: 8px;
}

details summary {
    font-family: 'DM Sans', sans-serif !important;
    color: #FAF3E0 !important;
    font-weight: 500;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: rgba(44, 24, 16, 0.3);
    border-radius: 12px;
    padding: 4px;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    color: #D4A574 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500;
}

.stTabs [aria-selected="true"] {
    background: rgba(183, 110, 121, 0.3) !important;
    color: #FAF3E0 !important;
}

/* Dataframe */
.stDataFrame {
    border-radius: 12px;
    overflow: hidden;
}

/* Selectbox */
div[data-baseweb="select"] {
    font-family: 'DM Sans', sans-serif !important;
}

/* Success/Info/Warning/Error boxes */
div[data-testid="stAlert"] {
    border-radius: 10px;
    font-family: 'DM Sans', sans-serif !important;
}

/* Plotly charts - dark theme */
.js-plotly-plot {
    border-radius: 12px;
    overflow: hidden;
}

/* Dividers */
hr {
    border-color: rgba(212, 165, 116, 0.15) !important;
    margin: 1.5rem 0 !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #1A1A2E; }
::-webkit-scrollbar-thumb { background: #D4A574; border-radius: 3px; }

/* Badge styles */
.verdict-badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 700;
    font-family: 'DM Sans', sans-serif;
    letter-spacing: 0.5px;
}
.badge-buy { background: rgba(135, 168, 120, 0.25); color: #98D4BB; border: 1px solid rgba(135, 168, 120, 0.4); }
.badge-sell { background: rgba(183, 110, 121, 0.25); color: #E8C4C4; border: 1px solid rgba(183, 110, 121, 0.4); }
.badge-neutral { background: rgba(212, 165, 116, 0.25); color: #D4A574; border: 1px solid rgba(212, 165, 116, 0.4); }

/* Stock card */
.stock-card {
    background: linear-gradient(135deg, rgba(44, 24, 16, 0.4) 0%, rgba(30, 30, 48, 0.4) 100%);
    border: 1px solid rgba(212, 165, 116, 0.15);
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 12px;
    backdrop-filter: blur(10px);
}

/* Hero section */
.hero-text {
    font-family: 'DM Serif Display', serif;
    font-size: 2.2rem;
    color: #FAF3E0;
    line-height: 1.2;
    margin-bottom: 4px;
}
.hero-sub {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.95rem;
    color: #D4A574;
    letter-spacing: 2px;
    text-transform: uppercase;
}
</style>
""", unsafe_allow_html=True)


# ── Chart Theme ──────────────────────────────────────────────────────────────
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(26,26,46,0.5)",
    font=dict(family="DM Sans, sans-serif", color="#FAF3E0", size=12),
    margin=dict(l=40, r=20, t=50, b=30),
    xaxis=dict(gridcolor="rgba(212,165,116,0.1)", zerolinecolor="rgba(212,165,116,0.1)"),
    yaxis=dict(gridcolor="rgba(212,165,116,0.1)", zerolinecolor="rgba(212,165,116,0.1)"),
    colorway=["#D4A574", "#B76E79", "#98D4BB", "#87A878", "#E8C4C4", "#C68B59", "#8B8589"],
)

VERDICT_COLORS = {
    "STRONG_BUY": "#98D4BB", "BUY": "#87A878",
    "NEUTRAL": "#D4A574",
    "SELL": "#B76E79", "STRONG_SELL": "#E8C4C4",
    "ERROR": "#8B8589",
}

PIE_COLORS = ["#87A878", "#98D4BB", "#D4A574", "#B76E79", "#E8C4C4", "#8B8589"]


# ── Helpers ──────────────────────────────────────────────────────────────────

def verdict_badge(verdict: str) -> str:
    if "BUY" in verdict:
        cls = "badge-buy"
    elif "SELL" in verdict:
        cls = "badge-sell"
    else:
        cls = "badge-neutral"
    return f'<span class="verdict-badge {cls}">{verdict}</span>'


def format_inr(val):
    if not val:
        return "N/A"
    return f"\u20b9{val:,.2f}"


def format_market_cap(mc):
    if not mc:
        return "N/A"
    cr = mc / 1e7
    if cr >= 1e5:
        return f"\u20b9{cr/1e5:.1f}L Cr"
    if cr >= 1:
        return f"\u20b9{cr:,.0f} Cr"
    return f"\u20b9{mc:,.0f}"


def safe_json(val):
    if not val:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def reasoning_teaser(reasoning: str, max_chars: int = 120) -> str:
    """Extract a brief teaser from reasoning text."""
    if not reasoning or reasoning == "N/A":
        return ""
    text = reasoning.strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."


def verdict_teaser_line(verdict: str, name: str, score, conf, reasoning: str = "") -> str:
    """Render a colored verdict badge + agent name + teaser as HTML."""
    bg = VERDICT_COLORS.get(verdict, "#8B8589")
    teaser = reasoning_teaser(reasoning)
    teaser_html = f'<br><span style="color:#8B8589;font-size:0.82em;font-style:italic;">{teaser}</span>' if teaser else ''
    return (
        f'<span style="background:{bg};color:#1A1A2E;padding:2px 10px;border-radius:12px;'
        f'font-size:0.8em;font-weight:700;">{verdict}</span> '
        f'<strong>{name}</strong> &mdash; {score}/10 | {conf:.0%}'
        f'{teaser_html}'
    )


def _run_backfill_in_dashboard(ticker: str, completeness: dict):
    """Run backfill directly in the dashboard with live progress."""
    from pipeline.backfill import (
        _build_stock_dict_from_scan, backfill_quant,
        backfill_research, backfill_agents, backfill_aggregation,
        EXPECTED_BASE_AGENTS, EXPECTED_RESEARCH_AGENTS,
    )
    from data.database import get_latest_scan_for_ticker

    c = completeness
    scan = get_latest_scan_for_ticker(ticker)
    if not scan:
        st.error(f"No scan data for {ticker}. Run a full analysis first.")
        return

    stock_dict = _build_stock_dict_from_scan(scan)
    scan_id = scan["id"]
    best_scan_id = c.get("best_scan_id", scan_id)

    # Count total steps
    steps = []
    if not c["has_quant"]:
        steps.append("quant")
    if c["agent_count"] < 36:
        steps.append("agents")
    if c["research_count"] < RESEARCH_AGENT_COUNT:
        steps.append("research")
    # Always re-aggregate at the end if we're filling anything
    steps.append("aggregate")
    total = len(steps)

    status = st.status(f"Filling {total} gap(s) for {ticker}...", expanded=True)
    progress = st.progress(0)
    step_num = 0

    for step_name in steps:
        step_num += 1
        frac = step_num / total

        if step_name == "quant":
            status.update(label=f"Step {step_num}/{total}: Running quant engine (pure math, fast)...", state="running")
            status.write(f"**Step {step_num}/{total}:** Computing valuations, Monte Carlo, support/resistance...")
            ok = backfill_quant(ticker, scan_id)
            status.write(f"  {'Done' if ok else 'Failed'}")
            progress.progress(frac)

        elif step_name == "agents":
            status.update(label=f"Step {step_num}/{total}: Running 36 AI analyst agents...", state="running")
            status.write(f"**Step {step_num}/{total}:** Running 36 base agents (this takes a few minutes)...")
            from agents.executor import run_health_check
            run_health_check()
            backfill_agents(ticker, stock_dict)
            status.write("  Done")
            progress.progress(frac)

        elif step_name == "research":
            status.update(label=f"Step {step_num}/{total}: Running {RESEARCH_AGENT_COUNT} research agents...", state="running")
            status.write(f"**Step {step_num}/{total}:** Cross-referencing news, earnings, annual reports...")
            from agents.executor import run_health_check
            run_health_check()
            stock_dict_r = dict(stock_dict)
            stock_dict_r["scan_id"] = best_scan_id
            backfill_research(ticker, best_scan_id, stock_dict_r)
            status.write("  Done")
            progress.progress(frac)

        elif step_name == "aggregate":
            status.update(label=f"Step {step_num}/{total}: Re-aggregating all analyses...", state="running")
            status.write(f"**Step {step_num}/{total}:** Synthesizing final verdict from all agents...")
            stock_dict_a = dict(stock_dict)
            stock_dict_a["scan_id"] = best_scan_id
            backfill_aggregation(ticker, best_scan_id, stock_dict_a)
            status.write("  Done")
            progress.progress(1.0)

    status.update(label=f"All gaps filled for {ticker}!", state="complete", expanded=False)
    st.success(f"Data is now complete for {ticker}. Refresh the page to see updated results.")
    st.balloons()


def show_completeness_warning(ticker: str):
    """Show a warning banner if data is incomplete, with a one-click 'Fill Gaps' button."""
    c = get_completeness_for_ticker(ticker)
    gaps = []
    if not c["has_quant"]:
        gaps.append("Quant Predictions")
    if c["research_count"] < RESEARCH_AGENT_COUNT:
        gaps.append(f"Research Agents ({c['research_count']}/{RESEARCH_AGENT_COUNT})")
    if c["agent_count"] < 36:
        gaps.append(f"Base Agents ({c['agent_count']}/36)")
    if not c["has_report"]:
        gaps.append("Aggregated Report")

    if gaps:
        gap_list = "  |  ".join(gaps)
        col_warn, col_btn = st.columns([4, 1])
        with col_warn:
            st.warning(f"**Incomplete data for {ticker}:** {gap_list}")
        with col_btn:
            if st.button(f"Fill Gaps", key=f"backfill_{ticker}_{page}", type="primary"):
                _run_backfill_in_dashboard(ticker, c)
    return c


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="hero-sub">MARKET INTELLIGENCE</div>', unsafe_allow_html=True)
    st.markdown("---")

    page = st.radio(
        "Navigate",
        [
            "Overview",
            "Stock Deep Dive",
            "Agent Reports",
            "Research Reports",
            "Quant Predictions",
            "Consensus Heatmap",
            "Analyze Anything",
            "Scan History",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.caption(f"Updated {datetime.now().strftime('%H:%M:%S')}")
    st.caption("Gemini 2.5 Flash + Groq + OpenRouter")


# ==============================================================================
# PAGE: OVERVIEW
# ==============================================================================

if page == "Overview":
    st.markdown('<p class="hero-text">Market Intelligence</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">AI-POWERED STOCK ANALYSIS FOR INDIAN MARKETS</p>', unsafe_allow_html=True)
    st.markdown("")

    reports = get_latest_reports(limit=20)

    if not reports:
        st.markdown("---")
        st.info("No analysis data yet. Run `python main.py` to start scanning.")
        st.stop()

    # Summary row
    buy_count = sum(1 for r in reports if "BUY" in r.get("overall_verdict", ""))
    sell_count = sum(1 for r in reports if "SELL" in r.get("overall_verdict", ""))
    avg_score = sum(r.get("overall_score", 5) for r in reports) / max(len(reports), 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stocks Analyzed", len(reports))
    c2.metric("Buy Signals", buy_count)
    c3.metric("Sell Signals", sell_count)
    c4.metric("Avg Score", f"{avg_score:.1f}/10")

    st.markdown("---")

    # Verdict distribution chart
    verdict_counts = {}
    for r in reports:
        v = r.get("overall_verdict", "NEUTRAL")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    chart_col, table_col = st.columns([1, 2])

    with chart_col:
        fig = go.Figure(data=[go.Pie(
            labels=list(verdict_counts.keys()),
            values=list(verdict_counts.values()),
            hole=0.55,
            marker_colors=[VERDICT_COLORS.get(v, "#8B8589") for v in verdict_counts],
            textinfo="label+value",
            textfont=dict(size=12, family="DM Sans"),
        )])
        fig.update_layout(**CHART_LAYOUT, height=320, showlegend=False,
                          title=dict(text="Verdict Split", font=dict(size=14)))
        st.plotly_chart(fig, use_container_width=True)

    with table_col:
        st.markdown("### Latest Verdicts")
        for report in reports:
            ticker = report["ticker"]
            verdict = report.get("overall_verdict", "NEUTRAL")
            score = report.get("overall_score", 5)
            company = report.get("company_name", ticker)
            price = report.get("current_price", 0)

            # Colored teaser line above expander
            _bg = VERDICT_COLORS.get(verdict, "#8B8589")
            _teaser = reasoning_teaser(report.get("consensus_summary", ""))
            _teaser_html = f' &mdash; <span style="color:#8B8589;font-size:0.82em;">{_teaser}</span>' if _teaser else ''
            st.markdown(
                f'<span style="background:{_bg};color:#1A1A2E;padding:2px 10px;border-radius:12px;'
                f'font-size:0.8em;font-weight:700;">{verdict}</span> '
                f'<strong>{ticker}</strong> {company} | {score}/10{_teaser_html}',
                unsafe_allow_html=True,
            )
            with st.expander(f"View details: {ticker}", expanded=False):
                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Price", format_inr(price))
                mc2.metric("Score", f"{score}/10")
                mc3.metric("Market Cap", format_market_cap(report.get("market_cap")))

                if report.get("consensus_summary"):
                    st.markdown(f"**Consensus:** {report['consensus_summary']}")

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**Bull Case**")
                    st.markdown(report.get("bull_case", "N/A"))
                    for c in safe_json(report.get("key_catalysts")):
                        st.markdown(f"- {c}")

                with col_b:
                    st.markdown("**Bear Case**")
                    st.markdown(report.get("bear_case", "N/A"))
                    for r in safe_json(report.get("key_risks")):
                        st.markdown(f"- {r}")

                if report.get("recommendation"):
                    st.info(f"**Recommendation:** {report['recommendation']}")

    # ── Data Health Panel ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Data Health")
    from data.database import get_completeness_all
    all_completeness = get_completeness_all()

    if all_completeness:
        any_gaps = False
        health_cols = st.columns(min(len(all_completeness), 4))
        for idx, (ticker, c) in enumerate(sorted(all_completeness.items())):
            gaps = []
            if not c["has_quant"]:
                gaps.append("Quant")
            if c["research_count"] < RESEARCH_AGENT_COUNT:
                gaps.append(f"Research ({c['research_count']}/{RESEARCH_AGENT_COUNT})")
            if c["agent_count"] < 36:
                gaps.append(f"Agents ({c['agent_count']}/36)")

            col = health_cols[idx % len(health_cols)]
            with col:
                if gaps:
                    any_gaps = True
                    st.markdown(
                        f'<div style="background:rgba(183,110,121,0.15);border:1px solid rgba(183,110,121,0.3);'
                        f'border-radius:10px;padding:12px;margin-bottom:8px;">'
                        f'<strong>{ticker}</strong><br>'
                        f'<span style="color:#B76E79;font-size:0.85em;">Missing: {", ".join(gaps)}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button(f"Fill Gaps", key=f"overview_backfill_{ticker}", type="primary"):
                        _run_backfill_in_dashboard(ticker, c)
                else:
                    st.markdown(
                        f'<div style="background:rgba(152,212,187,0.15);border:1px solid rgba(152,212,187,0.3);'
                        f'border-radius:10px;padding:12px;margin-bottom:8px;">'
                        f'<strong>{ticker}</strong><br>'
                        f'<span style="color:#98D4BB;font-size:0.85em;">Complete</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        if any_gaps:
            st.markdown("")
            if st.button("Fill ALL Gaps (all stocks)", key="backfill_all_overview", type="primary"):
                for ticker, c in sorted(all_completeness.items()):
                    gaps_exist = (
                        not c["has_quant"]
                        or c["research_count"] < 8
                        or c["agent_count"] < 36
                    )
                    if gaps_exist:
                        _run_backfill_in_dashboard(ticker, c)
        else:
            st.success("All stock data is complete!")
    else:
        st.info("No stocks analyzed yet.")


# ==============================================================================
# PAGE: STOCK DEEP DIVE
# ==============================================================================

elif page == "Stock Deep Dive":
    st.markdown('<p class="hero-text">Stock Deep Dive</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">32+ METRICS | AI SYNTHESIS | FULL BREAKDOWN</p>', unsafe_allow_html=True)

    reports = get_latest_reports(limit=20)
    tickers = [r["ticker"] for r in reports]

    if not tickers:
        st.info("No stocks analyzed yet.")
        st.stop()

    selected = st.selectbox("Select Stock", tickers)
    report = get_report_for_ticker(selected)

    if not report:
        st.warning(f"No report for {selected}")
        st.stop()

    show_completeness_warning(selected)

    verdict = report.get("overall_verdict", "NEUTRAL")
    st.markdown(f"### {report.get('company_name', selected)} ({selected})")
    st.markdown(verdict_badge(verdict), unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Score", f"{report.get('overall_score', 0)}/10")
    c2.metric("Price", format_inr(report.get("current_price")))
    c3.metric("Market Cap", format_market_cap(report.get("market_cap")))
    c4.metric("Sector", report.get("sector", "N/A"))
    c5.metric("Agreement", f"{report.get('agent_agreement_pct', 0):.0f}%")

    st.markdown("---")

    # Scanner Metrics
    if report.get("metrics_json"):
        metrics = json.loads(report["metrics_json"]) if isinstance(report["metrics_json"], str) else report["metrics_json"]

        st.markdown("### Scanner Metrics")
        tabs = st.tabs(["Price", "Volume", "Volatility", "Momentum", "Fundamentals", "Sentiment"])

        with tabs[0]:
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("vs 52w Low", f"{metrics.get('price_vs_52w_low', 0):.1f}%")
            mc2.metric("vs 52w High", f"-{metrics.get('price_vs_52w_high', 0):.1f}%")
            mc3.metric("Daily Return", f"{metrics.get('daily_return', 0):+.2f}%")
            mc4.metric("Monthly Return", f"{metrics.get('monthly_return', 0):+.2f}%")

        with tabs[1]:
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Volume Surge", f"{metrics.get('volume_surge', 1):.1f}x")
            mc2.metric("Relative Vol", f"{metrics.get('relative_volume', 1):.1f}x")
            mc3.metric("OBV Trend", "Up" if metrics.get("on_balance_volume_trend", 0) > 0 else "Down")

        with tabs[2]:
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Hist Vol", f"{metrics.get('historical_volatility', 0):.1f}%")
            mc2.metric("ATR %", f"{metrics.get('atr_percentage', 0):.2f}%")
            mc3.metric("BB Width", f"{metrics.get('bollinger_squeeze', 0):.1f}%")

        with tabs[3]:
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("RSI", f"{metrics.get('rsi', 50):.0f}")
            mc2.metric("MACD", "Bullish" if metrics.get("macd_signal", 0) > 0 else "Bearish")
            mc3.metric("Momentum", f"{metrics.get('momentum_score', 5):.1f}/10")
            mc4.metric("ROC 10d", f"{metrics.get('rate_of_change', 0):+.1f}%")

        with tabs[4]:
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("P/E", f"{metrics.get('pe_ratio_vs_sector', 0):.1f}")
            mc2.metric("P/B", f"{metrics.get('pb_ratio', 0):.2f}")
            mc3.metric("Rev Growth", f"{metrics.get('revenue_growth', 0):+.1f}%")
            mc4.metric("FCF Yield", f"{metrics.get('free_cash_flow_yield', 0):.2f}%")

        with tabs[5]:
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Short Interest", f"{metrics.get('short_interest', 0):.1f}%")
            mc2.metric("Analyst Rating", f"{metrics.get('analyst_rating_change', 3):.1f}/5")
            mc3.metric("Insider Own%", f"{metrics.get('insider_buying', 0):.1f}%")

    # AI Synthesis
    st.markdown("---")
    st.markdown("### AI Synthesis")

    tab_d, tab_s, tab_p = st.tabs(["Data Analysis", "Sentiment", "Predictions"])
    with tab_d:
        st.markdown(report.get("data_summary", "Not available yet."))
    with tab_s:
        st.markdown(report.get("sentiment_summary", "Not available yet."))
    with tab_p:
        st.markdown(report.get("prediction_summary", "Not available yet."))

    if report.get("recommendation"):
        st.markdown("---")
        st.success(f"**Recommendation:** {report['recommendation']}")

    # Agent verdict distribution
    st.markdown("---")
    st.markdown("### Agent Analyses")
    all_analyses = get_all_analyses_for_ticker(selected)

    if all_analyses:
        vc = {}
        for a in all_analyses:
            v = a.get("verdict", "NEUTRAL")
            vc[v] = vc.get(v, 0) + 1

        fig = go.Figure(data=[go.Pie(
            labels=list(vc.keys()), values=list(vc.values()),
            hole=0.5,
            marker_colors=[VERDICT_COLORS.get(v, "#8B8589") for v in vc],
        )])
        fig.update_layout(**CHART_LAYOUT, height=300, title="Agent Verdict Split")
        st.plotly_chart(fig, use_container_width=True)

        for a in all_analyses:
            v = a.get("verdict", "?")
            st.markdown(
                verdict_teaser_line(v, a.get("agent_name", "?"), a.get("score", 0),
                                    a.get("confidence", 0.5), a.get("reasoning", "")),
                unsafe_allow_html=True,
            )
            with st.expander(f"View analysis: {a.get('agent_name', '?')}"):
                st.markdown(f"**Role:** {a.get('agent_role', 'N/A')}")
                st.markdown(f"**Reasoning:** {a.get('reasoning', 'N/A')}")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Catalysts:**")
                    for c in safe_json(a.get("catalysts")):
                        st.markdown(f"- {c}")
                with col2:
                    st.markdown("**Risks:**")
                    for r in safe_json(a.get("risks")):
                        st.markdown(f"- {r}")

    # CIO Verdict & Agent Debate on Stock Deep Dive
    if report and report.get("full_report_json"):
        st.markdown("---")
        st.markdown("### Final CIO Verdict")
        _full = json.loads(report["full_report_json"]) if isinstance(report["full_report_json"], str) else report["full_report_json"]

        _v1, _v2, _v3 = st.columns(3)
        _v1.metric("Verdict", _full.get("overall_verdict", "N/A"))
        _v2.metric("Score", f"{_full.get('overall_score', 0)}/10")
        _v3.metric("Conviction", str(_full.get("conviction", "N/A")).replace("_", " ").title())

        if _full.get("bull_case"):
            st.success(f"**Bull Case:** {_full['bull_case']}")
        if _full.get("bear_case"):
            st.error(f"**Bear Case:** {_full['bear_case']}")
        if _full.get("entry_strategy"):
            st.markdown(f"**Entry:** {_full['entry_strategy']}")
        if _full.get("time_horizon"):
            st.markdown(f"**Time Horizon:** {_full['time_horizon']}")

        # Agent Debate
        _debate = _full.get("debate", {})
        if _debate and isinstance(_debate, dict) and len(_debate) > 1:
            st.markdown("---")
            st.markdown("### Agent Debate")
            st.caption("Where the AI agents disagree most strongly")

            if _debate.get("summary"):
                st.markdown(_debate["summary"])

            _disagreements = _debate.get("key_disagreements", [])
            if _disagreements and isinstance(_disagreements, list):
                st.markdown("#### Key Disagreements")
                for _i, _d in enumerate(_disagreements, 1):
                    st.warning(f"**Debate {_i}:** {_d}")

            _bull_pts = _debate.get("strongest_bull_points", [])
            _bear_pts = _debate.get("strongest_bear_points", [])
            if _bull_pts or _bear_pts:
                st.markdown("#### Bull vs Bear")
                _cb, _cbr = st.columns(2)
                with _cb:
                    st.markdown("**BULL CASE**")
                    for _pt in (_bull_pts if isinstance(_bull_pts, list) else []):
                        st.success(_pt)
                with _cbr:
                    st.markdown("**BEAR CASE**")
                    for _pt in (_bear_pts if isinstance(_bear_pts, list) else []):
                        st.error(_pt)

            _agreements = _debate.get("key_agreements", [])
            if _agreements and isinstance(_agreements, list):
                st.markdown("#### What ALL Agents Agree On")
                for _pt in _agreements:
                    st.markdown(f"- {_pt}")

            _conf = _debate.get("confidence_in_consensus")
            if _conf is not None:
                _pct = int(float(_conf) * 100) if float(_conf) <= 1 else int(float(_conf))
                st.metric("Consensus Confidence", f"{_pct}%")

            _outliers = _debate.get("notable_outlier_views", [])
            if _outliers and isinstance(_outliers, list):
                st.markdown("#### Wildcard & Outlier Views")
                for _view in _outliers:
                    st.info(f"{_view}")


# ==============================================================================
# PAGE: AGENT REPORTS
# ==============================================================================

elif page == "Agent Reports":
    st.markdown('<p class="hero-text">Agent Reports</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">36 AI ANALYSTS | EVERY PERSPECTIVE | FULL DETAIL</p>', unsafe_allow_html=True)

    reports = get_latest_reports(limit=20)
    tickers = [r["ticker"] for r in reports]

    if not tickers:
        st.info("No data yet.")
        st.stop()

    selected = st.selectbox("Select Stock", tickers)
    show_completeness_warning(selected)
    all_analyses = get_all_analyses_for_ticker(selected)

    if not all_analyses:
        st.warning(f"No analyses for {selected}")
        st.stop()

    report = get_report_for_ticker(selected)
    company_name = report.get("company_name", selected) if report else selected
    st.markdown(f"### {company_name} ({selected})")

    # Summary stats
    total = len(all_analyses)
    buy_agents = [a for a in all_analyses if "BUY" in a.get("verdict", "")]
    sell_agents = [a for a in all_analyses if "SELL" in a.get("verdict", "")]
    avg_score = sum(a.get("score", 5) for a in all_analyses) / max(total, 1)
    avg_conf = sum(a.get("confidence", 0.5) for a in all_analyses) / max(total, 1)
    max_agent = max(all_analyses, key=lambda a: a.get("score", 0))
    min_agent = min(all_analyses, key=lambda a: a.get("score", 10))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Agents", total)
    c2.metric("Bullish", len(buy_agents))
    c3.metric("Bearish", len(sell_agents))
    c4.metric("Avg Score", f"{avg_score:.1f}/10")
    c5.metric("Avg Confidence", f"{avg_conf:.0%}")

    # Most bullish vs bearish
    st.markdown("---")
    col_bull, col_bear = st.columns(2)
    with col_bull:
        st.markdown(f"**Most Bullish:** {max_agent.get('agent_name', '?')}")
        st.markdown(f"Score: {max_agent.get('score', 0)}/10 | {max_agent.get('verdict', '?')}")
        st.caption(str(max_agent.get("reasoning", ""))[:250])
    with col_bear:
        st.markdown(f"**Most Bearish:** {min_agent.get('agent_name', '?')}")
        st.markdown(f"Score: {min_agent.get('score', 0)}/10 | {min_agent.get('verdict', '?')}")
        st.caption(str(min_agent.get("reasoning", ""))[:250])

    st.markdown("---")

    # Charts
    chart1, chart2 = st.columns(2)

    with chart1:
        vc = {}
        for a in all_analyses:
            v = a.get("verdict", "NEUTRAL")
            vc[v] = vc.get(v, 0) + 1
        fig = go.Figure(data=[go.Pie(
            labels=list(vc.keys()), values=list(vc.values()),
            hole=0.5, marker_colors=[VERDICT_COLORS.get(v, "#8B8589") for v in vc],
        )])
        fig.update_layout(**CHART_LAYOUT, height=320, title="Verdict Distribution")
        st.plotly_chart(fig, use_container_width=True)

    with chart2:
        names = [a.get("agent_name", "?").split(" - ")[0] for a in all_analyses]
        scores = [a.get("score", 5) for a in all_analyses]
        colors = [VERDICT_COLORS.get(a.get("verdict", "NEUTRAL"), "#D4A574") for a in all_analyses]
        fig2 = go.Figure(data=[go.Bar(x=scores, y=names, orientation="h", marker_color=colors)])
        _layout = {**CHART_LAYOUT, "yaxis": {**CHART_LAYOUT.get("yaxis", {}), "autorange": "reversed"}}
        fig2.update_layout(**_layout, height=max(400, total * 22), title="Score by Agent")
        st.plotly_chart(fig2, use_container_width=True)

    # Confidence vs Score scatter
    st.markdown("### Confidence vs Score")
    scatter_df = pd.DataFrame([{
        "Agent": a.get("agent_name", "?"),
        "Score": a.get("score", 5),
        "Confidence": a.get("confidence", 0.5),
        "Verdict": a.get("verdict", "NEUTRAL"),
    } for a in all_analyses])

    fig3 = px.scatter(scatter_df, x="Score", y="Confidence", color="Verdict",
                      hover_data=["Agent"],
                      color_discrete_map=VERDICT_COLORS)
    fig3.update_layout(**CHART_LAYOUT, height=400)
    st.plotly_chart(fig3, use_container_width=True)

    st.markdown("---")

    # Filter & sort
    st.markdown("### Detailed Reports")
    filter_v = st.multiselect("Filter by Verdict",
                              ["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL", "ERROR"],
                              default=["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"])
    sort_by = st.radio("Sort", ["Score (High)", "Score (Low)", "Confidence", "Name"], horizontal=True)

    filtered = [a for a in all_analyses if a.get("verdict", "NEUTRAL") in filter_v]
    if sort_by == "Score (High)":
        filtered.sort(key=lambda a: a.get("score", 0), reverse=True)
    elif sort_by == "Score (Low)":
        filtered.sort(key=lambda a: a.get("score", 0))
    elif sort_by == "Confidence":
        filtered.sort(key=lambda a: a.get("confidence", 0), reverse=True)
    else:
        filtered.sort(key=lambda a: a.get("agent_name", ""))

    for i, a in enumerate(filtered):
        v = a.get("verdict", "?")
        name = a.get("agent_name", "Unknown")
        score = a.get("score", 0)
        conf = a.get("confidence", 0)

        st.markdown(
            verdict_teaser_line(v, name, score, conf, a.get("reasoning", "")),
            unsafe_allow_html=True,
        )
        with st.expander(f"View full analysis: {name}", expanded=(i < 3)):
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Verdict", v)
            mc2.metric("Score", f"{score}/10")
            mc3.metric("Confidence", f"{conf:.0%}")
            mc4.metric("Role", a.get("agent_role", "N/A").replace("_", " ").title())

            st.markdown("**Analysis:**")
            st.markdown(a.get("reasoning", "N/A"))

            for p in safe_json(a.get("key_points")):
                st.markdown(f"- {p}")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Catalysts:**")
                for c in safe_json(a.get("catalysts")):
                    st.markdown(f"- {c}")
            with col2:
                st.markdown("**Risks:**")
                for r in safe_json(a.get("risks")):
                    st.markdown(f"- {r}")

            if a.get("raw_response"):
                raw = a["raw_response"]
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except json.JSONDecodeError:
                        pass
                st.markdown("**Raw Response:**")
                st.json(raw if isinstance(raw, dict) else {"raw": str(raw)[:2000]})

    # CIO Verdict
    if report and report.get("full_report_json"):
        st.markdown("---")
        st.markdown("### Final CIO Verdict")
        full = json.loads(report["full_report_json"]) if isinstance(report["full_report_json"], str) else report["full_report_json"]

        v1, v2, v3 = st.columns(3)
        v1.metric("Verdict", full.get("overall_verdict", "N/A"))
        v2.metric("Score", f"{full.get('overall_score', 0)}/10")
        v3.metric("Conviction", str(full.get("conviction", "N/A")).replace("_", " ").title())

        if full.get("bull_case"):
            st.success(f"**Bull Case:** {full['bull_case']}")
        if full.get("bear_case"):
            st.error(f"**Bear Case:** {full['bear_case']}")
        if full.get("entry_strategy"):
            st.markdown(f"**Entry:** {full['entry_strategy']}")
        if full.get("position_size"):
            st.markdown(f"**Position Size:** {full['position_size']}")
        if full.get("time_horizon"):
            st.markdown(f"**Time Horizon:** {full['time_horizon']}")

        # ── Agent Debate Section ──────────────────────────────────────────
        debate = full.get("debate", {})
        if debate and isinstance(debate, dict) and len(debate) > 1:
            st.markdown("---")
            st.markdown("### Agent Debate")
            st.caption("Where the AI agents disagree most strongly")

            # Debate summary
            if debate.get("summary"):
                st.markdown(debate["summary"])

            # Key Disagreements (the core debate)
            disagreements = debate.get("key_disagreements", [])
            if disagreements and isinstance(disagreements, list):
                st.markdown("#### Key Disagreements")
                for i, d in enumerate(disagreements, 1):
                    st.warning(f"**Debate {i}:** {d}")

            # Bull vs Bear — side by side
            bull_pts = debate.get("strongest_bull_points", [])
            bear_pts = debate.get("strongest_bear_points", [])
            if bull_pts or bear_pts:
                st.markdown("#### Bull vs Bear")
                col_bull, col_bear = st.columns(2)
                with col_bull:
                    st.markdown("**BULL CASE**")
                    for pt in (bull_pts if isinstance(bull_pts, list) else []):
                        st.success(pt)
                with col_bear:
                    st.markdown("**BEAR CASE**")
                    for pt in (bear_pts if isinstance(bear_pts, list) else []):
                        st.error(pt)

            # Key agreements
            agreements = debate.get("key_agreements", [])
            if agreements and isinstance(agreements, list):
                st.markdown("#### What ALL Agents Agree On")
                for pt in agreements:
                    st.markdown(f"- {pt}")

            # Confidence in consensus
            conf = debate.get("confidence_in_consensus")
            if conf is not None:
                pct = int(float(conf) * 100) if float(conf) <= 1 else int(float(conf))
                st.metric("Consensus Confidence", f"{pct}%")

            # Notable outlier views
            outliers = debate.get("notable_outlier_views", [])
            if outliers and isinstance(outliers, list):
                st.markdown("#### Wildcard & Outlier Views")
                for view in outliers:
                    st.info(f"{view}")

            # Legacy format support (debate_topic_1, etc.)
            for key, topic_data in debate.items():
                if not isinstance(topic_data, dict) or "topic" not in topic_data:
                    continue
                with st.expander(f"Debate: {topic_data.get('topic', 'Unknown')}", expanded=False):
                    col_b, col_br = st.columns(2)
                    bull = topic_data.get("bull_side", {})
                    bear = topic_data.get("bear_side", {})
                    with col_b:
                        agents_str = ", ".join(bull.get("agents", [])) if isinstance(bull.get("agents"), list) else str(bull.get("agents", ""))
                        st.markdown(f"**BULL SIDE** ({agents_str})")
                        st.success(bull.get("argument", ""))
                    with col_br:
                        agents_str = ", ".join(bear.get("agents", [])) if isinstance(bear.get("agents"), list) else str(bear.get("agents", ""))
                        st.markdown(f"**BEAR SIDE** ({agents_str})")
                        st.error(bear.get("argument", ""))
                    if topic_data.get("moderator_note"):
                        st.info(f"**Moderator:** {topic_data['moderator_note']}")


# ==============================================================================
# PAGE: RESEARCH REPORTS
# ==============================================================================

elif page == "Research Reports":
    st.markdown('<p class="hero-text">Research Reports</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="hero-sub">{RESEARCH_AGENT_COUNT} AGENTS | NEWS | EARNINGS | REGULATORY | GOVERNANCE</p>', unsafe_allow_html=True)

    reports = get_latest_reports(limit=20)
    tickers = [r["ticker"] for r in reports]

    if not tickers:
        st.info("No data yet.")
        st.stop()

    selected = st.selectbox("Select Stock", tickers, key="research_stock")
    comp = show_completeness_warning(selected)
    research = get_research_analyses_for_ticker(selected)

    if not research:
        st.info(f"No research data for {selected} yet.")
        if st.button(f"Generate Research Agents for {selected}", key=f"gen_research_{selected}", type="primary"):
            _run_backfill_in_dashboard(selected, comp)
        st.stop()

    report = get_report_for_ticker(selected)
    company_name = report.get("company_name", selected) if report else selected
    st.markdown(f"### {company_name} ({selected})")

    total = len(research)
    buy_r = sum(1 for a in research if "BUY" in a.get("verdict", ""))
    sell_r = sum(1 for a in research if "SELL" in a.get("verdict", ""))
    avg_r = sum(a.get("score", 5) for a in research) / max(total, 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Research Agents", total)
    c2.metric("Bullish", buy_r)
    c3.metric("Bearish", sell_r)
    c4.metric("Avg Score", f"{avg_r:.1f}/10")

    # Compare research vs base agents
    all_analyses = get_all_analyses_for_ticker(selected)
    from research.research_agents import RESEARCH_ROLES
    base = [a for a in all_analyses if a.get("agent_role") not in RESEARCH_ROLES]

    if base:
        base_avg = sum(a.get("score", 5) for a in base) / max(len(base), 1)
        delta = avg_r - base_avg

        st.markdown("---")
        st.markdown("### Research vs Base Agents")
        col1, col2, col3 = st.columns(3)
        col1.metric("Base Avg", f"{base_avg:.1f}/10")
        col2.metric("Research Avg", f"{avg_r:.1f}/10")
        col3.metric("Delta", f"{delta:+.1f}", delta_color="normal")

        if abs(delta) > 1.5:
            if delta > 0:
                st.success("Research agents are MORE bullish  --  data supports thesis")
            else:
                st.error("Research agents are MORE bearish  --  data raises concerns")

    st.markdown("---")
    st.markdown("### Research Agent Details")

    for a in research:
        v = a.get("verdict", "?")
        st.markdown(
            verdict_teaser_line(v, a.get("agent_name", "?"), a.get("score", 0),
                                a.get("confidence", 0.5), a.get("reasoning", "")),
            unsafe_allow_html=True,
        )
        with st.expander(f"View research: {a.get('agent_name', '?')}", expanded=True):
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Verdict", v)
            mc2.metric("Score", f"{a.get('score', 0)}/10")
            mc3.metric("Confidence", f"{a.get('confidence', 0):.0%}")

            st.markdown(f"**Analysis:** {a.get('reasoning', 'N/A')}")

            raw = a.get("raw_response", "{}")
            if isinstance(raw, str):
                try:
                    raw_data = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    raw_data = {}
            else:
                raw_data = raw if isinstance(raw, dict) else {}

            if raw_data.get("reality_check"):
                st.info(f"**Reality Check:** {raw_data['reality_check']}")
            if raw_data.get("narrative_gap"):
                st.warning(f"**Narrative Gap:** {raw_data['narrative_gap']}")

            for p in safe_json(a.get("key_points")):
                st.markdown(f"- {p}")


# ==============================================================================
# PAGE: QUANT PREDICTIONS
# ==============================================================================

elif page == "Quant Predictions":
    st.markdown('<p class="hero-text">Quant Predictions</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">PURE MATH | FAIR VALUE | MONTE CARLO | LEVELS</p>', unsafe_allow_html=True)

    reports = get_latest_reports(limit=20)
    tickers = [r["ticker"] for r in reports]

    if not tickers:
        st.info("No data yet.")
        st.stop()

    selected = st.selectbox("Select Stock", tickers, key="quant_stock")
    comp = show_completeness_warning(selected)
    quant = get_quant_predictions_for_ticker(selected)

    if not quant:
        st.info(f"No quant data for {selected} yet.")
        if st.button(f"Generate Quant Predictions for {selected}", key=f"gen_quant_{selected}", type="primary"):
            _run_backfill_in_dashboard(selected, comp)
        st.stop()

    report = get_report_for_ticker(selected)
    company_name = report.get("company_name", selected) if report else selected
    st.markdown(f"### {company_name} ({selected})")

    valuations = quant.get("valuations_json", {})
    levels = quant.get("levels_json", {})
    predictions = quant.get("predictions_json", {})
    summary = quant.get("summary_json", {})

    current_price = summary.get("current_price") or valuations.get("current_price", 0)
    fair_value = valuations.get("composite_fair_value")
    upside = valuations.get("composite_upside")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current Price", format_inr(current_price))
    c2.metric("Fair Value", format_inr(fair_value))
    c3.metric("Upside", f"{upside:+.1f}%" if upside is not None else "N/A", delta_color="normal")
    mc = predictions.get("monte_carlo", {})
    c4.metric("P(Up 30d)", f"{mc.get('prob_positive', 'N/A')}%" if mc.get("prob_positive") is not None else "N/A")

    st.markdown("---")

    # Valuation gauges
    st.markdown("### Fair Value Estimates")
    gcol1, gcol2, gcol3 = st.columns(3)

    for col, (name, key) in zip(
        [gcol1, gcol2, gcol3],
        [("Graham Number", "graham_number"), ("DCF Value", "dcf_value"), ("PEG Value", "peg_value")]
    ):
        val = valuations.get(key)
        with col:
            if val and current_price:
                fig = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=current_price,
                    delta={"reference": val, "relative": True, "valueformat": ".1%"},
                    title={"text": name, "font": {"size": 14, "color": "#D4A574"}},
                    number={"font": {"color": "#FAF3E0"}},
                    gauge={
                        "axis": {"range": [min(current_price, val) * 0.5, max(current_price, val) * 1.5],
                                 "tickcolor": "#D4A574"},
                        "bar": {"color": "#D4A574"},
                        "steps": [
                            {"range": [0, val * 0.8], "color": "rgba(135,168,120,0.3)"},
                            {"range": [val * 0.8, val * 1.2], "color": "rgba(212,165,116,0.3)"},
                            {"range": [val * 1.2, max(current_price, val) * 1.5], "color": "rgba(183,110,121,0.3)"},
                        ],
                        "threshold": {"line": {"color": "#98D4BB", "width": 3}, "thickness": 0.75, "value": val},
                    },
                ))
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#FAF3E0"),
                                  height=250, margin=dict(t=50, b=10))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption(f"{name}: Insufficient data")

    # Comparison table
    rows = []
    for name, key, up_key in [
        ("Graham Number", "graham_number", "upside_graham"),
        ("DCF", "dcf_value", "upside_dcf"),
        ("PEG", "peg_value", "upside_peg"),
        ("Composite", "composite_fair_value", "composite_upside"),
    ]:
        val = valuations.get(key)
        up = valuations.get(up_key)
        rows.append({
            "Model": name,
            "Fair Value": format_inr(val),
            "Current": format_inr(current_price),
            "Upside": f"{up:+.1f}%" if up is not None else "N/A",
            "Signal": "UNDERVALUED" if up and up > 10 else "OVERVALUED" if up and up < -10 else "FAIR",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    # Support/Resistance
    st.markdown("### Support & Resistance")
    fib = levels.get("fibonacci", {})
    pivots = levels.get("pivot_points", {})
    mas = levels.get("moving_averages", {})

    all_levels = []
    if fib:
        for n, v in fib.items():
            if n.startswith("fib_") and v:
                all_levels.append({"Level": f"Fib {n.replace('fib_', '')}", "Price": v, "Type": "Fibonacci"})
    if pivots:
        for n, v in pivots.items():
            if v:
                all_levels.append({"Level": n.upper(), "Price": v, "Type": "Pivot"})
    if mas:
        for n, v in mas.items():
            if v:
                all_levels.append({"Level": n.upper(), "Price": v, "Type": "Moving Avg"})

    if all_levels:
        levels_df = pd.DataFrame(all_levels).sort_values("Price", ascending=False)
        type_colors = {"Fibonacci": "#B76E79", "Pivot": "#D4A574", "Moving Avg": "#98D4BB"}

        fig = go.Figure()
        for _, row in levels_df.iterrows():
            fig.add_hline(y=row["Price"], line_dash="dash",
                          line_color=type_colors.get(row["Type"], "#8B8589"),
                          annotation_text=f"{row['Level']}: {format_inr(row['Price'])}",
                          annotation_position="right")
        if current_price:
            fig.add_hline(y=current_price, line_color="#FAF3E0", line_width=3,
                          annotation_text=f"Current: {format_inr(current_price)}")

        _layout2 = {**CHART_LAYOUT, "yaxis": {**CHART_LAYOUT.get("yaxis", {}),
                    "range": [min(l["Price"] for l in all_levels) * 0.95,
                              max(l["Price"] for l in all_levels) * 1.05]}}
        fig.update_layout(**_layout2, height=500, title="Price Levels Map")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(levels_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Monte Carlo
    st.markdown("### Monte Carlo Simulation (30-day)")
    mc = predictions.get("monte_carlo", {})
    if mc and not mc.get("error"):
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Median 30d", format_inr(mc.get("median_price", 0)))
        mc2.metric("Expected Return", f"{mc.get('expected_return', 0):+.2f}%")
        mc3.metric("P(Positive)", f"{mc.get('prob_positive', 0):.0f}%")
        mc4.metric("Volatility", f"{mc.get('annualized_volatility', 0):.1f}%")

        percentiles = [
            ("P10", mc.get("p10", 0)),
            ("P25", mc.get("p25", 0)),
            ("Median", mc.get("median_price", 0)),
            ("P75", mc.get("p75", 0)),
            ("P90", mc.get("p90", 0)),
        ]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=[p[0] for p in percentiles], y=[p[1] for p in percentiles],
            marker_color=["#B76E79", "#D4A574", "#FAF3E0", "#87A878", "#98D4BB"],
            text=[format_inr(p[1]) for p in percentiles], textposition="outside",
            textfont=dict(color="#FAF3E0"),
        ))
        if current_price:
            fig.add_hline(y=current_price, line_dash="dash", line_color="#D4A574",
                          annotation_text=f"Current: {format_inr(current_price)}")
        fig.update_layout(**CHART_LAYOUT, height=400, title="30-Day Price Distribution")
        st.plotly_chart(fig, use_container_width=True)

        p1, p2, p3 = st.columns(3)
        p1.metric("P(Up >10%)", f"{mc.get('prob_up_10pct', 0):.0f}%")
        p2.metric("P(Down >10%)", f"{mc.get('prob_down_10pct', 0):.0f}%")
        p3.metric("Daily Vol", f"{mc.get('daily_volatility', 0):.2f}%")
    else:
        st.info("Monte Carlo data not available.")

    st.markdown("---")

    # Mean Reversion
    st.markdown("### Mean Reversion")
    mr = predictions.get("mean_reversion", {})
    if mr and not mr.get("error"):
        mr1, mr2, mr3, mr4 = st.columns(4)
        mr1.metric("Z-Score", f"{mr.get('z_score', 0):.2f}")
        mr2.metric("Target (SMA)", format_inr(mr.get("target_price", 0)))
        mr3.metric("Deviation", f"{mr.get('deviation_pct', 0):+.1f}%")
        mr4.metric("Signal", mr.get("signal", "FAIR"))

        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=mr.get("z_score", 0),
            title={"text": "Z-Score", "font": {"color": "#D4A574"}},
            number={"font": {"color": "#FAF3E0"}},
            gauge={
                "axis": {"range": [-3, 3], "tickcolor": "#D4A574"},
                "bar": {"color": "#D4A574"},
                "steps": [
                    {"range": [-3, -2], "color": "rgba(135,168,120,0.4)"},
                    {"range": [-2, -1], "color": "rgba(135,168,120,0.2)"},
                    {"range": [-1, 1], "color": "rgba(212,165,116,0.2)"},
                    {"range": [1, 2], "color": "rgba(183,110,121,0.2)"},
                    {"range": [2, 3], "color": "rgba(183,110,121,0.4)"},
                ],
            },
        ))
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#FAF3E0"), height=300)
        st.plotly_chart(fig, use_container_width=True)

        if mr.get("half_life_days"):
            st.markdown(f"**Mean reversion half-life:** {mr['half_life_days']:.0f} days")
        st.markdown(
            f"**Bands:** {format_inr(mr.get('band_lower_2std', 0))} (-2s) | "
            f"{format_inr(mr.get('band_lower_1std', 0))} (-1s) | "
            f"{format_inr(mr.get('target_price', 0))} (mean) | "
            f"{format_inr(mr.get('band_upper_1std', 0))} (+1s) | "
            f"{format_inr(mr.get('band_upper_2std', 0))} (+2s)"
        )
    else:
        st.info("Mean reversion data not available.")

    # Bollinger Bands
    bb = predictions.get("bollinger", {})
    if bb and not bb.get("error"):
        st.markdown("---")
        st.markdown("### Bollinger Bands")
        bb1, bb2, bb3, bb4 = st.columns(4)
        bb1.metric("Upper", format_inr(bb.get("upper", 0)))
        bb2.metric("Middle", format_inr(bb.get("middle", 0)))
        bb3.metric("Lower", format_inr(bb.get("lower", 0)))
        bb4.metric("%B", f"{bb.get('percent_b', 50):.0f}%")
        st.markdown(f"**Bandwidth:** {bb.get('bandwidth', 0):.1f}% | **Signal:** {bb.get('signal', 'NEUTRAL')}")


# ==============================================================================
# PAGE: CONSENSUS HEATMAP
# ==============================================================================

elif page == "Consensus Heatmap":
    st.markdown('<p class="hero-text">Consensus Heatmap</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">ALL AGENTS x ALL STOCKS</p>', unsafe_allow_html=True)

    reports = get_latest_reports(limit=15)

    if not reports:
        st.info("No data yet.")
        st.stop()

    data_rows = []
    for report in reports:
        ticker = report["ticker"]
        analyses = get_all_analyses_for_ticker(ticker)
        for a in analyses:
            data_rows.append({
                "Ticker": ticker,
                "Agent": a.get("agent_name", "?"),
                "Score": a.get("score", 5),
                "Verdict": a.get("verdict", "NEUTRAL"),
            })

    if data_rows:
        df = pd.DataFrame(data_rows)
        pivot = df.pivot_table(index="Agent", columns="Ticker", values="Score", aggfunc="mean")

        fig = px.imshow(
            pivot, labels=dict(x="Stock", y="Agent", color="Score"),
            aspect="auto", color_continuous_scale=["#B76E79", "#D4A574", "#FAF3E0", "#87A878", "#98D4BB"],
            zmin=1, zmax=10,
        )
        fig.update_layout(**CHART_LAYOUT, height=max(400, len(pivot) * 25), title="Agent Scores by Stock")
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.markdown("### Summary")
        for report in reports:
            ticker = report["ticker"]
            ticker_data = [r for r in data_rows if r["Ticker"] == ticker]
            buy_pct = sum(1 for a in ticker_data if "BUY" in a["Verdict"]) / max(len(ticker_data), 1) * 100
            avg = sum(a["Score"] for a in ticker_data) / max(len(ticker_data), 1)
            st.markdown(f"**{ticker}**: {buy_pct:.0f}% bullish | Avg: {avg:.1f}/10 | {report.get('overall_verdict', 'N/A')}")


# ==============================================================================
# PAGE: ANALYZE ANY STOCK
# ==============================================================================

elif page == "Analyze Anything":
    # Read-only if: shared mode OR cloud deployment (no API keys available)
    _has_api_keys = bool(os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_LITE_API_KEY") or os.environ.get("GROQ_API_KEYS"))
    _is_read_only = os.environ.get("SHARE_READ_ONLY", "") == "1" or not _has_api_keys

    st.markdown('<p class="hero-text">Analyze Anything</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">STOCKS | COMMODITIES | MUTUAL FUNDS — 47 AI AGENTS + QUANT MODELS</p>', unsafe_allow_html=True)

    if _is_read_only:
        st.info(
            "This is a **shared read-only** dashboard. "
            "You can browse all existing analyses, but running new analyses is disabled. "
            "Use the **Overview**, **Stock Deep Dive**, **Agent Reports**, and **Quant Predictions** pages to explore."
        )

    st.markdown("")

    # Build predictive dropdown: stocks + commodities + mutual funds
    _stock_tickers = sorted(set(NIFTY_50 + SENSEX_30 + NIFTY_NEXT_50 + EXTRA_WATCHLIST))
    _commodity_tickers = sorted(COMMODITIES)
    _mf_tickers = sorted(MUTUAL_FUNDS)
    _all_tickers_raw = _stock_tickers + ["--- COMMODITIES ---"] + _commodity_tickers + ["--- MUTUAL FUNDS ---"] + _mf_tickers
    _ticker_options = [""] + _all_tickers_raw

    def _format_ticker(x):
        if x == "":
            return "Type to search (e.g. RELIANCE, GOLD, SBI SMALL CAP)..."
        if x.startswith("--- "):
            return x
        if x in COMMODITY_INFO:
            info = COMMODITY_INFO[x]
            return f"{x} - {info['name']} ({info['category']})"
        if x in MUTUAL_FUND_INFO:
            info = MUTUAL_FUND_INFO[x]
            return f"{info['name']} ({info['category']}) - {info['amc']}"
        return x

    ticker_select = st.selectbox(
        "Search stocks, commodities & mutual funds (type to filter)",
        options=_ticker_options,
        index=0,
        format_func=_format_ticker,
        key="ticker_search",
    )

    # Also allow manual entry
    custom_ticker = st.text_input(
        "Or type any name — GOLD, CRUDE, SBI SMALL CAP, HDFC FLEXI CAP...",
        placeholder="e.g. GOLD, CRUDE, TCS, SBI SMALL CAP, HDFC MID CAP",
        key="custom_ticker_input",
    )

    # Common name -> ticker mapping for user-friendly input
    _ASSET_ALIASES = {
        # Commodities
        "GOLD": "GC=F", "SILVER": "SI=F", "PLATINUM": "PL=F",
        "CRUDE": "CL=F", "CRUDEOIL": "CL=F", "OIL": "CL=F", "WTI": "CL=F",
        "BRENT": "BZ=F", "NATURALGAS": "NG=F", "GAS": "NG=F", "NATGAS": "NG=F",
        "COPPER": "HG=F", "ALUMINUM": "ALI=F", "ALUMINIUM": "ALI=F",
        "CORN": "ZC=F", "WHEAT": "ZW=F", "SOYBEAN": "ZS=F", "SOYBEANS": "ZS=F",
        "COTTON": "CT=F", "COFFEE": "KC=F", "SUGAR": "SB=F",
        "GOLDETF": "GOLDBEES.NS", "SILVERETF": "SILVERBEES.NS",
        # Mutual Funds — common name aliases
        "SBI SMALL CAP": "MF:125497", "SBI SMALLCAP": "MF:125497",
        "SBI BLUE CHIP": "MF:119598", "SBI BLUECHIP": "MF:119598", "SBI LARGE CAP": "MF:119598",
        "SBI CONTRA": "MF:119835",
        "SBI EQUITY HYBRID": "MF:119609",
        "HDFC FLEXI CAP": "MF:118955", "HDFC FLEXICAP": "MF:118955",
        "HDFC MID CAP": "MF:118989", "HDFC MIDCAP": "MF:118989",
        "ICICI BLUECHIP": "MF:120586", "ICICI LARGE CAP": "MF:120586", "ICICI PRUDENTIAL BLUECHIP": "MF:120586",
        "PARAG PARIKH": "MF:122639", "PPFAS": "MF:122639", "PARAG PARIKH FLEXI CAP": "MF:122639",
        "MIRAE LARGE CAP": "MF:118825", "MIRAE ASSET LARGE CAP": "MF:118825",
        "NIPPON SMALL CAP": "MF:118778", "NIPPON INDIA SMALL CAP": "MF:118778",
        "KOTAK SMALL CAP": "MF:120164",
        "KOTAK FLEXICAP": "MF:120166", "KOTAK FLEXI CAP": "MF:120166",
        "AXIS SMALL CAP": "MF:125354",
        "AXIS MIDCAP": "MF:120505", "AXIS MID CAP": "MF:120505",
        "QUANT SMALL CAP": "MF:120828",
        "DSP MIDCAP": "MF:119071", "DSP MID CAP": "MF:119071",
        "MOTILAL OSWAL MIDCAP": "MF:127042",
        "TATA SMALL CAP": "MF:145206",
        "BANDHAN SMALL CAP": "MF:147946",
    }

    # Determine final ticker
    raw_input = custom_ticker.strip().upper() if custom_ticker.strip() else ticker_select
    if raw_input and raw_input.startswith("--- "):
        raw_input = ""
    ticker_input = raw_input

    if ticker_input:
        ticker = ticker_input.strip().upper()
        # Check aliases first (GOLD -> GC=F, SBI SMALL CAP -> MF:125497, etc.)
        if ticker in _ASSET_ALIASES:
            ticker = _ASSET_ALIASES[ticker]
            if ticker.startswith("MF:"):
                mf_name = MUTUAL_FUND_INFO.get(ticker, {}).get('name', '')
                st.info(f"Mapped to mutual fund: **{mf_name}** ({ticker})")
            else:
                st.info(f"Mapped to commodity ticker: **{ticker}** ({COMMODITY_INFO.get(ticker, {}).get('name', '')})")
        # Don't add .NS suffix for commodities, MFs, or tickers with special chars
        elif not is_commodity(ticker) and not is_mutual_fund(ticker) and not ticker.endswith(".NS") and not ticker.endswith(".BO") and "=" not in ticker and not ticker.startswith("MF:"):
            ticker = f"{ticker}.NS"

        # Check if we already have data
        existing = get_report_for_ticker(ticker)
        if existing:
            st.success(f"Found existing analysis for {ticker}. View it in Stock Deep Dive or Agent Reports.")
            show_completeness_warning(ticker)

        if _is_read_only:
            st.warning("New analyses are disabled in shared mode.")
        else:
            import threading

            # Initialize session state
            if "analysis_stop_flag" not in st.session_state:
                st.session_state.analysis_stop_flag = threading.Event()
            if "last_analysis_result" not in st.session_state:
                st.session_state.last_analysis_result = None

            # Show previous result if available
            prev = st.session_state.last_analysis_result
            if prev and prev.get("ticker") == ticker:
                if prev.get("success"):
                    st.success(f"Analysis complete for {ticker}! Navigate to Overview, Stock Deep Dive, or Agent Reports.")
                    report = get_report_for_ticker(ticker)
                    if report:
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Verdict", report.get("overall_verdict", "N/A"))
                        c2.metric("Score", f"{report.get('overall_score', 0)}/10")
                        c3.metric("Price", format_inr(report.get("current_price")))
                        if report.get("consensus_summary"):
                            st.markdown(f"**Consensus:** {report['consensus_summary']}")
                elif prev.get("cancelled"):
                    st.warning("Previous analysis was stopped. Partial data may be available.")
                elif prev.get("error"):
                    st.error(f"Previous analysis failed: {prev['error']}")

            # Buttons
            col_run, col_stop = st.columns([3, 1])
            run_clicked = col_run.button(f"Run Full Analysis on {ticker}", type="primary")
            stop_clicked = col_stop.button("Stop Analysis", type="secondary")

            if stop_clicked:
                st.session_state.analysis_stop_flag.set()
                st.warning("Stopping... will halt after the current agent finishes.")

            if run_clicked:
                from pipeline.on_demand import analyze_single_stock

                # Reset stop flag and previous result
                st.session_state.analysis_stop_flag = threading.Event()
                st.session_state.last_analysis_result = None

                # Progress UI
                status_box = st.status("Initializing analysis pipeline...", expanded=True)
                progress_bar = st.progress(0)

                step_names = {
                    1: "Computing 32+ metrics",
                    2: "Saving scan result",
                    3: "Quant prediction engine",
                    4: "Running 36 AI analyst agents",
                    5: "Running 11 research agents",
                    6: "Aggregating final verdict",
                    7: "Complete!",
                }

                def update_progress(step, total, msg):
                    progress_bar.progress(step / total, text=f"Step {step}/{total}: {step_names.get(step, msg)}")
                    status_box.update(label=msg, state="running")
                    status_box.write(f"**Step {step}/{total}:** {msg}")

                result = analyze_single_stock(
                    ticker,
                    progress_callback=update_progress,
                    stop_flag=st.session_state.analysis_stop_flag,
                )

                # Store result in session state so it persists across reruns
                st.session_state.last_analysis_result = {
                    "ticker": ticker,
                    "success": result.get("success"),
                    "error": result.get("error"),
                    "cancelled": result.get("cancelled"),
                }

                if result.get("cancelled"):
                    status_box.update(label="Analysis stopped by user", state="error")
                    st.warning("Stopped. Partial results saved to database.")
                elif result.get("success"):
                    progress_bar.progress(1.0, text="Analysis complete!")
                    status_box.update(label="Analysis complete!", state="complete", expanded=False)
                    st.success(f"Full analysis complete for {ticker}! Refreshing dashboard...")
                    # Force rerun so all pages pick up the new data
                    st.rerun()
                else:
                    status_box.update(label="Analysis failed", state="error")
                    st.error(f"Analysis failed: {result.get('error', 'Unknown error')}")
                    # Show what we have anyway
                    report = get_report_for_ticker(ticker)
                    if report:
                        st.info("Some data was saved before the error. Check Agent Reports.")
    else:
        st.markdown("""
        **How it works:**
        1. Search for any **stock** (RELIANCE, TCS), **commodity** (GOLD, CRUDE), or **mutual fund** (SBI SMALL CAP, HDFC FLEXI CAP)
        2. Or just type the name — common names auto-map to the right ticker
        3. Click 'Run Full Analysis' — 47 AI agents + 11 research agents + quant models analyze it
        4. Watch each step complete in real-time (you can stop anytime)
        5. View the **Agent Debate** — see where agents disagree most sharply
        6. Browse results in Stock Deep Dive, Agent Reports, or Quant Predictions
        """)


# ==============================================================================
# PAGE: SCAN HISTORY
# ==============================================================================

elif page == "Scan History":
    st.markdown('<p class="hero-text">Scan History</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">HISTORICAL SCAN DATA</p>', unsafe_allow_html=True)

    scans = get_latest_scan_results(limit=50)

    if not scans:
        st.info("No scan history yet.")
        st.stop()

    df = pd.DataFrame(scans)
    df["scan_timestamp"] = pd.to_datetime(df["scan_timestamp"])

    st.dataframe(
        df[["ticker", "company_name", "sector", "composite_score", "current_price", "market_cap", "scan_timestamp"]]
        .sort_values("composite_score", ascending=False),
        use_container_width=True, hide_index=True,
    )

    fig = px.bar(
        df.sort_values("composite_score", ascending=True).tail(20),
        x="composite_score", y="ticker", orientation="h",
        title="Top 20 Composite Scores",
        color="composite_score",
        color_continuous_scale=["#B76E79", "#D4A574", "#98D4BB"],
    )
    fig.update_layout(**CHART_LAYOUT, height=600)
    st.plotly_chart(fig, use_container_width=True)
