import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from analysis.technical import calculate_average_close, calculate_simple_return
from connectors.okx_client import OKXClient
from execution.paper_trader import execute_paper_trade
from services.autotrader_trade_service import (
    append_open_autotrader_trade,
    close_autotrader_trade,
    create_trade_id,
)
from services.db_service import get_connection, initialize_database
from strategy.signal_engine import generate_signal


def _build_default_runtime_state():
    return {
        "bot_enabled": True,
        "reward_multiple": 2.0,
        "leverage": 1.0,
        "auto_leverage_enabled": True,
        "target_risk_pct": 0.35,
        "min_leverage": 1.0,
        "max_leverage": 3.0,
        "position_size_btc": 0.01,
        "cooldown_candles": 2,
        "last_signal": None,
        "position_status": "FLAT",
        "entry_price": None,
        "last_trade_timestamp": None,
        "last_trade_candle_timestamp": None,
        "last_exit_candle_timestamp": None,
        "last_exit_side": None,
        "worker_last_seen_at": None,
        "worker_cycle_status": "IDLE",
        "worker_last_error": None,
        "worker_last_price": None,
        "worker_last_technical_signal": None,
        "worker_last_final_signal": None,
        "worker_last_action": "NONE",
        "worker_last_exit_reason": None,
        "active_trade_id": None,
        "active_trade_side": None,
        "active_trade_stop_loss": None,
        "active_trade_take_profit": None,
        "active_trade_rr_ratio": None,
        "active_trade_opened_at": None,
        "active_trade_leverage": None,
        "active_trade_position_size_btc": None,
    }


def _get_legacy_runtime_state_path(file_path="runtime_state.json"):
    project_root = Path(__file__).resolve().parents[2]
    return project_root / file_path


def _runtime_state_row_exists(db_name="crypta.db"):
    initialize_database(db_name)

    with get_connection(db_name) as connection:
        row = connection.execute(
            "SELECT id FROM runtime_state WHERE id = 1"
        ).fetchone()

    return row is not None


def _migrate_runtime_json_if_needed(file_path="runtime_state.json", db_name="crypta.db"):
    initialize_database(db_name)

    if _runtime_state_row_exists(db_name=db_name):
        return

    legacy_path = _get_legacy_runtime_state_path(file_path)

    if legacy_path.exists():
        with open(legacy_path, "r", encoding="utf-8") as file:
            loaded_state = json.load(file)

        state = _build_default_runtime_state()
        state.update(loaded_state)
    else:
        state = _build_default_runtime_state()

    save_runtime_state(state, file_path=file_path, db_name=db_name)


def load_runtime_state(file_path="runtime_state.json", db_name="crypta.db"):
    _migrate_runtime_json_if_needed(file_path=file_path, db_name=db_name)

    with get_connection(db_name) as connection:
        row = connection.execute(
            "SELECT state_json FROM runtime_state WHERE id = 1"
        ).fetchone()

    if row is None:
        state = _build_default_runtime_state()
        save_runtime_state(state, file_path=file_path, db_name=db_name)
        return state

    loaded_state = json.loads(row["state_json"])

    state = _build_default_runtime_state()
    state.update(loaded_state)
    return state


def save_runtime_state(state, file_path="runtime_state.json", db_name="crypta.db"):
    initialize_database(db_name)

    merged_state = _build_default_runtime_state()
    merged_state.update(state)

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection(db_name) as connection:
        connection.execute(
            """
            INSERT INTO runtime_state (id, state_json, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (
                json.dumps(merged_state, indent=2),
                updated_at,
            )
        )
        connection.commit()

    return merged_state


def update_worker_snapshot(state, overview=None, action=None, cycle_status=None, error=None):
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
    # wir bauen gerade primär für BTC,
    # aber halten die Funktion offen für weitere Assets
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
    # später wollen wir hier KI-basierte fundamentale / News-Signale einspeisen
    # deswegen machen wir die Kombinationslogik schon etwas sauberer
    if news_signal is None:
        return technical_signal

    if technical_signal == news_signal:
        return technical_signal

    if technical_signal == "HOLD":
        return news_signal

    if news_signal == "HOLD":
        return technical_signal

    # wenn technische und fundamentale Richtung hart kollidieren,
    # bleiben wir konservativ lieber draußen
    return "HOLD"


def _format_chart_timestamp_from_ms(timestamp_ms):
    return pd.to_datetime(int(timestamp_ms), unit="ms").strftime("%Y-%m-%d %H:%M:%S")


def _bar_to_timedelta(bar):
    bar_map = {
        "1m": pd.Timedelta(minutes=1),
        "5m": pd.Timedelta(minutes=5),
        "15m": pd.Timedelta(minutes=15),
        "1H": pd.Timedelta(hours=1),
        "4H": pd.Timedelta(hours=4),
        "1D": pd.Timedelta(days=1),
    }

    return bar_map.get(bar, pd.Timedelta(minutes=1))


def _calculate_selected_leverage(entry_price, stop_loss, state):
    manual_leverage = float(state.get("leverage", 1.0))
    min_leverage = float(state.get("min_leverage", 1.0))
    max_leverage = float(state.get("max_leverage", 3.0))
    auto_leverage_enabled = bool(state.get("auto_leverage_enabled", True))

    if not auto_leverage_enabled:
        return round(max(min(manual_leverage, max_leverage), min_leverage), 2)

    stop_distance_pct = abs(float(entry_price) - float(stop_loss)) / float(entry_price)

    if stop_distance_pct <= 0:
        return round(min_leverage, 2)

    target_risk_pct = float(state.get("target_risk_pct", 0.35)) / 100.0
    raw_leverage = target_risk_pct / stop_distance_pct

    chosen_leverage = max(min(raw_leverage, max_leverage), min_leverage)
    return round(chosen_leverage, 2)


def _is_same_candle_trade_blocked(state, current_candle_timestamp):
    last_trade_candle_timestamp = state.get("last_trade_candle_timestamp")

    if last_trade_candle_timestamp is None:
        return False

    return str(last_trade_candle_timestamp) == str(current_candle_timestamp)


def _is_cooldown_active(state, current_candle_timestamp, bar):
    cooldown_candles = int(state.get("cooldown_candles", 2))
    last_exit_candle_timestamp = state.get("last_exit_candle_timestamp")

    if cooldown_candles <= 0 or last_exit_candle_timestamp is None:
        return False

    current_ts = pd.to_datetime(current_candle_timestamp, errors="coerce")
    last_exit_ts = pd.to_datetime(last_exit_candle_timestamp, errors="coerce")

    if pd.isna(current_ts) or pd.isna(last_exit_ts):
        return False

    candle_delta = _bar_to_timedelta(bar)

    if candle_delta <= pd.Timedelta(0):
        return False

    candles_since_exit = (current_ts - last_exit_ts) / candle_delta

    return candles_since_exit < cooldown_candles


def build_long_trade_plan(overview, reward_multiple, state):
    signal_candle = overview["candles"][0]

    entry_price = float(overview["last_price"])
    candle_low = float(signal_candle["low"])

    risk_per_unit = entry_price - candle_low

    if risk_per_unit <= 0:
        risk_per_unit = max(entry_price * 0.001, 10.0)
        stop_loss = entry_price - risk_per_unit
    else:
        stop_loss = candle_low

    take_profit = entry_price + float(reward_multiple) * risk_per_unit
    reward_per_unit = take_profit - entry_price
    selected_leverage = _calculate_selected_leverage(entry_price, stop_loss, state)

    return {
        "side": "LONG",
        "entry_price": round(entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "risk_per_unit": round(risk_per_unit, 2),
        "reward_per_unit": round(reward_per_unit, 2),
        "rr_ratio": round(reward_per_unit / risk_per_unit, 2) if risk_per_unit != 0 else None,
        "selected_leverage": selected_leverage,
        "signal_candle_timestamp": int(signal_candle["timestamp"]),
        "signal_candle_chart_timestamp": _format_chart_timestamp_from_ms(signal_candle["timestamp"]),
        "signal_candle_open": float(signal_candle["open"]),
        "signal_candle_high": float(signal_candle["high"]),
        "signal_candle_low": float(signal_candle["low"]),
        "signal_candle_close": float(signal_candle["close"]),
    }


def build_short_trade_plan(overview, reward_multiple, state):
    signal_candle = overview["candles"][0]

    entry_price = float(overview["last_price"])
    candle_high = float(signal_candle["high"])

    risk_per_unit = candle_high - entry_price

    if risk_per_unit <= 0:
        risk_per_unit = max(entry_price * 0.001, 10.0)
        stop_loss = entry_price + risk_per_unit
    else:
        stop_loss = candle_high

    take_profit = entry_price - float(reward_multiple) * risk_per_unit
    reward_per_unit = entry_price - take_profit
    selected_leverage = _calculate_selected_leverage(entry_price, stop_loss, state)

    return {
        "side": "SHORT",
        "entry_price": round(entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "risk_per_unit": round(risk_per_unit, 2),
        "reward_per_unit": round(reward_per_unit, 2),
        "rr_ratio": round(reward_per_unit / risk_per_unit, 2) if risk_per_unit != 0 else None,
        "selected_leverage": selected_leverage,
        "signal_candle_timestamp": int(signal_candle["timestamp"]),
        "signal_candle_chart_timestamp": _format_chart_timestamp_from_ms(signal_candle["timestamp"]),
        "signal_candle_open": float(signal_candle["open"]),
        "signal_candle_high": float(signal_candle["high"]),
        "signal_candle_low": float(signal_candle["low"]),
        "signal_candle_close": float(signal_candle["close"]),
    }


def should_open_long(final_signal, state):
    return final_signal == "BUY" and state["position_status"] == "FLAT"


def should_open_short(final_signal, state):
    return final_signal == "SELL" and state["position_status"] == "FLAT"


def get_exit_reason(overview, state):
    if state["position_status"] == "LONG":
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

    if state["position_status"] == "SHORT":
        current_price = float(overview["last_price"])
        stop_loss = state.get("active_trade_stop_loss")
        take_profit = state.get("active_trade_take_profit")
        final_signal = overview["final_signal"]

        if stop_loss is not None and current_price >= float(stop_loss):
            return "STOP_LOSS"

        if take_profit is not None and current_price <= float(take_profit):
            return "TAKE_PROFIT"

        if final_signal == "BUY":
            return "BUY_SIGNAL"

    return None


def _can_open_new_trade(overview, state):
    current_candle_timestamp = _format_chart_timestamp_from_ms(
        overview["candles"][0]["timestamp"]
    )

    if _is_same_candle_trade_blocked(state, current_candle_timestamp):
        return False, "BLOCKED_SAME_CANDLE"

    if _is_cooldown_active(state, current_candle_timestamp, overview["bar"]):
        return False, "BLOCKED_COOLDOWN"

    return True, None


def _save_open_trade_to_state(state, trade_id, trade_plan, trade_event):
    state["entry_price"] = trade_plan["entry_price"]
    state["last_trade_timestamp"] = trade_event["timestamp"]
    state["last_trade_candle_timestamp"] = trade_plan["signal_candle_chart_timestamp"]
    state["worker_last_exit_reason"] = None

    state["active_trade_id"] = trade_id
    state["active_trade_side"] = trade_plan["side"]
    state["active_trade_stop_loss"] = trade_plan["stop_loss"]
    state["active_trade_take_profit"] = trade_plan["take_profit"]
    state["active_trade_rr_ratio"] = trade_plan["rr_ratio"]
    state["active_trade_opened_at"] = trade_event["timestamp"]
    state["active_trade_leverage"] = float(trade_plan["selected_leverage"])
    state["active_trade_position_size_btc"] = float(state.get("position_size_btc", 0.01))

    return state


def open_long_trade(overview, state, trade_file_path="paper_trades.csv"):
    reward_multiple = float(state.get("reward_multiple", 2.0))
    position_size_btc = float(state.get("position_size_btc", 0.01))

    trade_plan = build_long_trade_plan(
        overview,
        reward_multiple=reward_multiple,
        state=state
    )
    trade_id = create_trade_id()

    trade_event = execute_paper_trade(
        "BUY",
        overview["raw_ticker"],
        file_path=trade_file_path
    )

    autotrader_trade_row = {
        "trade_id": trade_id,
        "instrument": overview["instrument"],
        "bar": overview["bar"],
        "side": "LONG",
        "status": "OPEN",
        "entry_timestamp": trade_event["timestamp"],
        "entry_chart_timestamp": trade_plan["signal_candle_chart_timestamp"],
        "entry_price": trade_plan["entry_price"],
        "entry_signal": overview["final_signal"],
        "leverage": trade_plan["selected_leverage"],
        "position_size_btc": position_size_btc,
        "entry_signal_candle_timestamp": trade_plan["signal_candle_chart_timestamp"],
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
        "exit_chart_timestamp": None,
        "exit_price": None,
        "exit_reason": None,
        "pnl_usdt": None,
        "pnl_pct": None,
    }

    append_open_autotrader_trade(autotrader_trade_row)

    state["position_status"] = "LONG"
    state["worker_last_action"] = "OPEN_LONG"
    state = _save_open_trade_to_state(state, trade_id, trade_plan, trade_event)

    save_runtime_state(state)
    return trade_event, state


def open_short_trade(overview, state, trade_file_path="paper_trades.csv"):
    reward_multiple = float(state.get("reward_multiple", 2.0))
    position_size_btc = float(state.get("position_size_btc", 0.01))

    trade_plan = build_short_trade_plan(
        overview,
        reward_multiple=reward_multiple,
        state=state
    )
    trade_id = create_trade_id()

    trade_event = execute_paper_trade(
        "SELL",
        overview["raw_ticker"],
        file_path=trade_file_path
    )

    autotrader_trade_row = {
        "trade_id": trade_id,
        "instrument": overview["instrument"],
        "bar": overview["bar"],
        "side": "SHORT",
        "status": "OPEN",
        "entry_timestamp": trade_event["timestamp"],
        "entry_chart_timestamp": trade_plan["signal_candle_chart_timestamp"],
        "entry_price": trade_plan["entry_price"],
        "entry_signal": overview["final_signal"],
        "leverage": trade_plan["selected_leverage"],
        "position_size_btc": position_size_btc,
        "entry_signal_candle_timestamp": trade_plan["signal_candle_chart_timestamp"],
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
        "exit_chart_timestamp": None,
        "exit_price": None,
        "exit_reason": None,
        "pnl_usdt": None,
        "pnl_pct": None,
    }

    append_open_autotrader_trade(autotrader_trade_row)

    state["position_status"] = "SHORT"
    state["worker_last_action"] = "OPEN_SHORT"
    state = _save_open_trade_to_state(state, trade_id, trade_plan, trade_event)

    save_runtime_state(state)
    return trade_event, state


def close_active_trade(overview, state, exit_reason, trade_file_path="paper_trades.csv"):
    closing_side = state["position_status"]

    if closing_side == "LONG":
        close_signal = "SELL"
        action_name = f"CLOSE_LONG_{exit_reason}"
    else:
        close_signal = "BUY"
        action_name = f"CLOSE_SHORT_{exit_reason}"

    trade_event = execute_paper_trade(
        close_signal,
        overview["raw_ticker"],
        file_path=trade_file_path
    )

    current_chart_timestamp = _format_chart_timestamp_from_ms(
        overview["candles"][0]["timestamp"]
    )

    close_autotrader_trade(
        trade_id=state.get("active_trade_id"),
        exit_timestamp=trade_event["timestamp"],
        exit_chart_timestamp=current_chart_timestamp,
        exit_price=float(overview["last_price"]),
        exit_reason=exit_reason,
    )

    state["position_status"] = "FLAT"
    state["entry_price"] = None
    state["last_trade_timestamp"] = trade_event["timestamp"]
    state["last_trade_candle_timestamp"] = current_chart_timestamp
    state["last_exit_candle_timestamp"] = current_chart_timestamp
    state["last_exit_side"] = closing_side
    state["worker_last_action"] = action_name
    state["worker_last_exit_reason"] = exit_reason

    state["active_trade_id"] = None
    state["active_trade_side"] = None
    state["active_trade_stop_loss"] = None
    state["active_trade_take_profit"] = None
    state["active_trade_rr_ratio"] = None
    state["active_trade_opened_at"] = None
    state["active_trade_leverage"] = None
    state["active_trade_position_size_btc"] = None

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
        return close_active_trade(
            overview,
            state,
            exit_reason=exit_reason,
            trade_file_path=trade_file_path
        )

    can_open_trade, block_reason = _can_open_new_trade(overview, state)

    if should_open_long(final_signal, state):
        if not can_open_trade:
            state["worker_last_action"] = block_reason
            save_runtime_state(state)
            return None, state

        return open_long_trade(
            overview,
            state,
            trade_file_path=trade_file_path
        )

    if should_open_short(final_signal, state):
        if not can_open_trade:
            state["worker_last_action"] = block_reason
            save_runtime_state(state)
            return None, state

        return open_short_trade(
            overview,
            state,
            trade_file_path=trade_file_path
        )

    state["worker_last_action"] = "NO_TRADE"
    save_runtime_state(state)
    return None, state