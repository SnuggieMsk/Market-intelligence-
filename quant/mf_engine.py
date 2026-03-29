"""
Mutual Fund Quantitative Engine.
Computes NAV-based performance metrics, risk ratios, and SIP/Lumpsum projections.
"""

import numpy as np
import pandas as pd
from datetime import datetime


def compute_mf_quant(ticker: str) -> dict:
    """
    Compute comprehensive quantitative metrics for a mutual fund.
    Returns dict with: performance, risk, sip_analysis, projections.
    """
    from scanner.universe import get_mf_scheme_code, get_mutual_fund_info
    from mftool import Mftool

    scheme_code = get_mf_scheme_code(ticker)
    mf_info = get_mutual_fund_info(ticker)
    mf = Mftool()

    # Get full NAV history
    df = mf.get_scheme_historical_nav(scheme_code, as_Dataframe=True)
    if df is None or df.empty:
        return {"error": f"No NAV data for {ticker}"}

    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df.index = pd.to_datetime(df.index, format="%d-%m-%Y")
    df = df.sort_index().dropna(subset=["nav"])

    nav = df["nav"]
    current_nav = float(nav.iloc[-1])
    latest_date = nav.index[-1]

    # ── Performance Metrics ──────────────────────────────────────────────
    performance = {}

    # Rolling returns
    for label, days in [("1M", 30), ("3M", 90), ("6M", 180), ("1Y", 365), ("3Y", 1095), ("5Y", 1825)]:
        cutoff = latest_date - pd.Timedelta(days=days)
        past = nav[nav.index <= cutoff]
        if len(past) > 0:
            start_nav = float(past.iloc[-1])
            if label in ("3Y", "5Y"):
                years = days / 365.25
                cagr = ((current_nav / start_nav) ** (1 / years) - 1) * 100
                performance[f"return_{label}"] = round(cagr, 2)
                performance[f"return_{label}_type"] = "CAGR"
            else:
                ret = ((current_nav / start_nav) - 1) * 100
                performance[f"return_{label}"] = round(ret, 2)
                performance[f"return_{label}_type"] = "absolute"
        else:
            performance[f"return_{label}"] = None

    performance["current_nav"] = current_nav
    performance["nav_date"] = latest_date.strftime("%Y-%m-%d")
    performance["data_points"] = len(nav)
    performance["history_years"] = round((latest_date - nav.index[0]).days / 365.25, 1)

    # ── Risk Metrics ─────────────────────────────────────────────────────
    risk = {}

    # Use last 1 year for risk metrics
    one_year = nav[nav.index >= latest_date - pd.Timedelta(days=365)]
    daily_returns = one_year.pct_change().dropna()

    if len(daily_returns) > 20:
        ann_factor = np.sqrt(252)

        # Standard deviation (annualized)
        risk["std_dev_annual"] = round(float(daily_returns.std() * ann_factor * 100), 2)

        # Sharpe Ratio (assuming 6% risk-free rate for India)
        rf_daily = 0.06 / 252
        excess = daily_returns - rf_daily
        sharpe = float(excess.mean() / daily_returns.std() * ann_factor) if daily_returns.std() > 0 else 0
        risk["sharpe_ratio"] = round(sharpe, 2)

        # Sortino Ratio (downside deviation only)
        downside = daily_returns[daily_returns < 0]
        if len(downside) > 5:
            downside_std = float(downside.std() * ann_factor)
            sortino = float(excess.mean() * 252 / (downside_std * 100) * 100) if downside_std > 0 else 0
            risk["sortino_ratio"] = round(sortino, 2)
        else:
            risk["sortino_ratio"] = None

        # Max Drawdown
        cumulative = (1 + daily_returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        risk["max_drawdown"] = round(float(drawdown.min() * 100), 2)

        # Best and worst days/months
        risk["best_day"] = round(float(daily_returns.max() * 100), 2)
        risk["worst_day"] = round(float(daily_returns.min() * 100), 2)

        # Monthly returns for worst month
        monthly = one_year.resample("M").last().pct_change().dropna()
        if len(monthly) > 0:
            risk["best_month"] = round(float(monthly.max() * 100), 2)
            risk["worst_month"] = round(float(monthly.min() * 100), 2)

        # Positive days ratio
        risk["positive_days_pct"] = round(float((daily_returns > 0).mean() * 100), 1)

        # Beta vs Nifty 50 (approximate using volatility ratio)
        risk["volatility_annual"] = risk["std_dev_annual"]

    # ── SIP Analysis ─────────────────────────────────────────────────────
    sip_analysis = {}

    # Simulate SIP of Rs.10,000/month over available periods
    for label, months in [("1Y", 12), ("3Y", 36), ("5Y", 60)]:
        cutoff = latest_date - pd.Timedelta(days=months * 30.44)
        period_nav = nav[nav.index >= cutoff]

        if len(period_nav) < months * 15:  # Need reasonable data
            sip_analysis[f"sip_{label}"] = None
            continue

        # Get monthly NAVs (first trading day of each month)
        monthly_nav = period_nav.resample("MS").first().dropna()
        if len(monthly_nav) < 3:
            sip_analysis[f"sip_{label}"] = None
            continue

        sip_amount = 10000
        total_units = 0
        total_invested = 0

        for nav_val in monthly_nav:
            units = sip_amount / float(nav_val)
            total_units += units
            total_invested += sip_amount

        current_value = total_units * current_nav
        total_return = ((current_value / total_invested) - 1) * 100

        # XIRR approximation
        years = len(monthly_nav) / 12
        if years > 0 and current_value > 0 and total_invested > 0:
            xirr_approx = ((current_value / total_invested) ** (1 / years) - 1) * 100 if years >= 1 else total_return
        else:
            xirr_approx = 0

        sip_analysis[f"sip_{label}"] = {
            "total_invested": round(total_invested),
            "current_value": round(current_value),
            "total_return_pct": round(total_return, 2),
            "xirr_approx": round(xirr_approx, 2),
            "units_accumulated": round(total_units, 4),
            "months": len(monthly_nav),
        }

    # Lumpsum comparison for same periods
    for label, days in [("1Y", 365), ("3Y", 1095), ("5Y", 1825)]:
        cutoff = latest_date - pd.Timedelta(days=days)
        past = nav[nav.index <= cutoff]
        if len(past) > 0:
            start_nav = float(past.iloc[-1])
            lumpsum_invested = 10000 * (days // 30)  # Same total as SIP
            units = lumpsum_invested / start_nav
            current_value = units * current_nav
            total_return = ((current_value / lumpsum_invested) - 1) * 100
            years = days / 365.25
            cagr = ((current_nav / start_nav) ** (1 / years) - 1) * 100 if years >= 1 else total_return

            sip_analysis[f"lumpsum_{label}"] = {
                "total_invested": round(lumpsum_invested),
                "current_value": round(current_value),
                "total_return_pct": round(total_return, 2),
                "cagr": round(cagr, 2),
            }
        else:
            sip_analysis[f"lumpsum_{label}"] = None

    # ── Future Projections (3 scenarios) ─────────────────────────────────
    projections = {}

    # Base projections on historical CAGR and agent score
    hist_1y = performance.get("return_1Y")
    hist_3y = performance.get("return_3Y")

    base_rate = hist_3y if hist_3y is not None else (hist_1y if hist_1y is not None else 10)

    for period_label, years in [("1Y", 1), ("3Y", 3), ("5Y", 5)]:
        scenarios = {}
        for scenario, multiplier in [("bull", 1.5), ("base", 1.0), ("bear", 0.3)]:
            rate = base_rate * multiplier
            projected_nav = current_nav * ((1 + rate / 100) ** years)

            # SIP projection
            monthly_sip = 10000
            total_sip_invested = monthly_sip * 12 * years
            # Approximate SIP with average NAV over the projection
            avg_nav = (current_nav + projected_nav) / 2
            sip_units = total_sip_invested / avg_nav
            sip_value = sip_units * projected_nav

            # Lumpsum projection (same total invested)
            lumpsum_units = total_sip_invested / current_nav
            lumpsum_value = lumpsum_units * projected_nav

            scenarios[scenario] = {
                "expected_return_pct": round(rate, 1),
                "projected_nav": round(projected_nav, 2),
                "sip_invested": total_sip_invested,
                "sip_value": round(sip_value),
                "sip_return_pct": round(((sip_value / total_sip_invested) - 1) * 100, 1),
                "lumpsum_invested": total_sip_invested,
                "lumpsum_value": round(lumpsum_value),
                "lumpsum_return_pct": round(((lumpsum_value / total_sip_invested) - 1) * 100, 1),
            }
        projections[period_label] = scenarios

    return {
        "ticker": ticker,
        "fund_name": mf_info.get("name", ticker),
        "category": mf_info.get("category", "Unknown"),
        "amc": mf_info.get("amc", "Unknown"),
        "performance": performance,
        "risk": risk,
        "sip_analysis": sip_analysis,
        "projections": projections,
        "computed_at": datetime.utcnow().isoformat(),
    }
