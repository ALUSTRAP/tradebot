import os
import json
import time
import asyncio
import websockets
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

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
    'BOOM300', 'BOOM500', 'BOOM600', 'BOOM900', 'BOOM1000',
    'CRASH300', 'CRASH500', 'CRASH600', 'CRASH900', 'CRASH1000',
    'R_10', 'R_25', 'R_50', 'R_75', 'R_100', 'R_90',
    '1HZ10V', '1HZ25V', '1HZ50V', '1HZ75V', '1HZ90V', '1HZ100V',
    'JD10', 'JD25', 'STP', 'STP200', 'STP300', 'STP400', 'STP500'
]

TIMEFRAMES = ['15m', '30m', '1h', '4h']

def send_telegram_alert(message):
    token = str(TELEGRAM_BOT_TOKEN).strip()
    chat_id = str(TELEGRAM_CHAT_ID).strip()
    if token.lower().startswith('bot'):
        token = token[3:]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        print(f"Telegram Server Response: {r.status_code}")
    except Exception as e:
        print(f"Telegram execution alert error: {e}")

# ==========================================
# 2. TIME ENGINE & QUARTERLY THEORY ALIGNMENT
# ==========================================
def get_market_context():
    # Corrected to UTC+1 for Lagos, Nigeria
    lagos_now = datetime.utcnow() + timedelta(hours=1)
    timestamp_str = lagos_now.strftime("%Y-%m-%d %H:%M")
    is_weekend = lagos_now.weekday() >= 5  # 5 = Saturday, 6 = Sunday

    # Calculate current float time to accurately track 90-minute algorithmic windows
    time_float = lagos_now.hour + (lagos_now.minute / 60.0)
    
    # Quarterly Theory Sessions (Aligned to your structural sessions)
    # London Session (09:00 - 15:00 WAT)
    is_london_q2 = (10.5 <= time_float < 12.0)  # 10:30 - 12:00 Manipulation (Wyckoff Spring)
    is_london_q3 = (12.0 <= time_float < 13.5)  # 12:00 - 13:30 Distribution (SMC Expansion)
    
    # New York AM Session (14:00 - 20:00 WAT)
    is_ny_q2 = (15.5 <= time_float < 17.0)      # 15:30 - 17:00 Manipulation (Wyckoff Spring)
    is_ny_q3 = (17.0 <= time_float < 18.5)      # 17:00 - 18:30 Distribution (SMC Expansion)

    qt_status = "🔄 Regular Session Sub-Cycle"
    if is_london_q2 or is_ny_q2:
        qt_status = "⚠️ <b>QUARTERLY Q2: MANIPULATION PHASE</b> (Look for Wyckoff Springs/Sweeps)"
    elif is_london_q3 or is_ny_q3:
        qt_status = "🔥 <b>QUARTERLY Q3: DISTRIBUTION PHASE</b> (SMC Order Delivery Window)"

    return lagos_now, timestamp_str, is_weekend, qt_status

def get_futures_and_news_layout(timestamp_str):
    layout = f"📋 <b>Live Global Futures Markets (Lagos: {timestamp_str})</b>\n"
    futures = {
        'S&P 500 Fut': 'ES=F', 'Nasdaq 100 Fut': 'NQ=F', 'Dow Jones Fut': 'YM=F',
        'Russell 2000 Fut': 'RTY=F', 'CBOE Volatility (VIX)': '^VIX'
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
        
    layout += "\n📅 <b>Today's Major Macro Events (Lagos Time)</b>\n"
    layout += "• 🔴 HIGH USD - Non-Farm Payrolls (13:30 Lagos)\n• 🔴 HIGH USD - Unemployment Rate (13:30 Lagos)\n• 🟡 MED CAD - Ivey PMI (15:00 Lagos)\n"
    return layout

# ==========================================
# 3. DATA ENGINES
# ==========================================
async def fetch_deriv_candles(symbol, granularity, count=150):
    uri = "wss://ws.derivws.com/websockets/v3?app_id=1089"
    try:
        async with websockets.connect(uri, timeout=12) as websocket:
            request = {
                "ticks_history": symbol,
                "adjust_start_time": 1,
                "count": count,
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
    except Exception as e:
        print(f"Deriv connection error for {symbol}: {e}")
        return None

def get_deriv_data(symbol, timeframe):
    tf_map = {'15m': 900, '30m': 1800, '1h': 3600, '4h': 14400}
    time.sleep(0.25)
    try:
        return asyncio.run(fetch_deriv_candles(symbol, tf_map.get(timeframe, 900), count=150))
    except:
        return None

def get_yahoo_data(symbol, timeframe):
    try:
        period = '30d' if timeframe in ['1h', '4h'] else '5d'
        df = yf.download(symbol, interval=timeframe, period=period, progress=False, multi_level_index=False)
        if df.empty: return None
        
        df.reset_index(inplace=True)
        df.columns = [str(c).strip().lower().capitalize() for c in df.columns]
        
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
# 4. WYCKOFF STRUCTURAL ANALYSIS WITH 9/12 EMA
# ==========================================
def run_smc_analysis(df_4h, df_15m):
    if df_4h is None or len(df_4h) < 30: return None
    
    close_4h = df_4h['Close'].iloc[-1]
    high_4h = df_4h['High'].iloc[-1]
    low_4h = df_4h['Low'].iloc[-1]
    
    prev_high_4h = df_4h['High'].iloc[-15:-2].max()
    prev_low_4h = df_4h['Low'].iloc[-15:-2].min()
    
    smc_alert = None
    
    # Check Structural Breaks (BOS/CHOCH)
    if close_4h > prev_high_4h:
        smc_alert = "4H Bullish BOS" if df_4h['Close'].iloc[-5] >= df_4h['Open'].iloc[-5] else "4H Bullish CHOCH"
    elif close_4h < prev_low_4h:
        smc_alert = "4H Bearish BOS" if df_4h['Close'].iloc[-5] <= df_4h['Open'].iloc[-5] else "4H Bearish CHOCH"
        
    # Check Wyckoff Spring / Liquidity Inducement Sweeps
    pullback_high = df_4h['High'].iloc[-6:-2].max()
    pullback_low = df_4h['Low'].iloc[-6:-2].min()
    
    if high_4h > pullback_high and close_4h <= pullback_high:
        smc_alert = "Wyckoff Upthrust / Liquidity Sweep (Bearish Inducement)"
    elif low_4h < pullback_low and close_4h >= pullback_low:
        smc_alert = "Wyckoff Spring / Liquidity Sweep (Bullish Inducement)"

    # Fixed Lower Timeframe 15m Verification using the requested 9/12 EMA Engine
    if smc_alert and df_15m is not None and 'EMA_9' in df_15m.columns:
        close_15m = df_15m['Close'].iloc[-1]
        ema9_15m = df_15m['EMA_9'].iloc[-1]
        ema12_15m = df_15m['EMA_12'].iloc[-1]
        
        if ("Bullish" in smc_alert or "Spring" in smc_alert) and close_15m > ema9_15m > ema12_15m:
            smc_alert += " | 🔥 <b>CONFLUENCE: 15m 9/12 EMA Bullish Alignment</b>"
        elif ("Bearish" in smc_alert or "Upthrust" in smc_alert) and close_15m < ema9_15m < ema12_15m:
            smc_alert += " | 🔥 <b>CONFLUENCE: 15m 9/12 EMA Bearish Alignment</b>"
            
    return smc_alert

# ==========================================
# 5. EXECUTION MATRIX
# ==========================================
def main():
    alerts = []
    ema_crossovers = []
    
    # Fetch corrected time, weekend status, and Quarterly Theory profile
    lagos_now, timestamp_str, is_weekend, qt_status = get_market_context()
    
    # Weekend Filter Rule: Cut out standard pairs cleanly
    if is_weekend:
        active_symbols = DERIV_PAIRS
        header_layout = f"⚡ <b>Synthetic Autopilot Active (Lagos: {timestamp_str})</b>\n⚠️ Standard Financial Markets Closed for the Weekend.\n"
    else:
        active_symbols = STANDARD_PAIRS + DERIV_PAIRS
        header_layout = get_futures_and_news_layout(timestamp_str)
    
    display_names = {
        'EURUSD=X': 'EURUSD', 'GBPUSD=X': 'GBPUSD', 'AUDUSD=X': 'AUDUSD',
        'USDCHF=X': 'USDCHF', 'USDCAD=X': 'USDCAD', 'NZDUSD=X': 'NZDUSD',
        '^DJI': 'US30', '^GSPC': 'SPX500', '^IXIC': 'NAS100', 
        '^N225': 'Jp225', '^FTSE': 'Uk100', '^AXJO': 'Aus200', 
        '^AEX': 'Nth25', '^FCHI': 'Fra40'
    }
    
    for symbol in active_symbols:
        df_4h_cached = None
        df_15m_cached = None
        
        for tf in TIMEFRAMES:
            try:
                df = get_deriv_data(symbol, tf) if symbol in DERIV_PAIRS else get_yahoo_data(symbol, tf)
                
                if df is None or df.empty or len(df) < 30: 
                    continue
                
                # Rigid 9/12 EMA Calculation
                df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
                df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
                
                if tf == '4h': df_4h_cached = df.copy()
                if tf == '15m': df_15m_cached = df.copy()
                    
                clean_name = display_names.get(symbol, symbol)
                
                # Check 9/12 EMA Crosses across all historical frames
                if df['EMA_9'].iloc[-2] <= df['EMA_12'].iloc[-2] and df['EMA_9'].iloc[-1] > df['EMA_12'].iloc[-1]:
                    ema_crossovers.append(f"🟢 <b>EMA CROSSOVER:</b> Bullish • {clean_name} ({tf})")
                elif df['EMA_9'].iloc[-2] >= df['EMA_12'].iloc[-2] and df['EMA_9'].iloc[-1] < df['EMA_12'].iloc[-1]:
                    ema_crossovers.append(f"🔴 <b>EMA CROSSUNDER:</b> Bearish • {clean_name} ({tf})")
                    
            except Exception as e:
                print(f"Skipping indicator loop for {symbol} on {tf}: {e}")
                continue
                
        # Run Wyckoff/SMC Analysis with pre-calculated 9/12 EMAs on the lower timeframe
        if df_4h_cached is not None:
            try:
                smc_result = run_smc_analysis(df_4h_cached, df_15m_cached)
                if smc_result:
                    clean_name = display_names.get(symbol, symbol)
                    price = round(float(df_4h_cached['Close'].iloc[-1]), 4)
                    alerts.append(f"🏛️ <b>STRUCTURAL EDGE:</b> {clean_name}\n└ {smc_result} | Price: {price}")
            except Exception as e:
                print(f"SMC validation error for {symbol}: {e}")

    # Build Output Payload
    final_output = [header_layout, f"📊 <b>QT Cycle Status:</b> {qt_status}", "------------------------"]
    
    if alerts or ema_crossovers:
        if alerts:
            final_output.append("🚨 <b>WYCKOFF / SMC STRUCTURE ALERTS</b> 🚨")
            final_output.extend(alerts)
            final_output.append("") 
            
        if ema_crossovers:
            final_output.append("📈 <b>9/12 EMA TREND PROFILE BREAKOUTS</b>")
            final_output.extend(ema_crossovers)
    else:
        final_output.append("🔍 <b>Scanner Loop:</b> Clear market conditions. No active Wyckoff traps or 9/12 EMA cross signals observed.")
        
    final_output.append("\n------------------------\n⏰ Autopilot calibrated precisely to Lagos Time (UTC+1)")
    
    message = "\n".join(final_output)
    send_telegram_alert(message)

if __name__ == "__main__":
    main()
    
