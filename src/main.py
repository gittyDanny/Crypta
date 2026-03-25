from config.settings import Settings
from connectors.okx_client import OKXClient
from utils.logger import setup_logger


def main():
    logger = setup_logger()
    logger.info(f"{Settings.APP_NAME} startet...")

    client = OKXClient()

    try:
        ticker_data = client.get_ticker("BTC-USDT")
        logger.info("BTC-Daten erfolgreich geladen")
        print(ticker_data)
    except Exception as e:
        logger.error(f"Fehler beim Laden der OKX-Daten: {e}")


if __name__ == "__main__":
    main()