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
from services.autotrader_trade_service import load_autotrader_trades
from services.market_service import load_market_overview
from services.pnl_service import calculate_pnl_summary
from services.trade_history_service import load_trade_history, summarize_trade_history


def render_signal_box(signal):
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
    _, chart_df, forecast_df = build_chart_dataframes(overview)

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
    mean_error = accuracy_summary.get("mean_error")
    last_abs_error = accuracy_summary.get("last_abs_error")

    acc_col1, acc_col2, acc_col3, acc_col4, acc_col5, acc_col6 = st.columns(6)
    acc_col1.metric("Forecasts gesamt", total_count)
    acc_col2.metric("Ausgewertet", evaluated_count)
    acc_col3.metric("Offen", pending_count)
    acc_col4.metric("MAE", "-" if mae is None else f"{mae:.2f}")
    acc_col5.metric("MAPE", "-" if mape is None else f"{mape:.2f}%")
    acc_col6.metric("Ø Fehler", "-" if mean_error is None else f"{mean_error:.2f}")

    st.write(
        f"Die Durchschnittswerte basieren aktuell auf **{evaluated_count} ausgewerteten Forecasts**."
    )

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


def _find_nearest_position(timestamp_series, target_timestamp):
    differences = (timestamp_series - target_timestamp).abs()
    return int(differences.idxmin())


def _build_trade_duration_text(selected_trade):
    entry_timestamp = pd.to_datetime(selected_trade["entry_timestamp"])

    if pd.isna(entry_timestamp):
        return "-"

    if pd.isna(selected_trade["exit_timestamp"]):
        end_timestamp = pd.Timestamp.now()
    else:
        end_timestamp = pd.to_datetime(selected_trade["exit_timestamp"])

    duration = end_timestamp - entry_timestamp
    total_minutes = int(duration.total_seconds() // 60)

    hours = total_minutes // 60
    minutes = total_minutes % 60

    if hours > 0:
        return f"{hours}h {minutes}m"

    return f"{minutes}m"


def _resolve_trade_chart_times(trade_row):
    entry_chart_timestamp = pd.to_datetime(
        trade_row.get("entry_chart_timestamp"),
        errors="coerce"
    )

    exit_chart_timestamp = pd.to_datetime(
        trade_row.get("exit_chart_timestamp"),
        errors="coerce"
    )

    if pd.isna(entry_chart_timestamp):
        entry_chart_timestamp = pd.to_datetime(
            trade_row.get("entry_signal_candle_timestamp"),
            errors="coerce"
        )

    if pd.isna(entry_chart_timestamp):
        entry_chart_timestamp = pd.to_datetime(
            trade_row.get("entry_timestamp"),
            errors="coerce"
        )

    return entry_chart_timestamp, exit_chart_timestamp


def _get_candle_time_delta(chart_df):
    sorted_df = chart_df.sort_values("timestamp").copy()

    if len(sorted_df) < 2:
        return pd.Timedelta(minutes=1)

    time_differences = sorted_df["timestamp"].diff().dropna()

    if time_differences.empty:
        return pd.Timedelta(minutes=1)

    median_delta = time_differences.median()

    if pd.isna(median_delta) or median_delta <= pd.Timedelta(0):
        return pd.Timedelta(minutes=1)

    return median_delta


def build_autotrader_trade_view_figure(chart_df, trade_row):
    entry_chart_timestamp, exit_chart_timestamp = _resolve_trade_chart_times(trade_row)

    if pd.isna(entry_chart_timestamp):
        entry_chart_timestamp = chart_df["timestamp"].iloc[-1]

    entry_price = float(trade_row["entry_price"])
    stop_loss = float(trade_row["stop_loss"])
    take_profit = float(trade_row["take_profit"])
    side = str(trade_row["side"])

    working_df = chart_df.sort_values("timestamp").reset_index(drop=True).copy()
    candle_delta = _get_candle_time_delta(working_df)

    entry_pos = _find_nearest_position(working_df["timestamp"], entry_chart_timestamp)

    if pd.notna(exit_chart_timestamp):
        exit_pos = _find_nearest_position(working_df["timestamp"], exit_chart_timestamp)
    else:
        exit_pos = len(working_df) - 1
        exit_chart_timestamp = working_df["timestamp"].iloc[exit_pos]

    start_pos = max(0, min(entry_pos, exit_pos) - 3)
    end_pos = min(len(working_df) - 1, max(entry_pos, exit_pos) + 4)

    trade_chart_df = working_df.iloc[start_pos:end_pos + 1].copy()

    zone_start = working_df["timestamp"].iloc[entry_pos]
    zone_end = working_df["timestamp"].iloc[exit_pos]

    if exit_pos == entry_pos:
        zone_end = zone_start + candle_delta

    trade_fig = go.Figure(
        data=[
            go.Candlestick(
                x=trade_chart_df["timestamp"],
                open=trade_chart_df["open"],
                high=trade_chart_df["high"],
                low=trade_chart_df["low"],
                close=trade_chart_df["close"],
                name="Candles"
            )
        ]
    )

    if side == "LONG":
        trade_fig.add_shape(
            type="rect",
            x0=zone_start,
            x1=zone_end,
            y0=entry_price,
            y1=take_profit,
            fillcolor="rgba(34, 197, 94, 0.14)",
            line=dict(color="rgba(34, 197, 94, 0.30)", width=1),
            layer="below"
        )

        trade_fig.add_shape(
            type="rect",
            x0=zone_start,
            x1=zone_end,
            y0=stop_loss,
            y1=entry_price,
            fillcolor="rgba(239, 68, 68, 0.14)",
            line=dict(color="rgba(239, 68, 68, 0.30)", width=1),
            layer="below"
        )
    else:
        trade_fig.add_shape(
            type="rect",
            x0=zone_start,
            x1=zone_end,
            y0=take_profit,
            y1=entry_price,
            fillcolor="rgba(34, 197, 94, 0.14)",
            line=dict(color="rgba(34, 197, 94, 0.30)", width=1),
            layer="below"
        )

        trade_fig.add_shape(
            type="rect",
            x0=zone_start,
            x1=zone_end,
            y0=entry_price,
            y1=stop_loss,
            fillcolor="rgba(239, 68, 68, 0.14)",
            line=dict(color="rgba(239, 68, 68, 0.30)", width=1),
            layer="below"
        )

    trade_fig.add_shape(
        type="line",
        x0=zone_start,
        x1=zone_end,
        y0=entry_price,
        y1=entry_price,
        line=dict(color="#22d3ee", width=2)
    )

    trade_fig.add_shape(
        type="line",
        x0=zone_start,
        x1=zone_end,
        y0=stop_loss,
        y1=stop_loss,
        line=dict(color="#ef4444", width=2)
    )

    trade_fig.add_shape(
        type="line",
        x0=zone_start,
        x1=zone_end,
        y0=take_profit,
        y1=take_profit,
        line=dict(color="#22c55e", width=2)
    )

    trade_fig.add_shape(
        type="line",
        x0=zone_start,
        x1=zone_start,
        y0=min(stop_loss, take_profit),
        y1=max(stop_loss, take_profit),
        line=dict(color="#94a3b8", width=1, dash="dot")
    )

    trade_fig.add_shape(
        type="line",
        x0=zone_end,
        x1=zone_end,
        y0=min(stop_loss, take_profit),
        y1=max(stop_loss, take_profit),
        line=dict(color="#94a3b8", width=1, dash="dot")
    )

    entry_label = "Long Entry" if side == "LONG" else "Short Entry"

    trade_fig.add_trace(
        go.Scatter(
            x=[zone_start],
            y=[entry_price],
            mode="markers+text",
            name="Entry",
            marker=dict(symbol="triangle-right", size=12, color="#60a5fa"),
            text=[entry_label],
            textposition="bottom center"
        )
    )

    if pd.notna(trade_row["exit_price"]):
        exit_label = "-" if pd.isna(trade_row["exit_reason"]) else str(trade_row["exit_reason"])
        exit_marker_x = zone_end if exit_pos == entry_pos else working_df["timestamp"].iloc[exit_pos]

        trade_fig.add_trace(
            go.Scatter(
                x=[exit_marker_x],
                y=[float(trade_row["exit_price"])],
                mode="markers+text",
                name="Exit",
                marker=dict(symbol="x", size=12, color="#f8fafc"),
                text=[exit_label],
                textposition="top center"
            )
        )

    trade_fig.update_layout(
        title="Autotrader Trade View",
        xaxis_title="Zeit",
        yaxis_title="Preis",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=560
    )

    return trade_fig


def render_trade_details_block(selected_trade, chart_df, title):
    st.markdown(f"**{title}**")

    duration_text = _build_trade_duration_text(selected_trade)

    info_col1, info_col2, info_col3, info_col4, info_col5, info_col6 = st.columns(6)
    info_col1.metric("Status", str(selected_trade["status"]))
    info_col2.metric("Side", str(selected_trade["side"]))
    info_col3.metric("Entry", f"{float(selected_trade['entry_price']):.2f}")
    info_col4.metric("Stop Loss", f"{float(selected_trade['stop_loss']):.2f}")
    info_col5.metric("Take Profit", f"{float(selected_trade['take_profit']):.2f}")
    info_col6.metric("RR", f"{float(selected_trade['rr_ratio']):.2f}")

    info_row2_col1, info_row2_col2, info_row2_col3, info_row2_col4 = st.columns(4)
    info_row2_col1.metric("Hebel", f"{float(selected_trade['leverage']):.1f}x")
    info_row2_col2.metric("Positionsgröße", f"{float(selected_trade['position_size_btc']):.4f} BTC")
    info_row2_col3.metric("Dauer", duration_text)
    info_row2_col4.metric("Timeframe", str(selected_trade["bar"]))

    info_row3_col1, info_row3_col2, info_row3_col3 = st.columns(3)
    info_row3_col1.metric(
        "Exit",
        "-" if pd.isna(selected_trade["exit_price"]) else f"{float(selected_trade['exit_price']):.2f}"
    )
    info_row3_col2.metric(
        "Exit Reason",
        "-" if pd.isna(selected_trade["exit_reason"]) else str(selected_trade["exit_reason"])
    )
    info_row3_col3.metric(
        "PnL USDT",
        "-" if pd.isna(selected_trade["pnl_usdt"]) else f"{float(selected_trade['pnl_usdt']):.4f}"
    )

    trade_fig = build_autotrader_trade_view_figure(chart_df, selected_trade)
    st.plotly_chart(trade_fig, width="stretch")


def render_autotrader_trade_view(overview):
    st.subheader("Autotrader Trade View")

    _, chart_df, _ = build_chart_dataframes(overview)
    autotrader_trade_df = load_autotrader_trades()

    if autotrader_trade_df.empty:
        st.info("Es gibt noch keine strukturierten Autotrader-Trades mit SL/TP.")
        return

    filtered_df = autotrader_trade_df[
        autotrader_trade_df["instrument"] == overview["instrument"]
    ].copy()

    if filtered_df.empty:
        st.info("Für dieses Instrument gibt es noch keine Autotrader-Trades.")
        return

    open_trades_df = filtered_df[filtered_df["status"] == "OPEN"].copy()
    closed_trades_df = filtered_df[filtered_df["status"] == "CLOSED"].copy()

    if not open_trades_df.empty:
        open_trades_df = open_trades_df.sort_values("entry_timestamp", ascending=False)
        active_trade = open_trades_df.iloc[0]

        if str(active_trade["bar"]) != str(overview["bar"]):
            st.warning(
                f"Der aktive Trade wurde auf Basis von {active_trade['bar']} eröffnet, "
                f"du betrachtest gerade aber {overview['bar']}-Candles."
            )

        render_trade_details_block(
            active_trade,
            chart_df,
            "Aktiver Trade"
        )
    else:
        st.info("Aktuell gibt es keinen offenen Autotrader-Trade.")

    st.divider()

    if closed_trades_df.empty:
        st.info("Es gibt noch keine geschlossenen strukturierten Autotrader-Trades.")
        return

    closed_trades_df = closed_trades_df.sort_values("entry_timestamp", ascending=False).head(20).copy()

    trade_label_map = {}

    for _, row in closed_trades_df.iterrows():
        entry_time = row["entry_timestamp"]
        side = row["side"]
        trade_bar = row["bar"]

        if pd.isna(entry_time):
            label = f"{row['trade_id']} | {side} | {trade_bar} | CLOSED"
        else:
            label = f"{entry_time.strftime('%Y-%m-%d %H:%M')} | {side} | {trade_bar} | CLOSED"

        trade_label_map[row["trade_id"]] = label

    selected_trade_id = st.selectbox(
        "Geschlossenen Trade auswählen",
        options=list(trade_label_map.keys()),
        format_func=lambda trade_id: trade_label_map[trade_id],
        key="selected_closed_autotrader_trade_id"
    )

    selected_trade = closed_trades_df[closed_trades_df["trade_id"] == selected_trade_id].iloc[0]

    if str(selected_trade["bar"]) != str(overview["bar"]):
        st.warning(
            f"Der ausgewählte geschlossene Trade wurde auf Basis von {selected_trade['bar']} eröffnet, "
            f"du betrachtest gerade aber {overview['bar']}-Candles."
        )

    render_trade_details_block(
        selected_trade,
        chart_df,
        "Historischer Trade"
    )

    st.caption(
        "Grün zeigt die Zielzone, Rot die Risikozone. "
        "Die vertikalen Linien markieren Beginn und Ende der Trade-Dauer."
    )


def render_autotrader_status(overview):
    runtime_state = load_runtime_state()

    st.subheader("Autotrader Live-Status")

    bot_enabled = runtime_state.get("bot_enabled", True)
    reward_multiple = float(runtime_state.get("reward_multiple", 2.0))
    leverage = float(runtime_state.get("leverage", 1.0))
    auto_leverage_enabled = bool(runtime_state.get("auto_leverage_enabled", True))
    target_risk_pct = float(runtime_state.get("target_risk_pct", 0.35))
    min_leverage = float(runtime_state.get("min_leverage", 1.0))
    max_leverage = float(runtime_state.get("max_leverage", 3.0))
    position_size_btc = float(runtime_state.get("position_size_btc", 0.01))
    cooldown_candles = int(runtime_state.get("cooldown_candles", 2))

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
    worker_last_exit_reason = runtime_state.get("worker_last_exit_reason")
    active_trade_side = runtime_state.get("active_trade_side")
    active_trade_stop_loss = runtime_state.get("active_trade_stop_loss")
    active_trade_take_profit = runtime_state.get("active_trade_take_profit")
    active_trade_rr_ratio = runtime_state.get("active_trade_rr_ratio")
    active_trade_leverage = runtime_state.get("active_trade_leverage")

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

    row3_col1, row3_col2, row3_col3, row3_col4 = st.columns(4)
    row3_col1.metric(
        "Technisches Signal",
        "-" if worker_last_technical_signal is None else str(worker_last_technical_signal)
    )
    row3_col2.metric(
        "Letztes Runtime-Signal",
        "-" if worker_last_signal is None else str(worker_last_signal)
    )
    row3_col3.metric(
        "Stop Loss",
        "-" if active_trade_stop_loss is None else f"{float(active_trade_stop_loss):.2f}"
    )
    row3_col4.metric(
        "Take Profit",
        "-" if active_trade_take_profit is None else f"{float(active_trade_take_profit):.2f}"
    )

    row4_col1, row4_col2, row4_col3, row4_col4 = st.columns(4)
    row4_col1.metric("Reward Multiple", f"{reward_multiple:.2f}R")
    row4_col2.metric("Aktiver Hebel", "-" if active_trade_leverage is None else f"{float(active_trade_leverage):.2f}x")
    row4_col3.metric("Positionsgröße", f"{position_size_btc:.4f} BTC")
    row4_col4.metric(
        "Aktive Side",
        "-" if active_trade_side is None else str(active_trade_side)
    )

    row5_col1, row5_col2, row5_col3, row5_col4 = st.columns(4)
    row5_col1.metric("Auto-Leverage", "AN" if auto_leverage_enabled else "AUS")
    row5_col2.metric("Zielrisiko", f"{target_risk_pct:.2f}%")
    row5_col3.metric("Hebel-Range", f"{min_leverage:.1f}x - {max_leverage:.1f}x")
    row5_col4.metric("Cooldown", f"{cooldown_candles} Candles")

    if active_trade_rr_ratio is not None:
        st.write(f"Aktuelles Chance-Risiko-Verhältnis: **{float(active_trade_rr_ratio):.2f}**")

    if worker_last_trade_timestamp is not None:
        st.write(f"Letzter Auto-Trade: **{worker_last_trade_timestamp}**")

    if worker_last_exit_reason:
        st.write(f"Letzter Exit-Grund: **{worker_last_exit_reason}**")

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
    render_autotrader_trade_view(overview)
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
        index=0
    )

    candle_limit = st.slider(
        "Anzahl Candles",
        min_value=5,
        max_value=120,
        value=120,
        step=1
    )

    run_analysis = st.button("Analyse starten", width="stretch")

    live_mode = st.toggle("Live-Aktualisierung", value=True)

    refresh_seconds = st.slider(
        "Refresh alle Sekunden",
        min_value=5,
        max_value=60,
        value=5,
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

    reward_multiple = st.number_input(
        "Reward Multiple (R)",
        min_value=1.0,
        max_value=10.0,
        value=float(sidebar_runtime_state.get("reward_multiple", 2.0)),
        step=0.25,
        key="sidebar_reward_multiple"
    )

    manual_leverage = st.number_input(
        "Manueller Hebel",
        min_value=1.0,
        max_value=20.0,
        value=float(sidebar_runtime_state.get("leverage", 1.0)),
        step=0.5,
        key="sidebar_leverage"
    )

    auto_leverage_enabled = st.toggle(
        "Auto-Leverage",
        value=bool(sidebar_runtime_state.get("auto_leverage_enabled", True)),
        key="sidebar_auto_leverage_enabled"
    )

    target_risk_pct = st.number_input(
        "Zielrisiko pro Trade (%)",
        min_value=0.05,
        max_value=5.00,
        value=float(sidebar_runtime_state.get("target_risk_pct", 0.35)),
        step=0.05,
        disabled=not auto_leverage_enabled,
        key="sidebar_target_risk_pct"
    )

    min_leverage = st.number_input(
        "Min Hebel",
        min_value=1.0,
        max_value=20.0,
        value=float(sidebar_runtime_state.get("min_leverage", 1.0)),
        step=0.5,
        disabled=not auto_leverage_enabled,
        key="sidebar_min_leverage"
    )

    max_leverage = st.number_input(
        "Max Hebel",
        min_value=1.0,
        max_value=20.0,
        value=float(sidebar_runtime_state.get("max_leverage", 3.0)),
        step=0.5,
        disabled=not auto_leverage_enabled,
        key="sidebar_max_leverage"
    )

    position_size_btc = st.number_input(
        "Positionsgröße BTC",
        min_value=0.0010,
        max_value=1.0000,
        value=float(sidebar_runtime_state.get("position_size_btc", 0.01)),
        step=0.0010,
        format="%.4f",
        key="sidebar_position_size_btc"
    )

    cooldown_candles = st.number_input(
        "Cooldown Candles",
        min_value=0,
        max_value=20,
        value=int(sidebar_runtime_state.get("cooldown_candles", 2)),
        step=1,
        key="sidebar_cooldown_candles"
    )

    state_changed = False

    if autotrader_enabled != sidebar_runtime_state.get("bot_enabled", True):
        sidebar_runtime_state["bot_enabled"] = autotrader_enabled
        state_changed = True

    if float(reward_multiple) != float(sidebar_runtime_state.get("reward_multiple", 2.0)):
        sidebar_runtime_state["reward_multiple"] = float(reward_multiple)
        state_changed = True

    if float(manual_leverage) != float(sidebar_runtime_state.get("leverage", 1.0)):
        sidebar_runtime_state["leverage"] = float(manual_leverage)
        state_changed = True

    if bool(auto_leverage_enabled) != bool(sidebar_runtime_state.get("auto_leverage_enabled", True)):
        sidebar_runtime_state["auto_leverage_enabled"] = bool(auto_leverage_enabled)
        state_changed = True

    if float(target_risk_pct) != float(sidebar_runtime_state.get("target_risk_pct", 0.35)):
        sidebar_runtime_state["target_risk_pct"] = float(target_risk_pct)
        state_changed = True

    if float(min_leverage) != float(sidebar_runtime_state.get("min_leverage", 1.0)):
        sidebar_runtime_state["min_leverage"] = float(min_leverage)
        state_changed = True

    if float(max_leverage) != float(sidebar_runtime_state.get("max_leverage", 3.0)):
        sidebar_runtime_state["max_leverage"] = float(max_leverage)
        state_changed = True

    if float(position_size_btc) != float(sidebar_runtime_state.get("position_size_btc", 0.01)):
        sidebar_runtime_state["position_size_btc"] = float(position_size_btc)
        state_changed = True

    if int(cooldown_candles) != int(sidebar_runtime_state.get("cooldown_candles", 2)):
        sidebar_runtime_state["cooldown_candles"] = int(cooldown_candles)
        state_changed = True

    if state_changed:
        save_runtime_state(sidebar_runtime_state)
        sidebar_runtime_state = load_runtime_state()

    st.caption(
        "Auto-Leverage nutzt Stop-Distanz und Zielrisiko. "
        "Später kann hier zusätzlich KI-/News-/Fundamental-Logik einfließen."
    )

refresh_value = f"{refresh_seconds}s" if live_mode else None


def load_current_overview():
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