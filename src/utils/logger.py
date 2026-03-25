import logging


def setup_logger():
    # simples Logging, damit wir direkt sehen, was passiert
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    return logging.getLogger("crypta")