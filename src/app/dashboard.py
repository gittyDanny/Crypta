import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# hier fügen wir den src-Ordner zum Python-Pfad hinzu,
# damit Imports aus services, connectors usw. funktionieren
SRC_PATH = Path(__file__).resolve().parents[1]
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from execution.paper_trader import execute_paper_trade
from services.market_service import load_market_overview
from services.trade_history_service import load_trade_history, summarize_trade_history

def render_signal_box(signal):
    # hier ordnen wir jedem Signal eine Farbe und einen kleinen Beschreibungstext zu
    if signal == "BUY":
        background_color = "#123524"
        border_color = "#22c55e"
        text_color = "#86efac"
        description = "Einfaches Kaufsignal"
    elif signal == "SELL":
        background_color = "#3b1219"
        border_color = "#ef4444"
        text_color = "#fca5a5"
        description = "Einfaches Verkaufssignal"
    else:
        background_color = "#3a2f12"
        border_color = "#f59e0b"
        text_color = "#fcd34d"
        description = "Neutrales Haltesignal"

    st.markdown(
        f"""
        <div style="
            background-color: {background_color};
            border: 2px solid {border_color};
            border-radius: 12px;
            padding: 18px;
            margin-top: 10px;
            margin-bottom: 20px;
        ">
            <div style="font-size: 14px; color: {text_color}; opacity: 0.9;">
                Aktuelles Signal
            </div>
            <div style="font-size: 34px; font-weight: bold; color: {text_color}; margin-top: 8px;">
                {signal}
            </div>
            <div style="font-size: 16px; color: {text_color}; margin-top: 8px;">
                {description}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

st.set_page_config(page_title="Crypta", layout="wide")

st.title("Crypta")
st.caption("Modulares Bitcoin Analyse-Dashboard")

with st.sidebar:
    st.header("Einstellungen")

    instrument = st.selectbox(
        "Instrument",
        ["BTC-USDT", "ETH-USDT"],
        index=0
    )

    bar = st.selectbox(
        "Timeframe",
        ["15m", "1H", "4H", "1D"],
        index=1
    )

    candle_limit = st.slider(
        "Anzahl Candles",
        min_value=5,
        max_value=100,
        value=24,
        step=1
    )

    run_analysis = st.button("Analyse starten", width="stretch")

if run_analysis or "overview" not in st.session_state:
    try:
        st.session_state["overview"] = load_market_overview(
            inst_id=instrument,
            bar=bar,
            limit=str(candle_limit)
        )
    except Exception as e:
        st.error(f"Fehler beim Laden der Marktdaten: {e}")

if "overview" in st.session_state:
    overview = st.session_state["overview"]

    candles_df = pd.DataFrame(overview["candles"])

    candles_df["timestamp"] = pd.to_datetime(
        candles_df["timestamp"].astype("int64"),
        unit="ms"
    )

    chart_df = candles_df.sort_values("timestamp").copy()
    volume_colors = []

    for _, row in chart_df.iterrows():
        if row["close"] >= row["open"]:
            volume_colors.append("#22c55e")
        else:
            volume_colors.append("#ef4444")

    volume_fig = go.Figure(
        data=[
            go.Bar(
                x=chart_df["timestamp"],
                y=chart_df["volume"],
                name="Volumen",
                marker_color=volume_colors
            )
        ]
    )

    volume_fig.update_layout(
        title="Volumen",
        xaxis_title="Zeit",
        yaxis_title="BTC Volumen",
        template="plotly_dark",
        height=300
    )
    candlestick_fig = go.Figure(
        data=[
            go.Candlestick(
                x=chart_df["timestamp"],
                open=chart_df["open"],
                high=chart_df["high"],
                low=chart_df["low"],
                close=chart_df["close"],
                name="Candles"
            )
        ]
    )

    candlestick_fig.update_layout(
        title="Kerzenchart",
        xaxis_title="Zeit",
        yaxis_title="Preis",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=500
    )        

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Instrument", overview["instrument"])
    col2.metric("Aktueller Preis", f'{overview["last_price"]:.2f}')
    col3.metric("Preisveränderung", f'{overview["simple_return"]:.2%}')
    col4.metric("Signal", overview["signal"])

    render_signal_box(overview["signal"])

    st.subheader("Kerzenchart")
    st.plotly_chart(candlestick_fig, width="stretch")

    st.subheader("Volumen")
    st.plotly_chart(volume_fig, width="stretch")

    st.subheader("Schlusskurse")
    st.line_chart(
        chart_df.set_index("timestamp")["close"],
        width="stretch"
    )

    st.subheader("Kerzenchart")
    st.plotly_chart(candlestick_fig)

    st.subheader("Schlusskurse")
    st.line_chart(
        chart_df.set_index("timestamp")["close"],
        width="stretch"
    )

    st.subheader("Kurze Einordnung")
    latest_close = overview["candles"][0]["close"]

    st.write(f"Letzter Schlusskurs: **{latest_close:.2f}**")
    st.write(f"Durchschnittlicher Schlusskurs: **{overview['average_close']:.2f}**")
    st.write(f"Aktuelles Basissignal: **{overview['signal']}**")

    save_trade = st.button("Signal als Paper Trade speichern", width="stretch")

    if save_trade:
        paper_trade_result = execute_paper_trade(
            overview["signal"],
            overview["raw_ticker"]
        )
        st.success(
            f'Paper Trade gespeichert: '
            f'{paper_trade_result["instrument"]} | '
            f'{paper_trade_result["signal"]} | '
            f'{paper_trade_result["last_price"]:.2f}'
        )

    # hier laden wir die gespeicherte Trade-Historie immer,
    # damit sie auch ohne frischen Button-Klick sichtbar bleibt
    trade_df = load_trade_history()
    trade_summary = summarize_trade_history(trade_df)

    st.subheader("Paper-Trade-Historie")

    hist_col1, hist_col2, hist_col3, hist_col4 = st.columns(4)

    hist_col1.metric("Trades gesamt", trade_summary["total_trades"])
    hist_col2.metric("BUY", trade_summary["buy_count"])
    hist_col3.metric("SELL", trade_summary["sell_count"])
    hist_col4.metric("HOLD", trade_summary["hold_count"])

    if trade_summary["latest_trade"] is not None:
        latest_trade = trade_summary["latest_trade"]

        st.write("**Letzter gespeicherter Trade:**")
        st.write(
            f'{latest_trade["timestamp"]} | '
            f'{latest_trade["instrument"]} | '
            f'{latest_trade["signal"]} | '
            f'{latest_trade["last_price"]:.2f}'
        )

    if trade_df.empty:
        st.info("Es wurden noch keine Paper Trades gespeichert.")
    else:
        st.dataframe(
            trade_df.sort_values("timestamp", ascending=False),
            width="stretch",
            hide_index=True
        )