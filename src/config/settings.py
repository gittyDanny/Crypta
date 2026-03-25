import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # hier sammeln wir zentral Konfigurationen und spätere API-Keys
    OKX_API_KEY = os.getenv("OKX_API_KEY")
    OKX_SECRET_KEY = os.getenv("OKX_SECRET_KEY")
    OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE")

    NEWS_API_KEY = os.getenv("NEWS_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    APP_NAME = "Crypta"
    DEBUG = True