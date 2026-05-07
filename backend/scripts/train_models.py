from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.metrics import mean_absolute_error, mean_squared_error


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
PROCESSED_DIR = BACKEND_DIR / "data" / "processed"
MODEL_DIR = BACKEND_DIR / "data" / "models"
FORECAST_FEATURES = PROCESSED_DIR / "forecast_features.parquet"

sys.path.append(str(BACKEND_DIR))

from ml.lstm_model import train_lstm_forecaster  # noqa: E402
from ml.meta_learner import EnsembleMetaLearner  # noqa: E402
from ml.prophet_model import ProphetForecaster  # noqa: E402
from ml.xgb_model import XGBForecaster  # noqa: E402


HORIZONS = {
    "1h": {"target": "load_mw_next_1h", "steps": 4},
    "4h": {"target": "load_mw_next_4h", "steps": 16},
    "24h": {"target": "load_mw_next_24h", "steps": 96},
}
ZONES = [f"zone_{idx}" for idx in range(1, 7)]

TARGET_COLUMNS = {"load_mw_next_1h", "load_mw_next_4h", "load_mw_next_24h"}
NON_FEATURE_COLUMNS = {
    "timestamp",
    "weather_hour",
    "month_key",
    *TARGET_COLUMNS,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train VIDYUT AI forecasting models.")
    parser.add_argument("--zone", default="zone_1", choices=[*ZONES, "all"])
    parser.add_argument("--horizon", default="24h", choices=[*HORIZONS.keys(), "all"])
    parser.add_argument("--retrain-from-scratch", action="store_true")
    parser.add_argument("--skip-lstm", action="store_true", help="Useful for fast tabular-only experiments.")
    parser.add_argument("--max-xgb-rows", type=int, default=800_000)
    parser.add_argument("--lstm-epochs", type=int, default=60)
    return parser.parse_args()


def load_features() -> pd.DataFrame:
    if not FORECAST_FEATURES.exists():
        raise FileNotFoundError(
            f"Missing {FORECAST_FEATURES}. Run backend/scripts/feature_engineering.py first."
        )
    logger.info("Loading forecast features from {}", FORECAST_FEATURES)
    df = pd.read_parquet(FORECAST_FEATURES)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("timestamp").reset_index(drop=True)


def select_feature_columns(df: pd.DataFrame, target_column: str) -> list[str]:
    excluded = NON_FEATURE_COLUMNS | {target_column}
    columns = []
    for column in df.columns:
        if column in excluded:
            continue
        if column in {"feeder_id", "zone_id"}:
            continue
        if pd.api.types.is_numeric_dtype(df[column]) or pd.api.types.is_categorical_dtype(df[column]):
            columns.append(column)
    return columns


def chronological_holdout(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    unique_times = np.array(sorted(df["timestamp"].unique()))
    train_end = unique_times[int(len(unique_times) * 0.70)]
    test_start = unique_times[int(len(unique_times) * 0.85)]
    train = df[df["timestamp"] < train_end].copy()
    val = df[(df["timestamp"] >= train_end) & (df["timestamp"] < test_start)].copy()
    test = df[df["timestamp"] >= test_start].copy()
    return train, val, test


def metrics_dict(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true = y_true[mask]
    y_pred = y_pred[mask]
    denominator = np.clip(np.abs(y_true), 1e-6, None)
    return {
        "mape": round(float(np.mean(np.abs((y_true - y_pred) / denominator)) * 100.0), 4),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "rmse": round(float(mean_squared_error(y_true, y_pred, squared=False)), 4),
    }


def prepare_prophet_frame(df: pd.DataFrame, target_column: str) -> pd.DataFrame:
    prophet_df = (
        df.groupby("timestamp", as_index=False)
        .agg(
            y=(target_column, "mean"),
            temperature_c=("temperature_c", "mean"),
            is_holiday=("is_holiday", "max"),
            ev_density_per_km2=("ev_density_per_km2", "mean"),
            is_peak_hour=("is_peak_hour", "max"),
        )
        .rename(columns={"timestamp": "ds"})
        .dropna()
    )
    return prophet_df


def train_prophet(
    zone_df: pd.DataFrame,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    zone: str,
    target_column: str,
) -> tuple[ProphetForecaster, pd.DataFrame, Path]:
    prophet = ProphetForecaster(zone=zone, model_dir=MODEL_DIR)
    prophet_train = prepare_prophet_frame(train_df, target_column)
    prophet.fit(prophet_train)

    future = prepare_prophet_frame(zone_df, target_column).drop(columns=["y"])
    forecast = prophet.predict(periods=0, future_regressors_df=future)
    prediction_frame = test_df[["timestamp", target_column]].merge(
        forecast.rename(columns={"ds": "timestamp", "yhat": "prophet_pred"})[
            ["timestamp", "prophet_pred"]
        ],
        on="timestamp",
        how="left",
    )
    prediction_frame["prophet_pred"] = prediction_frame["prophet_pred"].fillna(method="ffill").fillna(method="bfill")
    path = prophet.save()
    return prophet, prediction_frame, path


def align_predictions(
    test_df: pd.DataFrame,
    target_column: str,
    lstm_predictions: pd.DataFrame,
    xgb_predictions: np.ndarray,
    prophet_predictions: pd.DataFrame,
) -> pd.DataFrame:
    base = test_df[["timestamp", "feeder_id", target_column]].copy()
    base = base.rename(columns={target_column: "y_true"})
    base["xgb"] = xgb_predictions

    if not lstm_predictions.empty:
        lstm_frame = lstm_predictions.rename(columns={"y_pred": "lstm"})[
            ["timestamp", "feeder_id", "lstm"]
        ]
        lstm_frame["timestamp"] = pd.to_datetime(lstm_frame["timestamp"])
        base = base.merge(lstm_frame, on=["timestamp", "feeder_id"], how="left")
    else:
        base["lstm"] = np.nan

    prophet_frame = prophet_predictions.rename(
        columns={target_column: "y_true", "prophet_pred": "prophet"}
    )[["timestamp", "prophet"]]
    base = base.merge(prophet_frame, on="timestamp", how="left")

    for column in ["lstm", "xgb", "prophet"]:
        base[column] = base[column].fillna(base[column].median())
    return base.dropna(subset=["y_true", "lstm", "xgb", "prophet"])


def log_mlflow_run(
    zone: str,
    horizon: str,
    report: dict,
    artifacts: list[Path],
) -> None:
    try:
        import mlflow
    except ImportError:
        logger.warning("MLflow is not installed; skipping MLflow run logging.")
        return

    mlflow.set_tracking_uri(f"file:///{(PROJECT_DIR / 'mlruns').as_posix()}")
    mlflow.set_experiment("vidyut-ai-forecasting")
    with mlflow.start_run(run_name=f"{zone}_{horizon}"):
        mlflow.log_param("zone", zone)
        mlflow.log_param("horizon", horizon)
        for model_name, values in report["metrics"].items():
            for metric_name, value in values.items():
                mlflow.log_metric(f"{model_name}_{metric_name}", value)
        for name, weight in report["ensemble_weights"].items():
            mlflow.log_metric(f"ensemble_weight_{name}", weight)
        for artifact in artifacts:
            if artifact.exists():
                mlflow.log_artifact(str(artifact))


def train_zone_horizon(
    df: pd.DataFrame,
    zone: str,
    horizon: str,
    skip_lstm: bool,
    max_xgb_rows: int,
    lstm_epochs: int,
    retrain_from_scratch: bool,
) -> dict:
    target_column = HORIZONS[horizon]["target"]
    horizon_steps = HORIZONS[horizon]["steps"]
    zone_df = df[df["zone_id"].astype(str) == zone].dropna(subset=[target_column]).copy()
    if zone_df.empty:
        raise ValueError(f"No rows available for {zone} and {horizon}.")

    train_df, val_df, test_df = chronological_holdout(zone_df)
    feature_columns = select_feature_columns(zone_df, target_column)
    logger.info(
        "Training zone={} horizon={} rows={} features={}",
        zone,
        horizon,
        f"{len(zone_df):,}",
        len(feature_columns),
    )
    if retrain_from_scratch:
        for artifact in MODEL_DIR.glob(f"*{zone}_{horizon}*"):
            artifact.unlink(missing_ok=True)
        report = MODEL_DIR / f"training_report_{zone}_{horizon}.json"
        report.unlink(missing_ok=True)

    artifacts: list[Path] = []
    lstm_predictions = pd.DataFrame()
    if skip_lstm:
        logger.warning("Skipping LSTM because --skip-lstm was provided.")
    else:
        lstm_result = train_lstm_forecaster(
            zone_df,
            feature_columns=feature_columns[:40] if len(feature_columns) >= 40 else feature_columns,
            zone=zone,
            horizon_label=horizon,
            horizon_steps=horizon_steps,
            model_dir=MODEL_DIR,
            epochs=lstm_epochs,
        )
        lstm_predictions = lstm_result.predictions
        artifacts.extend([lstm_result.checkpoint_path, lstm_result.curve_path])

    xgb = XGBForecaster(zone=zone, horizon=horizon, model_dir=MODEL_DIR)
    xgb.fit(train_df[feature_columns], train_df[target_column], max_rows=max_xgb_rows)
    xgb_predictions = xgb.predict(test_df[feature_columns])
    xgb_model_path = xgb.save()
    shap_path, top_features = xgb.save_shap_summary(train_df[feature_columns])
    artifacts.extend([xgb_model_path, shap_path])

    _, prophet_prediction_frame, prophet_path = train_prophet(zone_df, train_df, test_df, zone, target_column)
    artifacts.append(prophet_path)

    aligned = align_predictions(test_df, target_column, lstm_predictions, xgb_predictions, prophet_prediction_frame)
    if skip_lstm or aligned["lstm"].isna().all():
        aligned["lstm"] = aligned["xgb"]

    meta = EnsembleMetaLearner()
    validation_errors = {
        "lstm": metrics_dict(aligned["y_true"], aligned["lstm"])["mae"],
        "xgb": metrics_dict(aligned["y_true"], aligned["xgb"])["mae"],
        "prophet": metrics_dict(aligned["y_true"], aligned["prophet"])["mae"],
    }
    meta.update_weights(validation_errors)
    meta.fit(aligned[["lstm", "xgb", "prophet"]], aligned["y_true"])
    ensemble_prediction = meta.predict(aligned[["lstm", "xgb", "prophet"]])["prediction"]

    metrics = {
        "lstm": metrics_dict(aligned["y_true"], aligned["lstm"]),
        "xgb": metrics_dict(aligned["y_true"], aligned["xgb"]),
        "prophet": metrics_dict(aligned["y_true"], aligned["prophet"]),
        "ensemble": metrics_dict(aligned["y_true"], ensemble_prediction),
    }

    report = {
        "zone": zone,
        "horizon": horizon,
        "train_end": str(train_df["timestamp"].max()),
        "test_start": str(test_df["timestamp"].min()),
        "test_end": str(test_df["timestamp"].max()),
        "metrics": metrics,
        "ensemble_weights": meta.get_weights(),
        "xgb_top_features": top_features,
    }
    report_path = MODEL_DIR / f"training_report_{zone}_{horizon}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    artifacts.append(report_path)

    log_mlflow_run(zone, horizon, report, artifacts)
    if metrics["ensemble"]["mape"] >= 8.0:
        logger.warning(
            "Target MAPE not achieved for {} {}: ensemble MAPE={}%",
            zone,
            horizon,
            metrics["ensemble"]["mape"],
        )
    return report


def print_summary(reports: list[dict]) -> None:
    rows = []
    for report in reports:
        row = {"zone": report["zone"], "horizon": report["horizon"]}
        for model_name, values in report["metrics"].items():
            row[f"{model_name}_mape"] = values["mape"]
            row[f"{model_name}_mae"] = values["mae"]
            row[f"{model_name}_rmse"] = values["rmse"]
        rows.append(row)
    print("\nFinal training summary")
    print(pd.DataFrame(rows).to_string(index=False))


def main() -> None:
    args = parse_args()
    logger.remove()
    logger.add(lambda message: print(message, end=""), level="INFO")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df = load_features()
    zones = ZONES if args.zone == "all" else [args.zone]
    horizons = list(HORIZONS) if args.horizon == "all" else [args.horizon]

    reports = []
    for zone in zones:
        for horizon in horizons:
            reports.append(
                train_zone_horizon(
                    df,
                    zone=zone,
                    horizon=horizon,
                    skip_lstm=args.skip_lstm,
                    max_xgb_rows=args.max_xgb_rows,
                    lstm_epochs=args.lstm_epochs,
                    retrain_from_scratch=args.retrain_from_scratch,
                )
            )
    print_summary(reports)


if __name__ == "__main__":
    main()
