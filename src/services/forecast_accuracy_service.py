from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


FORECAST_HISTORY_COLUMNS = [
    "instrument",
    "bar",
    "forecast_origin_timestamp",
    "target_timestamp",
    "step_ahead",
    "forecast_close",
    "actual_close",
    "error_value",
    "abs_error",
    "abs_error_pct",
    "status",
    "created_at",
    "evaluated_at",
]


def _get_data_dir():
    # hier legen wir einen data-Ordner im Projekt an,
    # damit Forecast-Historie dauerhaft gespeichert werden kann
    data_dir = Path(__file__).resolve().parents[2] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _get_forecast_history_path():
    return _get_data_dir() / "forecast_history.csv"


def _build_empty_forecast_df():
    return pd.DataFrame(columns=FORECAST_HISTORY_COLUMNS)


def _load_forecast_history_df():
    # hier laden wir die CSV robust,
    # und sorgen dafür, dass alle erwarteten Spalten da sind
    path = _get_forecast_history_path()

    if not path.exists():
        return _build_empty_forecast_df()

    df = pd.read_csv(path)

    for column in FORECAST_HISTORY_COLUMNS:
        if column not in df.columns:
            df[column] = None

    numeric_columns = [
        "forecast_origin_timestamp",
        "target_timestamp",
        "step_ahead",
        "forecast_close",
        "actual_close",
        "error_value",
        "abs_error",
        "abs_error_pct",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    return df[FORECAST_HISTORY_COLUMNS]


def _save_forecast_history_df(df):
    path = _get_forecast_history_path()

    if df.empty:
        _build_empty_forecast_df().to_csv(path, index=False)
        return

    sorted_df = df.sort_values(
        ["target_timestamp", "step_ahead"],
        ascending=[False, True]
    ).copy()

    sorted_df.to_csv(path, index=False)


def _filter_history_df(history_df, inst_id=None, bar=None):
    filtered_df = history_df.copy()

    if inst_id is not None:
        filtered_df = filtered_df[filtered_df["instrument"] == inst_id]

    if bar is not None:
        filtered_df = filtered_df[filtered_df["bar"] == bar]

    return filtered_df


def store_forecast_snapshot(inst_id, bar, forecast_points):
    # hier speichern wir nur die echten Zukunftspunkte,
    # also nicht den ersten Punkt, der nur der aktuelle Anker ist
    if len(forecast_points) < 2:
        return 0

    history_df = _load_forecast_history_df()
    anchor_timestamp = int(forecast_points[0]["timestamp"])
    created_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    new_rows = []

    for step_ahead, point in enumerate(forecast_points[1:], start=1):
        target_timestamp = int(point["timestamp"])
        forecast_close = float(point["close"])

        duplicate_mask = (
            (history_df["instrument"] == inst_id) &
            (history_df["bar"] == bar) &
            (history_df["forecast_origin_timestamp"] == anchor_timestamp) &
            (history_df["target_timestamp"] == target_timestamp)
        )

        if duplicate_mask.any():
            continue

        new_rows.append(
            {
                "instrument": inst_id,
                "bar": bar,
                "forecast_origin_timestamp": anchor_timestamp,
                "target_timestamp": target_timestamp,
                "step_ahead": step_ahead,
                "forecast_close": round(forecast_close, 2),
                "actual_close": None,
                "error_value": None,
                "abs_error": None,
                "abs_error_pct": None,
                "status": "PENDING",
                "created_at": created_at,
                "evaluated_at": None,
            }
        )

    if len(new_rows) == 0:
        return 0

    new_rows_df = pd.DataFrame(new_rows, columns=FORECAST_HISTORY_COLUMNS)

    if history_df.empty:
        updated_df = new_rows_df
    else:
        updated_df = pd.concat([history_df, new_rows_df], ignore_index=True)

    _save_forecast_history_df(updated_df)
    return len(new_rows)


def reconcile_forecasts_with_actuals(inst_id, bar, candles):
    # hier prüfen wir, ob zu alten Forecast-Zeitpunkten inzwischen
    # echte Candle-Close-Werte vorhanden sind
    if len(candles) < 2:
        return 0

    history_df = _load_forecast_history_df()

    if history_df.empty:
        return 0

    actual_close_by_timestamp = {}

    for candle in candles:
        candle_timestamp = int(candle["timestamp"])
        actual_close_by_timestamp[candle_timestamp] = float(candle["close"])

    newest_visible_timestamp = max(actual_close_by_timestamp.keys())

    pending_mask = (
        (history_df["instrument"] == inst_id) &
        (history_df["bar"] == bar) &
        (history_df["status"] == "PENDING")
    )

    pending_indices = history_df[pending_mask].index.tolist()
    updated_count = 0
    evaluated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    for index in pending_indices:
        target_timestamp = history_df.at[index, "target_timestamp"]

        if pd.isna(target_timestamp):
            continue

        target_timestamp = int(target_timestamp)

        # hier warten wir bewusst, bis der Zielzeitpunkt nicht mehr
        # die neueste sichtbare Kerze ist, damit wir keinen halbfertigen Candle erwischen
        if target_timestamp >= newest_visible_timestamp:
            continue

        if target_timestamp not in actual_close_by_timestamp:
            continue

        forecast_close = float(history_df.at[index, "forecast_close"])
        actual_close = float(actual_close_by_timestamp[target_timestamp])

        error_value = actual_close - forecast_close
        abs_error = abs(error_value)

        if actual_close != 0:
            abs_error_pct = (abs_error / actual_close) * 100
        else:
            abs_error_pct = 0.0

        history_df.at[index, "actual_close"] = round(actual_close, 2)
        history_df.at[index, "error_value"] = round(error_value, 2)
        history_df.at[index, "abs_error"] = round(abs_error, 2)
        history_df.at[index, "abs_error_pct"] = round(abs_error_pct, 4)
        history_df.at[index, "status"] = "EVALUATED"
        history_df.at[index, "evaluated_at"] = evaluated_at

        updated_count += 1

    if updated_count > 0:
        _save_forecast_history_df(history_df)

    return updated_count


def build_forecast_accuracy_summary(inst_id=None, bar=None):
    history_df = _load_forecast_history_df()
    history_df = _filter_history_df(history_df, inst_id=inst_id, bar=bar)

    if history_df.empty:
        return {
            "total_count": 0,
            "evaluated_count": 0,
            "pending_count": 0,
            "mae": None,
            "mape": None,
            "last_abs_error": None,
        }

    evaluated_df = history_df[history_df["status"] == "EVALUATED"].copy()
    pending_df = history_df[history_df["status"] == "PENDING"].copy()

    if evaluated_df.empty:
        mae = None
        mape = None
        last_abs_error = None
    else:
        evaluated_df = evaluated_df.sort_values("target_timestamp", ascending=False)
        mae = round(float(evaluated_df["abs_error"].mean()), 2)
        mape = round(float(evaluated_df["abs_error_pct"].mean()), 2)
        last_abs_error = round(float(evaluated_df.iloc[0]["abs_error"]), 2)

    return {
        "total_count": int(len(history_df)),
        "evaluated_count": int(len(evaluated_df)),
        "pending_count": int(len(pending_df)),
        "mae": mae,
        "mape": mape,
        "last_abs_error": last_abs_error,
    }


def build_forecast_accuracy_by_step(inst_id=None, bar=None):
    # hier zerlegen wir die Accuracy zusätzlich nach Forecast-Schritten,
    # damit man z. B. Schritt 1 direkt mit Schritt 5 vergleichen kann
    history_df = _load_forecast_history_df()
    history_df = _filter_history_df(history_df, inst_id=inst_id, bar=bar)

    if history_df.empty:
        return []

    step_values = history_df["step_ahead"].dropna()

    if step_values.empty:
        return []

    max_step = int(step_values.max())
    step_rows = []

    for step in range(1, max_step + 1):
        step_df = history_df[history_df["step_ahead"] == step].copy()

        if step_df.empty:
            continue

        evaluated_df = step_df[step_df["status"] == "EVALUATED"].copy()
        pending_df = step_df[step_df["status"] == "PENDING"].copy()

        if evaluated_df.empty:
            mae = None
            mape = None
            last_abs_error = None
        else:
            evaluated_df = evaluated_df.sort_values("target_timestamp", ascending=False)
            mae = round(float(evaluated_df["abs_error"].mean()), 2)
            mape = round(float(evaluated_df["abs_error_pct"].mean()), 2)
            last_abs_error = round(float(evaluated_df.iloc[0]["abs_error"]), 2)

        step_rows.append(
            {
                "Schritt": step,
                "Gesamt": int(len(step_df)),
                "Ausgewertet": int(len(evaluated_df)),
                "Offen": int(len(pending_df)),
                "MAE": mae,
                "MAPE %": mape,
                "Letzter absoluter Fehler": last_abs_error,
            }
        )

    return step_rows


def load_recent_forecast_evaluations(inst_id=None, bar=None, limit=10):
    history_df = _load_forecast_history_df()
    history_df = _filter_history_df(history_df, inst_id=inst_id, bar=bar)

    if history_df.empty:
        return []

    evaluated_df = history_df[history_df["status"] == "EVALUATED"].copy()

    if evaluated_df.empty:
        return []

    evaluated_df = evaluated_df.sort_values(
        ["target_timestamp", "step_ahead"],
        ascending=[False, True]
    ).head(limit)

    evaluated_df["forecast_origin_time"] = pd.to_datetime(
        evaluated_df["forecast_origin_timestamp"],
        unit="ms"
    ).dt.strftime("%Y-%m-%d %H:%M")

    evaluated_df["target_time"] = pd.to_datetime(
        evaluated_df["target_timestamp"],
        unit="ms"
    ).dt.strftime("%Y-%m-%d %H:%M")

    display_df = evaluated_df[
        [
            "forecast_origin_time",
            "target_time",
            "step_ahead",
            "forecast_close",
            "actual_close",
            "error_value",
            "abs_error",
            "abs_error_pct",
        ]
    ].copy()

    display_df = display_df.rename(
        columns={
            "forecast_origin_time": "Forecast erstellt",
            "target_time": "Ist-Zeitpunkt",
            "step_ahead": "Schritt",
            "forecast_close": "Soll",
            "actual_close": "Ist",
            "error_value": "Abweichung",
            "abs_error": "Absoluter Fehler",
            "abs_error_pct": "Fehler %",
        }
    )

    return display_df.to_dict(orient="records")