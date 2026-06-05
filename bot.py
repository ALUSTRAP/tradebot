import os
import json
import asyncio
import websockets
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

# ==========================================
# 1. CONFIGURATION & TOKENS
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STANDARD_PAIRS = [
    # Major Forex Pairs
    'EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'AUDUSD=X', 'USDCHF=X', 'USDCAD=X', 'NZDUSD=X',
    # Minor/Cross Forex Pairs
    'EURGBP=X', 'EURAUD=X', 'EURJPY=X', 'GBPJPY=X', 'AUDJPY=X', 'EURCAD=X', 'EURNZD=X', 
    'GBPAUD=X', 'GBPCAD=X', 'GBPNZD=X', 'AUDCAD=X', 'AUDNZD=X', 'NZDJPY=X', 'CADJPY=X', 'CHFJPY=X'
]

DERIV_PAIRS = [
    # Standard Volatility Indices
    'R_10', 'R_25', 'R_50', 'R_75', 'R_100', 'R_250',
    # 1s Volatility Indices
    '1HZ10V', '1HZ25V', '1HZ50V', '1HZ75V', '1HZ100V', '1HZ150V', '1HZ200V', '1HZ300V',
    # Jump Indices
    'JD10', 'JD25', 'JD50', 'JD75', 'JD100',
    # Step Indices
    'STP', 'STP200', 'STP300', 'STP400', 'STP500'
]

TIMEFRAMES = ['15m', '30m', '1h']

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

# ==========================================
# 2. DUAL-ROUTING DATA ENGINE
# ==========================================
async def fetch_deriv_candles(symbol, granularity):
    """Connects to Deriv WebSocket for Synthetic Index Data"""
    uri = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
    try:
        async with websockets.connect(uri) as websocket:
            request = {
                "ticks_history": symbol,
                "adjust_start_time": 1,
                "count": 100,
                "end": "latest",
                "granularity": granularity, 
                "style": "candles"
            }
            await websocket.send(json.dumps(request))
            response = await websocket.recv()
            data = json.loads(response)
            
            if 'candles' in data:
                df = pd.DataFrame(data['candles'])
                df['datetime'] = pd.to_datetime(df['epoch'], unit='s')
                df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
                for col in ['Open', 'High', 'Low', 'Close']:
                    df[col] = df[col].astype(float)
                return df
    except Exception as e:
        print(f"Deriv API Error for {symbol}: {e}")
    return None

def get_deriv_data(symbol, timeframe):
    tf_map = {'15m': 900, '30m': 1800, '1h': 3600}
    granularity = tf_map.get(timeframe, 900)
    return asyncio.run(fetch_deriv_candles(symbol, granularity))

def get_yahoo_data(symbol, timeframe):
    try:
        df = yf.download(symbol, interval=timeframe, period="5d", progress=False)
        if df.empty: return None
        df.reset_index(inplace=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        print(f"Yahoo Data Error for {symbol}: {e}")
        return None

# ==========================================
# 3. CORE STRATEGY ENGINES (EMA, POI, CANDLES)
# ==========================================
def calculate_indicators(df):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
    return df

def check_ema_cross(df):
    if len(df) < 2: return None
    prev_9, prev_12 = df['EMA_9'].iloc[-2], df['EMA_12'].iloc[-2]
    curr_9, curr_12 = df['EMA_9'].iloc[-1], df['EMA_12'].iloc[-1]
    
    if prev_9 <= prev_12 and curr_9 > curr_12: return "BUY"
    if prev_9 >= prev_12 and curr_9 < curr_12: return "SELL"
    return None

def scan_ict_poi_and_candles(df):
    if len(df) < 5: return None
    
    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]
    
    recent_high = df['High'].iloc[-5:-1].max()
    recent_low = df['Low'].iloc[-5:-1].min()
    
    body = abs(last_candle['Close'] - last_candle['Open'])
    candle_range = last_candle['High'] - last_candle['Low']
    if candle_range == 0: return None
    
    lower_wick = min(last_candle['Open'], last_candle['Close']) - last_candle['Low']
    upper_wick = last_candle['High'] - max(last_candle['Open'], last_candle['Close'])
    
    is_hammer = lower_wick > (2 * body) and upper_wick < (0.5 * body)
    is_engulfing = (last_candle['Close'] > prev_candle['Open']) and (last_candle['Open'] < prev_candle['Close']) if last_candle['Close'] > last_candle['Open'] else False

    if last_candle['Close'] <= recent_low * 1.001 and (is_hammer or is_engulfing):
        return "ICT BULLISH POI (Order Block Mitigation)"
    if last_candle['Close'] >= recent_high * 0.999 and (upper_wick > (2 * body)):
        return "ICT BEARISH POI (Mitigation/Breaker)"
        
    return None

# ==========================================
# 4. MACRO ECONOMIC NEWS ENGINE
# ==========================================
def get_macro_news():
    try:
        url = "https://newsapi.org/v2/top-headlines?category=business&language=en&pageSize=2"
        return "⚠️ High Volatility Alert: Check Economic Calendar for USD/GBP folders before entering positions."
    except:
        return "⚠️ Keep track of daily USD news folders before trading standard currency pairs."

# ==========================================
# 5. MAIN INTEGRATED ENGINE
# ==========================================
def main():
    alerts = []
    all_pairs = STANDARD_PAIRS + DERIV_PAIRS
    
    news_status = get_macro_news()
    
    for symbol in all_pairs:
        for tf in TIMEFRAMES:
            
            if symbol in DERIV_PAIRS:
                df = get_deriv_data(symbol, tf)
            else:
                df = get_yahoo_data(symbol, tf)
                
            if df is None or df.empty or len(df) < 20:
                continue
                
            df = calculate_indicators(df)
            
            momentum_signal = check_ema_cross(df)
            poi_signal = scan_ict_poi_and_candles(df)
            
            clean_symbol = symbol.replace('=X', '')
            current_price = round(df['Close'].iloc[-1], 5)
            current_rsi = round(df['RSI'].iloc[-1], 1)
            
            if momentum_signal:
                emoji = "🟢" if momentum_signal == "BUY" else "🔴"
                alerts.append(f"{emoji} <b>MOMENTUM ALERT:</b> {momentum_signal} • {clean_symbol} ({tf})\n↳ [9/12 EMA Cross] | Price: {current_price} | RSI: {current_rsi}")
                
            if poi_signal:
                alerts.append(f"🏛️ <b>INSTITUTIONAL ALERT:</b> {clean_symbol} ({tf})\n↳ {poi_signal} | Price: {current_price} | RSI: {current_rsi}")
                
    if alerts:
        final_message = f"🚨 <b>HYBRID STRATEGY ALERTS</b> 🚨\n\n📊 <b>Macro Filter:</b> {news_status}\n\n" + "\n\n".join(alerts) + "\n\n------------------------\n⏰ Autopilot active via GitHub"
    else:
        final_message = f"🔎 <b>Hybrid Strategy Scan:</b> No fresh EMA crosses or verified blocks found.\n\n📊 <b>Macro Filter:</b> {news_status}\n------------------------\n⏰ Autopilot active via GitHub"
        
    send_telegram_alert(final_message)

if __name__ == "__main__":
    main()
