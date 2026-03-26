import sys
import time
from pathlib import Path

# hier fügen wir den src-Ordner zum Python-Pfad hinzu,
# weil diese Datei in src/bot liegt und sonst die Imports nicht gefunden werden
SRC_PATH = Path(__file__).resolve().parents[1]
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from utils.logger import setup_logger
from services.auto_trade_service import (
    load_runtime_state,
    build_market_overview,
    build_final_signal,
    execute_auto_paper_trade
)


def run_worker(inst_id="BTC-USDT", bar="1m", limit="30", interval_seconds=60):
    logger = setup_logger()
    logger.info("Crypta Realtime Worker startet...")

    state = load_runtime_state()
    logger.info(f"Aktueller Bot-Status: {state['position_status']}")

    while True:
        try:
            overview = build_market_overview(
                inst_id=inst_id,
                bar=bar,
                limit=limit
            )

            # später hängen wir hier News-Signal oder KI-Auswertung rein
            news_signal = None

            final_signal = build_final_signal(
                overview["technical_signal"],
                news_signal=news_signal
            )

            overview["final_signal"] = final_signal

            logger.info(
                f"Preis: {overview['last_price']:.2f} | "
                f"Return: {overview['simple_return']:.4%} | "
                f"Technisch: {overview['technical_signal']} | "
                f"Final: {final_signal}"
            )

            trade_result, state = execute_auto_paper_trade(overview, state)

            if trade_result is None:
                logger.info("Kein neuer Auto-Paper-Trade ausgeführt")
            else:
                logger.info(
                    f"Auto-Paper-Trade gespeichert: "
                    f"{trade_result['instrument']} | "
                    f"{trade_result['signal']} | "
                    f"{trade_result['last_price']:.2f}"
                )

        except Exception as e:
            logger.error(f"Fehler im Realtime Worker: {e}")

        logger.info(f"Warte {interval_seconds} Sekunden bis zum nächsten Zyklus...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_worker()