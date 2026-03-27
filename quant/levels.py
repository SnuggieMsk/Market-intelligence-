"""
Support/resistance level calculations — pure math.
Fibonacci retracement, pivot points, moving average levels.
"""

import pandas as pd
from typing import Optional


def fibonacci_retracement(high: float, low: float) -> dict:
    """
    Fibonacci retracement levels between a high and low.
    Returns key levels as prices.
    """
    diff = high - low
    return {
        "high": round(high, 2),
        "low": round(low, 2),
        "fib_236": round(high - 0.236 * diff, 2),
        "fib_382": round(high - 0.382 * diff, 2),
        "fib_500": round(high - 0.500 * diff, 2),
        "fib_618": round(high - 0.618 * diff, 2),
        "fib_786": round(high - 0.786 * diff, 2),
    }


def pivot_points(high: float, low: float, close: float) -> dict:
    """
    Standard pivot point calculations.
    Returns pivot, 3 resistance levels, and 3 support levels.
    """
    pivot = (high + low + close) / 3
    return {
        "pivot": round(pivot, 2),
        "r1": round(2 * pivot - low, 2),
        "r2": round(pivot + (high - low), 2),
        "r3": round(high + 2 * (pivot - low), 2),
        "s1": round(2 * pivot - high, 2),
        "s2": round(pivot - (high - low), 2),
        "s3": round(low - 2 * (high - pivot), 2),
    }


def moving_average_levels(close: pd.Series) -> dict:
    """
    Key moving average levels as support/resistance.
    """
    result = {}
    for window in [20, 50, 100, 200]:
        if len(close) >= window:
            sma = close.rolling(window).mean().iloc[-1]
            ema = close.ewm(span=window).mean().iloc[-1]
            result[f"sma_{window}"] = round(float(sma), 2)
            result[f"ema_{window}"] = round(float(ema), 2)
    return result


def compute_support_resistance(hist: pd.DataFrame) -> dict:
    """
    Compute all support/resistance levels from historical data.
    Uses 52-week high/low for Fibonacci, yesterday's OHLC for pivots.
    """
    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]

    # 52-week high/low for Fibonacci
    high_52w = float(high.max())
    low_52w = float(low.min())

    # Yesterday's OHLC for pivot points
    prev_high = float(high.iloc[-1])
    prev_low = float(low.iloc[-1])
    prev_close = float(close.iloc[-1])

    return {
        "fibonacci": fibonacci_retracement(high_52w, low_52w),
        "pivot_points": pivot_points(prev_high, prev_low, prev_close),
        "moving_averages": moving_average_levels(close),
        "current_price": round(float(close.iloc[-1]), 2),
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
    }
