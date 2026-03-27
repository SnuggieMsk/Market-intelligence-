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
    get_agent_analyses_for_scan
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
    ["Overview", "Stock Deep Dive", "Agent Reports", "Agent Consensus", "Scan History"],
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
# PAGE: OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

if page == "Overview":
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
