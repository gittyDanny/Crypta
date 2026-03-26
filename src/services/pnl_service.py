import pandas as pd


def calculate_pnl_summary(trade_df, current_price=None, position_size=0.01):
    # wenn noch keine Trades existieren, geben wir neutrale Standardwerte zurück
    if trade_df.empty:
        return {
            "position_size": position_size,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "total_pnl": 0.0,
            "closed_trades": 0,
            "position_status": "FLAT",
            "entry_price": None,
            "trade_log_df": pd.DataFrame()
        }

    # wir sortieren die Historie von alt nach neu,
    # weil die Reihenfolge für die PnL-Berechnung wichtig ist
    sorted_df = trade_df.sort_values("timestamp").copy()

    position_open = False
    entry_price = None
    entry_timestamp = None

    realized_pnl = 0.0
    closed_trades = 0
    trade_log = []

    for _, row in sorted_df.iterrows():
        signal = row["signal"]
        price = float(row["last_price"])
        timestamp = row["timestamp"]
        instrument = row["instrument"]

        # BUY öffnet nur dann eine Position, wenn wir gerade keine offen haben
        if signal == "BUY":
            if not position_open:
                position_open = True
                entry_price = price
                entry_timestamp = timestamp

        # SELL schließt nur dann eine Position, wenn gerade eine offen ist
        elif signal == "SELL":
            if position_open:
                pnl = (price - entry_price) * position_size
                realized_pnl += pnl
                closed_trades += 1

                trade_log.append(
                    {
                        "entry_timestamp": entry_timestamp,
                        "exit_timestamp": timestamp,
                        "instrument": instrument,
                        "entry_price": entry_price,
                        "exit_price": price,
                        "position_size": position_size,
                        "pnl": pnl
                    }
                )

                position_open = False
                entry_price = None
                entry_timestamp = None

        # HOLD macht absichtlich nichts
        elif signal == "HOLD":
            pass

    unrealized_pnl = 0.0

    # wenn noch eine Position offen ist und wir einen aktuellen Preis haben,
    # berechnen wir zusätzlich den offenen Gewinn / Verlust
    if position_open and current_price is not None:
        unrealized_pnl = (float(current_price) - entry_price) * position_size

    total_pnl = realized_pnl + unrealized_pnl

    if position_open:
        position_status = "LONG"
    else:
        position_status = "FLAT"

    trade_log_df = pd.DataFrame(trade_log)
    if not trade_log_df.empty:
        # hier bauen wir eine laufende Summe auf,
        # damit wir später die Entwicklung der Performance als Kurve zeigen können
        trade_log_df["cumulative_pnl"] = trade_log_df["pnl"].cumsum()

    return {
        "position_size": position_size,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "total_pnl": total_pnl,
        "closed_trades": closed_trades,
        "position_status": position_status,
        "entry_price": entry_price,
        "trade_log_df": trade_log_df
    }