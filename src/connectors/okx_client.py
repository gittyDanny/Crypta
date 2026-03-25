import requests


class OKXClient:
    def __init__(self):
        self.base_url = "https://www.okx.com"

    def get_ticker(self, inst_id="BTC-USDT"):
        # hier holen wir erstmal nur öffentliche BTC-Marktdaten
        url = f"{self.base_url}/api/v5/market/ticker?instId={inst_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()