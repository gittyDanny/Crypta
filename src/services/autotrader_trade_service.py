from pathlib import Path
from uuid import uuid4

import pandas as pd


AUTOTRADER_TRADE_COLUMNS = [
    "trade_id",
    "instrument",
    "bar",
    "side",
    "status",
    "entry_timestamp",
    "entry_price",
    "entry_signal",
    "entry_signal_candle_timestamp",
    "entry_signal_candle_open",
    "entry_signal_candle_high",
    "entry_signal_candle_low",
    "entry_signal_candle_close",
    "stop_loss",
    "take_profit",
    "risk_per_unit",
    "reward_per_unit",
    "rr_ratio",
    "exit_timestamp",
    "exit_price",
    "exit_reason",
    "pnl_usdt",
    "pnl_pct",
]


def _get_csv_path(file_path="autotrader_trades.csv"):
    project_root = Path(__file__).resolve().parents[2]
    return project_root / file_path


def _build_empty_trade_df():
    return pd.DataFrame(columns=AUTOTRADER_TRADE_COLUMNS)


def load_autotrader_trades(file_path="autotrader_trades.csv"):
    csv_path = _get_csv_path(file_path)

    if not csv_path.exists():
        return _build_empty_trade_df()

    trade_df = pd.read_csv(csv_path)

    for column in AUTOTRADER_TRADE_COLUMNS:
        if column not in trade_df.columns:
            trade_df[column] = None

    timestamp_columns = [
        "entry_timestamp",
        "entry_signal_candle_timestamp",
        "exit_timestamp",
    ]

    numeric_columns = [
        "entry_price",
        "entry_signal_candle_open",
        "entry_signal_candle_high",
        "entry_signal_candle_low",
        "entry_signal_candle_close",
        "stop_loss",
        "take_profit",
        "risk_per_unit",
        "reward_per_unit",
        "rr_ratio",
        "exit_price",
        "pnl_usdt",
        "pnl_pct",
    ]

    for column in timestamp_columns:
        trade_df[column] = pd.to_datetime(trade_df[column], errors="coerce")

    for column in numeric_columns:
        trade_df[column] = pd.to_numeric(trade_df[column], errors="coerce")

    return trade_df[AUTOTRADER_TRADE_COLUMNS]


def _save_autotrader_trades(trade_df, file_path="autotrader_trades.csv"):
    csv_path = _get_csv_path(file_path)

    if trade_df.empty:
        _build_empty_trade_df().to_csv(csv_path, index=False)
        return

    sorted_df = trade_df.sort_values("entry_timestamp", ascending=False).copy()
    sorted_df.to_csv(csv_path, index=False)


def create_trade_id():
    return uuid4().hex[:12]


def append_open_autotrader_trade(trade_row, file_path="autotrader_trades.csv"):
    trade_df = load_autotrader_trades(file_path=file_path)
    new_row_df = pd.DataFrame([trade_row], columns=AUTOTRADER_TRADE_COLUMNS)

    if trade_df.empty:
        updated_df = new_row_df
    else:
        updated_df = pd.concat([trade_df, new_row_df], ignore_index=True)

    _save_autotrader_trades(updated_df, file_path=file_path)
    return trade_row


def close_autotrader_trade(
    trade_id,
    exit_timestamp,
    exit_price,
    exit_reason,
    position_size=0.01,
    file_path="autotrader_trades.csv",
):
    trade_df = load_autotrader_trades(file_path=file_path)

    if trade_df.empty:
        return None

    trade_mask = trade_df["trade_id"] == trade_id

    if not trade_mask.any():
        return None

    trade_index = trade_df[trade_mask].index[0]

    entry_price = float(trade_df.at[trade_index, "entry_price"])
    pnl_usdt = (float(exit_price) - entry_price) * position_size

    if entry_price != 0:
        pnl_pct = ((float(exit_price) - entry_price) / entry_price) * 100
    else:
        pnl_pct = 0.0

    trade_df.at[trade_index, "status"] = "CLOSED"
    trade_df.at[trade_index, "exit_timestamp"] = exit_timestamp
    trade_df.at[trade_index, "exit_price"] = round(float(exit_price), 2)
    trade_df.at[trade_index, "exit_reason"] = exit_reason
    trade_df.at[trade_index, "pnl_usdt"] = round(float(pnl_usdt), 4)
    trade_df.at[trade_index, "pnl_pct"] = round(float(pnl_pct), 4)

    _save_autotrader_trades(trade_df, file_path=file_path)

    closed_trade = trade_df.loc[trade_index].to_dict()
    return closed_trade