from config.settings import Settings
from connectors.okx_client import OKXClient
from utils.logger import setup_logger
from analysis.technical import calculate_simple_return, calculate_average_close
from strategy.signal_engine import generate_signal


def main():
    logger = setup_logger()
    logger.info(f"{Settings.APP_NAME} startet...")

    client = OKXClient()

    try:
        ticker_data = client.get_ticker("BTC-USDT")
        logger.info("BTC-Ticker erfolgreich geladen")
        print("Ticker:")
        print(ticker_data)

        candles = client.get_candles_as_dicts("BTC-USDT", "1H", "5")
        logger.info("Candles erfolgreich geladen")
        print("\nLetzte 5 Candles:")

        for candle in candles:
            print(candle)

        simple_return = calculate_simple_return(candles)
        average_close = calculate_average_close(candles)
        signal = generate_signal(candles, simple_return, average_close)

        print("\nEinfache Analyse:")
        print(f"Preisveränderung über die 5 Candles: {simple_return:.4%}")
        print(f"Durchschnittlicher Schlusskurs: {average_close:.2f}")
        print(f"Aktuelles Signal: {signal}")

    except Exception as e:
        logger.error(f"Fehler beim Laden der OKX-Daten: {e}")


if __name__ == "__main__":
    main()