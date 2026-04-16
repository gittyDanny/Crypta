import json
from datetime import datetime
from pathlib import Path

from analysis.technical import calculate_average_close, calculate_simple_return
from connectors.okx_client import OKXClient
from execution.paper_trader import execute_paper_trade
from services.autotrader_trade_service import (
    append_open_autotrader_trade,
    close_autotrader_trade,
    create_trade_id,
)
from strategy.signal_engine import generate_signal


def _build_default_runtime_state():
    return {
        "bot_enabled": True,
        "last_signal": None,
        "position_status": "FLAT",
        "entry_price": None,
        "last_trade_timestamp": None,
        "worker_last_seen_at": None,
        "worker_cycle_status": "IDLE",
        "worker_last_error": None,
        "worker_last_price": None,
        "worker_last_technical_signal": None,
        "worker_last_final_signal": None,
        "worker_last_action": "NONE",
        "worker_last_exit_reason": None,
        "active_trade_id": None,
        "active_trade_stop_loss": None,
        "active_trade_take_profit": None,
        "active_trade_rr_ratio": None,
        "active_trade_opened_at": None,
    }


def load_runtime_state(file_path="runtime_state.json"):
    # hier laden wir den kleinen Zustands-Speicher,
    # und ergänzen fehlende Felder automatisch mit Standardwerten
    path = Path(file_path)

    if not path.exists():
        return _build_default_runtime_state()

    with open(path, "r", encoding="utf-8") as file:
        loaded_state = json.load(file)

    state = _build_default_runtime_state()
    state.update(loaded_state)
    return state


def save_runtime_state(state, file_path="runtime_state.json"):
    # hier speichern wir den aktuellen Zustand des Bots lokal als JSON
    merged_state = _build_default_runtime_state()
    merged_state.update(state)

    path = Path(file_path)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(merged_state, file, indent=2)

    return merged_state


def update_worker_snapshot(state, overview=None, action=None, cycle_status=None, error=None):
    # hier schreiben wir Live-Infos des Workers in den Runtime-State,
    # damit das Dashboard den Autotrader live verfolgen kann
    if overview is not None:
        state["worker_last_price"] = overview["last_price"]
        state["worker_last_technical_signal"] = overview["technical_signal"]
        state["worker_last_final_signal"] = overview.get("final_signal")
        state["last_signal"] = overview.get("final_signal")

    state["worker_last_seen_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if action is not None:
        state["worker_last_action"] = action

    if cycle_status is not None:
        state["worker_cycle_status"] = cycle_status

    if error is not None:
        state["worker_last_error"] = error
    elif cycle_status == "RUNNING":
        state["worker_last_error"] = None

    return state


def build_market_overview(inst_id="BTC-USDT", bar="1m", limit="30"):
    # hier holen wir die aktuellen Marktdaten und bauen daraus
    # die technische Kurzbewertung
    client = OKXClient()

    ticker_data = client.get_ticker(inst_id)
    candles = client.get_candles_as_dicts(inst_id, bar, limit)

    simple_return = calculate_simple_return(candles)
    average_close = calculate_average_close(candles)
    technical_signal = generate_signal(candles, simple_return, average_close)

    latest_market_data = ticker_data["data"][0]
    last_price = float(latest_market_data["last"])

    return {
        "instrument": inst_id,
        "bar": bar,
        "limit": limit,
        "last_price": last_price,
        "simple_return": simple_return,
        "average_close": average_close,
        "technical_signal": technical_signal,
        "raw_ticker": ticker_data,
        "candles": candles,
    }


def build_final_signal(technical_signal, news_signal=None):
    # heute ist der finale Entscheid noch identisch zum technischen Signal
    # später können wir hier News / KI / Sentiment mit reinmischen
    if news_signal is None:
        return technical_signal

    return technical_signal


def build_long_trade_plan(overview, reward_multiple=2.0):
    # hier bauen wir eine ganz einfache SL/TP-Logik für Long-Trades:
    # Stop Loss am Tief der Entry-Signal-Kerze und Take Profit bei 2R
    signal_candle = overview["candles"][0]

    entry_price = float(overview["last_price"])
    candle_low = float(signal_candle["low"])

    risk_per_unit = entry_price - candle_low

    if risk_per_unit <= 0:
        risk_per_unit = max(entry_price * 0.001, 10.0)
        stop_loss = entry_price - risk_per_unit
    else:
        stop_loss = candle_low

    take_profit = entry_price + reward_multiple * risk_per_unit
    reward_per_unit = take_profit - entry_price

    return {
        "entry_price": round(entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "risk_per_unit": round(risk_per_unit, 2),
        "reward_per_unit": round(reward_per_unit, 2),
        "rr_ratio": round(reward_per_unit / risk_per_unit, 2) if risk_per_unit != 0 else None,
        "signal_candle_timestamp": int(signal_candle["timestamp"]),
        "signal_candle_open": float(signal_candle["open"]),
        "signal_candle_high": float(signal_candle["high"]),
        "signal_candle_low": float(signal_candle["low"]),
        "signal_candle_close": float(signal_candle["close"]),
    }


def _format_candle_timestamp(timestamp_ms):
    return datetime.fromtimestamp(int(timestamp_ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")


def should_open_long(final_signal, state):
    return final_signal == "BUY" and state["position_status"] == "FLAT"


def get_exit_reason(overview, state):
    # hier prüfen wir Exit-Reihenfolge bewusst so:
    # erst Stop Loss / Take Profit, danach normales SELL-Signal
    if state["position_status"] != "LONG":
        return None

    current_price = float(overview["last_price"])
    stop_loss = state.get("active_trade_stop_loss")
    take_profit = state.get("active_trade_take_profit")
    final_signal = overview["final_signal"]

    if stop_loss is not None and current_price <= float(stop_loss):
        return "STOP_LOSS"

    if take_profit is not None and current_price >= float(take_profit):
        return "TAKE_PROFIT"

    if final_signal == "SELL":
        return "SELL_SIGNAL"

    return None


def open_long_trade(overview, state, trade_file_path="paper_trades.csv"):
    # hier öffnen wir eine neue Long-Position,
    # schreiben den Event-Trade und legen zusätzlich einen strukturierten Autotrade an
    trade_event = execute_paper_trade(
        "BUY",
        overview["raw_ticker"],
        file_path=trade_file_path
    )

    trade_plan = build_long_trade_plan(overview)
    trade_id = create_trade_id()

    autotrader_trade_row = {
        "trade_id": trade_id,
        "instrument": overview["instrument"],
        "bar": overview["bar"],
        "side": "LONG",
        "status": "OPEN",
        "entry_timestamp": trade_event["timestamp"],
        "entry_price": trade_plan["entry_price"],
        "entry_signal": overview["final_signal"],
        "entry_signal_candle_timestamp": _format_candle_timestamp(
            trade_plan["signal_candle_timestamp"]
        ),
        "entry_signal_candle_open": trade_plan["signal_candle_open"],
        "entry_signal_candle_high": trade_plan["signal_candle_high"],
        "entry_signal_candle_low": trade_plan["signal_candle_low"],
        "entry_signal_candle_close": trade_plan["signal_candle_close"],
        "stop_loss": trade_plan["stop_loss"],
        "take_profit": trade_plan["take_profit"],
        "risk_per_unit": trade_plan["risk_per_unit"],
        "reward_per_unit": trade_plan["reward_per_unit"],
        "rr_ratio": trade_plan["rr_ratio"],
        "exit_timestamp": None,
        "exit_price": None,
        "exit_reason": None,
        "pnl_usdt": None,
        "pnl_pct": None,
    }

    append_open_autotrader_trade(autotrader_trade_row)

    state["position_status"] = "LONG"
    state["entry_price"] = trade_plan["entry_price"]
    state["last_trade_timestamp"] = trade_event["timestamp"]
    state["worker_last_action"] = "OPEN_LONG"
    state["worker_last_exit_reason"] = None

    state["active_trade_id"] = trade_id
    state["active_trade_stop_loss"] = trade_plan["stop_loss"]
    state["active_trade_take_profit"] = trade_plan["take_profit"]
    state["active_trade_rr_ratio"] = trade_plan["rr_ratio"]
    state["active_trade_opened_at"] = trade_event["timestamp"]

    save_runtime_state(state)
    return trade_event, state


def close_long_trade(overview, state, exit_reason, trade_file_path="paper_trades.csv"):
    # hier schließen wir die offene Long-Position
    trade_event = execute_paper_trade(
        "SELL",
        overview["raw_ticker"],
        file_path=trade_file_path
    )

    close_autotrader_trade(
        trade_id=state.get("active_trade_id"),
        exit_timestamp=trade_event["timestamp"],
        exit_price=float(overview["last_price"]),
        exit_reason=exit_reason,
        position_size=0.01,
    )

    state["position_status"] = "FLAT"
    state["entry_price"] = None
    state["last_trade_timestamp"] = trade_event["timestamp"]
    state["worker_last_action"] = f"CLOSE_{exit_reason}"
    state["worker_last_exit_reason"] = exit_reason

    state["active_trade_id"] = None
    state["active_trade_stop_loss"] = None
    state["active_trade_take_profit"] = None
    state["active_trade_rr_ratio"] = None
    state["active_trade_opened_at"] = None

    save_runtime_state(state)
    return trade_event, state


def execute_auto_paper_trade(overview, state, trade_file_path="paper_trades.csv"):
    final_signal = overview["final_signal"]

    state = update_worker_snapshot(
        state,
        overview=overview,
        cycle_status="RUNNING"
    )

    if not state.get("bot_enabled", True):
        state["worker_last_action"] = "PAUSED"
        save_runtime_state(state)
        return None, state

    exit_reason = get_exit_reason(overview, state)

    if exit_reason is not None:
        return close_long_trade(
            overview,
            state,
            exit_reason=exit_reason,
            trade_file_path=trade_file_path
        )

    if should_open_long(final_signal, state):
        return open_long_trade(
            overview,
            state,
            trade_file_path=trade_file_path
        )

    state["worker_last_action"] = "NO_TRADE"
    save_runtime_state(state)
    return None, state