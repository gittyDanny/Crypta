import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# hier fügen wir den src-Ordner zum Python-Pfad hinzu,
# damit Imports aus services, connectors usw. funktionieren
SRC_PATH = Path(__file__).resolve().parents[1]
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from services.market_service import load_market_overview
from services.trade_history_service import load_trade_history, summarize_trade_history


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

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Instrument", overview["instrument"])
    col2.metric("Aktueller Preis", f'{overview["last_price"]:.2f}')
    col3.metric("Preisveränderung", f'{overview["simple_return"]:.2%}')
    col4.metric("Signal", overview["signal"])

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

    # ab hier laden wir die gespeicherte Trade-Historie aus der CSV
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