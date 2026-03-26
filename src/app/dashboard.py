import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# hier fügen wir den src-Ordner zum Python-Pfad hinzu,
# damit Imports aus services, connectors usw. funktionieren
SRC_PATH = Path(__file__).resolve().parents[1]
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from services.pnl_service import calculate_pnl_summary
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
    st.plotly_chart(candlestick_fig, use_container_width=True)

    st.subheader("Volumen")
    st.plotly_chart(volume_fig, use_container_width=True)

    st.subheader("Schlusskurse")
    st.line_chart(
        chart_df.set_index("timestamp")["close"],
        width="stretch"
    )

    st.subheader("Candles")
    st.dataframe(
        candles_df.sort_values("timestamp", ascending=False),
        width="stretch",
        hide_index=True
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
            f"Paper Trade gespeichert: "
            f"{paper_trade_result['instrument']} | "
            f"{paper_trade_result['signal']} | "
            f"{paper_trade_result['last_price']:.2f}"
        )

    trade_df = load_trade_history()
    trade_summary = summarize_trade_history(trade_df)

    pnl_summary = calculate_pnl_summary(
        trade_df,
        current_price=overview["last_price"],
        position_size=0.01
    )

    st.subheader("Paper-Trade PnL")

    realized_pnl = pnl_summary["realized_pnl"]
    unrealized_pnl = pnl_summary["unrealized_pnl"]
    total_pnl = pnl_summary["total_pnl"]
    position_status = pnl_summary["position_status"]
    position_size = pnl_summary["position_size"]
    closed_trades = pnl_summary["closed_trades"]
    entry_price = pnl_summary["entry_price"]
    trade_log_df = pnl_summary["trade_log_df"]

    pnl_col1, pnl_col2, pnl_col3, pnl_col4 = st.columns(4)

    pnl_col1.metric("Realisiert", f"{realized_pnl:.2f} USDT")
    pnl_col2.metric("Offen", f"{unrealized_pnl:.2f} USDT")
    pnl_col3.metric("Gesamt", f"{total_pnl:.2f} USDT")
    pnl_col4.metric("Position", position_status)

    st.write(f"Positionsgröße: **{position_size} BTC**")
    st.write(f"Geschlossene Trades: **{closed_trades}**")

    if entry_price is not None:
        st.write(f"Aktueller Entry-Preis der offenen Position: **{entry_price:.2f}**")

    if not trade_log_df.empty:
        pnl_chart_df = trade_log_df.sort_values("exit_timestamp").copy()

        pnl_fig = go.Figure(
            data=[
                go.Scatter(
                    x=pnl_chart_df["exit_timestamp"],
                    y=pnl_chart_df["cumulative_pnl"],
                    mode="lines+markers",
                    name="Kumulative PnL"
                )
            ]
        )

        pnl_fig.update_layout(
            title="Kumulative PnL",
            xaxis_title="Exit-Zeitpunkt",
            yaxis_title="USDT",
            template="plotly_dark",
            height=350
        )

        st.write("**PnL-Verlauf:**")
        st.plotly_chart(pnl_fig, use_container_width=True)

        st.write("**Abgeschlossene Trades:**")
        st.dataframe(
            trade_log_df.sort_values("exit_timestamp", ascending=False),
            width="stretch",
            hide_index=True
        )

    st.subheader("Paper-Trade-Historie")

    total_trades = trade_summary["total_trades"]
    buy_count = trade_summary["buy_count"]
    sell_count = trade_summary["sell_count"]
    hold_count = trade_summary["hold_count"]
    latest_trade = trade_summary["latest_trade"]

    hist_col1, hist_col2, hist_col3, hist_col4 = st.columns(4)

    hist_col1.metric("Trades gesamt", total_trades)
    hist_col2.metric("BUY", buy_count)
    hist_col3.metric("SELL", sell_count)
    hist_col4.metric("HOLD", hold_count)

    if latest_trade is not None:
        latest_timestamp = latest_trade["timestamp"]
        latest_instrument = latest_trade["instrument"]
        latest_signal = latest_trade["signal"]
        latest_last_price = float(latest_trade["last_price"])

        st.write("**Letzter gespeicherter Trade:**")
        st.write(
            f"{latest_timestamp} | "
            f"{latest_instrument} | "
            f"{latest_signal} | "
            f"{latest_last_price:.2f}"
        )

    if trade_df.empty:
        st.info("Es wurden noch keine Paper Trades gespeichert.")
    else:
        st.dataframe(
            trade_df.sort_values("timestamp", ascending=False),
            width="stretch",
            hide_index=True
        )