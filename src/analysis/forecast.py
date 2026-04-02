def _get_timestamp_ms(candle):
    # hier lesen wir den Zeitstempel robust aus,
    # falls wir später mal leicht andere Candle-Formate haben
    if "timestamp" in candle:
        return int(candle["timestamp"])

    if "ts" in candle:
        return int(candle["ts"])

    raise KeyError("Kein Timestamp-Feld in candle gefunden.")


def _get_close_price(candle):
    # hier holen wir den Schlusskurs als float,
    # damit wir sicher mit Zahlen rechnen
    return float(candle["close"])


def _calculate_linear_trend(values):
    # hier bauen wir eine ganz einfache lineare Trendgerade
    # ohne extra Bibliothek, damit die Logik nachvollziehbar bleibt
    point_count = len(values)

    x_values = list(range(point_count))

    sum_x = sum(x_values)
    sum_y = sum(values)
    sum_xx = sum(x * x for x in x_values)
    sum_xy = sum(x * y for x, y in zip(x_values, values))

    denominator = point_count * sum_xx - sum_x * sum_x

    if denominator == 0:
        return 0.0, values[-1]

    slope = (point_count * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / point_count

    return slope, intercept


def build_linear_forecast(candles, lookback=20, forecast_steps=5):
    # mit zu wenigen Kerzen wäre die Gerade Quatsch,
    # deshalb brechen wir dann sauber ab
    if len(candles) < 3:
        return []

    # OKX liefert bei dir die Candles von neu nach alt,
    # für die Forecast-Logik drehen wir sie daher einmal um
    ordered_candles = list(reversed(candles))

    usable_candles = ordered_candles[-lookback:]

    close_prices = [_get_close_price(candle) for candle in usable_candles]
    timestamps_ms = [_get_timestamp_ms(candle) for candle in usable_candles]

    slope, intercept = _calculate_linear_trend(close_prices)

    # hier schätzen wir den Abstand zwischen zwei Candles,
    # damit die Forecast-Punkte zeitlich weiterlaufen
    if len(timestamps_ms) >= 2:
        candle_distance_ms = timestamps_ms[-1] - timestamps_ms[-2]
    else:
        candle_distance_ms = 60 * 1000

    if candle_distance_ms <= 0:
        candle_distance_ms = 60 * 1000

    forecast_points = [
        {
            "timestamp": timestamps_ms[-1],
            "close": round(close_prices[-1], 2),
        }
    ]

    start_x = len(close_prices)

    for step in range(1, forecast_steps + 1):
        x_value = start_x + step - 1
        forecast_close = slope * x_value + intercept
        forecast_timestamp = timestamps_ms[-1] + candle_distance_ms * step

        forecast_points.append(
            {
                "timestamp": int(forecast_timestamp),
                "close": round(forecast_close, 2),
            }
        )

    return forecast_points