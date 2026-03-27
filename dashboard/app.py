"""
Streamlit Dashboard for Market Intelligence System.
Run with: streamlit run dashboard/app.py
"""

import json
import sys
import os
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import (
    init_db, get_latest_scan_results, get_latest_reports,
    get_report_for_ticker, get_all_analyses_for_ticker,
    get_agent_analyses_for_scan, get_quant_predictions_for_ticker,
    get_research_analyses_for_ticker,
)

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Market Intelligence Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Auto-refresh
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=300_000, key="auto_refresh")  # 5 minutes
except ImportError:
    pass

init_db()


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("Market Intelligence")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["Overview", "Analyze Any Stock", "Stock Deep Dive", "Agent Reports",
     "Research Reports", "Quant Predictions", "Agent Consensus", "Scan History"],
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    f"**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
)


# ── Helper Functions ──────────────────────────────────────────────────────────

def verdict_color(verdict: str) -> str:
    if "STRONG_BUY" in verdict:
        return "#00ff88"
    elif "BUY" in verdict:
        return "#44cc44"
    elif "STRONG_SELL" in verdict:
        return "#ff3333"
    elif "SELL" in verdict:
        return "#cc4444"
    return "#ffaa00"


def verdict_emoji(verdict: str) -> str:
    mapping = {
        "STRONG_BUY": "🟢🟢",
        "BUY": "🟢",
        "NEUTRAL": "🟡",
        "SELL": "🔴",
        "STRONG_SELL": "🔴🔴",
    }
    return mapping.get(verdict, "⚪")


def format_market_cap(mc):
    if not mc:
        return "N/A"
    # Indian notation: Cr (crore) and L Cr (lakh crore)
    cr = mc / 1e7  # 1 crore = 10 million
    if cr >= 1e5:
        return f"₹{cr/1e5:.1f}L Cr"
    if cr >= 1:
        return f"₹{cr:,.0f} Cr"
    return f"₹{mc:,.0f}"


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ANALYZE ANY STOCK
# ══════════════════════════════════════════════════════════════════════════════

if page == "Analyze Any Stock":
    st.title("Analyze Any Listed Stock")
    st.markdown("*Enter any NSE/BSE ticker to run the full analysis pipeline*")

    col_input, col_exchange = st.columns([3, 1])
    with col_input:
        raw_ticker = st.text_input(
            "Stock Ticker",
            placeholder="e.g. RELIANCE, TCS, INFY, HDFCBANK",
            help="Enter the stock symbol as listed on NSE. The .NS suffix will be added automatically.",
        )
    with col_exchange:
        exchange = st.selectbox("Exchange", ["NSE (.NS)", "BSE (.BO)"])

    # Quick suggestions
    st.markdown("**Popular:** `RELIANCE` `TCS` `INFY` `HDFCBANK` `ICICIBANK` `WIPRO` `ITC` `SBIN` `BAJFINANCE` `TATAMOTORS`")

    run_clicked = st.button("Run Full Analysis", type="primary", use_container_width=True)

    if run_clicked and raw_ticker:
        ticker = raw_ticker.strip().upper()
        suffix = ".NS" if "NSE" in exchange else ".BO"
        if not ticker.endswith((".NS", ".BO")):
            ticker += suffix

        st.markdown("---")
        st.subheader(f"Analyzing {ticker}...")

        # Progress tracking
        status_container = st.container()
        progress_bar = st.progress(0)

        steps = {
            "metrics": ("Scanning stock data & computing 32+ metrics...", 0.10),
            "quant": ("Running quantitative models (fair value, Monte Carlo, etc.)...", 0.25),
            "agents": ("Running 36 AI analyst agents...", 0.55),
            "research": ("Running 8 research agents (news, earnings cross-reference)...", 0.75),
            "aggregate": ("Synthesizing all analyses into final report...", 0.90),
        }

        status_text = status_container.empty()
        step_statuses = {}

        def progress_callback(step, detail):
            step_statuses[step] = detail
            info = steps.get(step, ("Processing...", 0.5))
            progress_bar.progress(info[1])
            status_text.markdown(f"**{info[0]}**\n\n{detail}")

        # Run the pipeline
        from pipeline.on_demand import analyze_single_stock

        with st.spinner("Running full analysis pipeline..."):
            result = analyze_single_stock(ticker, progress_callback=progress_callback)

        progress_bar.progress(1.0)

        if not result["success"] or result.get("error"):
            st.error(f"Analysis failed: {result.get('error', 'Unknown error')}")
            st.stop()

        # ── Display Results ──────────────────────────────────────────────
        status_text.empty()
        st.success(f"Analysis complete for {ticker}!")

        stock = result.get("stock", {})
        quant = result.get("quant", {})
        analyses = result.get("analyses", [])
        research = result.get("research", [])
        report = result.get("report", {})

        # Summary header
        st.markdown("---")
        st.subheader(f"{stock.get('company_name', ticker)} ({ticker})")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Price", f"₹{stock.get('current_price', 0):.2f}")
        c2.metric("Market Cap", format_market_cap(stock.get("market_cap")))
        c3.metric("Sector", stock.get("sector", "N/A"))
        c4.metric("Composite Score", f"{stock.get('composite_score', 0):.1f}")

        if report:
            verdict = report.get("overall_verdict", "N/A")
            c5.metric("Final Verdict", verdict)
        else:
            c5.metric("Agents Run", str(len(analyses)))

        # ── Final Report ──
        if report:
            st.markdown("---")
            st.subheader("Final Verdict")

            v_col1, v_col2, v_col3 = st.columns(3)
            v_col1.metric("Verdict", report.get("overall_verdict", "N/A"))
            v_col2.metric("Score", f"{report.get('overall_score', 0)}/10")
            v_col3.metric("Conviction", str(report.get("conviction", "N/A")).replace("_", " ").title())

            if report.get("consensus_summary"):
                st.markdown(f"**Consensus:** {report['consensus_summary']}")

            col_bull, col_bear = st.columns(2)
            with col_bull:
                st.markdown("**Bull Case:**")
                st.success(report.get("bull_case", "N/A"))
                if report.get("key_catalysts"):
                    catalysts = report["key_catalysts"] if isinstance(report["key_catalysts"], list) else []
                    for c in catalysts:
                        st.markdown(f"- {c}")
            with col_bear:
                st.markdown("**Bear Case:**")
                st.error(report.get("bear_case", "N/A"))
                if report.get("key_risks"):
                    risks = report["key_risks"] if isinstance(report["key_risks"], list) else []
                    for r in risks:
                        st.markdown(f"- {r}")

            if report.get("recommendation"):
                st.info(f"**Recommendation:** {report['recommendation']}")

            if report.get("entry_strategy"):
                st.markdown(f"**Entry Strategy:** {report['entry_strategy']}")
            if report.get("position_size"):
                st.markdown(f"**Position Size:** {report['position_size']}")
            if report.get("time_horizon"):
                st.markdown(f"**Time Horizon:** {report['time_horizon']}")

        # ── Quant Summary ──
        if quant and not quant.get("error"):
            st.markdown("---")
            st.subheader("Quantitative Analysis")

            summary = quant.get("summary", {})
            valuations = quant.get("valuations", {})
            predictions = quant.get("predictions", {})

            q1, q2, q3, q4 = st.columns(4)
            fair = valuations.get("composite_fair_value")
            upside = valuations.get("composite_upside")
            mc = predictions.get("monte_carlo", {})

            q1.metric("Fair Value", f"₹{fair:.2f}" if fair else "N/A")
            q2.metric("Upside/Downside", f"{upside:+.1f}%" if upside is not None else "N/A")
            q3.metric("P(Up 30d)", f"{mc.get('prob_positive', 'N/A')}%" if mc.get("prob_positive") is not None else "N/A")
            q4.metric("Monte Carlo Median", f"₹{mc.get('median_price', 0):.2f}" if mc.get("median_price") else "N/A")

            # Valuation table
            val_rows = []
            for name, key, up_key in [
                ("Graham Number", "graham_number", "upside_graham"),
                ("DCF", "dcf_value", "upside_dcf"),
                ("PEG Fair Value", "peg_value", "upside_peg"),
                ("Composite", "composite_fair_value", "composite_upside"),
            ]:
                val = valuations.get(key)
                up = valuations.get(up_key)
                val_rows.append({
                    "Model": name,
                    "Fair Value": f"₹{val:.2f}" if val else "N/A",
                    "Upside": f"{up:+.1f}%" if up is not None else "N/A",
                })
            st.dataframe(pd.DataFrame(val_rows), use_container_width=True, hide_index=True)

        # ── Agent Verdicts Summary ──
        if analyses:
            st.markdown("---")
            st.subheader(f"AI Agent Analysis ({len(analyses)} base + {len(research)} research)")

            buy_count = sum(1 for a in analyses if "BUY" in a.get("verdict", ""))
            sell_count = sum(1 for a in analyses if "SELL" in a.get("verdict", ""))
            error_count = sum(1 for a in analyses if a.get("verdict") == "ERROR")
            neutral_count = len(analyses) - buy_count - sell_count - error_count

            a1, a2, a3, a4 = st.columns(4)
            a1.metric("Bullish", buy_count)
            a2.metric("Bearish", sell_count)
            a3.metric("Neutral", neutral_count)
            a4.metric("Errors", error_count)

            # Verdict pie chart
            all_a = analyses + research
            verdict_counts = {}
            for a in all_a:
                v = a.get("verdict", "NEUTRAL")
                if v != "ERROR":
                    verdict_counts[v] = verdict_counts.get(v, 0) + 1

            if verdict_counts:
                fig = go.Figure(data=[go.Pie(
                    labels=list(verdict_counts.keys()),
                    values=list(verdict_counts.values()),
                    hole=0.4,
                    marker_colors=[verdict_color(v) for v in verdict_counts.keys()],
                )])
                fig.update_layout(title="Agent Verdict Distribution", height=350)
                st.plotly_chart(fig, use_container_width=True)

            # Individual agent details (collapsed)
            with st.expander(f"View all {len(all_a)} agent reports", expanded=False):
                for a in sorted(all_a, key=lambda x: x.get("score", 0), reverse=True):
                    v = a.get("verdict", "?")
                    name = a.get("agent_name", "Unknown")
                    score = a.get("score", 0)
                    conf = a.get("confidence", 0)
                    st.markdown(
                        f"**{verdict_emoji(v)} {name}** — {v} | "
                        f"Score: {score}/10 | Confidence: {conf:.0%}"
                    )
                    st.caption(a.get("reasoning", "")[:300])
                    st.markdown("---")

        st.markdown("---")
        st.info(
            "This stock has been saved to the database. You can view detailed breakdowns "
            "in the **Stock Deep Dive**, **Agent Reports**, **Research Reports**, and "
            "**Quant Predictions** pages."
        )

    elif run_clicked and not raw_ticker:
        st.warning("Please enter a stock ticker.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Overview":
    st.title("Market Intelligence Overview")

    reports = get_latest_reports(limit=20)

    if not reports:
        st.warning("No analysis reports yet. Run the scanner first: `python main.py`")
        st.info("""
        **Getting Started:**
        1. Copy `.env.example` to `.env` and add your API keys
        2. Install dependencies: `pip install -r requirements.txt`
        3. Run the scanner: `python main.py`
        4. Results will appear here automatically
        """)
        st.stop()

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    buy_reports = [r for r in reports if "BUY" in r.get("overall_verdict", "")]
    sell_reports = [r for r in reports if "SELL" in r.get("overall_verdict", "")]

    col1.metric("Stocks Analyzed", len(reports))
    col2.metric("Buy Signals", len(buy_reports))
    col3.metric("Sell Signals", len(sell_reports))
    avg_score = sum(r.get("overall_score", 5) for r in reports) / max(len(reports), 1)
    col4.metric("Avg Score", f"{avg_score:.1f}/10")

    st.markdown("---")

    # Main table
    st.subheader("Latest Analysis Results")

    for report in reports:
        ticker = report["ticker"]
        verdict = report.get("overall_verdict", "NEUTRAL")
        score = report.get("overall_score", 5)
        company = report.get("company_name", ticker)
        sector = report.get("sector", "")
        price = report.get("current_price", 0)
        mcap = report.get("market_cap", 0)
        recommendation = report.get("recommendation", "")
        agreement = report.get("agent_agreement_pct", 0)

        with st.expander(
            f"{verdict_emoji(verdict)} **{ticker}** — {company} | "
            f"Score: {score}/10 | {verdict} | ₹{price:.2f}"
        ):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Verdict", verdict)
            c2.metric("Score", f"{score}/10")
            c3.metric("Price", f"₹{price:.2f}")
            c4.metric("Market Cap", format_market_cap(mcap))

            if report.get("consensus_summary"):
                st.markdown(f"**Consensus:** {report['consensus_summary']}")

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**Bull Case:**")
                st.markdown(report.get("bull_case", "N/A"))
                if report.get("key_catalysts"):
                    catalysts = json.loads(report["key_catalysts"]) if isinstance(report["key_catalysts"], str) else report["key_catalysts"]
                    for c in catalysts:
                        st.markdown(f"- ✅ {c}")

            with col_b:
                st.markdown("**Bear Case:**")
                st.markdown(report.get("bear_case", "N/A"))
                if report.get("key_risks"):
                    risks = json.loads(report["key_risks"]) if isinstance(report["key_risks"], str) else report["key_risks"]
                    for r in risks:
                        st.markdown(f"- ⚠️ {r}")

            if recommendation:
                st.info(f"**Recommendation:** {recommendation}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: STOCK DEEP DIVE
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Stock Deep Dive":
    st.title("Stock Deep Dive")

    reports = get_latest_reports(limit=20)
    tickers = [r["ticker"] for r in reports]

    if not tickers:
        st.warning("No stocks analyzed yet. Run the scanner first.")
        st.stop()

    selected = st.selectbox("Select Stock", tickers)
    report = get_report_for_ticker(selected)

    if not report:
        st.warning(f"No report found for {selected}")
        st.stop()

    # Header
    verdict = report.get("overall_verdict", "NEUTRAL")
    st.markdown(
        f"### {verdict_emoji(verdict)} {selected} — "
        f"{report.get('company_name', selected)}"
    )

    # Key metrics row
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Verdict", verdict)
    c2.metric("Score", f"{report.get('overall_score', 0)}/10")
    c3.metric("Price", f"₹{report.get('current_price', 0):.2f}")
    c4.metric("Market Cap", format_market_cap(report.get("market_cap")))
    c5.metric("Sector", report.get("sector", "N/A"))

    st.markdown("---")

    # Detailed metrics from scan
    if report.get("metrics_json"):
        metrics = json.loads(report["metrics_json"]) if isinstance(report["metrics_json"], str) else report["metrics_json"]

        st.subheader("Scanner Metrics (32+)")

        tabs = st.tabs(["Price Action", "Volume", "Volatility", "Momentum", "Fundamentals", "Sentiment"])

        with tabs[0]:
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("vs 52w Low", f"{metrics.get('price_vs_52w_low', 0):.1f}%")
            mc2.metric("vs 52w High", f"-{metrics.get('price_vs_52w_high', 0):.1f}%")
            mc3.metric("Daily Return", f"{metrics.get('daily_return', 0):+.2f}%")
            mc4.metric("Monthly Return", f"{metrics.get('monthly_return', 0):+.2f}%")

        with tabs[1]:
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Volume Surge", f"{metrics.get('volume_surge', 1):.1f}x")
            mc2.metric("Relative Volume", f"{metrics.get('relative_volume', 1):.1f}x")
            mc3.metric("OBV Trend", "Rising" if metrics.get("on_balance_volume_trend", 0) > 0 else "Falling")

        with tabs[2]:
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Hist. Volatility", f"{metrics.get('historical_volatility', 0):.1f}%")
            mc2.metric("ATR %", f"{metrics.get('atr_percentage', 0):.2f}%")
            mc3.metric("BB Bandwidth", f"{metrics.get('bollinger_squeeze', 0):.1f}%")

        with tabs[3]:
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("RSI", f"{metrics.get('rsi', 50):.0f}")
            mc2.metric("MACD", "Bullish" if metrics.get("macd_signal", 0) > 0 else "Bearish")
            mc3.metric("Momentum", f"{metrics.get('momentum_score', 5):.1f}/10")
            mc4.metric("ROC (10d)", f"{metrics.get('rate_of_change', 0):+.1f}%")

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

    # Synthesis reports
    st.markdown("---")
    st.subheader("AI Synthesis Reports")

    tab_d, tab_s, tab_p = st.tabs(["Data Analysis", "Sentiment Analysis", "Prediction Analysis"])

    with tab_d:
        st.markdown(report.get("data_summary", "No data synthesis available."))
    with tab_s:
        st.markdown(report.get("sentiment_summary", "No sentiment synthesis available."))
    with tab_p:
        st.markdown(report.get("prediction_summary", "No prediction synthesis available."))

    # Recommendation
    st.markdown("---")
    if report.get("recommendation"):
        st.success(f"**Final Recommendation:** {report['recommendation']}")

    # Individual agent analyses
    st.markdown("---")
    st.subheader("Individual Agent Analyses (32+)")

    all_analyses = get_all_analyses_for_ticker(selected)
    if all_analyses:
        # Verdict distribution chart
        verdict_counts = {}
        for a in all_analyses:
            v = a.get("verdict", "NEUTRAL")
            verdict_counts[v] = verdict_counts.get(v, 0) + 1

        fig = go.Figure(data=[go.Pie(
            labels=list(verdict_counts.keys()),
            values=list(verdict_counts.values()),
            hole=0.4,
            marker_colors=[verdict_color(v) for v in verdict_counts.keys()],
        )])
        fig.update_layout(title="Agent Verdict Distribution", height=350)
        st.plotly_chart(fig, use_container_width=True)

        # Score distribution
        scores = [a.get("score", 5) for a in all_analyses if a.get("score")]
        if scores:
            fig2 = go.Figure(data=[go.Histogram(x=scores, nbinsx=10)])
            fig2.update_layout(title="Agent Score Distribution", xaxis_title="Score", yaxis_title="Count", height=300)
            st.plotly_chart(fig2, use_container_width=True)

        # Individual analyses
        for a in all_analyses:
            verdict = a.get("verdict", "?")
            with st.expander(
                f"{verdict_emoji(verdict)} {a.get('agent_name', '?')} — {verdict} "
                f"(Score: {a.get('score', 0)}/10, Conf: {a.get('confidence', 0):.0%})"
            ):
                st.markdown(f"**Role:** {a.get('agent_role', 'N/A')}")
                st.markdown(f"**Reasoning:** {a.get('reasoning', 'N/A')}")

                if a.get("key_points"):
                    points = json.loads(a["key_points"]) if isinstance(a["key_points"], str) else a["key_points"]
                    st.markdown("**Key Points:**")
                    for p in points:
                        st.markdown(f"- {p}")

                col1, col2 = st.columns(2)
                with col1:
                    if a.get("catalysts"):
                        cats = json.loads(a["catalysts"]) if isinstance(a["catalysts"], str) else a["catalysts"]
                        st.markdown("**Catalysts:**")
                        for c in cats:
                            st.markdown(f"- ✅ {c}")
                with col2:
                    if a.get("risks"):
                        risks = json.loads(a["risks"]) if isinstance(a["risks"], str) else a["risks"]
                        st.markdown("**Risks:**")
                        for r in risks:
                            st.markdown(f"- ⚠️ {r}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: AGENT REPORTS
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Agent Reports":
    st.title("Agent-by-Agent Full Reports")

    reports = get_latest_reports(limit=20)
    tickers = [r["ticker"] for r in reports]

    if not tickers:
        st.warning("No stocks analyzed yet. Run the scanner first.")
        st.stop()

    selected = st.selectbox("Select Stock to View All Agent Reports", tickers)
    all_analyses = get_all_analyses_for_ticker(selected)

    if not all_analyses:
        st.warning(f"No agent analyses for {selected}")
        st.stop()

    report = get_report_for_ticker(selected)
    company_name = report.get("company_name", selected) if report else selected

    st.markdown(f"### {company_name} ({selected})")

    # ── Summary Stats ─────────────────────────────────────────────────────
    total = len(all_analyses)
    buy_agents = [a for a in all_analyses if "BUY" in a.get("verdict", "")]
    sell_agents = [a for a in all_analyses if "SELL" in a.get("verdict", "")]
    neutral_agents = [a for a in all_analyses if a.get("verdict") == "NEUTRAL"]
    error_agents = [a for a in all_analyses if a.get("verdict") == "ERROR"]

    avg_score = sum(a.get("score", 5) for a in all_analyses) / max(total, 1)
    avg_conf = sum(a.get("confidence", 0.5) for a in all_analyses) / max(total, 1)
    max_score_agent = max(all_analyses, key=lambda a: a.get("score", 0))
    min_score_agent = min(all_analyses, key=lambda a: a.get("score", 10))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Agents", total)
    c2.metric("Bullish", len(buy_agents), delta=f"{len(buy_agents)/total*100:.0f}%")
    c3.metric("Bearish", len(sell_agents), delta=f"-{len(sell_agents)/total*100:.0f}%")
    c4.metric("Avg Score", f"{avg_score:.1f}/10")
    c5.metric("Avg Confidence", f"{avg_conf:.0%}")

    st.markdown("---")

    # ── Most Bullish & Most Bearish ───────────────────────────────────────
    col_bull, col_bear = st.columns(2)
    with col_bull:
        st.markdown(f"**Most Bullish Agent:**")
        st.markdown(
            f"**{max_score_agent.get('agent_name', '?')}** — "
            f"Score: {max_score_agent.get('score', 0)}/10 | "
            f"{max_score_agent.get('verdict', '?')}"
        )
        st.caption(max_score_agent.get("reasoning", "")[:200])
    with col_bear:
        st.markdown(f"**Most Bearish Agent:**")
        st.markdown(
            f"**{min_score_agent.get('agent_name', '?')}** — "
            f"Score: {min_score_agent.get('score', 0)}/10 | "
            f"{min_score_agent.get('verdict', '?')}"
        )
        st.caption(min_score_agent.get("reasoning", "")[:200])

    st.markdown("---")

    # ── Verdict & Score Charts ────────────────────────────────────────────
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        verdict_counts = {}
        for a in all_analyses:
            v = a.get("verdict", "NEUTRAL")
            verdict_counts[v] = verdict_counts.get(v, 0) + 1
        fig = go.Figure(data=[go.Pie(
            labels=list(verdict_counts.keys()),
            values=list(verdict_counts.values()),
            hole=0.4,
            marker_colors=[verdict_color(v) for v in verdict_counts.keys()],
        )])
        fig.update_layout(title="Verdict Distribution", height=300, margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with chart_col2:
        agent_names = [a.get("agent_name", "?").split(" - ")[0] for a in all_analyses]
        agent_scores = [a.get("score", 5) for a in all_analyses]
        score_colors = ["#00ff88" if s >= 7 else "#ff3333" if s <= 4 else "#ffaa00" for s in agent_scores]

        fig2 = go.Figure(data=[go.Bar(
            x=agent_scores, y=agent_names,
            orientation="h",
            marker_color=score_colors,
        )])
        fig2.update_layout(
            title="Score by Agent", height=max(400, total * 22),
            xaxis_title="Score", yaxis=dict(autorange="reversed"),
            margin=dict(l=10, t=40, b=20),
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ── Confidence vs Score Scatter ───────────────────────────────────────
    st.subheader("Confidence vs Score")
    scatter_data = pd.DataFrame([{
        "Agent": a.get("agent_name", "?"),
        "Score": a.get("score", 5),
        "Confidence": a.get("confidence", 0.5),
        "Verdict": a.get("verdict", "NEUTRAL"),
    } for a in all_analyses])

    fig3 = px.scatter(
        scatter_data, x="Score", y="Confidence",
        color="Verdict", hover_data=["Agent"],
        color_discrete_map={
            "STRONG_BUY": "#00ff88", "BUY": "#44cc44",
            "NEUTRAL": "#ffaa00",
            "SELL": "#cc4444", "STRONG_SELL": "#ff3333",
        },
        title="Agent Confidence vs Score",
    )
    fig3.update_layout(height=400)
    st.plotly_chart(fig3, use_container_width=True)

    st.markdown("---")

    # ── Filter by Verdict ─────────────────────────────────────────────────
    st.subheader("Detailed Agent Reports")
    filter_verdict = st.multiselect(
        "Filter by Verdict",
        ["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL", "ERROR"],
        default=["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"],
    )

    sort_by = st.radio("Sort by", ["Score (High to Low)", "Score (Low to High)", "Confidence", "Agent Name"], horizontal=True)

    filtered = [a for a in all_analyses if a.get("verdict", "NEUTRAL") in filter_verdict]

    if sort_by == "Score (High to Low)":
        filtered.sort(key=lambda a: a.get("score", 0), reverse=True)
    elif sort_by == "Score (Low to High)":
        filtered.sort(key=lambda a: a.get("score", 0))
    elif sort_by == "Confidence":
        filtered.sort(key=lambda a: a.get("confidence", 0), reverse=True)
    else:
        filtered.sort(key=lambda a: a.get("agent_name", ""))

    # ── Full Agent Cards ──────────────────────────────────────────────────
    for i, a in enumerate(filtered):
        verdict = a.get("verdict", "?")
        agent_name = a.get("agent_name", "Unknown Agent")
        score = a.get("score", 0)
        confidence = a.get("confidence", 0)
        reasoning = a.get("reasoning", "No reasoning provided")
        role = a.get("agent_role", "N/A")

        with st.expander(
            f"{verdict_emoji(verdict)} **{agent_name}** | "
            f"{verdict} | Score: {score}/10 | Confidence: {confidence:.0%}",
            expanded=(i < 3),  # Auto-expand top 3
        ):
            # Header row
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Verdict", verdict)
            mc2.metric("Score", f"{score}/10")
            mc3.metric("Confidence", f"{confidence:.0%}")
            mc4.metric("Role", role.replace("_", " ").title())

            # Full reasoning
            st.markdown("---")
            st.markdown("**Full Analysis & Reasoning:**")
            st.markdown(reasoning)

            # Key points
            if a.get("key_points"):
                points = json.loads(a["key_points"]) if isinstance(a["key_points"], str) else a["key_points"]
                if points:
                    st.markdown("**Key Points:**")
                    for p in points:
                        st.markdown(f"- {p}")

            # Catalysts & Risks side by side
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Catalysts (Bull Arguments):**")
                if a.get("catalysts"):
                    cats = json.loads(a["catalysts"]) if isinstance(a["catalysts"], str) else a["catalysts"]
                    if cats:
                        for c in cats:
                            st.markdown(f"- ✅ {c}")
                    else:
                        st.caption("None identified")
                else:
                    st.caption("None identified")

            with col2:
                st.markdown("**Risks (Bear Arguments):**")
                if a.get("risks"):
                    risks = json.loads(a["risks"]) if isinstance(a["risks"], str) else a["risks"]
                    if risks:
                        for r in risks:
                            st.markdown(f"- ⚠️ {r}")
                    else:
                        st.caption("None identified")
                else:
                    st.caption("None identified")

            # Raw response (collapsible within collapsible)
            if a.get("raw_response"):
                raw = a["raw_response"]
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except json.JSONDecodeError:
                        pass
                st.markdown("**Raw Agent Response:**")
                st.json(raw if isinstance(raw, dict) else {"raw": str(raw)[:3000]})

    # ── Synthesis Reports ─────────────────────────────────────────────────
    if report:
        st.markdown("---")
        st.subheader("Aggregator Synthesis Reports")

        st.markdown("**Data Synthesis (What the numbers say):**")
        st.info(report.get("data_summary", "Not available"))

        st.markdown("**Sentiment Synthesis (What the mood is):**")
        st.info(report.get("sentiment_summary", "Not available"))

        st.markdown("**Prediction Synthesis (What's likely to happen):**")
        st.info(report.get("prediction_summary", "Not available"))

        st.markdown("---")
        st.markdown("**Final CIO Verdict:**")

        if report.get("full_report_json"):
            full = json.loads(report["full_report_json"]) if isinstance(report["full_report_json"], str) else report["full_report_json"]

            v1, v2, v3 = st.columns(3)
            v1.metric("Overall Verdict", full.get("overall_verdict", "N/A"))
            v2.metric("Overall Score", f"{full.get('overall_score', 0)}/10")
            v3.metric("Conviction", full.get("conviction", "N/A").replace("_", " ").title())

            if full.get("bull_case"):
                st.success(f"**Bull Case:** {full['bull_case']}")
            if full.get("bear_case"):
                st.error(f"**Bear Case:** {full['bear_case']}")
            if full.get("consensus_summary"):
                st.markdown(f"**Consensus:** {full['consensus_summary']}")
            if full.get("entry_strategy"):
                st.markdown(f"**Entry Strategy:** {full['entry_strategy']}")
            if full.get("position_size"):
                st.markdown(f"**Suggested Position Size:** {full['position_size']}")
            if full.get("time_horizon"):
                st.markdown(f"**Time Horizon:** {full['time_horizon']}")
            if full.get("exit_triggers"):
                triggers = full["exit_triggers"]
                if isinstance(triggers, list):
                    st.markdown("**Exit Triggers:**")
                    for t in triggers:
                        st.markdown(f"- {t}")

        if report.get("recommendation"):
            st.markdown("---")
            st.success(f"**FINAL RECOMMENDATION:** {report['recommendation']}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: RESEARCH REPORTS
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Research Reports":
    st.title("Research & News Cross-Reference")
    st.markdown("*8 research agents verify whether company narratives match reality*")

    reports = get_latest_reports(limit=20)
    tickers = [r["ticker"] for r in reports]

    if not tickers:
        st.warning("No stocks analyzed yet. Run the scanner first.")
        st.stop()

    selected = st.selectbox("Select Stock", tickers, key="research_stock")
    research = get_research_analyses_for_ticker(selected)

    if not research:
        st.info(f"No research agent data for {selected}. Run the full pipeline to generate research reports.")
        st.stop()

    report = get_report_for_ticker(selected)
    company_name = report.get("company_name", selected) if report else selected
    st.markdown(f"### {company_name} ({selected})")

    # Summary metrics
    total = len(research)
    buy_r = sum(1 for a in research if "BUY" in a.get("verdict", ""))
    sell_r = sum(1 for a in research if "SELL" in a.get("verdict", ""))
    avg_score_r = sum(a.get("score", 5) for a in research) / max(total, 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Research Agents", total)
    c2.metric("Bullish", buy_r)
    c3.metric("Bearish", sell_r)
    c4.metric("Avg Score", f"{avg_score_r:.1f}/10")

    st.markdown("---")

    # Compare research vs base agents
    all_analyses = get_all_analyses_for_ticker(selected)
    research_roles = {
        "news_reality_check", "earnings_analyst", "annual_report_forensic",
        "research_cross_check", "management_credibility", "competitive_intel",
        "macro_news_correlator", "narrative_vs_numbers",
    }
    base_analyses = [a for a in all_analyses if a.get("agent_role") not in research_roles]

    if base_analyses:
        base_avg = sum(a.get("score", 5) for a in base_analyses) / max(len(base_analyses), 1)
        delta = avg_score_r - base_avg

        st.subheader("Research vs Base Agent Comparison")
        col1, col2, col3 = st.columns(3)
        col1.metric("Base Agents Avg Score", f"{base_avg:.1f}/10")
        col2.metric("Research Agents Avg Score", f"{avg_score_r:.1f}/10")
        col3.metric("Delta", f"{delta:+.1f}", delta_color="normal")

        if abs(delta) > 1.5:
            if delta > 0:
                st.success("Research agents are MORE bullish than base agents — news/earnings data supports the thesis")
            else:
                st.error("Research agents are MORE bearish than base agents — news/earnings data raises concerns")
        st.markdown("---")

    # Individual research agent cards
    st.subheader("Detailed Research Agent Reports")
    for a in research:
        verdict = a.get("verdict", "?")
        agent_name = a.get("agent_name", "Unknown")
        score = a.get("score", 0)
        confidence = a.get("confidence", 0)

        with st.expander(
            f"{verdict_emoji(verdict)} **{agent_name}** | {verdict} | Score: {score}/10",
            expanded=True,
        ):
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Verdict", verdict)
            mc2.metric("Score", f"{score}/10")
            mc3.metric("Confidence", f"{confidence:.0%}")

            st.markdown(f"**Analysis:** {a.get('reasoning', 'N/A')}")

            # Research-specific fields
            raw = a.get("raw_response", "{}")
            if isinstance(raw, str):
                try:
                    raw_data = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    raw_data = {}
            else:
                raw_data = raw if isinstance(raw, dict) else {}

            reality_check = raw_data.get("reality_check", "")
            narrative_gap = raw_data.get("narrative_gap", "")

            if reality_check:
                st.info(f"**Reality Check:** {reality_check}")
            if narrative_gap:
                st.warning(f"**Narrative Gap:** {narrative_gap}")

            if a.get("key_points"):
                points = json.loads(a["key_points"]) if isinstance(a["key_points"], str) else a["key_points"]
                if points:
                    st.markdown("**Key Findings:**")
                    for p in points:
                        st.markdown(f"- {p}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: QUANT PREDICTIONS
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Quant Predictions":
    st.title("Quantitative Prediction Engine")
    st.markdown("*Pure math models — fair value, support/resistance, Monte Carlo simulations*")

    reports = get_latest_reports(limit=20)
    tickers = [r["ticker"] for r in reports]

    if not tickers:
        st.warning("No stocks analyzed yet. Run the scanner first.")
        st.stop()

    selected = st.selectbox("Select Stock", tickers, key="quant_stock")
    quant = get_quant_predictions_for_ticker(selected)

    if not quant:
        st.info(f"No quant predictions for {selected}. Run: `python main.py` or `python main.py --quant-only`")
        st.stop()

    report = get_report_for_ticker(selected)
    company_name = report.get("company_name", selected) if report else selected
    st.markdown(f"### {company_name} ({selected})")

    valuations = quant.get("valuations_json", {})
    levels = quant.get("levels_json", {})
    predictions = quant.get("predictions_json", {})
    summary = quant.get("summary_json", {})

    # ── Summary Row ──
    current_price = summary.get("current_price") or valuations.get("current_price", 0)
    fair_value = valuations.get("composite_fair_value")
    upside = valuations.get("composite_upside")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current Price", f"₹{current_price:.2f}" if current_price else "N/A")
    c2.metric("Fair Value (Composite)", f"₹{fair_value:.2f}" if fair_value else "N/A")
    c3.metric("Upside/Downside", f"{upside:+.1f}%" if upside is not None else "N/A",
              delta_color="normal")
    mc = predictions.get("monte_carlo", {})
    c4.metric("P(Up in 30d)", f"{mc.get('prob_positive', 'N/A')}%"
              if mc.get("prob_positive") is not None else "N/A")

    st.markdown("---")

    # ── Valuation Models ──
    st.subheader("Fair Value Estimates")

    val_tab1, val_tab2, val_tab3 = st.tabs(["Gauge Charts", "Comparison Table", "Model Details"])

    with val_tab1:
        gcol1, gcol2, gcol3 = st.columns(3)
        for col, (name, key) in zip(
            [gcol1, gcol2, gcol3],
            [("Graham Number", "graham_number"), ("DCF Value", "dcf_value"), ("PEG Value", "peg_value")]
        ):
            val = valuations.get(key)
            with col:
                if val:
                    fig = go.Figure(go.Indicator(
                        mode="gauge+number+delta",
                        value=current_price,
                        delta={"reference": val, "relative": True, "valueformat": ".1%"},
                        title={"text": name},
                        gauge={
                            "axis": {"range": [min(current_price, val) * 0.5, max(current_price, val) * 1.5]},
                            "bar": {"color": "#444"},
                            "steps": [
                                {"range": [0, val * 0.8], "color": "#00ff88"},
                                {"range": [val * 0.8, val * 1.2], "color": "#ffaa00"},
                                {"range": [val * 1.2, max(current_price, val) * 1.5], "color": "#ff3333"},
                            ],
                            "threshold": {
                                "line": {"color": "blue", "width": 3},
                                "thickness": 0.75,
                                "value": val,
                            },
                        },
                    ))
                    fig.update_layout(height=250, margin=dict(t=40, b=10))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.caption(f"{name}: Insufficient data")

    with val_tab2:
        rows = []
        for name, key, upside_key in [
            ("Graham Number", "graham_number", "upside_graham"),
            ("DCF (Discounted Cash Flow)", "dcf_value", "upside_dcf"),
            ("PEG Ratio Fair Value", "peg_value", "upside_peg"),
            ("Composite Average", "composite_fair_value", "composite_upside"),
        ]:
            val = valuations.get(key)
            up = valuations.get(upside_key)
            rows.append({
                "Model": name,
                "Fair Value": f"₹{val:.2f}" if val else "N/A",
                "Current Price": f"₹{current_price:.2f}",
                "Upside": f"{up:+.1f}%" if up is not None else "N/A",
                "Signal": "UNDERVALUED" if up and up > 10 else "OVERVALUED" if up and up < -10 else "FAIR",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with val_tab3:
        st.markdown("""
        **Graham Number**: `sqrt(22.5 * EPS * Book Value)` — Benjamin Graham's intrinsic value formula
        **DCF**: Discounted Cash Flow — projects free cash flow 5 years forward, discounts at 10%
        **PEG**: Price/Earnings-to-Growth — fair P/E = earnings growth rate (when PEG = 1.0)
        """)

    st.markdown("---")

    # ── Support/Resistance Levels ──
    st.subheader("Support & Resistance Levels")

    fib = levels.get("fibonacci", {})
    pivots = levels.get("pivot_points", {})
    mas = levels.get("moving_averages", {})

    # Price chart with levels
    all_levels = []
    if fib:
        for name, val in fib.items():
            if name.startswith("fib_") and val:
                all_levels.append({"Level": f"Fib {name.replace('fib_', '')}", "Price": val, "Type": "Fibonacci"})
    if pivots:
        for name, val in pivots.items():
            if val:
                all_levels.append({"Level": name.upper(), "Price": val, "Type": "Pivot"})
    if mas:
        for name, val in mas.items():
            if val:
                all_levels.append({"Level": name.upper(), "Price": val, "Type": "Moving Avg"})

    if all_levels:
        levels_df = pd.DataFrame(all_levels).sort_values("Price", ascending=False)

        fig = go.Figure()
        colors = {"Fibonacci": "#9966ff", "Pivot": "#ff6600", "Moving Avg": "#0099ff"}
        for _, row in levels_df.iterrows():
            fig.add_hline(
                y=row["Price"], line_dash="dash",
                line_color=colors.get(row["Type"], "#888"),
                annotation_text=f"{row['Level']}: ₹{row['Price']:.2f}",
                annotation_position="right",
            )

        fig.add_hline(y=current_price, line_color="white", line_width=3,
                      annotation_text=f"Current: ₹{current_price:.2f}")
        fig.update_layout(
            title="Price Levels Map",
            yaxis_title="Price (₹)",
            height=500,
            yaxis=dict(range=[min(l["Price"] for l in all_levels) * 0.95,
                              max(l["Price"] for l in all_levels) * 1.05]),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Table view
        st.dataframe(levels_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── Monte Carlo Simulation ──
    st.subheader("Monte Carlo Price Simulation (30-day)")

    mc = predictions.get("monte_carlo", {})
    if mc and not mc.get("error"):
        mc_col1, mc_col2, mc_col3, mc_col4 = st.columns(4)
        mc_col1.metric("Median Price (30d)", f"₹{mc.get('median_price', 0):.2f}")
        mc_col2.metric("Expected Return", f"{mc.get('expected_return', 0):+.2f}%")
        mc_col3.metric("P(Positive)", f"{mc.get('prob_positive', 0):.0f}%")
        mc_col4.metric("Ann. Volatility", f"{mc.get('annualized_volatility', 0):.1f}%")

        # Distribution chart
        percentiles = [
            ("P10 (Bearish)", mc.get("p10", 0)),
            ("P25", mc.get("p25", 0)),
            ("Median", mc.get("median_price", 0)),
            ("P75", mc.get("p75", 0)),
            ("P90 (Bullish)", mc.get("p90", 0)),
        ]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=[p[0] for p in percentiles],
            y=[p[1] for p in percentiles],
            marker_color=["#ff3333", "#ffaa00", "#ffffff", "#88cc88", "#00ff88"],
            text=[f"₹{p[1]:.2f}" for p in percentiles],
            textposition="outside",
        ))
        fig.add_hline(y=current_price, line_dash="dash", line_color="cyan",
                      annotation_text=f"Current: ₹{current_price:.2f}")
        fig.update_layout(title="30-Day Price Distribution", yaxis_title="Price (₹)", height=400)
        st.plotly_chart(fig, use_container_width=True)

        # Probabilities
        st.markdown("**Probability Analysis:**")
        p_col1, p_col2, p_col3 = st.columns(3)
        p_col1.metric("P(Up >10%)", f"{mc.get('prob_up_10pct', 0):.0f}%")
        p_col2.metric("P(Down >10%)", f"{mc.get('prob_down_10pct', 0):.0f}%")
        p_col3.metric("Daily Volatility", f"{mc.get('daily_volatility', 0):.2f}%")
    else:
        st.info("Monte Carlo simulation data not available.")

    st.markdown("---")

    # ── Mean Reversion ──
    st.subheader("Mean Reversion Analysis")

    mr = predictions.get("mean_reversion", {})
    if mr and not mr.get("error"):
        mr_col1, mr_col2, mr_col3, mr_col4 = st.columns(4)
        mr_col1.metric("Z-Score", f"{mr.get('z_score', 0):.2f}")
        mr_col2.metric("Target (SMA)", f"₹{mr.get('target_price', 0):.2f}")
        mr_col3.metric("Deviation", f"{mr.get('deviation_pct', 0):+.1f}%")
        signal = mr.get("signal", "FAIR")
        mr_col4.metric("Signal", signal)

        # Z-score gauge
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=mr.get("z_score", 0),
            title={"text": "Z-Score (distance from mean)"},
            gauge={
                "axis": {"range": [-3, 3]},
                "bar": {"color": "#444"},
                "steps": [
                    {"range": [-3, -2], "color": "#00ff88"},   # Oversold
                    {"range": [-2, -1], "color": "#88cc88"},
                    {"range": [-1, 1], "color": "#ffaa00"},    # Fair
                    {"range": [1, 2], "color": "#cc8844"},
                    {"range": [2, 3], "color": "#ff3333"},     # Overbought
                ],
            },
        ))
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

        if mr.get("half_life_days"):
            st.markdown(f"**Estimated mean reversion half-life:** {mr['half_life_days']:.0f} days")
        st.markdown(f"**Bands:** ₹{mr.get('band_lower_2std', 0):.2f} (−2σ) → "
                    f"₹{mr.get('band_lower_1std', 0):.2f} (−1σ) → "
                    f"₹{mr.get('target_price', 0):.2f} (mean) → "
                    f"₹{mr.get('band_upper_1std', 0):.2f} (+1σ) → "
                    f"₹{mr.get('band_upper_2std', 0):.2f} (+2σ)")
    else:
        st.info("Mean reversion data not available.")

    st.markdown("---")

    # ── Bollinger Bands ──
    st.subheader("Bollinger Band Position")

    bb = predictions.get("bollinger", {})
    if bb and not bb.get("error"):
        bb_col1, bb_col2, bb_col3, bb_col4 = st.columns(4)
        bb_col1.metric("Upper Band", f"₹{bb.get('upper', 0):.2f}")
        bb_col2.metric("Middle (SMA20)", f"₹{bb.get('middle', 0):.2f}")
        bb_col3.metric("Lower Band", f"₹{bb.get('lower', 0):.2f}")
        bb_col4.metric("%B Position", f"{bb.get('percent_b', 50):.0f}%")

        st.markdown(f"**Bandwidth:** {bb.get('bandwidth', 0):.1f}% | **Signal:** {bb.get('signal', 'NEUTRAL')}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: AGENT CONSENSUS
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Agent Consensus":
    st.title("Agent Consensus Heatmap")

    reports = get_latest_reports(limit=15)

    if not reports:
        st.warning("No data yet. Run the scanner first.")
        st.stop()

    # Build consensus matrix
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

        # Heatmap: agents vs tickers
        pivot = df.pivot_table(index="Agent", columns="Ticker", values="Score", aggfunc="mean")

        fig = px.imshow(
            pivot,
            labels=dict(x="Stock", y="Agent", color="Score"),
            aspect="auto",
            color_continuous_scale="RdYlGn",
            zmin=1, zmax=10,
        )
        fig.update_layout(height=max(400, len(pivot) * 25), title="Agent Scores by Stock")
        st.plotly_chart(fig, use_container_width=True)

        # Agreement table
        st.subheader("Consensus Summary")
        for report in reports:
            ticker = report["ticker"]
            ticker_analyses = [r for r in data_rows if r["Ticker"] == ticker]
            buy_pct = sum(1 for a in ticker_analyses if "BUY" in a["Verdict"]) / max(len(ticker_analyses), 1) * 100
            avg_score = sum(a["Score"] for a in ticker_analyses) / max(len(ticker_analyses), 1)
            st.markdown(
                f"**{ticker}**: {buy_pct:.0f}% bullish | "
                f"Avg score: {avg_score:.1f}/10 | "
                f"Verdict: {report.get('overall_verdict', 'N/A')}"
            )
    else:
        st.info("No agent analyses found yet.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SCAN HISTORY
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Scan History":
    st.title("Scan History")

    scans = get_latest_scan_results(limit=50)

    if not scans:
        st.warning("No scan history yet.")
        st.stop()

    df = pd.DataFrame(scans)
    df["scan_timestamp"] = pd.to_datetime(df["scan_timestamp"])

    st.dataframe(
        df[["ticker", "company_name", "sector", "composite_score", "current_price", "market_cap", "scan_timestamp"]]
        .sort_values("composite_score", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    # Score distribution
    fig = px.bar(
        df.sort_values("composite_score", ascending=True).tail(20),
        x="composite_score", y="ticker",
        orientation="h",
        title="Top 20 Composite Scores",
        color="composite_score",
        color_continuous_scale="RdYlGn",
    )
    fig.update_layout(height=600)
    st.plotly_chart(fig, use_container_width=True)
