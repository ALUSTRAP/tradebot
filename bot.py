import os
import requests

# 1. Forex Configuration
FOREX_PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "AUDUSD=X", "USDCAD=X", "NZDUSD=X"]
TIMEFRAMES = ["15m", "30m", "1h"]

# 2. Stock & Volatility Indices Configuration (Fetched instantly on every run)
INDICES = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq 100",
    "^DJI": "Dow Jones",
    "^FTSE": "FTSE 100 (UK)",
    "^GDAXI": "DAX 40 (GER)",
    "^N225": "Nikkei 225 (JPN)",
    "^STOXX50E": "Euro Stoxx 50",
    "^FCHI": "CAC 40 (FRA)",
    "^AXJO": "ASX 200 (AUS)",
    "^VIX": "CBOE Volatility Index (VIX)",
    "^VXV": "3-Month Volatility Index"
}

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

def get_indices_snapshot(headers):
    """Fetches live current prices for Stock and Volatility Indices."""
    symbols_string = ",".join(INDICES.keys())
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols_string}"
    
    try:
        response = requests.get(url, headers=headers).json()
        result_list = response.get("quoteResponse", {}).get("result", [])
        
        stock_lines = []
        vol_lines = []
        
        for item in result_list:
            symbol = item.get("symbol")
            friendly_name = INDICES.get(symbol, symbol)
            price = item.get("regularMarketPrice", 0.0)
            change = item.get("regularMarketChangePercent", 0.0)
            
            # Format display with a directional arrow
            arrow = "🔺" if change >= 0 else "🔻"
            line = f"• {friendly_name}: `{price:,.2f}` ({arrow}{change:.2f}%)"
            
            if "Volatility" in friendly_name or symbol == "^VIX" or symbol == "^VXV":
                vol_lines.append(line)
            else:
                stock_lines.append(line)
                
        output = "📈 **Major Stock Indices**\n" + "\n".join(stock_lines)
        if vol_lines:
            output += "\n\n⚠️ **Volatility & Sentiment (Fear Gauges)**\n" + "\n".join(vol_lines)
        return output
    except Exception as e:
        return f"⚠️ Indices/Volatility Fetch Error: {str(e)}"

def analyze_forex(headers):
    """Scans Forex pairs for active 9/12 EMA crosses."""
    alerts = []
    for timeframe in TIMEFRAMES:
        if timeframe == "15m":
            range_param = "5d"
        elif timeframe == "30m":
            range_param = "7d"
        else:
            range_param = "14d"
        
        for pair in FOREX_PAIRS:
            clean_name = pair.replace("=X", "")
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{pair}?range={range_param}&interval={timeframe}"
            
            try:
                res = requests.get(url, headers=headers).json()
                candles = res.get("chart", {}).get("result", [None])[0]
                if not candles:
                    continue
                    
                close_prices = candles.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                close_prices = [p for p in close_prices if p is not None]
                
                if len(close_prices) < 20:
                    continue
                    
                current_price = close_prices[-1]
                ema9 = calculate_ema(close_prices, 9)
                ema12 = calculate_ema(close_prices, 12)
                rsi10 = calculate_rsi(close_prices, period=10)
                
                ema_crossed_up = (ema9[-1] > ema12[-1] and ema9[-2] <= ema12[-2])
                ema_crossed_down = (ema9[-1] < ema12[-1] and ema9[-2] >= ema12[-2])
                
                if ema_crossed_up:
                    alerts.append(f"🟢 **BUY** • `{clean_name}` ({timeframe}) | Price: `{current_price:.4f}` | RSI(10): `{rsi10:.1f}`")
                elif ema_crossed_down and rsi10 > 30:
                    alerts.append(f"🔴 **SELL** • `{clean_name}` ({timeframe}) | Price: `{current_price:.4f}` | RSI(10): `{rsi10:.1f}`")
                            
            except Exception as e:
                print(f"Error scanning {clean_name} on {timeframe}: {e}")
                
    if not alerts:
        return "🔍 **Forex Technical Scan:** No new 9/12 EMA crosses on 15m, 30m, or 1h setups."
    return "🚨 **STRATEGY ALERTS TRIGGERED** 🚨\n" + "\n".join(alerts)

def run_pipeline():
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # Run both parts of your script
    indices_data = get_indices_snapshot(headers)
    forex_data = analyze_forex(headers)
    
    final_report = (
        "📊 **Live Market Dashboard** 📊\n"
        "-------------------------\n"
        f"{indices_data}\n"
        "-------------------------\n"
        f"{forex_data}\n"
        "-------------------------\n"
        "⏰ *Checked automatically via GitHub*"
    )
    return final_report

def send_telegram_alert(text_message):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text_message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

if __name__ == "__main__":
    report = run_pipeline()
    send_telegram_alert(report)
