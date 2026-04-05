import json
from datetime import datetime
from pathlib import Path

from analysis.technical import calculate_average_close, calculate_simple_return
from connectors.okx_client import OKXClient
from execution.paper_trader import execute_paper_trade
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


def should_execute_trade(final_signal, state):
    # hier bestimmen wir, ob wirklich ein neuer Trade ausgeführt werden soll,
    # damit wir nicht jede Minute denselben SELL oder BUY speichern
    position_status = state["position_status"]

    if final_signal == "BUY" and position_status == "FLAT":
        return True, "OPEN_LONG"

    if final_signal == "SELL" and position_status == "LONG":
        return True, "CLOSE_LONG"

    return False, None


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

    should_execute, action = should_execute_trade(final_signal, state)

    if not should_execute:
        state["worker_last_action"] = "NO_TRADE"
        save_runtime_state(state)
        return None, state

    trade_result = execute_paper_trade(
        final_signal,
        overview["raw_ticker"],
        file_path=trade_file_path
    )

    if action == "OPEN_LONG":
        state["position_status"] = "LONG"
        state["entry_price"] = overview["last_price"]
    elif action == "CLOSE_LONG":
        state["position_status"] = "FLAT"
        state["entry_price"] = None

    state["last_trade_timestamp"] = trade_result["timestamp"]
    state["worker_last_action"] = action

    save_runtime_state(state)
    return trade_result, state