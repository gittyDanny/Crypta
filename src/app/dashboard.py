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

from execution.paper_trader import execute_paper_trade
from services.auto_trade_service import load_runtime_state, save_runtime_state
from services.market_service import load_market_overview
from services.pnl_service import calculate_pnl_summary
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


def build_chart_dataframes(overview):
    # hier wandeln wir die Candle-Liste in DataFrames um,
    # damit wir danach Charts und Tabellen einfacher bauen können
    candles_df = pd.DataFrame(overview["candles"])

    candles_df["timestamp"] = pd.to_datetime(
        candles_df["timestamp"].astype("int64"),
        unit="ms"
    )

    chart_df = candles_df.sort_values("timestamp").copy()

    forecast_df = pd.DataFrame(overview.get("forecast_points", []))

    if not forecast_df.empty:
        forecast_df["timestamp"] = pd.to_datetime(
            forecast_df["timestamp"].astype("int64"),
            unit="ms"
        )

    return candles_df, chart_df, forecast_df


def build_volume_figure(chart_df):
    # hier färben wir die Volumenbalken grün oder rot,
    # je nachdem ob die Kerze bullisch oder bärisch war
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

    return volume_fig


def build_candlestick_figure(chart_df, forecast_df):
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

    if not forecast_df.empty:
        candlestick_fig.add_trace(
            go.Scatter(
                x=forecast_df["timestamp"],
                y=forecast_df["close"],
                mode="lines+markers",
                name="Forecast",
                line=dict(width=2, dash="dash")
            )
        )

    candlestick_fig.update_layout(
        title="Kerzenchart",
        xaxis_title="Zeit",
        yaxis_title="Preis",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=500
    )

    return candlestick_fig


def build_close_figure(chart_df, forecast_df):
    close_fig = go.Figure()

    close_fig.add_trace(
        go.Scatter(
            x=chart_df["timestamp"],
            y=chart_df["close"],
            mode="lines",
            name="Real Close"
        )
    )

    if not forecast_df.empty and len(forecast_df) > 1:
        forecast_only_df = forecast_df.iloc[1:].copy()

        close_fig.add_trace(
            go.Scatter(
                x=forecast_only_df["timestamp"],
                y=forecast_only_df["close"],
                mode="lines+markers",
                name="Forecast",
                line=dict(width=2, dash="dash")
            )
        )

    close_fig.update_layout(
        title="Schlusskurse + Forecast",
        xaxis_title="Zeit",
        yaxis_title="Preis",
        template="plotly_dark",
        height=350
    )

    return close_fig


def render_market_summary(overview):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Instrument", overview["instrument"])
    col2.metric("Aktueller Preis", f'{overview["last_price"]:.2f}')
    col3.metric("Preisveränderung", f'{overview["simple_return"]:.2%}')
    col4.metric("Signal", overview["signal"])

    render_signal_box(overview["signal"])


def render_charts(overview):
    candles_df, chart_df, forecast_df = build_chart_dataframes(overview)

    candlestick_fig = build_candlestick_figure(chart_df, forecast_df)
    volume_fig = build_volume_figure(chart_df)
    close_fig = build_close_figure(chart_df, forecast_df)

    st.subheader("Kerzenchart")
    st.plotly_chart(candlestick_fig, width="stretch")

    if not forecast_df.empty:
        st.caption(
            "Forecast = einfache lineare Trendprojektion der letzten Schlusskurse, "
            "keine echte Preisvorhersage."
        )

    st.subheader("Volumen")
    st.plotly_chart(volume_fig, width="stretch")

    st.subheader("Schlusskurse + Forecast")
    st.plotly_chart(close_fig, width="stretch")


def render_forecast_accuracy(overview):
    st.subheader("Forecast Accuracy")

    accuracy_summary = overview.get("forecast_accuracy_summary", {})
    accuracy_by_step = overview.get("forecast_accuracy_by_step", [])
    recent_forecast_evaluations = overview.get("recent_forecast_evaluations", [])

    total_count = accuracy_summary.get("total_count", 0)
    evaluated_count = accuracy_summary.get("evaluated_count", 0)
    pending_count = accuracy_summary.get("pending_count", 0)
    mae = accuracy_summary.get("mae")
    mape = accuracy_summary.get("mape")
    last_abs_error = accuracy_summary.get("last_abs_error")

    acc_col1, acc_col2, acc_col3, acc_col4, acc_col5 = st.columns(5)
    acc_col1.metric("Forecasts gesamt", total_count)
    acc_col2.metric("Ausgewertet", evaluated_count)
    acc_col3.metric("Offen", pending_count)
    acc_col4.metric("MAE", "-" if mae is None else f"{mae:.2f}")
    acc_col5.metric("MAPE", "-" if mape is None else f"{mape:.2f}%")

    if last_abs_error is not None:
        st.write(f"Letzter absoluter Fehler: **{last_abs_error:.2f}**")

    with st.expander("Accuracy pro Forecast-Schritt", expanded=True):
        if len(accuracy_by_step) == 0:
            st.info("Es gibt noch keine Schritt-Auswertung.")
        else:
            step_df = pd.DataFrame(accuracy_by_step)
            st.dataframe(
                step_df,
                width="stretch",
                hide_index=True
            )

    with st.expander("Letzte Forecast-Auswertungen", expanded=False):
        if len(recent_forecast_evaluations) == 0:
            st.info("Es wurden noch keine Forecasts mit echten Ist-Werten verglichen.")
        else:
            accuracy_df = pd.DataFrame(recent_forecast_evaluations)
            st.dataframe(
                accuracy_df,
                width="stretch",
                hide_index=True
            )


def render_analysis_details(overview):
    st.subheader("Kurze Einordnung")

    signal_details = overview.get("signal_details", {})

    latest_close = signal_details.get("latest_close")
    average_close = signal_details.get("average_close", overview["average_close"])
    simple_return = signal_details.get("simple_return", overview["simple_return"])
    signal_reason = signal_details.get("reason", "Keine Begründung verfügbar.")
    close_vs_average = signal_details.get("close_vs_average", "UNBEKANNT")
    return_direction = signal_details.get("return_direction", "UNBEKANNT")

    if latest_close is not None:
        st.write(f"Letzter Schlusskurs: **{latest_close:.2f}**")
    else:
        st.write("Letzter Schlusskurs: **-**")

    st.write(f"Durchschnittlicher Schlusskurs: **{average_close:.2f}**")
    st.write(f"Preisveränderung: **{simple_return:.2%}**")
    st.write(f"Aktuelles Basissignal: **{overview['signal']}**")

    detail_col1, detail_col2 = st.columns(2)
    detail_col1.write(f"Close vs. Durchschnitt: **{close_vs_average}**")
    detail_col2.write(f"Return-Richtung: **{return_direction}**")

    st.info(signal_reason)


def render_save_trade_button(overview):
    save_trade = st.button(
        "Signal als Paper Trade speichern",
        width="stretch",
        key="save_paper_trade_button"
    )

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


def render_autotrader_status(overview):
    runtime_state = load_runtime_state()

    st.subheader("Autotrader Live-Status")

    bot_enabled = runtime_state.get("bot_enabled", True)
    worker_position_status = runtime_state["position_status"]
    worker_last_signal = runtime_state["last_signal"]
    worker_entry_price = runtime_state["entry_price"]
    worker_last_trade_timestamp = runtime_state["last_trade_timestamp"]
    worker_last_seen_at = runtime_state.get("worker_last_seen_at")
    worker_cycle_status = runtime_state.get("worker_cycle_status")
    worker_last_error = runtime_state.get("worker_last_error")
    worker_last_price = runtime_state.get("worker_last_price")
    worker_last_technical_signal = runtime_state.get("worker_last_technical_signal")
    worker_last_final_signal = runtime_state.get("worker_last_final_signal")
    worker_last_action = runtime_state.get("worker_last_action")

    row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
    row1_col1.metric("Autotrader", "AN" if bot_enabled else "AUS")
    row1_col2.metric("Runtime-Position", worker_position_status)
    row1_col3.metric(
        "Letztes Final-Signal",
        "-" if worker_last_final_signal is None else str(worker_last_final_signal)
    )
    row1_col4.metric(
        "Letzte Aktion",
        "-" if worker_last_action is None else str(worker_last_action)
    )

    row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
    row2_col1.metric(
        "Worker-Zyklus",
        "-" if worker_cycle_status is None else str(worker_cycle_status)
    )
    row2_col2.metric(
        "Heartbeat",
        "-" if worker_last_seen_at is None else str(worker_last_seen_at)
    )
    row2_col3.metric(
        "Letzter Preis",
        "-" if worker_last_price is None else f"{float(worker_last_price):.2f}"
    )
    row2_col4.metric(
        "Entry-Preis",
        "-" if worker_entry_price is None else f"{float(worker_entry_price):.2f}"
    )

    row3_col1, row3_col2, row3_col3 = st.columns(3)
    row3_col1.metric(
        "Technisches Signal",
        "-" if worker_last_technical_signal is None else str(worker_last_technical_signal)
    )
    row3_col2.metric(
        "Letztes Runtime-Signal",
        "-" if worker_last_signal is None else str(worker_last_signal)
    )
    row3_col3.metric(
        "Letzter Auto-Trade",
        "-" if worker_last_trade_timestamp is None else str(worker_last_trade_timestamp)
    )

    if bot_enabled:
        st.write("Der Autotrader ist aktiviert. Der Worker muss dafür in einem separaten Terminal laufen.")
    else:
        st.warning("Der Autotrader ist deaktiviert. Der Worker kann weiterlaufen, führt aber keine Trades aus.")

    if worker_last_error:
        st.error(f"Letzter Worker-Fehler: {worker_last_error}")


def render_pnl_section(overview):
    trade_df = load_trade_history()

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
    pnl_col4.metric("Paper-Trade Position", position_status)

    st.write(f"Positionsgröße: **{position_size} BTC**")
    st.write(f"Geschlossene Trades: **{closed_trades}**")

    if entry_price is not None:
        st.write(f"Aktueller Entry-Preis der offenen Paper-Trade-Position: **{entry_price:.2f}**")

    with st.expander("PnL-Verlauf und abgeschlossene Trades", expanded=False):
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

            st.plotly_chart(pnl_fig, width="stretch")
            st.dataframe(
                trade_log_df.sort_values("exit_timestamp", ascending=False),
                width="stretch",
                hide_index=True
            )
        else:
            st.info("Es gibt noch keine abgeschlossenen Trades.")


def render_tables_and_history(overview):
    candles_df, _, _ = build_chart_dataframes(overview)
    trade_df = load_trade_history()
    trade_summary = summarize_trade_history(trade_df)

    with st.expander("Candles", expanded=False):
        st.dataframe(
            candles_df.sort_values("timestamp", ascending=False),
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

    with st.expander("Komplette Trade-Historie", expanded=False):
        if trade_df.empty:
            st.info("Es wurden noch keine Paper Trades gespeichert.")
        else:
            st.dataframe(
                trade_df.sort_values("timestamp", ascending=False),
                width="stretch",
                hide_index=True
            )


def render_live_dashboard(overview):
    render_market_summary(overview)
    render_charts(overview)
    render_forecast_accuracy(overview)
    render_analysis_details(overview)
    render_save_trade_button(overview)
    render_autotrader_status(overview)
    render_pnl_section(overview)
    render_tables_and_history(overview)


st.set_page_config(page_title="Crypta", layout="wide")

st.title("Crypta")
st.caption("Modulares Bitcoin Analyse-Dashboard")

sidebar_runtime_state = load_runtime_state()

with st.sidebar:
    st.header("Einstellungen")

    instrument = st.selectbox(
        "Instrument",
        ["BTC-USDT", "ETH-USDT"],
        index=0
    )

    bar = st.selectbox(
        "Timeframe",
        ["1m", "5m", "15m", "1H", "4H", "1D"],
        index=3
    )

    candle_limit = st.slider(
        "Anzahl Candles",
        min_value=5,
        max_value=120,
        value=24,
        step=1
    )

    run_analysis = st.button("Analyse starten", width="stretch")

    live_mode = st.toggle("Live-Aktualisierung", value=True)

    refresh_seconds = st.slider(
        "Refresh alle Sekunden",
        min_value=5,
        max_value=60,
        value=10,
        step=5,
        disabled=not live_mode,
    )

    st.divider()
    st.subheader("Autotrader")

    autotrader_enabled = st.toggle(
        "Autotrader aktiv",
        value=sidebar_runtime_state.get("bot_enabled", True),
        key="sidebar_autotrader_enabled"
    )

    if autotrader_enabled != sidebar_runtime_state.get("bot_enabled", True):
        sidebar_runtime_state["bot_enabled"] = autotrader_enabled
        save_runtime_state(sidebar_runtime_state)
        sidebar_runtime_state = load_runtime_state()

    st.caption("Der Worker muss weiter in einem separaten Terminal laufen.")

refresh_value = f"{refresh_seconds}s" if live_mode else None


def load_current_overview():
    # hier kapseln wir den Ladeaufruf,
    # damit wir denselben Code für Button und Live-Refresh benutzen
    return load_market_overview(
        inst_id=instrument,
        bar=bar,
        limit=str(candle_limit)
    )


@st.fragment(run_every=refresh_value)
def render_live_fragment():
    try:
        overview = load_current_overview()
        st.session_state["overview"] = overview
    except Exception as e:
        st.error(f"Fehler beim Laden der Marktdaten: {e}")
        return

    render_live_dashboard(overview)


if run_analysis or "overview" not in st.session_state:
    try:
        st.session_state["overview"] = load_current_overview()
    except Exception as e:
        st.error(f"Fehler beim Laden der Marktdaten: {e}")

if live_mode:
    render_live_fragment()
elif "overview" in st.session_state:
    render_live_dashboard(st.session_state["overview"])