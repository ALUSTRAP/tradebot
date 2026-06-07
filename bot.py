import os
import json
import time
import asyncio
import websockets
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import numpy as np

# ==========================================
# 1. CONFIGURATION & TARGET ASSETS
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STANDARD_PAIRS = [
    # Forex Majors
    'EURUSD=X', 'GBPUSD=X', 'AUDUSD=X', 'USDCHF=X', 'USDCAD=X', 'NZDUSD=X',
    # Global Indices
    '^GSPC',   # SPX (S&P 500)
    '^AEX',    # Nth (Netherlands 25)
    '^N225',   # Jp225 (Nikkei)
    '^FTSE',   # Uk100 (FTSE)
    '^IXIC',   # Nasdaq
    '^GDAXI',  # GER (DAX)
    '^FCHI'    # FRA (CAC 40)
]

DERIV_PAIRS = [
    # Standard Volatility
    'R_10', 'R_25', 'R_50', 'R_75', 'R_90', 'R_100',
    # 1s Volatility
    '1HZ10V', '1HZ25V', '1HZ50V', '1HZ75V', '1HZ90V', '1HZ100V',
    # Jump Indices
    'JD10', 'JD25',
    # Boom / Crash
    'BOOM300', 'BOOM900', 'BOOM1000', 
    # Step Indices
    'STP', 'STP200', 'STP300', 'STP400', 'STP500'
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
# 2. TIME ENGINE & QUARTERLY THEORY
# ==========================================
def get_market_context():
    lagos_now = datetime.utcnow() + timedelta(hours=1)
    timestamp_str = lagos_now.strftime("%Y-%m-%d %H:%M")
    is_weekend = lagos_now.weekday() >= 5 

    time_float = lagos_now.hour + (lagos_now.minute / 60.0)
    
    is_london_q2 = (10.5 <= time_float < 12.0)  
    is_london_q3 = (12.0 <= time_float < 13.5)  
    is_ny_q2     = (15.5 <= time_float < 17.0)  
    is_ny_q3     = (17.0 <= time_float < 18.5)  

    if is_london_q2 or is_ny_q2:
        qt_status = "⚠️ Q2 MANIPULATION PHASE (Liquidity Trap Window)"
    elif is_london_q3 or is_ny_q3:
        qt_status = "🔥 Q3 DISTRIBUTION PHASE (SMC Order Delivery Window)"
    else:
        qt_status = "🔄 Regular Cycle Session"

    return timestamp_str, is_weekend, qt_status

# ==========================================
# 3. LIVE DATA ACQUISITION ENGINES
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
        print(f"WebSocket skipped for {symbol}: {e}")
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
        print(f"Yahoo data fetch skipped for {symbol}: {e}")
    return None

# ==========================================
# 4. CHARTNAGARI SMC LOGIC EXTRACTION
# ==========================================
def chartnagari_smc_scanner(df):
    """
    Translates Go logic to calculate Swing Highs/Lows, Liquidity Sweeps, and Order Blocks.
    """
    if df is None or len(df) < 50:
        return None

    df = df.copy()
    
    # Calculate Swing Highs and Lows (Fractal Logic)
    df['Swing_High'] = df['High'][(df['High'] > df['High'].shift(1)) & (df['High'] > df['High'].shift(2)) & (df['High'] > df['High'].shift(-1)) & (df['High'] > df['High'].shift(-2))]
    df['Swing_Low'] = df['Low'][(df['Low'] < df['Low'].shift(1)) & (df['Low'] < df['Low'].shift(2)) & (df['Low'] < df['Low'].shift(-1)) & (df['Low'] < df['Low'].shift(-2))]
    
    # Forward fill to maintain the levels across candles
    df['Last_Swing_High'] = df['Swing_High'].ffill()
    df['Last_Swing_Low'] = df['Swing_Low'].ffill()

    current_close = df['Close'].iloc[-1]
    current_high = df['High'].iloc[-1]
    current_low = df['Low'].iloc[-1]
    
    prev_swing_high = df['Last_Swing_High'].iloc[-3]
    prev_swing_low = df['Last_Swing_Low'].iloc[-3]
    
    # Sweep Detection (Wick crosses swing level, but candle body closes inside)
    if current_high > prev_swing_high and current_close < prev_swing_high:
        return "⚠️ Sell-Side Trap: Liquidity Swept Above Swing High (Bearish OB Forming)"
        
    elif current_low < prev_swing_low and current_close > prev_swing_low:
        return "⚠️ Buy-Side Trap: Liquidity Swept Below Swing Low (Bullish OB Forming)"

    return None

# ==========================================
# 5. CORE EXECUTION MOTOR
# ==========================================
def main():
    timestamp_str, is_weekend, qt_status = get_market_context()
    active_symbols = DERIV_PAIRS if is_weekend else (STANDARD_PAIRS + DERIV_PAIRS)
    
    display_names = {
        'EURUSD=X': 'EURUSD', 'GBPUSD=X': 'GBPUSD', 'AUDUSD=X': 'AUDUSD',
        'USDCHF=X': 'USDCHF', 'USDCAD=X': 'USDCAD', 'NZDUSD=X': 'NZDUSD',
        '^DJI': 'US30', '^GSPC': 'SPX500', '^IXIC': 'NAS100', 
        '^N225': 'Jp225', '^FTSE': 'Uk100', '^AXJO': 'Aus200', 
        '^AEX': 'Nth25', '^FCHI': 'Fra40'
    }
    
    triggered_alerts = []

    for symbol in active_symbols:
        df_4h_cached = None
        clean_name = display_names.get(symbol, symbol)
        
        for tf in TIMEFRAMES:
            try:
                df = get_deriv_data(symbol, tf) if symbol in DERIV_PAIRS else get_yahoo_data(symbol, tf)
                if df is None or df.empty or len(df) < 15:
                    continue
                
                if tf == '4h': 
                    df_4h_cached = df.copy()
                
                df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
                df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
                
                if df['EMA_9'].iloc[-2] <= df['EMA_12'].iloc[-2] and df['EMA_9'].iloc[-1] > df['EMA_12'].iloc[-1]:
                    triggered_alerts.append(f"🟢 <b>EMA BULLISH CROSSOVER</b>\n📈 Asset: <b>{clean_name} ({tf})</b>\n📊 Time Context: {qt_status}\n💰 Price: {round(df['Close'].iloc[-1], 4)}")
                elif df['EMA_9'].iloc[-2] >= df['EMA_12'].iloc[-2] and df['EMA_9'].iloc[-1] < df['EMA_12'].iloc[-1]:
                    triggered_alerts.append(f"🔴 <b>EMA BEARISH CROSSUNDER</b>\n📉 Asset: <b>{clean_name} ({tf})</b>\n📊 Time Context: {qt_status}\n💰 Price: {round(df['Close'].iloc[-1], 4)}")
                    
            except Exception as e:
                print(f"Error looping indicators for {symbol} on {tf}: {e}")
                continue
                
        if df_4h_cached is not None:
            try:
                trap_result = chartnagari_smc_scanner(df_4h_cached)
                if trap_result:
                    current_price = round(float(df_4h_cached['Close'].iloc[-1]), 4)
                    triggered_alerts.append(f"🏛️ <b>SMC LIQUIDITY TRAP DETECTED</b>\n🚨 Signal: <b>{trap_result}</b>\n🎯 Asset: <b>{clean_name} (4H)</b>\n📊 Time Context: {qt_status}\n💰 Current Price: {current_price}")
            except Exception as e:
                print(f"SMC scanning fault on {symbol}: {e}")

    if triggered_alerts:
        final_payload = [
            f"⚡ <b>TRADERULES COMPASS SIGNALS (Lagos: {timestamp_str})</b>",
            "========================\n"
        ]
        final_payload.extend(triggered_alerts)
        final_payload.append("\n========================\n⏰ Autopilot Calibrated to Lagos Time (UTC+1)")
        
        message = "\n\n".join(final_payload)
        send_telegram_alert(message)
    else:
        print(f"Scanner executed successfully at {timestamp_str} Lagos Time. Market quiet, zero alerts triggered.")

if __name__ == "__main__":
    main()
