import os
import json
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import websocket  # Synchronous client bypassing the GitHub event loop bug
from datetime import datetime
from zoneinfo import ZoneInfo

# ==========================================
# 1. CONFIGURATION & TARGET ASSETS
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STANDARD_PAIRS = [
    # Forex Majors
    'EURUSD=X', 'GBPUSD=X', 'AUDUSD=X', 'USDCHF=X', 'USDCAD=X', 'NZDUSD=X',
    # Crosses
    'EURGBP=X', 'EURAUD=X', 'AUDCAD=X', 'GBPAUD=X', 'GBPCAD=X',
    # Precious Metals
    'GC=F',  # Gold COMEX Futures
    'SI=F',  # Silver COMEX Futures
    # Global Indices
    '^GSPC', '^AEX', '^N225', '^FTSE', '^IXIC', '^GDAXI', '^FCHI'
]

DERIV_PAIRS = [
    # Standard Volatility Indices
    'R_10', 'R_25', 'R_50', 'R_75', 'R_90', 'R_100',
    # 1s Volatility Indices
    '1HZ10V', '1HZ25V', '1HZ50V', '1HZ75V', '1HZ90V', '1HZ100V',
    # Jump Indices
    'JD10', 'JD25',
    # Boom Indices
    'BOOM50', 'BOOM100', 'BOOM150', 'BOOM200', 
    'BOOM300', 'BOOM500', 'BOOM600', 'BOOM900', 'BOOM1000',
    # Crash Indices
    'CRASH50', 'CRASH100', 'CRASH150', 'CRASH200', 
    'CRASH300', 'CRASH500', 'CRASH600', 'CRASH900', 'CRASH1000',
    # Step Indices
    'STP', 'STP200', 'STP300', 'STP400', 'STP500'
]

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
    session_status = "🟢 Weekend Synthetic Session" if is_weekend else "🌐 Weekday Global Session"
    return ontario_now, timestamp_str, is_weekend, session_status

# ==========================================
# 3. ROBUST DATA FETCHING & RESAMPLING
# ==========================================
def fetch_deriv_candles_sync(symbol, granularity, count=150):
    uri = "wss://ws.derivws.com/websockets/v3?app_id=1089"
    try:
        ws = websocket.create_connection(uri, timeout=10)
        request = {
            "ticks_history": symbol, "adjust_start_time": 1,
            "count": count, "end": "latest",
            "granularity": granularity, "style": "candles"
        }
        ws.send(json.dumps(request))
        response = ws.recv()
        ws.close()
        
        data = json.loads(response)
        if 'candles' in data:
            df = pd.DataFrame(data['candles'])
            df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
            for col in ['Open', 'High', 'Low', 'Close']: 
                df[col] = df[col].astype(float)
            return df
    except Exception as e:
        print(f"Deriv data connection skip for {symbol}: {e}")
        return None

def get_data(symbol, timeframe, is_deriv):
    if is_deriv:
        time.sleep(0.1)  
        tf_map = {'30m': 1800, '1h': 3600, '4h': 14400}
        return fetch_deriv_candles_sync(symbol, tf_map.get(timeframe, 1800))
    else:
        time.sleep(1.0)  
        try:
            if timeframe == '4h':
                yf_interval = '1h'  
                period = '30d'
            elif timeframe == '1h':
                yf_interval = '1h'
                period = '14d'
            else: # 30m
                yf_interval = '30m'
                period = '7d'
                
            df = yf.download(symbol, interval=yf_interval, period=period, progress=False)
            if df is None or df.empty:
                return None
                
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            if timeframe == '4h':
                df = df.resample('4H').agg({
                    'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
                }).dropna()
                
            return df
        except Exception as e:
            print(f"⚠️ Yahoo Finance Error on {symbol} ({timeframe}): {e}")
            return None

# ==========================================
# 4. LIVE ECONOMIC CALENDAR DATA ENGINE
# ==========================================
def clean_economic_value(val_str):
    if not val_str or str(val_str).strip() == "": return None
    try:
        clean = "".join([c for c in str(val_str) if c.isdigit() or c in ['.', '-']])
        return float(clean) if clean else None
    except:
        return None

def fetch_economic_news_alerts(ontario_now):
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    news_alerts = []
    pending_currencies = []
    try:
        res = requests.get(url, timeout=12)
        if res.status_code != 200:
            print(f"⚠️ News API connection response code: {res.status_code}")
            return news_alerts, pending_currencies
            
        events = res.json()
        today_str = ontario_now.strftime("%Y-%m-%d")
        
        for event in events:
            if today_str in event.get('date', ''):
                impact = event.get('impact', 'Low')
                country = event.get('country', '')
                title = event.get('title', '')
                
                event_time = event.get('time', '')
                if not event_time and 'T' in event.get('date', ''):
                    event_time = event.get('date', '').split('T')[1][:5]
                if not event_time:
                    event_time = "Specified Today"
                
                if impact in ['High', 'Medium'] and country in ['USD', 'EUR', 'GBP', 'AUD', 'CAD', 'CHF', 'NZD']:
                    act_str = event.get('actual', '')
                    for_str = event.get('forecast', '')
                    prev_str = event.get('previous', '')
                    
                    if not act_str:
                        pending_currencies.append(country)
                        news_alerts.append(
                            f"📅 <b>UPCOMING IMPACT NEWS ALERT</b>\n"
                            f"🔴 Impact: <b>{impact}</b>\n"
                            f"⏰ Time: <b>{event_time}</b>\n"
                            f"🌐 Currency: <b>{country}</b> | Event: <b>{title}</b>\n"
                            f"📊 Status: Pending Release (Standby for direction)"
                        )
                    else:
                        act_val = clean_economic_value(act_str)
                        for_val = clean_economic_value(for_str)
                        
                        bias_message = "🔄 Mixed/Neutral Bias (Watch price action structure)"
                        
                        if act_val is not None and for_val is not None:
                            is_inverted = any(k in title.lower() for k in ['unemployment', 'claims', 'jobless'])
                            is_better = (act_val < for_val) if is_inverted else (act_val > for_val)
                            
                            if country == 'USD':
                                if is_better:
                                    bias_message = "🦅 <b>USD STRONG (BUY USD Bias)</b>\n📉 <b>SELL:</b> EURUSD, GBPUSD, AUDUSD, NZDUSD, ^GSPC, ^IXIC\n📈 <b>BUY:</b> USDCAD, USDCHF"
                                else:
                                    bias_message = "🪵 <b>USD WEAK (SELL USD Bias)</b>\n📈 <b>BUY:</b> EURUSD, GBPUSD, AUDUSD, NZDUSD, ^GSPC, ^IXIC\n📉 <b>SELL:</b> USDCAD, USDCHF"
                            elif country == 'EUR':
                                bias_message = f"📈 <b>BUY EURUSD</b>" if is_better else f"📉 <b>SELL EURUSD</b>"
                            elif country == 'GBP':
                                bias_message = f"📈 <b>BUY GBPUSD</b>" if is_better else f"📉 <b>SELL GBPUSD</b>"
                            elif country == 'AUD':
                                bias_message = f"📈 <b>BUY AUDUSD</b>" if is_better else f"📉 <b>SELL AUDUSD</b>"
                            elif country == 'NZD':
                                bias_message = f"📈 <b>BUY NZDUSD</b>" if is_better else f"📉 <b>SELL NZDUSD</b>"
                            elif country == 'CAD':
                                bias_message = f"📉 <b>SELL USDCAD</b>" if is_better else f"📈 <b>BUY USDCAD</b>"
                            elif country == 'CHF':
                                bias_message = f"📉 <b>SELL USDCHF</b>" if is_better else f"📈 <b>BUY USDCHF</b>"
                        
                        news_alerts.append(
                            f"⚡ <b>LIVE ECONOMIC RELEASE IMPACT</b>\n"
                            f"📢 Event: <b>{title} ({country})</b>\n"
                            f"⏰ Time: <b>{event_time}</b>\n"
                            f"🎯 Actual: <b>{act_str}</b> | Forecast: <b>{for_str}</b> | Prev: {prev_str}\n"
                            f"⚖️ Macro Directional Vector:\n{bias_message}"
                        )
        return news_alerts, pending_currencies
    except Exception as e:
        print(f"❌ Failed to parse macroeconomic calendar: {e}")
        return news_alerts, pending_currencies

# ==========================================
# 5. EXECUTION ENGINE (PURE INDICATOR + NEWS)
# ==========================================
def main():
    ontario_now, timestamp_str, is_weekend, session_status = get_market_context()
    
    # Active asset selection: Synthetics on weekends, Standard + Synthetics on weekdays
    active_symbols = DERIV_PAIRS if is_weekend else (STANDARD_PAIRS + DERIV_PAIRS)
    
    send_telegram_alert(f"🧪 <b>SYSTEM CHECK:</b> TDO(28) & EMA Scanner running ({timestamp_str} EST).\n📌 Mode: {session_status}")
    
    asset_grouped_alerts = {}
    summary_matrix_lines = []
    
    # Fetch macroeconomic calendar alerts on weekdays
    economic_news, pending_currencies = ([], []) if is_weekend else fetch_economic_news_alerts(ontario_now)

    for symbol in active_symbols:
        is_deriv = symbol in DERIV_PAIRS
        clean_name = symbol.replace('=X', '').replace('^', '')
        current_pair_alerts = []
        
        tally = {'dem_buy': 0, 'dem_sell': 0, 'ema_bull': 0, 'ema_bear': 0}
        target_timeframes = ['30m', '1h', '4h']
        
        for tf in target_timeframes:
            df = get_data(symbol, tf, is_deriv)
            if df is None or len(df) < 40: continue  
            
            # --- 9 / 21 EMA CROSSOVER ENGINE ---
            df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
            df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()  
            
            if df['EMA_9'].iloc[-2] <= df['EMA_21'].iloc[-2] and df['EMA_9'].iloc[-1] > df['EMA_21'].iloc[-1]:
                current_pair_alerts.append(f"🟢 <b>EMA BULLISH CROSSOVER (9/21) [{tf}]</b>\n💰 Price: {round(df['Close'].iloc[-1], 4)}")
                tally['ema_bull'] += 1
            elif df['EMA_9'].iloc[-2] >= df['EMA_21'].iloc[-2] and df['EMA_9'].iloc[-1] < df['EMA_21'].iloc[-1]:
                current_pair_alerts.append(f"🔴 <b>EMA BEARISH CROSSUNDER (9/21) [{tf}]</b>\n📉 Price: {round(df['Close'].iloc[-1], 4)}")
                tally['ema_bear'] += 1

            # --- TDO / DEMARKER (28) OSCILLATOR ENGINE ---
            high_diff = df['High'].diff()
            demax = np.where(high_diff > 0, high_diff, 0.0)
            
            low_diff = df['Low'].shift(1) - df['Low']
            demin = np.where(low_diff > 0, low_diff, 0.0)
            
            demax_sma = pd.Series(demax).rolling(window=28).mean()
            demin_sma = pd.Series(demin).rolling(window=28).mean()
            
            tdo_series = demax_sma / (demax_sma + demin_sma)
            
            if len(tdo_series) >= 3:
                current_tdo = tdo_series.iloc[-2]
                prev_tdo = tdo_series.iloc[-3]
                current_price = df['Close'].iloc[-1]
                
                if prev_tdo < 0.300 and current_tdo >= 0.300:
                    current_pair_alerts.append(
                        f"🔵 <b>TDO(28) OVERSOLD RECOVERY [{tf}]</b>\n"
                        f"💰 Price: {round(current_price, 4)} | 📊 TDO: {round(current_tdo, 3)}"
                    )
                    tally['dem_buy'] += 1
                elif prev_tdo > 0.700 and current_tdo <= 0.700:
                    current_pair_alerts.append(
                        f"🔴 <b>TDO(28) OVERBOUGHT DISTRIBUTION [{tf}]</b>\n"
                        f"📉 Price: {round(current_price, 4)} | 📊 TDO: {round(current_tdo, 3)}"
                    )
                    tally['dem_sell'] += 1

        if current_pair_alerts:
            asset_grouped_alerts[clean_name] = current_pair_alerts
            
            bias, quality, execution = "⏳ Neutral", "⭐ (Low)", "Mixed Signals"
            is_conflict = (tally['dem_buy'] or tally['ema_bull']) and (tally['dem_sell'] or tally['ema_bear'])
            
            if is_conflict:
                quality, execution = "⭐⭐ (Low)", "Timeframe Conflict"
            elif tally['dem_buy'] > 0 and tally['ema_bull'] > 0:
                bias, quality, execution = "🔵 Long", "⭐⭐⭐⭐⭐", "EMA + TDO(28) Aligned"
            elif tally['dem_sell'] > 0 and tally['ema_bear'] > 0:
                bias, quality, execution = "🔴 Short", "⭐⭐⭐⭐⭐", "EMA + TDO(28) Aligned"
            elif tally['dem_buy'] > 0 or tally['ema_bull'] > 0:
                bias, quality, execution = "🔵 Long", "⭐⭐⭐", "Single Indicator Trigger"
            elif tally['dem_sell'] > 0 or tally['ema_bear'] > 0:
                bias, quality, execution = "🔴 Short", "⭐⭐⭐", "Single Indicator Trigger"

            # News risk warning on affected weekday pairs
            if not is_deriv:
                for curr in pending_currencies:
                    if curr in clean_name:
                        quality, execution = "⚠️ Risk", f"Wait for {curr} News"
                        break
                        
            summary_matrix_lines.append(f"🔹 <b>{clean_name}:</b> {bias} | {quality} | {execution}")

    # ==========================================
    # 6. TELEGRAM DISPATCH FORMATTING MATRIX
    # ==========================================
    if len(economic_news) > 0 or len(asset_grouped_alerts) > 0:
        final_payload = [
            f"⚡ <b>TRADERULES COMPASS SIGNALS ({timestamp_str} EST)</b>", 
            f"📌 Market Mode: {session_status}",
            "========================"
        ]
        
        # A. Append macro calendar releases first
        if economic_news:
            final_payload.extend(economic_news)
            final_payload.append("========================")
            
        # B. Append technical triggers grouped under individual assets
        if asset_grouped_alerts:
            for asset_name, signals in asset_grouped_alerts.items():
                asset_block = f"🔸 <b>{asset_name}</b>\n" + "\n\n".join(signals)
                final_payload.append(asset_block)
                
        # C. Append Summary Action Matrix
        if summary_matrix_lines:
            final_payload.append("========================")
            final_payload.append("💡 <b>SUMMARY ACTION MATRIX</b>")
            final_payload.extend(summary_matrix_lines)
                
        send_telegram_alert("\n\n".join(final_payload))
    else:
        print(f"Scanner executed successfully at {timestamp_str} EST. No active news or TDO/EMA signals.")

if __name__ == "__main__":
    main()
