from pathlib import Path
import pandas as pd


def load_trade_history():
    # hier gehen wir vom aktuellen Dateipfad aus eine Ebene hoch bis zum Projektordner
    # dort liegt unsere paper_trades.csv
    project_root = Path(__file__).resolve().parents[2]
    csv_path = project_root / "paper_trades.csv"

    # falls die Datei noch nicht existiert, geben wir einfach ein leeres DataFrame zurück
    # so crasht das Dashboard nicht beim ersten Start
    if not csv_path.exists():
        return pd.DataFrame()

    trade_df = pd.read_csv(csv_path)

    # falls Daten da sind, wandeln wir den Zeitstempel in ein richtiges Datumsformat um
    # das ist später für Sortierung und Anzeige angenehmer
    if not trade_df.empty:
        trade_df["timestamp"] = pd.to_datetime(trade_df["timestamp"])

    return trade_df


def summarize_trade_history(trade_df):
    # wenn noch keine Trades existieren, geben wir neutrale Standardwerte zurück
    if trade_df.empty:
        return {
            "total_trades": 0,
            "buy_count": 0,
            "sell_count": 0,
            "hold_count": 0,
            "latest_trade": None
        }

    buy_count = (trade_df["signal"] == "BUY").sum()
    sell_count = (trade_df["signal"] == "SELL").sum()
    hold_count = (trade_df["signal"] == "HOLD").sum()

    # wir sortieren nach Zeit, damit wir wirklich den neuesten Trade bekommen
    sorted_df = trade_df.sort_values("timestamp", ascending=False)
    latest_trade = sorted_df.iloc[0].to_dict()

    return {
        "total_trades": len(trade_df),
        "buy_count": int(buy_count),
        "sell_count": int(sell_count),
        "hold_count": int(hold_count),
        "latest_trade": latest_trade
    }