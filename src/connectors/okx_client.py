import requests


class OKXClient:
    def __init__(self):
        # hier speichern wir die Basis-URL von OKX,
        # damit wir sie nicht in jeder Methode neu schreiben müssen
        self.base_url = "https://www.okx.com"

    def get_ticker(self, inst_id="BTC-USDT"):
        # diese Methode holt aktuelle Ticker-Daten für ein Instrument
        # inst_id ist hier standardmäßig BTC-USDT, kann aber später auch ETH-USDT usw. sein
        url = f"{self.base_url}/api/v5/market/ticker?instId={inst_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_candles(self, inst_id="BTC-USDT", bar="1H", limit="5"):
        # hier holen wir Kerzendaten von OKX
        # bar="1H" bedeutet 1-Stunden-Kerzen
        # limit="5" bedeutet: gib mir 5 Kerzen zurück
        url = (
            f"{self.base_url}/api/v5/market/candles"
            f"?instId={inst_id}&bar={bar}&limit={limit}"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_candles_as_dicts(self, inst_id="BTC-USDT", bar="1H", limit="5"):
        # OKX liefert die Daten als Liste von Listen zurück
        # das ist technisch okay, aber für uns noch etwas unübersichtlich
        # deshalb wandeln wir jede Kerze in ein Dictionary um,
        # damit später klar ist, was open, high, low, close usw. ist
        raw_data = self.get_candles(inst_id, bar, limit)

        candles = []

        for entry in raw_data["data"]:
            candle = {
                "timestamp": entry[0],
                "open": float(entry[1]),
                "high": float(entry[2]),
                "low": float(entry[3]),
                "close": float(entry[4]),
                "volume": float(entry[5]),
                "volume_currency": float(entry[6]),
            }
            candles.append(candle)

        return candles