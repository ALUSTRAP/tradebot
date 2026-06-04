import os
import requests
from datetime import datetime, timedelta, timezone

# 1. Forex & Timeframe Configuration
FOREX_PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "AUDUSD=X", "USDCAD=X", "NZDUSD=X"]
TIMEFRAMES = ["15m", "30m", "1h"]

# 2. Stock & Volatility Indices Configuration
STOCK_INDICES = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq 100",
    "^DJI": "Dow Jones",
    "^FTSE": "FTSE 100 (UK)",
    "^GDAXI": "DAX 40 (GER)",
    "^N225": "Nikkei 225 (JPN)",
    "^STOXX50E": "Euro Stoxx 50",
    "^FCHI": "CAC 40 (FRA)",
    "^AXJO": "ASX 200 (AUS)"
}

VOLATILITY_INDICES = {
    "^VIX": "CBOE Volatility Index (VIX)",
    "^VXV": "3-Month Volatility Index"
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

def fetch_group_prices(symbols_dict, headers):
    lines = []
    symbols_string = ",".join(symbols_dict.keys())
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols_string}"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result_list = response.json().get("quoteResponse", {}).get("result", [])
            for item in result_list:
                symbol = item.get("symbol")
                friendly_name = symbols_dict.get(symbol, symbol)
                price = item.get("regularMarketPrice")
                change = item.get("regularMarketChangePercent", 0.0)
                if price is not None:
                    arrow = "🔺" if change >= 0 else "🔻"
                    lines.append(f"• {friendly_name}: `{price:,.2f}` ({arrow}{change:.2f}%)")
    except Exception as e:
        print(f"Error fetching group indices: {e}")
    return lines

def get_indices_snapshot(headers):
    stock_lines = fetch_group_prices(STOCK_INDICES, headers)
    vol_lines = fetch_group_prices(VOLATILITY_INDICES, headers)
    output = "📈 **Major Stock Indices**\n"
    output += "\n".join(stock_lines) if stock_lines else "⚠️ Stock indices temporarily offline."
    if vol_lines:
        output += "\n\n⚠️ **Volatility & Sentiment**\n" + "\n".join(vol_lines)
    return output

def get_macro_news():
    """Fetches global economic news events and determines what currencies are currently unsafe to trade."""
    unsafe_currencies = set()
    news_lines = []
    
    # Using an open-source unauthenticated financial calendar repository
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            events = response.json()
            now_utc = datetime.now(timezone.utc)
            today_str = now_utc.strftime("%Y-%m-%d")
            
            for event in events:
                event_date = event.get("date", "")[:10]  # Extracts YYYY-MM-DD
                impact = event.get("impact", "").lower() # high (Red), medium (Orange/Yellow)
                currency = event.get("country", "").upper()
                title = event.get("title", "Economic News")
                
                # We only track High (Red) and Medium (Yellow) events affecting our pairs
                if impact in ["high", "medium"] and event_date == today_str:
                    event_time_str = event.get("date", "")
                    # Convert to parsable datetime
                    try:
                        event_time = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))
                    except:
                        continue
                    
                    time_diff = abs((now_utc - event_time).total_seconds() / 60.0)
                    time_display = event_time.strftime("%H:%M UTC")
                    
                    if impact == "high":
                        icon = "🔴 HIGH"
                        # Red News Safety Rule: If within 30 mins before or after, lock out the currency
                        if time_diff <= 30:
                            unsafe_currencies.add(currency)
                    else:
                        icon = "🟡 MED"
                        
                    news_lines.append(f"• [{icon}] `{currency}` - {title} ({time_display})")
                    
    except Exception as e:
        print(f"Error checking calendar: {e}")
        
    news_block = "🗓️ **Today's Macro News (Red & Yellow)**\n"
    if news_lines:
        news_block += "\n".join(news_lines[:12])  # Display up to 12 events to avoid cluttered layouts
    else:
        news_block += "• No high/medium impact events scheduled for today."
        
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
            base_curr = clean_name[:3]  # e.g. EUR
            quote_curr = clean_name[3:] # e.g. USD
            
            # AUTOMATIC SAFETY CHECK
            if base_curr in unsafe_currencies or quote_curr in unsafe_currencies:
                # If checking quietly, skip scanning this pair due to active Red News proximity
                print(f"Skipping {clean_name} due to active high-impact Red News.")
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
        alerts.append(f"\n⚠️ *Note: Certain pairs skipped scanning due to active 🔴 Red News status.*")
        
    return "🚨 **STRATEGY ALERTS TRIGGERED** 🚨\n" + "\n".join(alerts)

def run_pipeline():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    
    news_data, unsafe_currencies = get_macro_news()
    indices_data = get_indices_snapshot(headers)
    forex_data = analyze_forex(headers, unsafe_currencies)
    
    final_report = (
        "📊 **Live Market Dashboard** 📊\n"
        "-------------------------\n"
        f"{news_data}\n"
        "-------------------------\n"
        f"{indices_data}\n"
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
