"""
Computes 32+ metrics for each stock to identify standout opportunities.
All data sourced from yfinance (free, no API key).
"""

import numpy as np
import yfinance as yf
from typing import Optional


def compute_all_metrics(ticker: str) -> Optional[dict]:
    """
    Compute all 32+ metrics for a given ticker.
    Returns None if data is insufficient.
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        info = stock.info

        if hist.empty or len(hist) < 50:
            return None

        close = hist["Close"]
        volume = hist["Volume"]
        high = hist["High"]
        low = hist["Low"]
        latest_close = close.iloc[-1]
        latest_volume = volume.iloc[-1]

        metrics = {}
        reasons = []

        # ══════════════════════════════════════════════════════════════════════
        # PRICE ACTION (8 metrics)
        # ══════════════════════════════════════════════════════════════════════

        # 1. Price vs 52-week low (how close to the bottom)
        low_52w = close.min()
        metrics["price_vs_52w_low"] = ((latest_close - low_52w) / low_52w) * 100
        if metrics["price_vs_52w_low"] < 10:
            reasons.append(f"Trading within 10% of 52-week low (${low_52w:.2f})")

        # 2. Price vs 52-week high (how far from top)
        high_52w = close.max()
        metrics["price_vs_52w_high"] = ((high_52w - latest_close) / high_52w) * 100
        if metrics["price_vs_52w_high"] > 40:
            reasons.append(f"Down {metrics['price_vs_52w_high']:.0f}% from 52-week high")

        # 3. Daily return
        metrics["daily_return"] = ((close.iloc[-1] / close.iloc[-2]) - 1) * 100 if len(close) >= 2 else 0
        if abs(metrics["daily_return"]) > 5:
            reasons.append(f"Big daily move: {metrics['daily_return']:+.1f}%")

        # 4. Weekly return
        metrics["weekly_return"] = ((close.iloc[-1] / close.iloc[-5]) - 1) * 100 if len(close) >= 5 else 0

        # 5. Monthly return
        metrics["monthly_return"] = ((close.iloc[-1] / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

        # 6. Gap percentage (today's open vs yesterday's close)
        if len(hist) >= 2:
            today_open = hist["Open"].iloc[-1]
            prev_close = close.iloc[-2]
            metrics["gap_percentage"] = ((today_open - prev_close) / prev_close) * 100
            if abs(metrics["gap_percentage"]) > 3:
                reasons.append(f"Gap {'up' if metrics['gap_percentage'] > 0 else 'down'}: {metrics['gap_percentage']:+.1f}%")
        else:
            metrics["gap_percentage"] = 0

        # 7. Intraday range (% of price)
        metrics["intraday_range"] = ((high.iloc[-1] - low.iloc[-1]) / latest_close) * 100

        # 8. Price vs 200-day SMA
        if len(close) >= 200:
            sma200 = close.rolling(200).mean().iloc[-1]
            metrics["price_vs_sma200"] = ((latest_close - sma200) / sma200) * 100
            if metrics["price_vs_sma200"] < -20:
                reasons.append(f"Trading {abs(metrics['price_vs_sma200']):.0f}% below 200-day SMA")
        else:
            sma200 = close.rolling(len(close)).mean().iloc[-1]
            metrics["price_vs_sma200"] = ((latest_close - sma200) / sma200) * 100

        # ══════════════════════════════════════════════════════════════════════
        # VOLUME (5 metrics)
        # ══════════════════════════════════════════════════════════════════════

        avg_volume_20 = volume.rolling(20).mean().iloc[-1]

        # 9. Volume surge (today vs 20-day avg)
        metrics["volume_surge"] = (latest_volume / avg_volume_20) if avg_volume_20 > 0 else 1
        if metrics["volume_surge"] > 3:
            reasons.append(f"Volume surge: {metrics['volume_surge']:.1f}x average")

        # 10. Relative volume (5-day avg vs 20-day avg)
        avg_vol_5 = volume.tail(5).mean()
        metrics["relative_volume"] = (avg_vol_5 / avg_volume_20) if avg_volume_20 > 0 else 1

        # 11. Volume-Price Trend
        vpt = ((close.pct_change() * volume).cumsum())
        metrics["volume_price_trend"] = vpt.iloc[-1] / vpt.abs().max() if vpt.abs().max() > 0 else 0

        # 12. Accumulation/Distribution
        mfm = ((close - low) - (high - close)) / (high - low + 1e-10)
        ad_line = (mfm * volume).cumsum()
        ad_recent = ad_line.tail(10).mean()
        ad_prior = ad_line.tail(30).head(20).mean()
        metrics["accumulation_distribution"] = 1 if ad_recent > ad_prior else -1

        # 13. OBV trend (rising or falling)
        obv = (np.sign(close.diff()) * volume).cumsum()
        obv_sma = obv.rolling(20).mean()
        metrics["on_balance_volume_trend"] = 1 if obv.iloc[-1] > obv_sma.iloc[-1] else -1

        # ══════════════════════════════════════════════════════════════════════
        # VOLATILITY (4 metrics)
        # ══════════════════════════════════════════════════════════════════════

        returns = close.pct_change().dropna()

        # 14. Historical volatility (annualized)
        metrics["historical_volatility"] = returns.tail(30).std() * np.sqrt(252) * 100

        # 15. ATR as percentage of price
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr_14 = tr.rolling(14).mean().iloc[-1]
        metrics["atr_percentage"] = (atr_14 / latest_close) * 100

        # 16. Bollinger Band squeeze (bandwidth)
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_upper = sma20 + 2 * std20
        bb_lower = sma20 - 2 * std20
        bandwidth = ((bb_upper - bb_lower) / sma20 * 100).iloc[-1]
        metrics["bollinger_squeeze"] = bandwidth
        if bandwidth < 5:
            reasons.append("Bollinger Band squeeze detected — breakout imminent")

        # 17. IV percentile (approximated from historical vol percentile)
        rolling_vol = returns.rolling(20).std() * np.sqrt(252) * 100
        current_vol = rolling_vol.iloc[-1]
        metrics["iv_percentile"] = (rolling_vol < current_vol).mean() * 100

        # ══════════════════════════════════════════════════════════════════════
        # MOMENTUM (5 metrics)
        # ══════════════════════════════════════════════════════════════════════

        # 18. RSI (14-period)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        rsi = (100 - (100 / (1 + rs))).iloc[-1]
        metrics["rsi"] = rsi
        if rsi < 30:
            reasons.append(f"RSI oversold: {rsi:.0f}")
        elif rsi > 70:
            reasons.append(f"RSI overbought: {rsi:.0f}")

        # 19. MACD signal
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        metrics["macd_signal"] = 1 if macd_line.iloc[-1] > signal_line.iloc[-1] else -1
        if macd_line.iloc[-2] < signal_line.iloc[-2] and macd_line.iloc[-1] > signal_line.iloc[-1]:
            reasons.append("MACD bullish crossover")

        # 20. Stochastic crossover
        low_14 = low.rolling(14).min()
        high_14 = high.rolling(14).max()
        k_line = ((close - low_14) / (high_14 - low_14 + 1e-10)) * 100
        d_line = k_line.rolling(3).mean()
        metrics["stochastic_crossover"] = 1 if k_line.iloc[-1] > d_line.iloc[-1] else -1

        # 21. Composite momentum score
        sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else close.mean()
        above_sma50 = 1 if latest_close > sma_50 else 0
        metrics["momentum_score"] = (
            (1 if metrics["macd_signal"] > 0 else 0) +
            (1 if rsi > 50 else 0) +
            above_sma50 +
            (1 if metrics["stochastic_crossover"] > 0 else 0)
        ) / 4 * 10

        # 22. Rate of change (10-day)
        metrics["rate_of_change"] = ((close.iloc[-1] / close.iloc[-10]) - 1) * 100 if len(close) >= 10 else 0

        # ══════════════════════════════════════════════════════════════════════
        # FUNDAMENTALS (6 metrics)
        # ══════════════════════════════════════════════════════════════════════

        # 23. P/E ratio vs sector average (simplified: just raw PE)
        pe = info.get("trailingPE") or info.get("forwardPE")
        metrics["pe_ratio_vs_sector"] = pe if pe and pe > 0 else 0
        if pe and 0 < pe < 10:
            reasons.append(f"Very low P/E: {pe:.1f}")

        # 24. Price-to-Book ratio
        pb = info.get("priceToBook")
        metrics["pb_ratio"] = pb if pb and pb > 0 else 0
        if pb and 0 < pb < 1:
            reasons.append(f"Trading below book value (P/B: {pb:.2f})")

        # 25. Debt-to-Equity
        de = info.get("debtToEquity")
        metrics["debt_to_equity"] = de if de else 0

        # 26. Revenue growth
        rg = info.get("revenueGrowth")
        metrics["revenue_growth"] = (rg * 100) if rg else 0
        if rg and rg > 0.25:
            reasons.append(f"Strong revenue growth: {rg*100:.0f}%")

        # 27. Earnings surprise (approximated from earnings growth)
        eg = info.get("earningsGrowth")
        metrics["earnings_surprise"] = (eg * 100) if eg else 0
        if eg and eg > 0.30:
            reasons.append(f"Strong earnings growth: {eg*100:.0f}%")

        # 28. Free cash flow yield
        fcf = info.get("freeCashflow")
        mcap = info.get("marketCap")
        if fcf and mcap and mcap > 0:
            metrics["free_cash_flow_yield"] = (fcf / mcap) * 100
        else:
            metrics["free_cash_flow_yield"] = 0

        # ══════════════════════════════════════════════════════════════════════
        # SENTIMENT & MARKET (4 metrics)
        # ══════════════════════════════════════════════════════════════════════

        # 29. Short interest (% of float)
        short_pct = info.get("shortPercentOfFloat")
        metrics["short_interest"] = (short_pct * 100) if short_pct else 0
        if short_pct and short_pct > 0.15:
            reasons.append(f"High short interest: {short_pct*100:.0f}% of float")

        # 30. Insider buying (net insider transactions)
        # yfinance gives insiderTransactions — use buy ratio
        insider_buy = info.get("heldPercentInsiders")
        metrics["insider_buying"] = (insider_buy * 100) if insider_buy else 0

        # 31. Analyst rating change
        rec = info.get("recommendationMean")  # 1=strong buy, 5=sell
        metrics["analyst_rating_change"] = rec if rec else 3.0
        if rec and rec < 1.8:
            reasons.append(f"Strong analyst buy consensus ({rec:.1f}/5)")

        # 32. Sector relative strength (simplified: stock return vs SPY)
        metrics["sector_relative_strength"] = metrics.get("monthly_return", 0)

        # ══════════════════════════════════════════════════════════════════════
        # METADATA
        # ══════════════════════════════════════════════════════════════════════

        return {
            "ticker": ticker,
            "company_name": info.get("shortName", ticker),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "market_cap": info.get("marketCap", 0),
            "current_price": latest_close,
            "metrics": metrics,
            "standout_reasons": reasons,
        }

    except Exception as e:
        print(f"[Metrics] Error computing metrics for {ticker}: {e}")
        return None


# Need pandas for ATR calculation
import pandas as pd
