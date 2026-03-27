"""
Price prediction models — pure math, zero LLM calls.
Bollinger bands, Monte Carlo simulation, mean reversion targets.
"""

import numpy as np
import pandas as pd
from typing import Optional


def bollinger_bands(close: pd.Series, window: int = 20, num_std: float = 2.0) -> dict:
    """
    Bollinger Bands with current position indicator.
    Returns upper/middle/lower bands and %B (position within bands).
    """
    sma = close.rolling(window).mean().iloc[-1]
    std = close.rolling(window).std().iloc[-1]
    current = float(close.iloc[-1])

    upper = float(sma + num_std * std)
    lower = float(sma - num_std * std)
    middle = float(sma)

    bandwidth = ((upper - lower) / middle) * 100
    percent_b = ((current - lower) / (upper - lower)) * 100 if (upper - lower) > 0 else 50

    return {
        "upper": round(upper, 2),
        "middle": round(middle, 2),
        "lower": round(lower, 2),
        "bandwidth": round(bandwidth, 2),
        "percent_b": round(percent_b, 2),
        "current_price": round(current, 2),
        "signal": "OVERBOUGHT" if percent_b > 100 else "OVERSOLD" if percent_b < 0 else "NEUTRAL",
    }


def monte_carlo_simulation(
    close: pd.Series,
    days_forward: int = 30,
    n_simulations: int = 1000,
) -> dict:
    """
    Monte Carlo price simulation using geometric Brownian motion.
    Uses historical log returns to estimate drift and volatility.
    Returns percentile-based price forecasts.
    """
    # Calculate log returns
    log_returns = np.log(close / close.shift(1)).dropna()

    if len(log_returns) < 20:
        return {"error": "Insufficient data for simulation"}

    mu = float(log_returns.mean())  # Daily drift
    sigma = float(log_returns.std())  # Daily volatility
    current_price = float(close.iloc[-1])

    # Simulate paths
    np.random.seed(42)  # Reproducible
    simulations = np.zeros((n_simulations, days_forward))
    simulations[:, 0] = current_price

    for t in range(1, days_forward):
        random_shocks = np.random.normal(mu, sigma, n_simulations)
        simulations[:, t] = simulations[:, t-1] * np.exp(random_shocks)

    final_prices = simulations[:, -1]

    return {
        "current_price": round(current_price, 2),
        "days_forward": days_forward,
        "n_simulations": n_simulations,
        "median_price": round(float(np.median(final_prices)), 2),
        "mean_price": round(float(np.mean(final_prices)), 2),
        "p10": round(float(np.percentile(final_prices, 10)), 2),
        "p25": round(float(np.percentile(final_prices, 25)), 2),
        "p75": round(float(np.percentile(final_prices, 75)), 2),
        "p90": round(float(np.percentile(final_prices, 90)), 2),
        "expected_return": round(float((np.median(final_prices) / current_price - 1) * 100), 2),
        "prob_positive": round(float((final_prices > current_price).mean() * 100), 1),
        "prob_up_10pct": round(float((final_prices > current_price * 1.10).mean() * 100), 1),
        "prob_down_10pct": round(float((final_prices < current_price * 0.90).mean() * 100), 1),
        "max_simulated": round(float(final_prices.max()), 2),
        "min_simulated": round(float(final_prices.min()), 2),
        "daily_drift": round(mu * 100, 4),
        "daily_volatility": round(sigma * 100, 4),
        "annualized_volatility": round(sigma * np.sqrt(252) * 100, 2),
    }


def mean_reversion_target(close: pd.Series, window: int = 50) -> dict:
    """
    Mean reversion analysis: current price vs SMA, z-score, and reversion target.
    Estimates half-life of mean reversion using autocorrelation.
    """
    if len(close) < window:
        return {"error": "Insufficient data"}

    current = float(close.iloc[-1])
    sma = float(close.rolling(window).mean().iloc[-1])
    std = float(close.rolling(window).std().iloc[-1])

    # Z-score: how many std devs from the mean
    z_score = (current - sma) / std if std > 0 else 0

    # Half-life estimation via autocorrelation of price deviations
    deviations = close - close.rolling(window).mean()
    deviations = deviations.dropna()
    if len(deviations) > 10:
        autocorr = float(deviations.autocorr(lag=1))
        if 0 < autocorr < 1:
            half_life = -np.log(2) / np.log(autocorr)
        else:
            half_life = None
    else:
        half_life = None

    # Reversion probability based on z-score
    from scipy.stats import norm
    reversion_prob = norm.cdf(-abs(z_score)) * 2 * 100  # Two-tailed

    return {
        "current_price": round(current, 2),
        "sma": round(sma, 2),
        "z_score": round(z_score, 2),
        "target_price": round(sma, 2),  # Mean reversion target = SMA
        "deviation_pct": round(((current - sma) / sma) * 100, 2),
        "half_life_days": round(float(half_life), 1) if half_life else None,
        "reversion_probability": round(reversion_prob, 1),
        "signal": "OVERSOLD" if z_score < -2 else "OVERBOUGHT" if z_score > 2 else "FAIR",
        "band_upper_1std": round(sma + std, 2),
        "band_lower_1std": round(sma - std, 2),
        "band_upper_2std": round(sma + 2 * std, 2),
        "band_lower_2std": round(sma - 2 * std, 2),
    }


def compute_all_predictions(hist: pd.DataFrame) -> dict:
    """Run all prediction models. Returns combined dict."""
    close = hist["Close"]

    result = {}

    try:
        result["bollinger"] = bollinger_bands(close)
    except Exception as e:
        result["bollinger"] = {"error": str(e)}

    try:
        result["monte_carlo"] = monte_carlo_simulation(close)
    except Exception as e:
        result["monte_carlo"] = {"error": str(e)}

    try:
        result["mean_reversion"] = mean_reversion_target(close)
    except Exception as e:
        result["mean_reversion"] = {"error": str(e)}

    return result
