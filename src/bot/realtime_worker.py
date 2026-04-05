import sys
import time
from pathlib import Path

# hier fügen wir den src-Ordner zum Python-Pfad hinzu,
# weil diese Datei in src/bot liegt und sonst die Imports nicht gefunden werden
SRC_PATH = Path(__file__).resolve().parents[1]
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from services.auto_trade_service import (
    build_final_signal,
    build_market_overview,
    execute_auto_paper_trade,
    load_runtime_state,
    save_runtime_state,
    update_worker_snapshot,
)
from utils.logger import setup_logger


def run_worker(inst_id="BTC-USDT", bar="1m", limit="30", interval_seconds=60):
    logger = setup_logger()
    logger.info("Crypta Realtime Worker startet...")

    initial_state = load_runtime_state()
    logger.info(f"Aktueller Bot-Status: {initial_state['position_status']}")

    while True:
        try:
            state = load_runtime_state()

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

            state = update_worker_snapshot(
                state,
                overview=overview,
                cycle_status="RUNNING"
            )
            save_runtime_state(state)

            logger.info(
                f"Preis: {overview['last_price']:.2f} | "
                f"Return: {overview['simple_return']:.4%} | "
                f"Technisch: {overview['technical_signal']} | "
                f"Final: {final_signal} | "
                f"Bot aktiv: {state['bot_enabled']}"
            )

            trade_result, state = execute_auto_paper_trade(overview, state)

            if trade_result is None:
                if state.get("worker_last_action") == "PAUSED":
                    logger.info("Autotrader ist pausiert. Nur Live-Tracking aktiv.")
                else:
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

            state = load_runtime_state()
            state = update_worker_snapshot(
                state,
                action="ERROR",
                cycle_status="ERROR",
                error=str(e)
            )
            save_runtime_state(state)

        logger.info(f"Warte {interval_seconds} Sekunden bis zum nächsten Zyklus...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_worker()