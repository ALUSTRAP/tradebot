import os
import requests
from datetime import datetime, timedelta, timezone

# 1. Forex Configuration
FOREX_PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "AUDUSD=X", "USDCAD=X", "NZDUSD=X"]
TIMEFRAMES = ["15m", "30m", "1h"]

# 2. Liquid Futures (Using symbols that work seamlessly on the chart endpoint)
FUTURES_INDICES = {
    "ES=F": "S&P 500 Futures",
    "NQ=F": "Nasdaq 100 Futures",
    "YM=F": "Dow Jones Futures",
    "RTY=F": "Russell 2000 Fut",
    "NQ=M": "Micro Nasdaq Fut",
    "^VIX": "CBOE Volatility (VIX)"
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

def get_futures_snapshot_safe(headers):
    """Fetches futures data through the highly stable chart API endpoint to completely bypass summary blocks."""
    lines = []
    
    for symbol, friendly_name in FUTURES_INDICES.items():
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2d&interval=1m"
        try:
            res = requests.get(url, headers=headers).json()
            chart_data = res.get("chart", {}).get("result", [None])[0]
            if not chart_data:
                continue
                
            meta = chart_data.get("meta", {})
            current_price = meta.get("regularMarketPrice")
            prev_close = meta.get("previousClose")
            
            if current_price is not None and prev_close is not None:
                # Calculate percent change manually since the summary endpoint is blocked
                change_pct = ((current_price - prev_close) / prev_close) * 100
                arrow = "🔺" if change_pct >= 0 else "🔻"
                lines.append(f"• {friendly_name}: `{current_price:,.2f}` ({arrow}{change_pct:.2f}%)")
        except Exception as e:
            print(f"Error fetching chart data for {symbol}: {e}")
            
    output = "📊 **Live Global Futures Markets**\n"
    if lines:
        output += "\n".join(lines)
    else:
        output += "⚠️ Futures data feed temporarily lagging."
    return output

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
    except Exception as e:
        print(f"Error checking calendar: {e}")
        
    news_block = "🗓️ **Today's Macro News (Red & Yellow)**\n"
    if news_lines:
        news_block += "\n".join(news_lines[:12])
    else:
        news_block += "• No major macro impacts scheduled for today."
    return news_block, unsafe_currencies

def analyze_forex(headers, unsafe_currencies):
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
            base_curr = clean_name[:3]
            quote_curr = clean_name[3:]
            
            if base_curr in unsafe_currencies or quote_curr in unsafe_currencies:
                continue
                
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
        return "🔍 **Forex Technical Scan:** No new 9/12 EMA crosses found."
    if unsafe_currencies:
        alerts.append(f"\n⚠️ *Note: High impact news active. Certain currency pairs safely bypassed.*")
    return "🚨 **STRATEGY ALERTS TRIGGERED** 🚨\n" + "\n".join(alerts)

def run_pipeline():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    
    news_data, unsafe_currencies = get_macro_news()
    futures_data = get_futures_snapshot_safe(headers)
    forex_data = analyze_forex(headers, unsafe_currencies)
    
    final_report = (
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
