# =========================================
# APP.PY
# HYBRID SCREENING + MARKET LAYER
# SAFE STREAMLIT VERSION
# =========================================

# =========================================
# IMPORT
# =========================================
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import warnings
from datetime import datetime
from io import BytesIO

warnings.filterwarnings("ignore")

# =========================================
# PAGE CONFIG
# =========================================
st.set_page_config(
    page_title="Hybrid Screening",
    layout="wide"
)

# =========================================
# TITLE
# =========================================
st.title("📈 HYBRID SCREENING + MARKET LAYER")

st.markdown("""
Upload file Excel daftar saham

Kolom wajib:
- Kode
""")

# =========================================
# UPLOAD FILE
# =========================================
uploaded_file = st.file_uploader(
    "Upload File Excel",
    type=["xlsx", "xls"]
)

# =========================================
# DATE INPUT
# =========================================
pakai_hari_ini = st.checkbox(
    "Pakai tanggal hari ini",
    value=True
)

if pakai_hari_ini:

    tanggal_input = pd.Timestamp.today()

else:

    tanggal_manual = st.date_input(
        "Pilih tanggal screening"
    )

    tanggal_input = pd.to_datetime(
        tanggal_manual
    )

# =========================================
# BUTTON
# =========================================
run_button = st.button(
    "🚀 Jalankan Screening"
)

# =========================================
# FUNCTION MA STATE
# =========================================
def get_state(
    close,
    maA,
    maB,
    maC,
    maD,
    maE,
    maF
):

    ma_list = [
        maA,
        maB,
        maC,
        maD,
        maE,
        maF
    ]

    ma_max = max(ma_list)
    ma_min = min(ma_list)

    spread = round(
        (ma_max - ma_min)
        / close,
        4
    )

    bull = (
        maA > maB and
        maB > maC and
        maC > maD and
        maD > maE and
        maE > maF
    )

    bear = (
        maA < maB and
        maB < maC and
        maC < maD and
        maD < maE and
        maE < maF
    )

    if (
        spread < 0.03 and
        close > maD
    ):

        return "MELILIT UP"

    elif (
        spread < 0.03 and
        close <= maD
    ):

        return "MELILIT DOWN"

    elif (
        bull and
        spread <= 0.05
    ):

        return "RAPAT UP"

    elif (
        bear and
        spread <= 0.05
    ):

        return "RAPAT DOWN"

    elif spread <= 0.07:

        return "RENGGANG"

    else:

        return "JAUH"

# =========================================
# FUNCTION ATR
# =========================================
def calculate_atr(
    df,
    period=14
):

    tr1 = (
        df["High"] -
        df["Low"]
    )

    tr2 = abs(
        df["High"] -
        df["Close"].shift(1)
    )

    tr3 = abs(
        df["Low"] -
        df["Close"].shift(1)
    )

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    atr = (
        tr
        .rolling(period)
        .mean()
    )

    return atr

# =========================================
# FUNCTION REJECTION
# =========================================
def count_rejections(
    recent_df,
    ma_col,
    tolerance
):

    rejection_count = 0

    if recent_df.empty:
        return 0

    for i in range(len(recent_df)):

        try:

            low = recent_df["Low"].iloc[i]
            close = recent_df["Close"].iloc[i]
            ma = recent_df[ma_col].iloc[i]

            if pd.isna(ma):
                continue

            rejection = (

                (
                    low >= (
                        ma * (1 - tolerance)
                    )
                )

                and

                (
                    low <= (
                        ma * (1 + tolerance)
                    )
                )

                and

                (
                    close > ma
                )

            )

            if rejection:
                rejection_count += 1

        except:
            continue

    return rejection_count

# =========================================
# MAIN
# =========================================
if uploaded_file and run_button:

    try:

        # =========================================
        # READ EXCEL
        # =========================================
        excel_df = pd.read_excel(
            uploaded_file
        )

        # =========================================
        # VALIDASI KOLOM
        # =========================================
        if "Kode" not in excel_df.columns:

            st.error(
                "Kolom 'Kode' tidak ditemukan."
            )

            st.stop()

        # =========================================
        # LIST SAHAM
        # =========================================
        saham_list = (
            excel_df["Kode"]
            .astype(str)
            .str.upper()
            .str.strip()
            .str.replace(".JK", "", regex=False)
            + ".JK"
        ).tolist()

        saham_list = sorted(
            list(set(saham_list))
        )

        saham_list = [
            x for x in saham_list
            if x != ".JK"
        ]

        st.info(
            f"Jumlah saham: {len(saham_list)}"
        )

        # =========================================
        # DOWNLOAD IHSG
        # =========================================
        st.write("Download IHSG...")

        ihsg = yf.download(
            "^JKSE",
            period="1y",
            auto_adjust=False,
            progress=False
        )

        if ihsg.empty:

            st.error(
                "Gagal download IHSG"
            )

            st.stop()

        if isinstance(
            ihsg.columns,
            pd.MultiIndex
        ):

            ihsg.columns = (
                ihsg.columns
                .get_level_values(0)
            )

        ihsg.columns = (
            ihsg.columns
            .str.title()
        )

        ihsg = ihsg[
            ihsg.index <= tanggal_input
        ].copy()

        ihsg = ihsg.dropna(
            subset=["Close"]
        )

        if len(ihsg) < 60:

            st.error(
                "Data IHSG kurang dari 60 hari"
            )

            st.stop()

        ihsg_close = (
            ihsg["Close"]
            .dropna()
        )

        # =========================================
        # MARKET DATA
        # =========================================
        st.write("Download market global...")

        market_tickers = {
            "EIDO": "EIDO",
            "DXY": "DX-Y.NYB",
            "USDIDR": "IDR=X",
            "US10Y": "^TNX",
            "SP500": "^GSPC"
        }

        market_results = []
        market_score = 0

        for nama, ticker in market_tickers.items():

            try:

                market_df = yf.download(
                    ticker,
                    period="1mo",
                    auto_adjust=False,
                    progress=False
                )

                if market_df.empty:
                    continue

                if isinstance(
                    market_df.columns,
                    pd.MultiIndex
                ):

                    market_df.columns = (
                        market_df.columns
                        .get_level_values(0)
                    )

                market_df.columns = (
                    market_df.columns
                    .str.title()
                )

                market_df = market_df.dropna(
                    subset=["Close"]
                )

                if len(market_df) < 5:
                    continue

                close_now = float(
                    market_df["Close"].iloc[-1]
                )

                close_prev = float(
                    market_df["Close"].iloc[-2]
                )

                change_pct = round(
                    (
                        (
                            close_now -
                            close_prev
                        )
                        /
                        close_prev
                    ) * 100,
                    2
                )

                status = "NEUTRAL"
                score = 0

                if nama == "EIDO":

                    if change_pct > 0.5:

                        status = "BULLISH"
                        score = 3

                    elif change_pct < -0.5:

                        status = "BEARISH"
                        score = -3

                elif nama == "DXY":

                    if change_pct > 0.3:

                        status = "NEGATIVE"
                        score = -1

                    elif change_pct < -0.3:

                        status = "POSITIVE"
                        score = 1

                elif nama == "USDIDR":

                    if change_pct > 0.3:

                        status = "NEGATIVE"
                        score = -2

                    elif change_pct < -0.3:

                        status = "POSITIVE"
                        score = 2

                elif nama == "US10Y":

                    if change_pct > 1:

                        status = "RISK OFF"
                        score = -3

                    elif change_pct < -1:

                        status = "RISK ON"
                        score = 2

                elif nama == "SP500":

                    if change_pct > 0.5:

                        status = "BULLISH"
                        score = 3

                    elif change_pct < -0.5:

                        status = "BEARISH"
                        score = -3

                market_score += score

                market_results.append({

                    "Indicator": nama,
                    "Change %": change_pct,
                    "Status": status,
                    "Score": score

                })

            except:
                continue

        # =========================================
        # MARKET REGIME
        # =========================================
        if market_score >= 5:

            market_regime = "✅ RISK ON"

        elif market_score <= -5:

            market_regime = "❌ RISK OFF"

        else:

            market_regime = "⚠️ NEUTRAL"

        # =========================================
        # DOWNLOAD DAILY
        # =========================================
        st.write("Download daily data...")

        daily_data = yf.download(
            tickers=saham_list,
            period="1y",
            group_by="ticker",
            auto_adjust=False,
            progress=True,
            threads=True
        )

        # =========================================
        # DOWNLOAD WEEKLY
        # =========================================
        st.write("Download weekly data...")

        weekly_data = yf.download(
            tickers=saham_list,
            period="3y",
            interval="1wk",
            group_by="ticker",
            auto_adjust=False,
            progress=True,
            threads=True
        )

        # =========================================
        # MULTI CHECK
        # =========================================
        is_multi = len(saham_list) > 1

        # =========================================
        # LIQUIDITY
        # =========================================
        MIN_LIQUIDITY = 1_500_000_000

        # =========================================
        # HASIL
        # =========================================
        hasil = []

        progress_bar = st.progress(0)

        # =========================================
        # LOOP
        # =========================================
        for idx, kode in enumerate(saham_list):

            try:

                progress_bar.progress(
                    (idx + 1) / len(saham_list)
                )

                # =========================================
                # EXTRACT
                # =========================================
                if is_multi:

                    try:

                        data = (
                            daily_data[kode]
                            .copy()
                        )

                        weekly = (
                            weekly_data[kode]
                            .copy()
                        )

                    except:
                        continue

                else:

                    data = daily_data.copy()
                    weekly = weekly_data.copy()

                # =========================================
                # EMPTY CHECK
                # =========================================
                if data.empty:
                    continue

                if weekly.empty:
                    continue

                # =========================================
                # FIX COLUMN
                # =========================================
                data.columns = (
                    data.columns
                    .str.title()
                )

                weekly.columns = (
                    weekly.columns
                    .str.title()
                )

                # =========================================
                # SORT
                # =========================================
                data = data.sort_index()
                weekly = weekly.sort_index()

                # =========================================
                # FILTER DATE
                # =========================================
                data = data[
                    data.index <= tanggal_input
                ].copy()

                weekly = weekly[
                    weekly.index <= tanggal_input
                ].copy()

                # =========================================
                # CLEAN
                # =========================================
                data = (
                    data
                    .dropna(how="all")
                    .dropna(subset=["Close"])
                )

                weekly = (
                    weekly
                    .dropna(how="all")
                    .dropna(subset=["Close"])
                )

                # =========================================
                # VALIDASI
                # =========================================
                if len(data) < 220:
                    continue

                if len(weekly) < 25:
                    continue

                if len(data["Close"].dropna()) < 220:
                    continue

                if len(weekly["Close"].dropna()) < 25:
                    continue

                if len(data["Volume"].dropna()) < 20:
                    continue

                # =========================================
                # CLOSE SERIES
                # =========================================
                close_series = (
                    data["Close"]
                    .dropna()
                )

                if len(close_series) < 220:
                    continue

                # =========================================
                # MA
                # =========================================
                data["MA3"] = close_series.rolling(3).mean()
                data["MA5"] = close_series.rolling(5).mean()
                data["MA10"] = close_series.rolling(10).mean()
                data["MA20"] = close_series.rolling(20).mean()
                data["MA50"] = close_series.rolling(50).mean()
                data["MA100"] = close_series.rolling(100).mean()
                data["MA200"] = close_series.rolling(200).mean()

                # =========================================
                # RSI
                # =========================================
                delta = close_series.diff()

                gain = delta.where(
                    delta > 0,
                    0
                )

                loss = -delta.where(
                    delta < 0,
                    0
                )

                avg_gain = gain.ewm(
                    alpha=1/14,
                    min_periods=14,
                    adjust=False
                ).mean()

                avg_loss = loss.ewm(
                    alpha=1/14,
                    min_periods=14,
                    adjust=False
                ).mean()

                rs = avg_gain / avg_loss

                data["RSI"] = (
                    100 -
                    (
                        100 /
                        (1 + rs)
                    )
                )

                # =========================================
                # ATR
                # =========================================
                data["ATR"] = calculate_atr(data)

                data["ATR_PERCENT"] = (
                    data["ATR"]
                    /
                    data["Close"]
                ) * 100

                # =========================================
                # VOLUME
                # =========================================
                valid_volume = data[
                    data["Volume"] > 0
                ].copy()

                if len(valid_volume) < 20:
                    continue

                volume_now = float(
                    valid_volume["Volume"].iloc[-1]
                )

                volume_avg = float(
                    valid_volume["Volume"]
                    .tail(20)
                    .mean()
                )

                if (
                    pd.isna(volume_avg)
                    or
                    volume_avg <= 0
                ):

                    volume_ratio = 0

                else:

                    volume_ratio = round(
                        volume_now /
                        volume_avg,
                        2
                    )

                # =========================================
                # VALUE
                # =========================================
                data["VALUE"] = (
                    data["Close"] *
                    data["Volume"]
                )

                data["AVG_VALUE20"] = (
                    data["VALUE"]
                    .rolling(20)
                    .mean()
                )

                avg_value20_series = (
                    data["AVG_VALUE20"]
                    .dropna()
                )

                if avg_value20_series.empty:
                    continue

                avg_value20 = float(
                    avg_value20_series.iloc[-1]
                )

                if avg_value20 < MIN_LIQUIDITY:
                    continue

                # =========================================
                # WEEKLY
                # =========================================
                weekly["MA20W"] = (
                    weekly["Close"]
                    .rolling(20)
                    .mean()
                )

                weekly_close_series = (
                    weekly["Close"]
                    .dropna()
                )

                weekly_ma20_series = (
                    weekly["MA20W"]
                    .dropna()
                )

                if (
                    weekly_close_series.empty
                    or
                    weekly_ma20_series.empty
                ):
                    continue

                weekly_close = float(
                    weekly_close_series.iloc[-1]
                )

                weekly_ma20 = float(
                    weekly_ma20_series.iloc[-1]
                )

                weekly_up = (
                    weekly_close >
                    weekly_ma20
                )

                # =========================================
                # SAFE LAST VALUE
                # =========================================
                try:

                    close = float(
                        close_series.iloc[-1]
                    )

                    ma3 = float(
                        data["MA3"].dropna().iloc[-1]
                    )

                    ma5 = float(
                        data["MA5"].dropna().iloc[-1]
                    )

                    ma10 = float(
                        data["MA10"].dropna().iloc[-1]
                    )

                    ma20 = float(
                        data["MA20"].dropna().iloc[-1]
                    )

                    ma50 = float(
                        data["MA50"].dropna().iloc[-1]
                    )

                    ma100 = float(
                        data["MA100"].dropna().iloc[-1]
                    )

                    ma200 = float(
                        data["MA200"].dropna().iloc[-1]
                    )

                    rsi = round(
                        float(
                            data["RSI"]
                            .dropna()
                            .iloc[-1]
                        ),
                        2
                    )

                    atr = float(
                        data["ATR"]
                        .dropna()
                        .iloc[-1]
                    )

                    atr_percent = round(
                        float(
                            data["ATR_PERCENT"]
                            .dropna()
                            .iloc[-1]
                        ),
                        2
                    )

                except:
                    continue

                # =========================================
                # REJECTION
                # =========================================
                recent_4 = data.tail(4).copy()

                ma20_reject = count_rejections(
                    recent_4,
                    "MA20",
                    0.005
                )

                ma50_reject = count_rejections(
                    recent_4,
                    "MA50",
                    0.01
                )

                ma200_reject = count_rejections(
                    recent_4,
                    "MA200",
                    0.015
                )

                rejection_text = []

                if ma20_reject >= 1:
                    rejection_text.append("MA20")

                if ma50_reject >= 1:
                    rejection_text.append("MA50")

                if ma200_reject >= 1:
                    rejection_text.append("MA200")

                if len(rejection_text) == 0:

                    ma_rejection_status = "None"

                else:

                    ma_rejection_status = ",".join(
                        rejection_text
                    )

                # =========================================
                # STATE
                # =========================================
                S_state = get_state(
                    close,
                    ma3,
                    ma5,
                    ma10,
                    ma20,
                    ma20,
                    ma20
                )

                # =========================================
                # SPREAD
                # =========================================
                ma_valid = [
                    ma3,
                    ma5,
                    ma10,
                    ma20,
                    ma50,
                    ma100
                ]

                spread_percent = round(
                    (
                        max(ma_valid)
                        -
                        min(ma_valid)
                    )
                    /
                    close
                    * 100,
                    2
                )

                # =========================================
                # RS SAFE
                # =========================================
                if len(close_series) < 60:
                    continue

                if len(ihsg_close) < 60:
                    continue

                stock_return = (

                    close_series.iloc[-1]
                    /
                    close_series.iloc[-60]

                ) - 1

                ihsg_return = (

                    ihsg_close.iloc[-1]
                    /
                    ihsg_close.iloc[-60]

                ) - 1

                rs_score = round(
                    stock_return -
                    ihsg_return,
                    2
                )

                # =========================================
                # SCORE
                # =========================================
                final_score = round(

                    (
                        rs_score * 20
                    )

                    +

                    (
                        volume_ratio * 5
                    )

                    +

                    (
                        10 - spread_percent
                    ),

                    2

                )

                # =========================================
                # QUALITY
                # =========================================
                if final_score >= 40:

                    quality = "🔥 SUPER STRONG"

                elif final_score >= 30:

                    quality = "🚀 STRONG"

                elif final_score >= 18:

                    quality = "✅ GOOD"

                elif final_score >= 8:

                    quality = "👀 WATCHLIST"

                else:

                    quality = "❌ AVOID"

                # =========================================
                # SAVE
                # =========================================
                hasil.append({

                    "Saham": kode.replace(".JK", ""),

                    "Final Score": final_score,

                    "Market Regime": market_regime,

                    "Quality": quality,

                    "Close": int(close),

                    "S.STATE": S_state,

                    "MA_Rejection_Status":
                    ma_rejection_status,

                    "Spread %": spread_percent,

                    "RSI": rsi,

                    "ATR %": atr_percent,

                    "RS": rs_score,

                    "Volume Ratio": volume_ratio,

                    "Weekly":
                    "UPTREND"
                    if weekly_up
                    else "DOWNTREND",

                    "Liquidity(B)": round(
                        avg_value20 / 1_000_000_000,
                        2
                    )

                })

            except:
                continue

        # =========================================
        # DATAFRAME
        # =========================================
        df = pd.DataFrame(hasil)

        market_df = pd.DataFrame(
            market_results
        )

        # =========================================
        # FINAL
        # =========================================
        if not df.empty:

            df = df.sort_values(
                by="Final Score",
                ascending=False
            ).reset_index(drop=True)

            st.success(
                "SCREENING SELESAI"
            )

            st.dataframe(
                df,
                use_container_width=True
            )

            # =========================================
            # EXPORT EXCEL
            # =========================================
            output = BytesIO()

            with pd.ExcelWriter(
                output,
                engine="openpyxl"
            ) as writer:

                summary_df = pd.DataFrame([

                    {
                        "Timestamp":
                        datetime.now().strftime(
                            "%d-%m-%Y %H:%M:%S"
                        ),

                        "Market Score":
                        market_score,

                        "Market Regime":
                        market_regime
                    }

                ])

                summary_df.to_excel(
                    writer,
                    sheet_name="Market",
                    index=False,
                    startrow=0
                )

                market_df.to_excel(
                    writer,
                    sheet_name="Market",
                    index=False,
                    startrow=4
                )

                df.to_excel(
                    writer,
                    sheet_name="Screener",
                    index=False
                )

            output.seek(0)

            st.download_button(

                label="📥 Download Excel",

                data=output,

                file_name=
                "HYBRID_SCREENING_MARKET.xlsx",

                mime=
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

            )

        else:

            st.warning(
                "Tidak ada saham yang lolos screening."
            )

    except Exception as e:

        st.error(
            f"ERROR BESAR: {e}"
        )
