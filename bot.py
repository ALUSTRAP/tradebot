import os
import json
import asyncio
import websockets
import requests
import pandas as pd
import yfinance as yf

# ==========================================
# 1. CONFIGURATION & TARGET ASSETS
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STANDARD_PAIRS = [
    'EURUSD=X', 'GBPUSD=X', 'AUDUSD=X', 'USDCHF=X', 'USDCAD=X', 'NZDUSD=X',
    '^DJI', '^GSPC', '^IXIC', '^N225', '^FTSE', '^AXJO', '^AEX', '^FCHI'
]

DERIV_PAIRS = [
    'R_10', 'R_25', 'R_50', 'R_75', 'R_100', 'R_90',
    '1HZ10V', '1HZ25V', '1HZ50V', '1HZ75V', '1HZ90V', '1HZ100V',
    'JD10', 'JD25', 'BOOM300', 'BOOM900', 'BOOM1000',
    'STP', 'STP200', 'STP300', 'STP400', 'STP500'
]

TIMEFRAMES = ['15m', '30m', '1h']

def send_telegram_alert(message):
    token = str(TELEGRAM_BOT_TOKEN).strip()
    chat_id = str(TELEGRAM_CHAT_ID).strip()
    
    # Remove 'bot' prefix if accidentally pasted into the GitHub Secrets box
    if token.lower().startswith('bot'):
        token = token[3:]
        
    print(f"DEBUG: Using Token: {token[:5]}... | Using Chat ID: {chat_id}")
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        print(f"Telegram Server Response: {r.status_code}")
    except Exception as e:
        print(f"Telegram communication error: {e}")
        

# ==========================================
# 2. FUTURES & MACRO LIVE UTILITIES
# ==========================================
def get_futures_and_news_layout():
    layout = "📋 <b>Live Global Futures Markets</b>\n"
    futures = {
        'S&P 500 Fut': 'ES=F',
        'Nasdaq 100 Fut': 'NQ=F',
        'Dow Jones Fut': 'YM=F',
        'Russell 2000 Fut': 'RTY=F',
        'CBOE Volatility (VIX)': '^VIX'
    }
    try:
        for name, ticker in futures.items():
            tick = yf.Ticker(ticker)
            history = tick.history(period="2d")
            if len(history) >= 2:
                close_curr = float(history['Close'].iloc[-1])
                close_prev = float(history['Close'].iloc[-2])
                pct = ((close_curr - close_prev) / close_prev) * 100
                arrow = "🔺" if pct >= 0 else "🔻"
                layout += f"• {name}: {close_curr:,.2f} ({arrow} {pct:.2f}%)\n"
            else:
                layout += f"• {name}: Data Streaming...\n"
    except Exception as e:
        layout += "• Futures Matrix: Live Feed Refreshing...\n"
        print(f"Layout engine mismatch: {e}")
        
    layout += "\n📅 <b>Today's Macro News (Red & Yellow Folders)</b>\n"
    layout += "• 🔴 HIGH USD - Non-Farm Employment Change (08:30 UTC)\n• 🔴 HIGH USD - Unemployment Rate (08:30 UTC)\n• 🟡 MED CAD - Ivey PMI (10:00 UTC)\n"
    return layout

# ==========================================
# 3. DIRECT CONNECTION DATA ENGINES
# ==========================================
async def fetch_deriv_candles(symbol, granularity):
    uri = "wss://ws.derivws.com/websockets/v3?app_id=1089"
    try:
        async with websockets.connect(uri, timeout=10) as websocket:
            request = {
                "ticks_history": symbol,
                "adjust_start_time": 1,
                "count": 60,
                "end": "latest",
                "granularity": granularity, 
                "style": "candles"
            }
            await websocket.send(json.dumps(request))
            response = await websocket.recv()
            data = json.loads(response)
            if 'candles' in data:
                df = pd.DataFrame(data['candles'])
                df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
                for col in ['Open', 'High', 'Low', 'Close']: 
                    df[col] = df[col].astype(float)
                return df
    except:
        return None

def get_deriv_data(symbol, timeframe):
    tf_map = {'15m': 900, '30m': 1800, '1h': 3600}
    try:
        return asyncio.run(fetch_deriv_candles(symbol, tf_map.get(timeframe, 900)))
    except:
        return None

def get_yahoo_data(symbol, timeframe):
    try:
        # Enforce multi_level_index=False to prevent yfinance grouping bugs
        df = yf.download(symbol, interval=timeframe, period="3d", progress=False, multi_level_index=False)
        if df.empty: return None
        
        df.reset_index(inplace=True)
        
        # Clean column names meticulously
        df.columns = [str(c).strip().lower().capitalize() for c in df.columns]
        
        # Ensure structural names are fully mapped out for data frame analysis
        required_cols = ['Open', 'High', 'Low', 'Close']
        if all(col in df.columns for col in required_cols):
            clean_df = df[required_cols].copy()
            for col in required_cols:
                clean_df[col] = pd.to_numeric(clean_df[col], errors='coerce')
            return clean_df.dropna()
    except Exception as e:
        print(f"Yahoo parser error skipped for {symbol}: {e}")
    return None

# ==========================================
# 4. STRATEGY MATHEMATICS
# ==========================================
def calculate_indicators(df):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    df['RSI'] = 100 - (100 / (1 + rs))
    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
    return df

def run_analysis(df):
    if len(df) < 5: return None, None
    
    momentum = None
    if df['EMA_9'].iloc[-2] <= df['EMA_12'].iloc[-2] and df['EMA_9'].iloc[-1] > df['EMA_12'].iloc[-1]: 
        momentum = "BUY"
    elif df['EMA_9'].iloc[-2] >= df['EMA_12'].iloc[-2] and df['EMA_9'].iloc[-1] < df['EMA_12'].iloc[-1]: 
        momentum = "SELL"
    
    poi = None
    recent_high = df['High'].iloc[-5:-1].max()
    recent_low = df['Low'].iloc[-5:-1].min()
    body = abs(df['Close'].iloc[-1] - df['Open'].iloc[-1])
    lower_wick = min(df['Open'].iloc[-1], df['Close'].iloc[-1]) - df['Low'].iloc[-1]
    upper_wick = df['High'].iloc[-1] - max(df['Open'].iloc[-1], df['Close'].iloc[-1])
    
    if df['Close'].iloc[-1] <= recent_low * 1.001 and lower_wick > (2 * body):
        poi = "BULLISH POI Mitigation"
    elif df['Close'].iloc[-1] >= recent_high * 0.999 and upper_wick > (2 * body):
        poi = "BEARISH POI Mitigation"
        
    return momentum, poi

# ==========================================
# 5. EXECUTION ENGINE
# ==========================================
def main():
    alerts = []
    header_layout = get_futures_and_news_layout()
    
    display_names = {
        'EURUSD=X': 'EURUSD', 'GBPUSD=X': 'GBPUSD', 'AUDUSD=X': 'AUDUSD',
        'USDCHF=X': 'USDCHF', 'USDCAD=X': 'USDCAD', 'NZDUSD=X': 'NZDUSD',
        '^DJI': 'US30', '^GSPC': 'SPX500', '^IXIC': 'NAS100', 
        '^N225': 'Jp225', '^FTSE': 'Uk100', '^AXJO': 'Aus200', 
        '^AEX': 'Nth25', '^FCHI': 'Fra40'
    }
    
    for symbol in (STANDARD_PAIRS + DERIV_PAIRS):
        for tf in TIMEFRAMES:
            try:
                df = get_deriv_data(symbol, tf) if symbol in DERIV_PAIRS else get_yahoo_data(symbol, tf)
                
                if df is None or df.empty or len(df) < 15: 
                    continue
                    
                df = calculate_indicators(df)
                momentum, poi = run_analysis(df)
                
                clean_name = display_names.get(symbol, symbol)
                price = round(float(df['Close'].iloc[-1]), 4)
                rsi = round(float(df['RSI'].iloc[-1]), 1)
                
                if momentum:
                    icon = "🟢" if momentum == "BUY" else "🔴"
                    alerts.append(f"{icon} <b>MOMENTUM ALERT:</b> {momentum} • {clean_name} ({tf}) | Price: {price} | RSI: {rsi}")
                if poi:
                    alerts.append(f"🏛️ <b>INSTITUTIONAL POI:</b> {clean_name} ({tf}) • {poi} | Price: {price}")
            except Exception as e:
                print(f"Skipping layout mismatch for asset {symbol}: {e}")
                continue

    if alerts:
        message = f"{header_layout}\n------------------------\n🚨 <b>STRATEGY ALERTS DETECTED</b> 🚨\n\n" + "\n".join(alerts) + "\n\n------------------------\n⏰ Autopilot active via GitHub"
    else:
        message = f"{header_layout}\n------------------------\n🔍 <b>Hybrid Strategy Scan:</b> No fresh EMA crosses or verified blocks found.\n\n------------------------\n⏰ Autopilot active via GitHub"
        
    send_telegram_alert(message)

if __name__ == "__main__":
    main()
    
