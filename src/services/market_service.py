from analysis.forecast import build_linear_forecast
from analysis.technical import calculate_average_close, calculate_simple_return
from connectors.okx_client import OKXClient
from services.forecast_accuracy_service import (
    build_forecast_accuracy_summary,
    load_recent_forecast_evaluations,
    reconcile_forecasts_with_actuals,
    store_forecast_snapshot,
)
from strategy.signal_engine import build_signal_details, generate_signal


def load_market_overview(inst_id="BTC-USDT", bar="1H", limit="24"):
    # hier holen wir alle Marktdaten zentral,
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

    # hier speichern wir den aktuellen Forecast,
    # aber nur einmal pro Ursprungskerze
    store_forecast_snapshot(inst_id, bar, forecast_points)

    # hier prüfen wir, ob alte Forecasts inzwischen
    # mit echten Ist-Werten verglichen werden können
    reconcile_forecasts_with_actuals(inst_id, bar, candles)

    forecast_accuracy_summary = build_forecast_accuracy_summary(
        inst_id=inst_id,
        bar=bar,
    )

    recent_forecast_evaluations = load_recent_forecast_evaluations(
        inst_id=inst_id,
        bar=bar,
        limit=10,
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
        "forecast_accuracy_summary": forecast_accuracy_summary,
        "recent_forecast_evaluations": recent_forecast_evaluations,
        "raw_ticker": ticker_data,
    }