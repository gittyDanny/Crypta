def calculate_simple_return(candles):
    # hier prüfen wir erstmal, ob genug Kerzen da sind
    # mit weniger als 2 kann man keine Veränderung berechnen
    if len(candles) < 2:
        return None

    # Achtung:
    # OKX liefert die Candles hier von neu nach alt
    # candles[0] ist also die neueste Kerze
    # candles[-1] ist die älteste Kerze in unserer kleinen Auswahl
    newest_close = candles[0]["close"]
    oldest_close = candles[-1]["close"]

    # einfache prozentuale Veränderung
    # Beispiel:
    # alt 100, neu 110 -> (110 - 100) / 100 = 0.10 = 10%
    simple_return = (newest_close - oldest_close) / oldest_close

    return simple_return


def calculate_average_close(candles):
    # ohne Kerzen können wir keinen Durchschnitt bilden
    if len(candles) == 0:
        return None

    close_sum = 0

    # hier laufen wir durch alle Kerzen und addieren die Schlusskurse
    for candle in candles:
        close_sum += candle["close"]

    average_close = close_sum / len(candles)

    return average_close