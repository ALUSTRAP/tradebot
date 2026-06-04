import os
import requests

# List of currency pairs to scan
PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "AUDUSD=X", "USDCAD=X", "NZDUSD=X"]
TIMEFRAMES = ["30m", "1h"]

def calculate_ema(prices, period):
    """Calculates Exponential Moving Average."""
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
    """Calculates Relative Strength Index (RSI)."""
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

def calculate_macd(prices):
    """Calculates MACD Line and Signal Line arrays."""
    ema12 = calculate_ema(prices, 12)
    ema26 = calculate_ema(prices, 26)
    macd_line = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    signal_line = [0.0] * 26 + calculate_ema(macd_line[26:], 9)
    return macd_line, signal_line

def analyze_market():
    alerts = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for timeframe in TIMEFRAMES:
        # Request appropriate history range depending on timeframe data density
        range_param = "7d" if timeframe == "30m" else "14d"
        
        for pair in PAIRS:
            clean_name = pair.replace("=X", "")
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{pair}?range={range_param}&interval={timeframe}"
            
            try:
                res = requests.get(url, headers=headers).json()
                candles = res.get("chart", {}).get("result", [None])[0]
                if not candles:
                    continue
                    
                close_prices = candles.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                close_prices = [p for p in close_prices if p is not None]
                
                if len(close_prices) < 35:  # Ensure enough historical data bars are present
                    continue
                    
                current_price = close_prices[-1]
                
                # Tech Indicator Calculations
                ema9 = calculate_ema(close_prices, 9)
                ema12 = calculate_ema(close_prices, 12)
                rsi10 = calculate_rsi(close_prices, period=10)
                macd_line, signal_line = calculate_macd(close_prices)
                
                # Check Crossovers (Comparing current closed candle [-1] against previous candle [-2])
                ema_crossed_up = (ema9[-1] > ema12[-1] and ema9[-2] <= ema12[-2])
                ema_crossed_down = (ema9[-1] < ema12[-1] and ema9[-2] >= ema12[-2])
                
                macd_crossed_up = (macd_line[-1] > signal_line[-1] and macd_line[-2] <= signal_line[-2])
                macd_crossed_down = (macd_line[-1] < signal_line[-1] and macd_line[-2] >= signal_line[-2])
                
                # Bullish Alert Strategy Execution
                if ema_crossed_up and macd_crossed_up:
                    alerts.append(
                        f"🟢 **BUY SIGNAL** • `{clean_name}` ({timeframe})\n"
                        f"Price: `{current_price:.4f}`\n"
                        f"• EMA 9 crossed above EMA 12\n"
                        f"• MACD Bullish Cross Confirmed\n"
                        f"• RSI(10): `{rsi10:.1f}`"
                    )
                
                # Bearish Alert Strategy Execution
                elif ema_crossed_down and rsi10 > 30 and macd_crossed_down:
                    alerts.append(
                        f"🔴 **SELL SIGNAL** • `{clean_name}` ({timeframe})\n"
                        f"Price: `{current_price:.4f}`\n"
                        f"• EMA 9 crossed below EMA 12\n"
                        f"• MACD Bearish Cross Confirmed\n"
                        f"• RSI(10): `{rsi10:.1f}` (Not Oversold)"
                    )
                            
            except Exception as e:
                print(f"Error scanning {clean_name} on {timeframe}: {e}")
                
    if not alerts:
        return "🔍 **Market Scan Completed:** No matching cross confirmations found on the 30m or 1h charts."
    
    return "🚨 **STRATEGY ALERTS TRIGGERED** 🚨\n\n" + "\n\n---\n\n".join(alerts)

def send_telegram_alert(text_message):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text_message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

if __name__ == "__main__":
    report = analyze_market()
    send_telegram_alert(report)
    
