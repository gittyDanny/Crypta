def build_signal_details(candles, simple_return, average_close):
    # hier prüfen wir zuerst, ob überhaupt Daten vorhanden sind,
    # weil wir sonst keine sinnvolle Aussage bauen können
    if len(candles) == 0:
        return {
            "signal": "NO_DATA",
            "latest_close": None,
            "average_close": average_close,
            "simple_return": simple_return,
            "close_vs_average": "NO_DATA",
            "return_direction": "NO_DATA",
            "reason": "Keine Marktdaten vorhanden.",
        }

    # hier wandeln wir den letzten Schlusskurs in float um,
    # damit die Vergleiche sauber numerisch laufen
    latest_close = float(candles[0]["close"])

    # hier merken wir uns, ob der Kurs über oder unter dem Durchschnitt liegt
    if latest_close > average_close:
        close_vs_average = "ABOVE_AVERAGE"
    elif latest_close < average_close:
        close_vs_average = "BELOW_AVERAGE"
    else:
        close_vs_average = "AT_AVERAGE"

    # hier merken wir uns die Richtung der letzten Preisveränderung
    if simple_return > 0:
        return_direction = "POSITIVE"
    elif simple_return < 0:
        return_direction = "NEGATIVE"
    else:
        return_direction = "FLAT"

    # hier bleibt die eigentliche Signal-Logik bewusst einfach,
    # aber wir hängen direkt eine verständliche Begründung dran
    if close_vs_average == "ABOVE_AVERAGE" and return_direction == "POSITIVE":
        signal = "BUY"
        reason = (
            "BUY, weil der letzte Schlusskurs über dem Durchschnitt liegt "
            "und die Preisveränderung positiv ist."
        )
    elif close_vs_average == "BELOW_AVERAGE" and return_direction == "NEGATIVE":
        signal = "SELL"
        reason = (
            "SELL, weil der letzte Schlusskurs unter dem Durchschnitt liegt "
            "und die Preisveränderung negativ ist."
        )
    else:
        signal = "HOLD"
        reason = (
            "HOLD, weil die Indikatoren kein klares Kauf- oder Verkaufssignal ergeben."
        )

    return {
        "signal": signal,
        "latest_close": latest_close,
        "average_close": average_close,
        "simple_return": simple_return,
        "close_vs_average": close_vs_average,
        "return_direction": return_direction,
        "reason": reason,
    }


def generate_signal(candles, simple_return, average_close):
    # hier behalten wir die alte Funktion bei,
    # damit bestehender Code weiter funktioniert
    signal_details = build_signal_details(candles, simple_return, average_close)
    return signal_details["signal"]