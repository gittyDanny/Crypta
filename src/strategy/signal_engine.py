def generate_signal(candles, simple_return, average_close):
    # hier prüfen wir erstmal, ob überhaupt Kerzen da sind
    # ohne Daten können wir kein Signal bauen
    if len(candles) == 0:
        return "NO_DATA"

    latest_close = candles[0]["close"]

    # hier definieren wir erstmal extrem einfache Regeln,
    # damit du die Logik gut verstehen kannst
    # später kann man das natürlich viel schlauer machen

    # wenn der Kurs über dem Durchschnitt liegt und die Rendite positiv ist,
    # werten wir das erstmal als einfaches Kaufsignal
    if latest_close > average_close and simple_return > 0:
        return "BUY"

    # wenn der Kurs unter dem Durchschnitt liegt und die Rendite negativ ist,
    # werten wir das erstmal als Verkaufssignal
    if latest_close < average_close and simple_return < 0:
        return "SELL"

    # alles dazwischen behandeln wir erstmal neutral
    return "HOLD"