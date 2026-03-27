"""
Fair value estimation models — pure math, zero LLM calls.
Graham Number, simplified DCF, PEG-based valuation.
"""

import math
from typing import Optional


def graham_number(eps: float, book_value_per_share: float) -> Optional[float]:
    """
    Graham Number = sqrt(22.5 * EPS * Book Value Per Share)
    Returns intrinsic value per share, or None if inputs are invalid.
    """
    if not eps or not book_value_per_share or eps <= 0 or book_value_per_share <= 0:
        return None
    return math.sqrt(22.5 * eps * book_value_per_share)


def simplified_dcf(
    fcf: float,
    growth_rate: float = 0.10,
    discount_rate: float = 0.10,
    terminal_growth: float = 0.03,
    shares_outstanding: float = 1,
    projection_years: int = 5,
) -> Optional[float]:
    """
    Simplified DCF: projects free cash flow, discounts back.
    Returns per-share intrinsic value, or None if inputs invalid.
    """
    if not fcf or fcf <= 0 or not shares_outstanding or shares_outstanding <= 0:
        return None
    if discount_rate <= terminal_growth:
        return None  # Invalid — would produce infinite value

    total_pv = 0
    projected_fcf = fcf

    # Project cash flows for each year
    for year in range(1, projection_years + 1):
        projected_fcf *= (1 + growth_rate)
        pv = projected_fcf / ((1 + discount_rate) ** year)
        total_pv += pv

    # Terminal value (Gordon Growth Model)
    terminal_fcf = projected_fcf * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    terminal_pv = terminal_value / ((1 + discount_rate) ** projection_years)
    total_pv += terminal_pv

    return total_pv / shares_outstanding


def peg_fair_value(eps: float, earnings_growth_rate: float, target_peg: float = 1.0) -> Optional[float]:
    """
    PEG-based fair value: Fair P/E = Growth Rate (when PEG=1).
    Returns fair price per share, or None if inputs invalid.
    """
    if not eps or eps <= 0 or not earnings_growth_rate or earnings_growth_rate <= 0:
        return None
    # Growth rate as percentage (e.g. 15 for 15%)
    growth_pct = earnings_growth_rate * 100 if earnings_growth_rate < 1 else earnings_growth_rate
    fair_pe = growth_pct * target_peg
    return eps * fair_pe


def compute_all_valuations(current_price: float, info: dict) -> dict:
    """
    Compute all valuation models. Returns dict with fair values and upside %.
    Handles missing data gracefully — skips models that lack inputs.
    """
    result = {
        "current_price": current_price,
        "graham_number": None,
        "dcf_value": None,
        "peg_value": None,
        "upside_graham": None,
        "upside_dcf": None,
        "upside_peg": None,
        "composite_fair_value": None,
        "composite_upside": None,
    }

    eps = info.get("trailingEps") or info.get("forwardEps")
    bvps = info.get("bookValue")
    fcf = info.get("freeCashflow")
    shares = info.get("sharesOutstanding")
    earnings_growth = info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")
    revenue_growth = info.get("revenueGrowth")

    # Graham Number
    gn = graham_number(eps, bvps)
    if gn:
        result["graham_number"] = round(gn, 2)
        result["upside_graham"] = round(((gn - current_price) / current_price) * 100, 1)

    # DCF
    growth = earnings_growth or revenue_growth or 0.10
    if growth < 0:
        growth = 0.05  # Use conservative growth for declining companies
    dcf = simplified_dcf(fcf, growth_rate=min(growth, 0.25), shares_outstanding=shares)
    if dcf:
        result["dcf_value"] = round(dcf, 2)
        result["upside_dcf"] = round(((dcf - current_price) / current_price) * 100, 1)

    # PEG
    peg = peg_fair_value(eps, earnings_growth if earnings_growth and earnings_growth > 0 else 0.10)
    if peg:
        result["peg_value"] = round(peg, 2)
        result["upside_peg"] = round(((peg - current_price) / current_price) * 100, 1)

    # Composite (average of available models)
    fair_values = [v for v in [gn, dcf, peg] if v is not None]
    if fair_values:
        composite = sum(fair_values) / len(fair_values)
        result["composite_fair_value"] = round(composite, 2)
        result["composite_upside"] = round(((composite - current_price) / current_price) * 100, 1)

    return result
