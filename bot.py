import os
import json
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

# ==========================================
# 1. CONFIGURATION & TARGET ASSETS
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CORE_ASSETS = {
    'GC=F': 'Gold (XAUUSD)',
    'EURUSD=X': 'EURUSD',
    'GBPJPY=X': 'GBPJPY',
    'SI=F': 'Silver (XAGUSD)',
    '^DJI': 'US 30 (Dow Jones)',
    '^GSPC': 'S&P 500'
}

def send_telegram_alert(message):
    token = str(TELEGRAM_BOT_TOKEN).strip()
    if token.lower().startswith("bot"):
        token = token[3:]  
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": str(TELEGRAM_CHAT_ID).strip(), "text": message, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            print(f"Telegram Error Output: {res.text}")
    except Exception as e:
        print(f"Telegram dispatch failure: {e}")

# ==========================================
# 2. TIME ENGINE (ONTARIO / EASTERN TIME)
# ==========================================
def get_market_context():
    ontario_now = datetime.now(ZoneInfo("America/Toronto"))
    timestamp_str = ontario_now.strftime("%Y-%m-%d %H:%M")
    is_weekend = ontario_now.weekday() >= 5 

    time_float = ontario_now.hour + (ontario_now.minute / 60.0)
    
    # Adjusted for Eastern Time Session Windows
    is_london_q2 = (3.5 <= time_float < 5.0)  # London morning manipulation in ET
    is_london_q3 = (5.0 <= time_float < 6.5)  
    is_ny_q2     = (8.5 <= time_float < 10.0)   # NY Open Q2
    is_ny_q3     = (10.0 <= time_float < 11.5)  # NY Open Q3

    if is_london_q2 or is_ny_q2:
        qt_status = "⚠️ Q2 MANIPULATION PHASE"
    elif is_london_q3 or is_ny_q3:
        qt_status = "🔥 Q3 DISTRIBUTION PHASE"
    else:
        qt_status = "🔄 Regular Session"

    return timestamp_str, is_weekend, qt_status

# ==========================================
# 3. LIGHTWEIGHT DATA FETCHING
# ==========================================
def get_data(symbol, timeframe):
    time.sleep(0.5)  
    try:
        if timeframe == '4h':
            yf_interval = '1h'  
            period = '30d'
        elif timeframe == '1h':
            yf_interval = '1h'
            period = '14d'
        else:
            yf_interval = timeframe
            period = '7s' if timeframe == '15m' else '5d'
            
        df = yf.download(symbol, interval=yf_interval, period=period, progress=False)
        if df is None or df.empty:
            return None
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        if timeframe == '4h':
            df = df.resample('4H').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
            
        return df
    except Exception as e:
        print(f"⚠️ Yahoo Finance Error on {symbol} ({timeframe}): {e}")
        return None

# ==========================================
# 4. EXECUTION ENGINE
# ==========================================
def main():
    timestamp_str, is_weekend, qt_status = get_market_context()
    
    if is_weekend:
        print(f"[{timestamp_str}] Markets closed for the weekend. Skipping scan.")
        return

    send_telegram_alert(f"🧪 <b>SYSTEM CHECK:</b> Ontario Optimized Scanner running ({timestamp_str} EST).")
    
    asset_grouped_alerts = {}
    summary_matrix_lines = []

    for symbol, friendly_name in CORE_ASSETS.items():
        current_pair_alerts = []
        tally = {'dem_buy': 0, 'dem_sell': 0, 'ema_bull': 0, 'ema_bear': 0}
        
        target_timeframes = ['15m', '1h', '4h']
        
        for tf in target_timeframes:
            df = get_data(symbol, tf)
            if df is None or len(df) < 40: continue  
            
            # --- 9 / 21 EMA CROSSOVER ---
            df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
            df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()  
            
            if df['EMA_9'].iloc[-2] <= df['EMA_21'].iloc[-2] and df['EMA_9'].iloc[-1] > df['EMA_21'].iloc[-1]:
                current_pair_alerts.append(f"🟢 <b>EMA BULLISH CROSSOVER (9/21) [{tf}]</b>\n💰 Price: {round(df['Close'].iloc[-1], 4)}")
                tally['ema_bull'] += 1
            elif df['EMA_9'].iloc[-2] >= df['EMA_21'].iloc[-2] and df['EMA_9'].iloc[-1] < df['EMA_21'].iloc[-1]:
                current_pair_alerts.append(f"🔴 <b>EMA BEARISH CROSSUNDER (9/21) [{tf}]</b>\n📉 Price: {round(df['Close'].iloc[-1], 4)}")
                tally['ema_bear'] += 1

            # --- DEMARKER / TDO (28) OSCILLATOR ENGINE ---
            high_diff = df['High'].diff()
            demax = np.where(high_diff > 0, high_diff, 0.0)
            
            low_diff = df['Low'].shift(1) - df['Low']
            demin = np.where(low_diff > 0, low_diff, 0.0)
            
            demax_sma = pd.Series(demax).rolling(window=28).mean()
            demin_sma = pd.Series(demin).rolling(window=28).mean()
            
            tdo_series = demax_sma / (demax_sma + demin_sma)
            
            # --- ATR VOLATILITY SETUP ---
            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - df['Close'].shift())
            low_close = np.abs(df['Low'] - df['Close'].shift())
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = true_range.rolling(window=14).mean().iloc[-1]

            if len(tdo_series) >= 3:
                current_tdo = tdo_series.iloc[-2]
                prev_tdo = tdo_series.iloc[-3]
                current_price = df['Close'].iloc[-1]
                
                if prev_tdo < 0.300 and current_tdo >= 0.300:
                    current_pair_alerts.append(
                        f"🔵 <b>TDO(28) OVERSOLD RECOVERY [{tf}]</b>\n"
                        f"💰 Price: {round(current_price, 4)} | 📊 TDO: {round(current_tdo, 3)} | 📐 ATR: {round(atr, 4)}"
                    )
                    tally['dem_buy'] += 1
                elif prev_tdo > 0.700 and current_tdo <= 0.700:
                    current_pair_alerts.append(
                        f"🔴 <b>TDO(28) OVERBOUGHT DISTRIBUTION [{tf}]</b>\n"
                        f"📉 Price: {round(current_price, 4)} | 📊 TDO: {round(current_tdo, 3)} | 📐 ATR: {round(atr, 4)}"
                    )
                    tally['dem_sell'] += 1

        if current_pair_alerts:
            asset_grouped_alerts[friendly_name] = current_pair_alerts
            
            bias, quality = "⏳ Neutral", "⭐⭐⭐"
            if tally['dem_buy'] > 0 or tally['ema_bull'] > 0:
                bias, quality = "🔵 Long", "⭐⭐⭐⭐"
            elif tally['dem_sell'] > 0 or tally['ema_bear'] > 0:
                bias, quality = "🔴 Short", "⭐⭐⭐⭐"
                
            summary_matrix_lines.append(f"🔹 <b>{friendly_name}:</b> {bias} | {quality}")

    # ==========================================
    # 5. TELEGRAM DISPATCH
    # ==========================================
    if len(asset_grouped_alerts) > 0:
        final_payload = [
            f"⚡ <b>CORE SCANNER REPORT (Ontario: {timestamp_str})</b>", 
            f"📌 Market Context: {qt_status}",
            "========================"
        ]
        
        for asset_name, signals in asset_grouped_alerts.items():
            asset_block = f"🔸 <b>{asset_name}</b>\n" + "\n\n".join(signals)
            final_payload.append(asset_block)
                
        if summary_matrix_lines:
            final_payload.append("========================")
            final_payload.append("💡 <b>QUICK ACTION MATRIX</b>")
            final_payload.extend(summary_matrix_lines)
                
        send_telegram_alert("\n\n".join(final_payload))
    else:
        print(f"Scanner executed successfully at {timestamp_str}. No core triggers found.")

if __name__ == "__main__":
    main()
