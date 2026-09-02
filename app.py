import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import warnings
from datetime import datetime
import io
import requests

warnings.filterwarnings("ignore")

# =========================================
# FUNCTION GET STOCKS FROM TRADINGVIEW
# =========================================
def get_idx_stocks_from_tradingview():
    url = "https://scanner.tradingview.com/indonesia/scan"
    payload = {
        "filter": [{"left": "exchange", "operation": "equal", "right": "IDX"}],
        "options": {"active_symbols_only": True},
        "symbols": {"query": {"types": ["stock"]}},
        "columns": ["name", "sector"],
        "range": [0, 1500]
    }
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        raise Exception(f"Gagal koneksi ke TradingView. Status: {response.status_code}")
    
    data = response.json()
    hasil = []
    for item in data.get('data', []):
        ticker = item['d'][0]
        sektor = item['d'][1] if item['d'][1] else "Unknown"
        hasil.append({"Kode": ticker, "Sektor": sektor})
        
    return pd.DataFrame(hasil)

# =========================================
# FUNCTION MA STATE
# =========================================
def get_state(close, maA, maB, maC, maD, maE, maF):
    ma_list = [maA, maB, maC, maD, maE, maF]
    ma_max = max(ma_list)
    ma_min = min(ma_list)
    spread = round((ma_max - ma_min) / close, 4)

    bull = (maA > maB and maB > maC and maC > maD and maD > maE and maE > maF)
    bear = (maA < maB and maB < maC and maC < maD and maD < maE and maE < maF)

    if spread < 0.03 and close > maD:
        return "MELILIT UP"
    elif spread < 0.03 and close <= maD:
        return "MELILIT DOWN"
    elif bull and spread <= 0.05:
        return "RAPAT UP"
    elif bear and spread <= 0.05:
        return "RAPAT DOWN"
    elif spread <= 0.07:
        return "RENGGANG"
    else:
        return "JAUH"

# =========================================
# FUNCTION ATR
# =========================================
def calculate_atr(df, period=14):
    tr1 = df["High"] - df["Low"]
    tr2 = abs(df["High"] - df["Close"].shift(1))
    tr3 = abs(df["Low"] - df["Close"].shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr

# =========================================
# FUNCTION REJECTION
# =========================================
def count_rejections(recent_df, ma_col, tolerance):
    rejection_count = 0
    if recent_df.empty:
        return 0

    for i in range(len(recent_df)):
        low = recent_df["Low"].iloc[i]
        close = recent_df["Close"].iloc[i]
        ma = recent_df[ma_col].iloc[i]

        if pd.isna(ma):
            continue

        rejection = (
            (low >= (ma * (1 - tolerance))) and
            (low <= (ma * (1 + tolerance))) and
            (close > ma)
        )

        if rejection:
            rejection_count += 1

    return rejection_count

# =========================================
# STREAMLIT UI & MENU
# =========================================
st.set_page_config(page_title="Hybrid Screening & Breakout", layout="wide")

# MENAMBAHKAN MENU SIDEBAR
st.sidebar.title("Navigasi Screener")
menu_pilihan = st.sidebar.radio(
    "Pilih Menu:", 
    ("Hybrid Screening + Market Layer", "Rectangle Breakout Detector (Baru)")
)

if menu_pilihan == "Hybrid Screening + Market Layer":
    # =========================================================================
    # SCRIPT LAMA ANDA DIMULAI DARI SINI (SAMA PERSIS, HANYA DIGESER INDENTASI)
    # =========================================================================
    st.title("📈 Hybrid Screening + Market Layer")
    st.info("💡 Aplikasi ini menarik data saham dari TradingView dan mengkalkulasi rotasi sektor global (Intermarket Analysis).")

    pakai_hari_ini = st.radio("Pakai tanggal hari ini?", ("Ya", "Tidak"))

    if pakai_hari_ini == "Ya":
        tanggal_input = pd.Timestamp.today()
    else:
        tanggal_manual = st.date_input("Masukkan tanggal screening")
        tanggal_input = pd.to_datetime(tanggal_manual)

    st.write(f"**Screening menggunakan data sampai:** {tanggal_input.date()}")

    if st.button("Mulai Screening"):
        with st.spinner("Menarik data dari TradingView dan melakukan screening..."):
            try:
                excel_df = get_idx_stocks_from_tradingview()
            except Exception as e:
                st.error(f"Gagal mengambil data dari TradingView: {e}")
                st.stop()
                
            excel_df["Kode_JK"] = (
                excel_df["Kode"]
                .astype(str)
                .str.upper()
                .str.strip()
                + ".JK"
            )
            
            sektor_dict = dict(zip(excel_df["Kode_JK"], excel_df["Sektor"]))
            saham_list = sorted(list(set(excel_df["Kode_JK"].tolist())))
            st.info(f"Jumlah saham ditarik: {len(saham_list)}")

            st.write("Download IHSG...")
            ihsg = yf.download("^JKSE", period="1y", auto_adjust=False, progress=False)

            if isinstance(ihsg.columns, pd.MultiIndex):
                ihsg.columns = ihsg.columns.get_level_values(0)
            ihsg.columns = ihsg.columns.str.title()
            
            if "Close" not in ihsg.columns:
                st.error("Gagal mengunduh data IHSG dari Yahoo Finance. Silakan coba beberapa saat lagi.")
                st.stop()
            
            for col in ihsg.columns:
                ihsg[col] = pd.to_numeric(ihsg[col], errors="coerce")

            ihsg = ihsg[ihsg.index <= tanggal_input].copy()
            ihsg_close = ihsg["Close"].dropna()

            if len(ihsg_close) < 60:
                st.error(f"Data IHSG kurang dari 60 hari. Pastikan tanggal atau koneksi aman.")
                st.stop()

            st.write("Download market global & indikator ketakutan...")
            market_tickers = {
                "EIDO": "EIDO", "DXY": "DX-Y.NYB", "USDIDR": "IDR=X", 
                "US10Y": "^TNX", "SP500": "^GSPC", "VIX": "^VIX"
            }

            market_results = []
            market_score = 0

            for nama, ticker in market_tickers.items():
                try:
                    market_df_raw = yf.download(ticker, period="1mo", auto_adjust=False, progress=False)
                    if market_df_raw.empty or len(market_df_raw) < 5: continue
                    if isinstance(market_df_raw.columns, pd.MultiIndex):
                        market_df_raw.columns = market_df_raw.columns.get_level_values(0)
                    market_df_raw.columns = market_df_raw.columns.str.title()
                    market_df_raw = market_df_raw.dropna(subset=["Close"])
                    if market_df_raw.empty or len(market_df_raw) < 5: continue
                    
                    close_now = float(market_df_raw["Close"].iloc[-1])
                    close_prev = float(market_df_raw["Close"].iloc[-2])
                    change_pct = round(((close_now - close_prev) / close_prev) * 100, 2)

                    status = "NEUTRAL"
                    score = 0

                    if nama == "EIDO":
                        if change_pct > 0.5: status, score = "BULLISH", 3
                        elif change_pct < -0.5: status, score = "BEARISH", -3
                    elif nama == "DXY":
                        if change_pct > 0.3: status, score = "NEGATIVE", -1
                        elif change_pct < -0.3: status, score = "POSITIVE", 1
                    elif nama == "USDIDR":
                        if change_pct > 0.3: status, score = "NEGATIVE", -2
                        elif change_pct < -0.3: status, score = "POSITIVE", 2
                    elif nama == "US10Y":
                        if change_pct > 1: status, score = "RISK OFF", -3
                        elif change_pct < -1: status, score = "RISK ON", 2
                    elif nama == "SP500":
                        if change_pct > 0.5: status, score = "BULLISH", 3
                        elif change_pct < -0.5: status, score = "BEARISH", -3
                    elif nama == "VIX":
                        if change_pct > 5: status, score = "PANIC", -4
                        elif change_pct < -2: status, score = "CALM", 2

                    market_score += score
                    market_results.append({
                        "Indicator": nama, "Change %": change_pct, "Status": status, "Score": score
                    })
                except Exception as e:
                    st.write(f"ERROR MARKET {nama}: {e}")

            if market_score >= 5: market_regime = "✅ RISK ON"
            elif market_score <= -5: market_regime = "❌ RISK OFF"
            else: market_regime = "⚠️ NEUTRAL"

            st.write("Download rotasi intermarket & sektoral global...")
            commodity_tickers = {
                "Oil": "CL=F", "Gold": "GC=F", "Silver": "SI=F", "Copper": "HG=F",
                "CPO_Proxy": "ZL=F", "Agriculture": "DBA", "Shipping": "BDRY",
                "GlobalBank": "XLF", "GlobalHealth": "XLV", "GlobalTech": "QQQ",
                "GlobalProperty": "XLRE", "GlobalTelecom": "XLC", "GlobalTransport": "^DJT",
                "GlobalRetail": "XLY"
            }
            
            commodity_results = []
            commodity_bonus_pool = {
                "Energy": 0, "Basic": 0, "Industrial": 0, "Financial": 0,
                "Health": 0, "Non-Cyclical": 0, "Technology": 0, 
                "Real Estate": 0, "Telecom": 0, "Transport": 0, "Cyclical": 0
            }

            for nama, ticker in commodity_tickers.items():
                try:
                    comm_df_raw = yf.download(ticker, period="1mo", auto_adjust=False, progress=False)
                    if comm_df_raw.empty or len(comm_df_raw) < 5: continue
                    if isinstance(comm_df_raw.columns, pd.MultiIndex):
                        comm_df_raw.columns = comm_df_raw.columns.get_level_values(0)
                    comm_df_raw.columns = comm_df_raw.columns.str.title()
                    comm_df_raw = comm_df_raw.dropna(subset=["Close"])
                    if comm_df_raw.empty or len(comm_df_raw) < 5: continue

                    close_now = float(comm_df_raw["Close"].iloc[-1])
                    close_prev = float(comm_df_raw["Close"].iloc[-2])
                    change_pct = round(((close_now - close_prev) / close_prev) * 100, 2)

                    status = "NEUTRAL"
                    if change_pct > 0.3: status = "BULLISH"
                    elif change_pct < -0.3: status = "BEARISH"

                    if status == "BULLISH":
                        if nama == "Oil": commodity_bonus_pool["Energy"] += 3
                        elif nama in ["Gold", "Silver", "Copper"]: commodity_bonus_pool["Basic"] += 2
                        elif nama == "Shipping": commodity_bonus_pool["Industrial"] += 2
                        elif nama == "GlobalBank": commodity_bonus_pool["Financial"] += 3
                        elif nama == "GlobalHealth": commodity_bonus_pool["Health"] += 2
                        elif nama in ["CPO_Proxy", "Agriculture"]: commodity_bonus_pool["Non-Cyclical"] += 2
                        elif nama == "GlobalTech": commodity_bonus_pool["Technology"] += 3
                        elif nama == "GlobalProperty": commodity_bonus_pool["Real Estate"] += 2
                        elif nama == "GlobalTelecom": commodity_bonus_pool["Telecom"] += 2
                        elif nama == "GlobalTransport": commodity_bonus_pool["Transport"] += 2
                        elif nama == "GlobalRetail": commodity_bonus_pool["Cyclical"] += 2
                    elif status == "BEARISH":
                        if nama == "Oil": commodity_bonus_pool["Energy"] -= 3
                        elif nama in ["Gold", "Silver", "Copper"]: commodity_bonus_pool["Basic"] -= 2
                        elif nama == "Shipping": commodity_bonus_pool["Industrial"] -= 2
                        elif nama == "GlobalBank": commodity_bonus_pool["Financial"] -= 3
                        elif nama == "GlobalHealth": commodity_bonus_pool["Health"] -= 2
                        elif nama in ["CPO_Proxy", "Agriculture"]: commodity_bonus_pool["Non-Cyclical"] -= 2
                        elif nama == "GlobalTech": commodity_bonus_pool["Technology"] -= 3
                        elif nama == "GlobalProperty": commodity_bonus_pool["Real Estate"] -= 2
                        elif nama == "GlobalTelecom": commodity_bonus_pool["Telecom"] -= 2
                        elif nama == "GlobalTransport": commodity_bonus_pool["Transport"] -= 2
                        elif nama == "GlobalRetail": commodity_bonus_pool["Cyclical"] -= 2

                    commodity_results.append({"Indicator/Sektor": nama, "Change %": change_pct, "Status": status})
                except Exception as e:
                    st.write(f"ERROR COMMODITY {nama}: {e}")

            st.write("Download data harian dan mingguan saham...")
            daily_data = yf.download(tickers=saham_list, period="1y", group_by="ticker", auto_adjust=False, progress=False, threads=True)
            weekly_data = yf.download(tickers=saham_list, period="3y", interval="1wk", group_by="ticker", auto_adjust=False, progress=False, threads=True)

            is_multi = len(saham_list) > 1
            MIN_LIQUIDITY = 1_500_000_000
            hasil = []

            st.write("Memproses Screener...")

            for kode in saham_list:
                try:
                    if is_multi:
                        try:
                            data = daily_data[kode].copy()
                            weekly = weekly_data[kode].copy()
                        except: continue
                    else:
                        data = daily_data.copy()
                        weekly = weekly_data.copy()

                    if data.empty or len(data) < 50: continue
                    if weekly.empty or len(weekly) < 20: continue

                    data.columns = data.columns.str.title()
                    weekly.columns = weekly.columns.str.title()

                    data = data.sort_index()
                    weekly = weekly.sort_index()

                    data = data[data.index <= tanggal_input].copy()
                    weekly = weekly[weekly.index <= tanggal_input].copy()

                    data = data.dropna(how="all").dropna(subset=["Close"])
                    weekly = weekly.dropna(how="all").dropna(subset=["Close"])

                    if data.empty or len(data) < 220: continue
                    if weekly.empty or len(weekly) < 25: continue
                    if data["Close"].dropna().shape[0] < 220: continue
                    if weekly["Close"].dropna().shape[0] < 25: continue
                    if data["Volume"].dropna().shape[0] < 20: continue

                    close_series = data["Close"]

                    data["MA3"] = close_series.rolling(3).mean()
                    data["MA5"] = close_series.rolling(5).mean()
                    data["MA10"] = close_series.rolling(10).mean()
                    data["MA20"] = close_series.rolling(20).mean()
                    data["MA50"] = close_series.rolling(50).mean()
                    data["MA100"] = close_series.rolling(100).mean()
                    data["MA200"] = close_series.rolling(200).mean()

                    delta = close_series.diff()
                    gain = delta.where(delta > 0, 0)
                    loss = -delta.where(delta < 0, 0)
                    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                    rs = avg_gain / avg_loss
                    data["RSI"] = 100 - (100 / (1 + rs))

                    ema8 = close_series.ewm(span=8, adjust=False).mean()
                    ema21 = close_series.ewm(span=21, adjust=False).mean()
                    data["MACD"] = ema8 - ema21
                    data["MACD_SIGNAL"] = data["MACD"].ewm(span=5, adjust=False).mean()

                    rsi_min = data["RSI"].rolling(5).min()
                    rsi_max = data["RSI"].rolling(5).max()
                    data["STOCH_RSI"] = ((data["RSI"] - rsi_min) / (rsi_max - rsi_min)) * 100
                    data["K"] = data["STOCH_RSI"].rolling(3).mean()
                    data["D"] = data["K"].rolling(3).mean()

                    data["ATR"] = calculate_atr(data)
                    data["ATR_PERCENT"] = (data["ATR"] / data["Close"]) * 100

                    valid_volume = data[data["Volume"] > 0].copy()
                    if valid_volume.empty or len(valid_volume) < 20: continue
                    if len(valid_volume["Volume"].dropna()) < 20: continue

                    volume_now = float(valid_volume["Volume"].iloc[-1])
                    volume_avg = float(valid_volume["Volume"].tail(20).mean())

                    if pd.isna(volume_avg) or volume_avg <= 0:
                        volume_ratio = 0
                    else:
                        volume_ratio = round(volume_now / volume_avg, 2)

                    data["VALUE"] = data["Close"] * data["Volume"]
                    data["AVG_VALUE20"] = data["VALUE"].rolling(20).mean()
                    avg_value20_series = data["AVG_VALUE20"].dropna()

                    if avg_value20_series.empty: continue
                    avg_value20 = float(avg_value20_series.iloc[-1])

                    if avg_value20 < MIN_LIQUIDITY: continue

                    weekly["MA20W"] = weekly["Close"].rolling(20).mean()
                    weekly_close_series = weekly["Close"].dropna()
                    weekly_ma20_series = weekly["MA20W"].dropna()

                    if weekly_close_series.empty or weekly_ma20_series.empty: continue

                    weekly_close = float(weekly_close_series.iloc[-1])
                    weekly_ma20 = float(weekly_ma20_series.iloc[-1])
                    weekly_up = (weekly_close > weekly_ma20)

                    if len(close_series) < 60: continue

                    close = float(close_series.iloc[-1])
                    ma3 = float(data["MA3"].iloc[-1])
                    ma5 = float(data["MA5"].iloc[-1])
                    ma10 = float(data["MA10"].iloc[-1])
                    ma20 = float(data["MA20"].iloc[-1])
                    ma50 = float(data["MA50"].iloc[-1])
                    ma100 = float(data["MA100"].iloc[-1])
                    ma200 = float(data["MA200"].iloc[-1])

                    rsi_val = round(float(data["RSI"].iloc[-1]), 2)
                    atr = float(data["ATR"].iloc[-1])
                    atr_percent = round(float(data["ATR_PERCENT"].iloc[-1]), 2)

                    critical_values = [close, ma20, ma50, ma100, ma200, rsi_val, atr]
                    if any(pd.isna(x) for x in critical_values): continue

                    if len(data) < 3: continue

                    macd_now = data["MACD"].iloc[-1]
                    macd_signal_now = data["MACD_SIGNAL"].iloc[-1]
                    macd_prev = data["MACD"].iloc[-2]
                    macd_signal_prev = data["MACD_SIGNAL"].iloc[-2]

                    macd_bull = macd_now > macd_signal_now
                    macd_fresh_bull = (macd_prev <= macd_signal_prev and macd_now > macd_signal_now)
                    macd_bear = macd_now < macd_signal_now
                    macd_fresh_bear = (macd_prev >= macd_signal_prev and macd_now < macd_signal_now)

                    k_now = data["K"].iloc[-1]
                    d_now = data["D"].iloc[-1]
                    k_prev = data["K"].iloc[-2]
                    d_prev = data["D"].iloc[-2]

                    stoch_bull = k_now > d_now
                    stoch_fresh_bull = (k_prev <= d_prev and k_now > d_now)
                    stoch_bear = k_now < d_now
                    stoch_fresh_bear = (k_prev >= d_prev and k_now < d_now)

                    recent_4 = data.tail(4).copy()
                    ma20_reject = count_rejections(recent_4, "MA20", 0.005)
                    ma50_reject = count_rejections(recent_4, "MA50", 0.01)
                    ma200_reject = count_rejections(recent_4, "MA200", 0.015)

                    rejection_score = 0
                    rejection_text = []

                    if ma20_reject >= 2:
                        rejection_score += 2; rejection_text.append(f"MA20 ({ma20_reject}x)")
                    elif ma20_reject == 1:
                        rejection_score += 1; rejection_text.append("MA20")
                    if close < ma20: rejection_score -= 1

                    if ma50_reject >= 2:
                        rejection_score += 3; rejection_text.append(f"MA50 ({ma50_reject}x)")
                    elif ma50_reject == 1:
                        rejection_score += 2; rejection_text.append("MA50")
                    if close < ma50: rejection_score -= 2

                    if ma50_reject >= 1 and weekly_up: rejection_score += 1

                    if ma200_reject >= 2:
                        rejection_score += 4; rejection_text.append(f"MA200 ({ma200_reject}x)")
                    elif ma200_reject == 1:
                        rejection_score += 2; rejection_text.append("MA200")
                    if close < ma200: rejection_score -= 4

                    volume_confirmation = False
                    if volume_ratio >= 1.2 and (ma20_reject >= 1 or ma50_reject >= 1 or ma200_reject >= 1):
                        rejection_score += 1
                        volume_confirmation = True

                    if len(rejection_text) == 0: ma_rejection_status = "None"
                    else: ma_rejection_status = ",".join(rejection_text)

                    S_state = get_state(close, ma3, ma5, ma10, ma20, ma20, ma20)
                    M_state = get_state(close, ma3, ma5, ma10, ma20, ma50, ma50)
                    L_state = get_state(close, ma3, ma5, ma10, ma20, ma50, ma100)

                    ma_valid = [ma3, ma5, ma10, ma20, ma50, ma100]
                    spread_percent = round((max(ma_valid) - min(ma_valid)) / close * 100, 2)

                    stock_return = (close_series.iloc[-1] / close_series.iloc[-60]) - 1
                    ihsg_return = (ihsg_close.iloc[-1] / ihsg_close.iloc[-60]) - 1
                    rs_score = round(stock_return - ihsg_return, 2)

                    semua_dinamis_di_atas = (ma3 > ma5 and ma5 > ma10 and ma10 > ma20)
                    trend_up = ma20 > ma50
                    jarak_ke_ma50 = ((close - ma50) / ma50) * 100

                    market_phase = "SIDEWAYS"
                    action_plan = "WAIT"
                    entry_price = "-"
                    cutloss_price = "-"

                    if volume_ratio >= 1.5 and rs_score > 0.10 and close > ma5 and spread_percent > 4.5:
                        market_phase = "4. STRONG UPTREND"; action_plan = "FOLLOW MOMENTUM"
                        entry_price = f"{int(ma3)}"; cutloss_price = int(close - (atr * 1.5))
                    elif spread_percent < 3 and close > ma20:
                        market_phase = "1. MBULET"; action_plan = "BREAKOUT BASE"
                        highest_ma = max([ma3, ma5, ma10, ma20])
                        entry_price = f"> {int(highest_ma)}"; cutloss_price = int(ma20 - (atr * 0.5))
                    elif semua_dinamis_di_atas and 3 <= spread_percent <= 4.5:
                        market_phase = "2. DINAMIS RAPAT"; action_plan = "BUY PULLBACK"
                        entry_price = f"{int(ma10)} - {int(ma5)}"; cutloss_price = int(ma20 - atr)
                    elif semua_dinamis_di_atas and 4.5 < spread_percent <= 7 and 0 < jarak_ke_ma50 <= 10 and trend_up:
                        market_phase = "3. DINAMIS RENGGANG"; action_plan = "BUY CONTINUATION"
                        entry_price = f"{int(ma5)}"; cutloss_price = int(ma10 - atr)
                    elif close < ma20:
                        market_phase = "WEAK"

                    score = 0
                    ma_state_score = {"MELILIT UP": 4, "RAPAT UP": 3, "RENGGANG": 1, "JAUH": 0, "MELILIT DOWN": -3, "RAPAT DOWN": -5}
                    score += (ma_state_score.get(S_state, 0) + ma_state_score.get(M_state, 0) + ma_state_score.get(L_state, 0))
                    score += rejection_score

                    if spread_percent < 2: score += 2; spread_status = "SUPER RAPAT"
                    elif spread_percent < 3: score += 1; spread_status = "RAPAT"
                    elif spread_percent < 5: spread_status = "SEHAT"
                    elif spread_percent > 12: score -= 2; spread_status = "OVEREXTENDED"
                    elif spread_percent > 8: score -= 1; spread_status = "JAUH"
                    else: spread_status = "NORMAL"

                    if close > ma20: score += 2
                    else: score -= 2

                    if weekly_up: score += 2; weekly_status = "UPTREND"
                    else: score -= 2; weekly_status = "DOWNTREND"

                    if rsi_val > 80: score -= 3; rsi_status = "OVERHEAT"
                    elif rsi_val > 70: score -= 1; rsi_status = "HOT"
                    elif 45 <= rsi_val <= 65: score += 1; rsi_status = "HEALTHY"
                    elif rsi_val < 35: score -= 1; rsi_status = "WEAK"
                    else: rsi_status = "NORMAL"

                    if 2 <= atr_percent <= 6: score += 2; atr_status = "HEALTHY"
                    elif 6 < atr_percent <= 10: score += 1; atr_status = "VOLATILE"
                    elif atr_percent > 15: score -= 2; atr_status = "EXTREME"
                    else: atr_status = "NORMAL"

                    if rs_score > 0.15: score += 6; rs_status = "LEADER"
                    elif rs_score > 0.05: score += 3; rs_status = "OUTPERFORM"
                    elif rs_score < -0.05: score -= 4; rs_status = "UNDERPERFORM"
                    else: rs_status = "NORMAL"

                    if volume_ratio >= 2: score += 5; volume_status = "SUPER"
                    elif volume_ratio >= 1.5: score += 3; volume_status = "BREAKOUT"
                    elif volume_ratio >= 1.2: score += 1; volume_status = "ACCUMULATION"
                    else: volume_status = "NORMAL"

                    if macd_fresh_bull: score += 5; macd_status = "FRESH BULL"
                    elif macd_bull: score += 3; macd_status = "BULLISH"
                    elif macd_fresh_bear: score -= 5; macd_status = "FRESH BEAR"
                    elif macd_bear: score -= 3; macd_status = "BEARISH"
                    else: macd_status = "NEUTRAL"

                    if stoch_fresh_bull: score += 2; stoch_status = "FRESH BULL"
                    elif stoch_bull: score += 1; stoch_status = "BULLISH"
                    elif stoch_fresh_bear: score -= 2; stoch_status = "FRESH BEAR"
                    elif stoch_bear: score -= 1; stoch_status = "BEARISH"
                    else: stoch_status = "NEUTRAL"

                    if rsi_val > 78 and spread_percent > 8 and volume_ratio > 2:
                        score -= 5

                    phase_score = {"4. STRONG UPTREND": 10, "3. DINAMIS RENGGANG": 8, "2. DINAMIS RAPAT": 7, "1. MBULET": 5, "SIDEWAYS": 0, "WEAK": -6}
                    score += phase_score.get(market_phase, 0)

                    market_bonus = 0
                    if market_regime == "✅ RISK ON":
                        if market_phase == "4. STRONG UPTREND": market_bonus = 5
                        elif market_phase == "3. DINAMIS RENGGANG": market_bonus = 3
                        elif market_phase == "2. DINAMIS RAPAT": market_bonus = 2
                        elif market_phase == "1. MBULET": market_bonus = 1
                        elif market_phase == "WEAK": market_bonus = -2
                    elif market_regime == "❌ RISK OFF":
                        if market_phase == "4. STRONG UPTREND": market_bonus = -1
                        elif market_phase == "3. DINAMIS RENGGANG": market_bonus = -3
                        elif market_phase == "2. DINAMIS RAPAT": market_bonus = -4
                        elif market_phase == "1. MBULET": market_bonus = -2
                        elif market_phase == "WEAK": market_bonus = -5

                    sektor_saham = sektor_dict.get(kode, "-")
                    sec_up = str(sektor_saham).upper()
                    commodity_bonus = 0
                    
                    if "ENERGY" in sec_up: commodity_bonus += commodity_bonus_pool["Energy"]
                    elif "BASIC" in sec_up: commodity_bonus += commodity_bonus_pool["Basic"]
                    elif "INDUSTRIAL" in sec_up: commodity_bonus += commodity_bonus_pool["Industrial"]
                    elif "FINAN" in sec_up: commodity_bonus += commodity_bonus_pool["Financial"]
                    elif "HEALTH" in sec_up: commodity_bonus += commodity_bonus_pool["Health"]
                    elif "NON-CYCLICAL" in sec_up or "NON CYCLICAL" in sec_up: commodity_bonus += commodity_bonus_pool["Non-Cyclical"]
                    elif "CYCLICAL" in sec_up: commodity_bonus += commodity_bonus_pool["Cyclical"]
                    elif "TECH" in sec_up: commodity_bonus += commodity_bonus_pool["Technology"]
                    elif "ESTATE" in sec_up or "PROPERTY" in sec_up: commodity_bonus += commodity_bonus_pool["Real Estate"]
                    elif "TELECOM" in sec_up or "INFRA" in sec_up: commodity_bonus += commodity_bonus_pool["Telecom"]
                    elif "TRANSPORT" in sec_up or "LOGISTIC" in sec_up: commodity_bonus += commodity_bonus_pool["Transport"]

                    final_score = score + market_bonus + commodity_bonus

                    if final_score >= 40: quality = "🔥 SUPER STRONG"
                    elif final_score >= 30: quality = "🚀 STRONG"
                    elif final_score >= 18: quality = "✅ GOOD"
                    elif final_score >= 8: quality = "👀 WATCHLIST"
                    else: quality = "❌ AVOID"

                    hasil.append({
                        "Saham": kode.replace(".JK", ""),
                        "Sektor": sektor_saham,
                        "Phase": market_phase,
                        "Score": score,
                        "Market Bonus": market_bonus,
                        "Sektor Bonus": commodity_bonus,
                        "Final Score": final_score,
                        "Market Regime": market_regime,
                        "Quality": quality,
                        "Strategi": action_plan,
                        "Antre Beli": entry_price,
                        "Cut Loss": cutloss_price,
                        "Close": int(close),
                        "S.STATE": S_state,
                        "M.STATE": M_state,
                        "L.STATE": L_state,
                        "MA_Rejection_Status": ma_rejection_status,
                        "Spread %": spread_percent,
                        "Spread": spread_status,
                        "RSI": rsi_val,
                        "RSI Status": rsi_status,
                        "ATR %": atr_percent,
                        "ATR Status": atr_status,
                        "RS": rs_score,
                        "RS Status": rs_status,
                        "Volume Ratio": volume_ratio,
                        "Volume": volume_status,
                        "MACD": macd_status,
                        "STOCH RSI": stoch_status,
                        "Weekly": weekly_status,
                        "Liquidity(B)": round(avg_value20 / 1_000_000_000, 2)
                    })

                except Exception as e:
                    pass 

            df = pd.DataFrame(hasil)
            market_df_final = pd.DataFrame(market_results)
            commodity_df_final = pd.DataFrame(commodity_results)

            if not df.empty:
                kolom_urut = [
                    "Saham", "Sektor", "Phase", "Score", "Market Bonus", "Sektor Bonus", "Final Score", "Market Regime", "Quality",
                    "Strategi", "Antre Beli", "Cut Loss", "Close", "S.STATE", "M.STATE", "L.STATE",
                    "MA_Rejection_Status", "Spread %", "Spread", "RSI", "RSI Status", "ATR %", "ATR Status",
                    "RS", "RS Status", "Volume Ratio", "Volume", "MACD", "STOCH RSI", "Weekly", "Liquidity(B)"
                ]
                df = df[kolom_urut]
                df = df.sort_values(by="Final Score", ascending=False).reset_index(drop=True)

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    summary_df = pd.DataFrame([{
                        "Timestamp": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
                        "Market Score": market_score,
                        "Market Regime": market_regime
                    }])
                    summary_df.to_excel(writer, sheet_name="Market_Regime", index=False, startrow=0)
                    market_df_final.to_excel(writer, sheet_name="Market_Regime", index=False, startrow=4)
                    
                    commodity_df_final.to_excel(writer, sheet_name="Intermarket_Sectors", index=False)
                    df.to_excel(writer, sheet_name="Screener", index=False)
                
                output.seek(0)
                
                st.success("✅ Screening Canggih Selesai!")
                st.dataframe(df.head(15))
                
                st.download_button(
                    label="📥 Download Excel Hasil Screening",
                    data=output,
                    file_name=f"HYBRID_SCREENING_PRO_{tanggal_input.date()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("Tidak ada saham yang memenuhi kriteria likuiditas dasar.")


elif menu_pilihan == "Rectangle Breakout Detector (Baru)":
    # =========================================================================
    # FITUR BARU: TYPE 1 BREAKOUT DETECTOR
    # =========================================================================
    st.title("🚀 Rectangle Breakout Detector (Type 1)")
    st.info("💡 Mencari saham yang sedang berada dalam rentang konsolidasi panjang (Rectangle) dan baru saja menembus (Breakout) resistance dengan dorongan volume, atau yang hampir menembus (Mau Breakout).")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        window_days = st.number_input("Periode Konsolidasi (Hari)", min_value=20, max_value=200, value=60, help="60 hari bursa setara dengan kurang lebih 3 bulan.")
    with col2:
        max_width = st.number_input("Maks. Lebar Rectangle (%)", min_value=5, max_value=50, value=20, help="Jarak antara Resistance dan Support tidak boleh lebih dari persentase ini agar tetap rapi.") / 100.0
    with col3:
        prox_pct = st.number_input("Toleransi 'Mau Breakout' (%)", min_value=1, max_value=10, value=2, help="Jika harga close berada di bawah resistance sejauh sekian persen, maka statusnya Mau Breakout.") / 100.0
        
    MIN_LIQ_BREAKOUT = st.number_input("Minimal Rata-rata Transaksi Harian (Rp)", value=2_000_000_000, step=500_000_000)

    if st.button("Mulai Scan Breakout"):
        with st.spinner("Mengunduh data dan mencari saham Breakout..."):
            try:
                excel_df = get_idx_stocks_from_tradingview()
                excel_df["Kode_JK"] = excel_df["Kode"].astype(str).str.upper().str.strip() + ".JK"
                sektor_dict = dict(zip(excel_df["Kode_JK"], excel_df["Sektor"]))
                saham_list = sorted(list(set(excel_df["Kode_JK"].tolist())))
                
                st.write(f"Mengunduh historis {len(saham_list)} saham...")
                daily_data = yf.download(tickers=saham_list, period="6mo", group_by="ticker", auto_adjust=False, progress=False, threads=True)
                
                is_multi = len(saham_list) > 1
                hasil_breakout = []
                
                for kode in saham_list:
                    try:
                        if is_multi:
                            try:
                                data = daily_data[kode].copy()
                            except: continue
                        else:
                            data = daily_data.copy()
                            
                        data.columns = data.columns.str.title()
                        data = data.dropna(subset=["Close", "High", "Low", "Volume"])
                        
                        if len(data) < window_days: continue
                        
                        # Filter Likuiditas Dasar
                        data["Value"] = data["Close"] * data["Volume"]
                        avg_val = data["Value"].tail(20).mean()
                        if avg_val < MIN_LIQ_BREAKOUT: continue
                        
                        # LOGIKA RECTANGLE & BREAKOUT
                        data['Resistance'] = data['High'].rolling(window=window_days).max().shift(1)
                        data['Support'] = data['Low'].rolling(window=window_days).min().shift(1)
                        data['Width'] = (data['Resistance'] - data['Support']) / data['Support']
                        data['Vol_MA20'] = data['Volume'].rolling(window=20).mean().shift(1)
                        
                        last_row = data.iloc[-1]
                        if pd.isna(last_row['Width']): continue
                        
                        is_rectangle = last_row['Width'] <= max_width
                        
                        # Deteksi Mau Breakout
                        jarak_ke_res = (last_row['Resistance'] - last_row['Close']) / last_row['Close']
                        mau_breakout = is_rectangle and (0 <= jarak_ke_res <= prox_pct) and (last_row['Close'] < last_row['Resistance'])
                        
                        # Deteksi Breakout (Type 1)
                        is_breakout = is_rectangle and (last_row['Close'] > last_row['Resistance'])
                        vol_konfirmasi = last_row['Volume'] > (last_row['Vol_MA20'] * 1.5)
                        
                        status = "None"
                        if is_breakout and vol_konfirmasi:
                            status = "🔥 TYPE 1 BREAKOUT (VOL CONFRIM)"
                        elif is_breakout:
                            status = "✅ BREAKOUT (LOW VOL)"
                        elif mau_breakout:
                            status = "👀 MAU BREAKOUT"
                            
                        if status != "None":
                            hasil_breakout.append({
                                "Saham": kode.replace(".JK", ""),
                                "Sektor": sektor_dict.get(kode, "-"),
                                "Status": status,
                                "Harga Close": int(last_row['Close']),
                                "Resistance": int(last_row['Resistance']),
                                "Support": int(last_row['Support']),
                                "Jarak ke Res (%)": round(jarak_ke_res * 100, 2),
                                "Lebar Pattern (%)": round(last_row['Width'] * 100, 2),
                                "Lonjakan Vol (xMA)": round(last_row['Volume'] / last_row['Vol_MA20'], 2) if last_row['Vol_MA20'] > 0 else 0,
                                "Avg Liq (Milyar)": round(avg_val / 1_000_000_000, 2)
                            })
                            
                    except Exception:
                        pass
                
                df_break = pd.DataFrame(hasil_breakout)
                if not df_break.empty:
                    # Sort agar yang sudah breakout berada di paling atas
                    df_break = df_break.sort_values(by=["Status", "Lonjakan Vol (xMA)"], ascending=[True, False]).reset_index(drop=True)
                    
                    st.success(f"Ditemukan {len(df_break)} saham dengan pola Rectangle!")
                    st.dataframe(df_break)
                    
                    output_break = io.BytesIO()
                    with pd.ExcelWriter(output_break, engine="openpyxl") as writer:
                        df_break.to_excel(writer, sheet_name="Breakout", index=False)
                    output_break.seek(0)
                    
                    st.download_button(
                        label="📥 Download Excel Hasil Breakout",
                        data=output_break,
                        file_name=f"TYPE1_BREAKOUT_{pd.Timestamp.today().date()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("Tidak ada saham yang memenuhi kriteria Rectangle Breakout saat ini.")
            
            except Exception as e:
                st.error(f"Terjadi kesalahan: {e}")
