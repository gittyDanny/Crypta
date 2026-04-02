from connectors.okx_client import OKXClient
from analysis.technical import calculate_simple_return, calculate_average_close
from analysis.forecast import build_linear_forecast
from strategy.signal_engine import generate_signal, build_signal_details


def load_market_overview(inst_id="BTC-USDT", bar="1H", limit="24"):
    # hier bündeln wir weiter die Marktdaten,
    # damit das Dashboard später nur noch anzeigen muss
    client = OKXClient()

    ticker_data = client.get_ticker(inst_id)
    candles = client.get_candles_as_dicts(inst_id, bar, limit)

    simple_return = calculate_simple_return(candles)
    average_close = calculate_average_close(candles)

    signal = generate_signal(candles, simple_return, average_close)
    signal_details = build_signal_details(candles, simple_return, average_close)

    lookback = min(int(limit), 20)
    forecast_points = build_linear_forecast(
        candles,
        lookback=lookback,
        forecast_steps=5,
    )

    latest_market_data = ticker_data["data"][0]
    last_price = float(latest_market_data["last"])

    return {
        "instrument": inst_id,
        "bar": bar,
        "limit": limit,
        "last_price": last_price,
        "simple_return": simple_return,
        "average_close": average_close,
        "signal": signal,
        "signal_details": signal_details,
        "candles": candles,
        "forecast_points": forecast_points,
        "raw_ticker": ticker_data,
    }