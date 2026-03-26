import json
from pathlib import Path

from connectors.okx_client import OKXClient
from analysis.technical import calculate_simple_return, calculate_average_close
from strategy.signal_engine import generate_signal
from execution.paper_trader import execute_paper_trade


def load_runtime_state(file_path="runtime_state.json"):
    # hier laden wir einen kleinen Zustands-Speicher,
    # damit der Bot weiß, ob gerade eine Position offen ist
    path = Path(file_path)

    if not path.exists():
        return {
            "last_signal": None,
            "position_status": "FLAT",
            "entry_price": None,
            "last_trade_timestamp": None
        }

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_runtime_state(state, file_path="runtime_state.json"):
    # hier speichern wir den aktuellen Zustand des Bots lokal als JSON
    path = Path(file_path)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(state, file, indent=2)


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
        "candles": candles
    }


def build_final_signal(technical_signal, news_signal=None):
    # heute ist der finale Entscheid noch identisch zum technischen Signal
    # später können wir hier News / KI / Sentiment mit reinmischen
    if news_signal is None:
        return technical_signal

    return technical_signal


def should_execute_trade(final_signal, state):
    # hier bestimmen wir, ob wirklich ein neuer Trade ausgeführt werden soll
    # damit wir nicht jede Minute denselben SELL oder BUY speichern
    position_status = state["position_status"]

    if final_signal == "BUY" and position_status == "FLAT":
        return True, "OPEN_LONG"

    if final_signal == "SELL" and position_status == "LONG":
        return True, "CLOSE_LONG"

    return False, None


def execute_auto_paper_trade(overview, state, trade_file_path="paper_trades.csv"):
    final_signal = overview["final_signal"]

    should_execute, action = should_execute_trade(final_signal, state)

    # auch wenn wir nichts ausführen, speichern wir das letzte Signal im State
    # damit wir den aktuellen Bot-Zustand nachvollziehen können
    state["last_signal"] = final_signal

    if not should_execute:
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

    save_runtime_state(state)

    return trade_result, state