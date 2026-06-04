import os
import requests
from datetime import datetime, timezone

# 1. Configuration
FOREX_PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "AUDUSD=X", "USDCAD=X", "NZDUSD=X"]
TIMEFRAMES = ["15m", "30m", "1h"]

FUTURES_INDICES = {
    "ES=F": "S&P 500 Futures",
    "NQ=F": "Nasdaq 100 Futures",
    "YM=F": "Dow Jones Futures",
    "RTY=F": "Russell 2000 Fut",
    "CBOE Volatility (VIX)": "^VIX"
}

def calculate_ema(prices, period):
    if len(prices) < period:
        return [0.0] * len(prices)
    ema = []
    k = 2 / (period + 1)
    sma = sum(prices[:period]) / period
    ema.append(sma)
    for price in prices[period:]:
        next_ema = (price * k) + (ema[-1] * (1 - k))
        ema.append(next_ema)
    return [0.0] * (period - 1) + ema

def calculate_rsi(prices, period=10):
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))

def scan_hybrid_poi_and_ema(opens, highs, lows, closes, clean_name, timeframe):
    """
    Executes BOTH the 9/12 EMA trend strategy and the advanced 
    Institutional POI (Order Block, Breaker, Reclaimed) strategy simultaneously.
    """
    signals = []
    if len(closes) < 25:
        return signals
        
    # ==========================================
    # STRATEGY 1: 9/12 EMA TREND CONTINUATION
    # ==========================================
    ema9 = calculate_ema(closes, 9)
    ema12 = calculate_ema(closes, 12)
    rsi10 = calculate_rsi(closes, period=10)
    
    ema_crossed_up = (ema9[-1] > ema12[-1] and ema9[-2] <= ema12[-2])
    ema_crossed_down = (ema9[-1] < ema12[-1] and ema9[-2] >= ema12[-2])
    
    if ema_crossed_up:
        signals.append(f"🟢 **MOMENTUM ALERT: BUY** • `{clean_name}` ({timeframe}) `[9/12 EMA Cross]` | Price: `{closes[-1]:.4f}` | RSI: `{rsi10:.1f}`")
    elif ema_crossed_down and rsi10 > 30:
        signals.append(f"🔴 **MOMENTUM ALERT: SELL** • `{clean_name}` ({timeframe}) `[9/12 EMA Cross]` | Price: `{closes[-1]:.4f}` | RSI: `{rsi10:.1f}`")

    # ==========================================
    # STRATEGY 2: INSTITUTIONAL POI ENGINE
    # ==========================================
    # Look back at historical structural footprints to identify zones
    for idx in range(-8, -3):
        op, hi, lo, cl = opens[idx], highs[idx], lows[idx], closes[idx]
        is_bearish_candle = cl < op
        is_bullish_candle = cl > op
        
        # Current confirmation candle metrics
        curr_op, curr_hi, curr_lo, curr_cl = opens[-1], highs[-1], lows[-1], closes[-1]
        curr_body = abs(curr_cl - curr_op)
        
        # 🟢 BULLISH POI HUNTS
        if is_bearish_candle:
            ob_top = max(op, cl)
            ob_bottom = lo
            
            # Standard Order Block Confirmation
            if min(closes[idx+1:-1]) > ob_bottom and curr_lo <= ob_top and curr_cl >= ob_bottom:
                is_engulfing = curr_cl > curr_op and curr_cl > closes[-2]
                is_hammer = (min(curr_op, curr_cl) - curr_lo) > (curr_body * 1.5)
                
                if is_engulfing or is_hammer:
                    confirmation_type = "Bullish Engulfing" if is_engulfing else "Hammer Rejection"
                    signals.append(
                        f"🎯 **POI ALERT: STANDARD ORDER BLOCK (BUY)** • `{clean_name}` ({timeframe})\n"
                        f"  • **Zone (Demand):** `{ob_bottom:.4f}` - `{ob_top:.4f}`\n"
                        f"  • **Confirmation:** `{confirmation_type}` formed inside POI.\n"
                        f"  • **Risk Setup:** Stop Loss below `{ob_bottom:.4f}`"
                    )

            # Breaker Block Confirmation
            elif max(closes[idx+1:-1]) > ob_top and curr_lo <= ob_top and curr_cl >= ob_bottom:
                is_engulfing = curr_cl > curr_op and curr_cl > closes[-2]
                is_hammer = (min(curr_op, curr_cl) - curr_lo) > (curr_body * 1.5)
                
                if is_engulfing or is_hammer:
                    confirmation_type = "Bullish Engulfing" if is_engulfing else "Hammer Rejection"
                    signals.append(
                        f"⚡ **POI ALERT: BULLISH BREAKER BLOCK (BUY)** • `{clean_name}` ({timeframe})\n"
                        f"  • **Zone (Flipped Resistance):** `{ob_bottom:.4f}` - `{ob_top:.4f}`\n"
                        f"  • **Confirmation:** `{confirmation_type}` confirming structural support flip."
                    )

        # 🔴 BEARISH POI HUNTS
        if is_bullish_candle:
            ob_top = hi
            ob_bottom = min(op, cl)
            
            # Standard Bearish Order Block Confirmation
            if max(closes[idx+1:-1]) < ob_top and curr_hi >= ob_bottom and curr_cl <= ob_top:
                is_bearish_engulfing = curr_cl < curr_op and curr_cl < closes[-2]
                is_shooting_star = (curr_hi - max(curr_op, curr_cl)) > (curr_body * 1.5)
                
                if is_bearish_engulfing or is_shooting_star:
                    confirmation_type = "Bearish Engulfing" if is_bearish_engulfing else "Shooting Star Rejection"
                    signals.append(
                        f"🚨 **POI ALERT: BEARISH ORDER BLOCK (SELL)** • `{clean_name}` ({timeframe})\n"
                        f"  • **Zone (Supply):** `{ob_bottom:.4f}` - `{ob_top:.4f}`\n"
                        f"  • **Confirmation:** `{confirmation_type}` verified inside POI."
                    )
                    
            # Bearish Breaker Block Confirmation
            elif min(closes[idx+1:-1]) < ob_bottom and curr_hi >= ob_bottom and curr_cl <= ob_top:
                is_bearish_engulfing = curr_cl < curr_op and curr_cl < closes[-2]
                is_shooting_star = (curr_hi - max(curr_op, curr_cl)) > (curr_body * 1.5)
                
                if is_bearish_engulfing or is_shooting_star:
                    confirmation_type = "Bearish Engulfing" if is_bearish_engulfing else "Shooting Star Rejection"
                    signals.append(
                        f"🩸 **POI ALERT: BEARISH BREAKER BLOCK (SELL)** • `{clean_name}` ({timeframe})\n"
                        f"  • **Zone (Flipped Support):** `{ob_bottom:.4f}` - `{ob_top:.4f}`\n"
                        f"  • **Confirmation:** `{confirmation_type}` tracking institutional supply."
                    )

    # Reclaimed Block Tracking
    if len(closes) >= 12:
        if closes[-1] > highs[-3] and closes[-3] < lows[-6] and closes[-6] > highs[-9]:
            signals.append(
                f"👑 **POI ALERT: RECLAIMED ORDER BLOCK (BUY)** • `{clean_name}` ({timeframe})\n"
                f"  • **Status:** Market closed back over reclaimed smart money parameters. Momentum active."
            )

    return signals

def get_futures_snapshot_safe(headers):
    lines = []
    for symbol, friendly_name in FUTURES_INDICES.items():
        sym = friendly_name if friendly_name == "^VIX" else symbol
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2d&interval=1m"
        try:
            res = requests.get(url, headers=headers).json()
            chart_data = res.get("chart", {}).get("result", [None])[0]
            if not chart_data:
                continue
            meta = chart_data.get("meta", {})
            current_price = meta.get("regularMarketPrice")
            prev_close = meta.get("previousClose")
            
            if current_price is not None and prev_close is not None:
                change_pct = ((current_price - prev_close) / prev_close) * 100
                arrow = "🔺" if change_pct >= 0 else "🔻"
                lines.append(f"• {friendly_name if friendly_name != '^VIX' else symbol}: `{current_price:,.2f}` ({arrow}{change_pct:.2f}%)")
        except:
            pass
    output = "📊 **Live Global Futures Markets**\n"
    return output + ("\n".join(lines) if lines else "⚠️ Futures data feed temporarily lagging.")

def get_macro_news():
    unsafe_currencies = set()
    news_lines = []
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            events = response.json()
            now_utc = datetime.now(timezone.utc)
            today_str = now_utc.strftime("%Y-%m-%d")
            
            for event in events:
                event_date = event.get("date", "")[:10]
                impact = event.get("impact", "").lower()
                currency = event.get("country", "").upper()
                title = event.get("title", "Economic News")
                
                if impact in ["high", "medium"] and event_date == today_str:
                    event_time_str = event.get("date", "")
                    try:
                        event_time = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))
                    except:
                        continue
                    time_diff = abs((now_utc - event_time).total_seconds() / 60.0)
                    time_display = event_time.strftime("%H:%M UTC")
                    
                    if impact == "high":
                        icon = "🔴 HIGH"
                        if time_diff <= 30:
                            unsafe_currencies.add(currency)
                    else:
                        icon = "🟡 MED"
                    news_lines.append(f"• [{icon}] `{currency}` - {title} ({time_display})")
    except:
        pass
    news_block = "🗓️ **Today's Macro News (Red & Yellow)**\n"
    return news_block + ("\n".join(news_lines[:12]) if news_lines else "• No major macro impacts scheduled for today."), unsafe_currencies

def analyze_forex(headers, unsafe_currencies):
    master_alerts = []
    
    for timeframe in TIMEFRAMES:
        range_param = "5d" if timeframe == "15m" else ("7d" if timeframe == "30m" else "14d")
        
        for pair in FOREX_PAIRS:
            clean_name = pair.replace("=X", "")
            if clean_name[:3] in unsafe_currencies or clean_name[3:] in unsafe_currencies:
                continue
                
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{pair}?range={range_param}&interval={timeframe}"
            try:
                res = requests.get(url, headers=headers).json()
                candles = res.get("chart", {}).get("result", [None])[0]
                if not candles:
                    continue
                    
                quotes = candles.get("indicators", {}).get("quote", [{}])[0]
                opens = [o for o in quotes.get("open", []) if o is not None]
                highs = [h for h in quotes.get("high", []) if h is not None]
                lows = [l for l in quotes.get("low", []) if l is not None]
                closes = [c for c in quotes.get("close", []) if c is not None]
                
                pair_signals = scan_hybrid_poi_and_ema(opens, highs, lows, closes, clean_name, timeframe)
                master_alerts.extend(pair_signals)
                            
            except Exception as e:
                print(f"Error scanning {clean_name}: {e}")
                
    if not master_alerts:
        return "🔍 **Hybrid Strategy Scan:** No fresh EMA crosses or verified blocks found."
    if unsafe_currencies:
        master_alerts.append(f"\n⚠️ *Note: High impact news active. Certain pairs bypassed safely.*")
    return "🚨 **HYBRID STRATEGY ALERTS** 🚨\n\n" + "\n\n---\n\n".join(master_alerts)

def run_pipeline():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    news_data, unsafe_currencies = get_macro_news()
    futures_data = get_futures_snapshot_safe(headers)
    forex_data = analyze_forex(headers, unsafe_currencies)
    
    return (
        "📊 **Live Market Dashboard** 📊\n"
        "-------------------------\n"
        f"{news_data}\n"
        "-------------------------\n"
        f"{futures_data}\n"
        "-------------------------\n"
        f"{forex_data}\n"
        "-------------------------\n"
        "⏰ *Autopilot active via GitHub*"
    )

def send_telegram_alert(text_message):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text_message, "parse_mode": "Markdown"})

if __name__ == "__main__":
    send_telegram_alert(run_pipeline())
