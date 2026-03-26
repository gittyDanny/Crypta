import csv
import os
from datetime import datetime


def execute_paper_trade(signal, ticker_data, file_path="paper_trades.csv"):
    # hier holen wir uns die eigentlichen Ticker-Infos aus der OKX-Antwort
    # ticker_data ist noch das ganze Dictionary, also greifen wir auf data[0] zu
    market_data = ticker_data["data"][0]

    inst_id = market_data["instId"]
    last_price = float(market_data["last"])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # hier bauen wir eine Zeile, die später in die CSV geschrieben wird
    trade_row = [timestamp, inst_id, signal, last_price]

    # wir prüfen, ob die Datei schon existiert
    # wenn nicht, schreiben wir zuerst eine Kopfzeile
    file_exists = os.path.exists(file_path)

    with open(file_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow(["timestamp", "instrument", "signal", "last_price"])

        writer.writerow(trade_row)

    return {
        "timestamp": timestamp,
        "instrument": inst_id,
        "signal": signal,
        "last_price": last_price
    }