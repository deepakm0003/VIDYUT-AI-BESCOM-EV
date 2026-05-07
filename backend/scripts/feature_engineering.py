from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow  # noqa: F401 - ensures the configured parquet engine is importable.
from loguru import logger
from tqdm import tqdm


SEED = 42
BACKEND_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BACKEND_DIR / "data" / "raw"
PROCESSED_DIR = BACKEND_DIR / "data" / "processed"

FORECAST_OUT = PROCESSED_DIR / "forecast_features.parquet"
SCHEDULER_OUT = PROCESSED_DIR / "scheduler_features.parquet"
SITE_OUT = PROCESSED_DIR / "site_scoring_features.parquet"
MANIFEST_OUT = PROCESSED_DIR / "feature_manifest.json"

TOTAL_ADDRESSABLE_EVS = 600_000
EV_EVENT_CHUNK_SIZE = 250_000

KARNATAKA_HOLIDAYS = {
    "2024-01-15",
    "2024-01-26",
    "2024-03-08",
    "2024-03-29",
    "2024-04-09",
    "2024-04-11",
    "2024-05-01",
    "2024-06-17",
    "2024-08-15",
    "2024-09-07",
    "2024-10-02",
    "2024-10-11",
    "2024-10-31",
    "2024-11-01",
    "2024-12-25",
    "2025-01-14",
    "2025-01-26",
    "2025-03-31",
    "2025-04-10",
    "2025-04-18",
    "2025-05-01",
    "2025-06-07",
    "2025-08-15",
    "2025-08-27",
    "2025-10-02",
    "2025-10-20",
    "2025-11-01",
    "2025-12-25",
}


def require_raw_file(filename: str) -> Path:
    path = RAW_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing raw input: {path}")
    return path


def save_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    logger.info("Saved {} rows to {}", f"{len(df):,}", path)


def optimize_forecast_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    float_cols = df.select_dtypes(include=["float64"]).columns
    int_cols = df.select_dtypes(include=["int64", "UInt32", "UInt8"]).columns

    for column in float_cols:
        df[column] = df[column].astype("float32")
    for column in int_cols:
        if column.endswith("_count") or column in {"days_since_start", "week_number"}:
            df[column] = df[column].astype("int32")
        else:
            df[column] = df[column].astype("int16")

    for column in ("feeder_id", "zone_id"):
        if column in df.columns:
            df[column] = df[column].astype("category")
    return df


def infer_feeder_cadence_minutes(feeder_df: pd.DataFrame) -> int:
    sample = feeder_df[["timestamp", "feeder_id"]].head(250_000).copy()
    diffs = (
        sample.sort_values(["feeder_id", "timestamp"])
        .groupby("feeder_id", observed=True)["timestamp"]
        .diff()
        .dropna()
        .dt.total_seconds()
        .div(60)
    )
    if diffs.empty:
        return 15
    cadence = int(round(float(diffs.median())))
    return max(15, cadence)


def periods_for_hours(hours: int, cadence_minutes: int) -> int:
    return max(1, int(round((hours * 60) / cadence_minutes)))


def load_feeder_data() -> pd.DataFrame:
    logger.info("Loading feeder load data")
    feeder = pd.read_csv(
        require_raw_file("feeder_load_data.csv"),
        parse_dates=["timestamp"],
        dtype={
            "feeder_id": "category",
            "zone_id": "category",
            "load_mw": "float32",
            "headroom_mw": "float32",
            "voltage_pu": "float32",
            "temperature_c": "float32",
            "is_overload": "int8",
        },
    )
    feeder = feeder.sort_values(["feeder_id", "timestamp"], kind="mergesort").reset_index(drop=True)
    feeder["load_mw"] = feeder.groupby("feeder_id", observed=True)["load_mw"].ffill()
    feeder["headroom_mw"] = feeder.groupby("feeder_id", observed=True)["headroom_mw"].ffill()
    feeder["voltage_pu"] = feeder.groupby("feeder_id", observed=True)["voltage_pu"].ffill()
    logger.info("Loaded feeder rows: {}", f"{len(feeder):,}")
    return feeder


def build_time_features(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Building time features")
    timestamp = df["timestamp"]
    df["hour_of_day"] = timestamp.dt.hour.astype("int16")
    df["minute_of_hour"] = timestamp.dt.minute.astype("int16")
    df["day_of_week"] = timestamp.dt.dayofweek.astype("int16")
    df["month"] = timestamp.dt.month.astype("int16")
    df["quarter"] = timestamp.dt.quarter.astype("int16")
    df["is_weekend"] = (df["day_of_week"] >= 5).astype("int8")
    df["is_holiday"] = timestamp.dt.strftime("%Y-%m-%d").isin(KARNATAKA_HOLIDAYS).astype("int8")
    df["is_peak_hour"] = df["hour_of_day"].between(18, 20).astype("int8")
    df["days_since_start"] = (timestamp.dt.normalize() - timestamp.min().normalize()).dt.days.astype("int32")
    df["week_number"] = timestamp.dt.isocalendar().week.astype("int16")
    return df


def build_load_features(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    logger.info("Building lag, rolling, and target features")
    cadence_minutes = infer_feeder_cadence_minutes(df)
    logger.info("Inferred feeder cadence: {} minutes", cadence_minutes)

    grouped_load = df.groupby("feeder_id", observed=True)["load_mw"]
    lag_specs = {
        "load_mw_lag_1h": 1,
        "load_mw_lag_2h": 2,
        "load_mw_lag_4h": 4,
        "load_mw_lag_24h": 24,
        "load_mw_lag_48h": 48,
        "load_mw_lag_1week": 168,
    }
    for column, hours in lag_specs.items():
        df[column] = grouped_load.shift(periods_for_hours(hours, cadence_minutes))

    periods_4h = periods_for_hours(4, cadence_minutes)
    periods_24h = periods_for_hours(24, cadence_minutes)
    df["load_mw_rolling_mean_4h"] = grouped_load.transform(
        lambda values: values.rolling(periods_4h, min_periods=1).mean()
    )
    df["load_mw_rolling_mean_24h"] = grouped_load.transform(
        lambda values: values.rolling(periods_24h, min_periods=1).mean()
    )
    df["load_mw_rolling_std_4h"] = grouped_load.transform(
        lambda values: values.rolling(periods_4h, min_periods=2).std()
    )
    df["load_mw_rolling_std_24h"] = grouped_load.transform(
        lambda values: values.rolling(periods_24h, min_periods=2).std()
    )
    df["load_mw_ewm_alpha_0.3"] = grouped_load.transform(lambda values: values.ewm(alpha=0.3, adjust=False).mean())
    df["load_mw_ewm_alpha_0.7"] = grouped_load.transform(lambda values: values.ewm(alpha=0.7, adjust=False).mean())
    df["pct_headroom_used"] = df["load_mw"] / (df["load_mw"] + df["headroom_mw"]).replace(0, np.nan)

    df["load_mw_next_1h"] = grouped_load.shift(-periods_for_hours(1, cadence_minutes))
    df["load_mw_next_4h"] = grouped_load.shift(-periods_for_hours(4, cadence_minutes))
    df["load_mw_next_24h"] = grouped_load.shift(-periods_for_hours(24, cadence_minutes))
    return df, cadence_minutes


def load_weather_features() -> pd.DataFrame:
    logger.info("Loading weather data")
    weather = pd.read_csv(require_raw_file("weather_data.csv"), parse_dates=["timestamp"])
    weather = weather.sort_values("timestamp").reset_index(drop=True)
    numeric_cols = ["temperature_c", "humidity_pct", "wind_speed_kmh", "solar_irradiance_wm2", "is_rain", "feels_like_c"]
    for column in numeric_cols:
        weather[column] = weather[column].fillna(weather[column].median())

    weather["temperature_lag_1h"] = weather["temperature_c"].shift(1)
    weather["temperature_rolling_mean_4h"] = weather["temperature_c"].rolling(4, min_periods=1).mean()
    weather["cooling_degree_hours"] = np.maximum(0.0, weather["temperature_c"] - 25.0)
    weather = weather.rename(columns={"timestamp": "weather_hour"})
    return weather[
        [
            "weather_hour",
            "temperature_c",
            "humidity_pct",
            "wind_speed_kmh",
            "solar_irradiance_wm2",
            "is_rain",
            "temperature_lag_1h",
            "temperature_rolling_mean_4h",
            "cooling_degree_hours",
        ]
    ]


def load_vahan_zone_features() -> pd.DataFrame:
    logger.info("Loading VAHAN registration features")
    vahan = pd.read_csv(require_raw_file("vahan_ev_registrations.csv"))
    zone_month = (
        vahan.groupby(["month", "zone_id"], as_index=False)
        .agg(
            ev_density_per_km2=("ev_density_per_km2", "mean"),
            ev_count_cumulative=("ev_count_cumulative", "sum"),
        )
    )
    zone_month["ev_adoption_rate"] = zone_month["ev_count_cumulative"] / TOTAL_ADDRESSABLE_EVS
    return zone_month.drop(columns=["ev_count_cumulative"]).rename(columns={"month": "month_key"})


def build_ev_interval_features() -> pd.DataFrame:
    logger.info("Building active EV session interval features")
    events = []
    session_path = require_raw_file("ev_sessions.csv")

    read_columns = [
        "feeder_id",
        "start_time",
        "end_time",
        "duration_minutes",
        "energy_kwh",
        "session_type",
    ]
    for chunk in tqdm(
        pd.read_csv(session_path, usecols=read_columns, chunksize=EV_EVENT_CHUNK_SIZE),
        desc="ev active events",
    ):
        chunk["start_time"] = pd.to_datetime(chunk["start_time"])
        chunk["end_time"] = pd.to_datetime(chunk["end_time"])
        chunk["start_interval"] = chunk["start_time"].dt.floor("15min")
        chunk["end_interval"] = chunk["end_time"].dt.ceil("15min")
        avg_power_mw = (chunk["energy_kwh"] / (chunk["duration_minutes"] / 60.0)).replace([np.inf, -np.inf], np.nan)
        avg_power_mw = avg_power_mw.fillna(0.0).clip(0.0, 180.0) / 1000.0
        bmtc_flag = (chunk["session_type"] == "bmtc_bus").astype("int16")

        starts = pd.DataFrame(
            {
                "feeder_id": chunk["feeder_id"].to_numpy(),
                "timestamp": chunk["start_interval"].to_numpy(),
                "active_delta": 1,
                "ev_load_delta_mw": avg_power_mw.to_numpy(),
                "bmtc_delta": bmtc_flag.to_numpy(),
            }
        )
        ends = pd.DataFrame(
            {
                "feeder_id": chunk["feeder_id"].to_numpy(),
                "timestamp": chunk["end_interval"].to_numpy(),
                "active_delta": -1,
                "ev_load_delta_mw": -avg_power_mw.to_numpy(),
                "bmtc_delta": -bmtc_flag.to_numpy(),
            }
        )
        events.extend([starts, ends])

    event_df = pd.concat(events, ignore_index=True)
    event_df = (
        event_df.groupby(["feeder_id", "timestamp"], as_index=False)
        .agg(
            active_delta=("active_delta", "sum"),
            ev_load_delta_mw=("ev_load_delta_mw", "sum"),
            bmtc_delta=("bmtc_delta", "sum"),
        )
        .sort_values(["feeder_id", "timestamp"])
    )
    event_df["active_sessions_count"] = event_df.groupby("feeder_id", observed=True)["active_delta"].cumsum().clip(lower=0)
    event_df["ev_load_contribution_mw"] = event_df.groupby("feeder_id", observed=True)["ev_load_delta_mw"].cumsum().clip(lower=0)
    event_df["bmtc_buses_charging"] = event_df.groupby("feeder_id", observed=True)["bmtc_delta"].cumsum().clip(lower=0)
    return event_df[
        [
            "feeder_id",
            "timestamp",
            "active_sessions_count",
            "ev_load_contribution_mw",
            "bmtc_buses_charging",
        ]
    ]


def merge_ev_state_asof(forecast: pd.DataFrame, ev_state: pd.DataFrame) -> pd.DataFrame:
    logger.info("Joining active EV state to feeder intervals")
    ev_state = ev_state.sort_values(["feeder_id", "timestamp"])
    merged_parts = []
    left_columns = forecast.columns

    for feeder_id, left in tqdm(forecast.groupby("feeder_id", observed=True, sort=False), desc="merge ev state"):
        right = ev_state[ev_state["feeder_id"] == feeder_id]
        left_sorted = left.sort_values("timestamp")
        if right.empty:
            left_sorted = left_sorted.copy()
            left_sorted["active_sessions_count"] = 0
            left_sorted["ev_load_contribution_mw"] = 0.0
            left_sorted["bmtc_buses_charging"] = 0
        else:
            left_sorted = pd.merge_asof(
                left_sorted,
                right.drop(columns=["feeder_id"]).sort_values("timestamp"),
                on="timestamp",
                direction="backward",
            )
            left_sorted["active_sessions_count"] = left_sorted["active_sessions_count"].fillna(0)
            left_sorted["ev_load_contribution_mw"] = left_sorted["ev_load_contribution_mw"].fillna(0.0)
            left_sorted["bmtc_buses_charging"] = left_sorted["bmtc_buses_charging"].fillna(0)
        merged_parts.append(left_sorted)

    return pd.concat(merged_parts, ignore_index=True)[
        list(left_columns) + ["active_sessions_count", "ev_load_contribution_mw", "bmtc_buses_charging"]
    ]


def build_forecast_features() -> tuple[pd.DataFrame, int]:
    feeder = load_feeder_data()
    feeder = build_time_features(feeder)
    feeder, cadence_minutes = build_load_features(feeder)

    logger.info("Joining weather features")
    weather = load_weather_features()
    feeder["weather_hour"] = feeder["timestamp"].dt.floor("h")
    forecast = feeder.merge(weather, on="weather_hour", how="left", suffixes=("", "_weather"))
    if "temperature_c_weather" in forecast.columns:
        forecast["temperature_c"] = forecast["temperature_c_weather"].fillna(forecast["temperature_c"])
    forecast = forecast.drop(columns=["weather_hour", "temperature_c_weather"], errors="ignore")
    weather_feature_cols = [
        "humidity_pct",
        "wind_speed_kmh",
        "solar_irradiance_wm2",
        "is_rain",
        "temperature_lag_1h",
        "temperature_rolling_mean_4h",
        "cooling_degree_hours",
    ]
    for column in weather_feature_cols:
        forecast[column] = forecast[column].fillna(forecast[column].median())

    logger.info("Joining VAHAN zone-month features")
    vahan_zone = load_vahan_zone_features()
    forecast["month_key"] = forecast["timestamp"].dt.strftime("%Y-%m")
    forecast = forecast.merge(
        vahan_zone,
        on=["month_key", "zone_id"],
        how="left",
    ).drop(columns=["month_key"])
    forecast["ev_density_per_km2"] = forecast["ev_density_per_km2"].fillna(forecast["ev_density_per_km2"].median())
    forecast["ev_adoption_rate"] = forecast["ev_adoption_rate"].ffill().fillna(0.0)

    ev_state = build_ev_interval_features()
    forecast = merge_ev_state_asof(forecast, ev_state)

    fill_cols = [
        column
        for column in forecast.columns
        if column.startswith("load_mw_lag_")
        or column.startswith("load_mw_rolling_")
        or column.startswith("load_mw_ewm_")
        or column in {"pct_headroom_used", "temperature_lag_1h", "temperature_rolling_mean_4h"}
    ]
    for column in fill_cols:
        forecast[column] = forecast.groupby("feeder_id", observed=True)[column].ffill().bfill()

    forecast = optimize_forecast_dtypes(forecast)
    return forecast, cadence_minutes


def asof_forecast_lookup(sessions: pd.DataFrame, forecast_lookup: pd.DataFrame) -> pd.DataFrame:
    logger.info("Joining session starts to forecast/headroom lookup")
    parts = []
    for feeder_id, left in tqdm(sessions.groupby("feeder_id", observed=True, sort=False), desc="scheduler forecast join"):
        right = forecast_lookup[forecast_lookup["feeder_id"] == feeder_id].sort_values("timestamp")
        left_sorted = left.sort_values("start_interval")
        if right.empty:
            left_sorted["feeder_headroom_at_start"] = np.nan
            left_sorted["forecast_load_next_4h"] = np.nan
        else:
            merged = pd.merge_asof(
                left_sorted,
                right.drop(columns=["feeder_id"]),
                left_on="start_interval",
                right_on="timestamp",
                direction="nearest",
                tolerance=pd.Timedelta("1h"),
            )
            left_sorted = merged.drop(columns=["timestamp"], errors="ignore")
        parts.append(left_sorted)
    return pd.concat(parts, ignore_index=True)


def build_scheduler_features(forecast: pd.DataFrame) -> pd.DataFrame:
    logger.info("Building scheduler/session features")
    sessions = pd.read_csv(
        require_raw_file("ev_sessions.csv"),
        parse_dates=["start_time", "end_time"],
        dtype={
            "session_id": "string",
            "station_id": "category",
            "zone_id": "category",
            "feeder_id": "category",
            "duration_minutes": "float32",
            "energy_kwh": "float32",
            "vehicle_type": "category",
            "session_type": "category",
        },
    )
    sessions["start_interval"] = sessions["start_time"].dt.floor("15min")
    sessions["energy_needed_kwh"] = sessions["energy_kwh"].astype("float32")
    sessions["max_power_kw"] = (
        sessions["energy_kwh"] / (sessions["duration_minutes"] / 60.0)
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(3.0, 180.0)
    sessions["deadline_time"] = sessions["end_time"]
    sessions["is_bmtc"] = (sessions["session_type"] == "bmtc_bus").astype("int8")
    sessions["flexibility_minutes"] = np.maximum(
        0.0,
        (sessions["deadline_time"] - sessions["start_time"]).dt.total_seconds() / 60.0
        - sessions["duration_minutes"],
    )
    sessions["preferred_window_start"] = np.where(
        sessions["is_bmtc"].eq(1),
        sessions["start_time"].dt.normalize() + pd.to_timedelta(22, unit="h"),
        sessions["start_time"],
    )
    sessions["preferred_window_end"] = np.where(
        sessions["is_bmtc"].eq(1),
        sessions["start_time"].dt.normalize() + pd.to_timedelta(28, unit="h"),
        sessions["deadline_time"],
    )
    sessions["priority_score"] = (
        sessions["is_bmtc"] * 50.0
        + sessions["energy_needed_kwh"].clip(0, 180) / 3.6
        + (1.0 / (1.0 + sessions["flexibility_minutes"] / 60.0)) * 30.0
    ).astype("float32")

    forecast_lookup = forecast[
        ["timestamp", "feeder_id", "headroom_mw", "load_mw_next_4h"]
    ].rename(
        columns={
            "headroom_mw": "feeder_headroom_at_start",
            "load_mw_next_4h": "forecast_load_next_4h",
        }
    )
    scheduler = asof_forecast_lookup(sessions, forecast_lookup)
    scheduler["feeder_headroom_at_start"] = scheduler["feeder_headroom_at_start"].fillna(
        scheduler["feeder_headroom_at_start"].median()
    )
    scheduler["forecast_load_next_4h"] = scheduler["forecast_load_next_4h"].fillna(
        scheduler["forecast_load_next_4h"].median()
    )

    scheduler = scheduler[
        [
            "session_id",
            "station_id",
            "feeder_id",
            "start_time",
            "energy_needed_kwh",
            "max_power_kw",
            "deadline_time",
            "feeder_headroom_at_start",
            "forecast_load_next_4h",
            "is_bmtc",
            "priority_score",
            "preferred_window_start",
            "preferred_window_end",
            "flexibility_minutes",
        ]
    ]
    return scheduler


def percentile_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    ranked = series.rank(pct=True)
    if not higher_is_better:
        ranked = 1.0 - ranked
    return (ranked * 100).clip(0, 100)


def build_site_scoring_features(forecast: pd.DataFrame) -> pd.DataFrame:
    logger.info("Building ward-level site scoring features")
    rng = np.random.default_rng(SEED)
    vahan = pd.read_csv(require_raw_file("vahan_ev_registrations.csv"))
    latest_month = vahan["month"].max()
    latest = vahan[vahan["month"] == latest_month].copy().reset_index(drop=True)

    zone_headroom = (
        forecast.groupby("zone_id", observed=True)
        .agg(
            avg_headroom_mw=("headroom_mw", "mean"),
            annual_solar=("solar_irradiance_wm2", "mean"),
        )
        .reset_index()
    )
    latest = latest.merge(zone_headroom, on="zone_id", how="left")

    n_rows = len(latest)
    latest["latitude"] = 12.9716 + rng.normal(0.0, 0.115, n_rows)
    latest["longitude"] = 77.5946 + rng.normal(0.0, 0.145, n_rows)
    latest["nearest_evcs_km"] = np.clip(7.0 - latest["ev_density_per_km2"] / 900.0 + rng.normal(0, 1.0, n_rows), 0.2, 12.0)
    latest["nearest_substation_km"] = np.clip(rng.gamma(2.0, 0.9, n_rows), 0.1, 8.0)
    latest["available_headroom_kva"] = np.clip(latest["avg_headroom_mw"].fillna(latest["avg_headroom_mw"].median()) * 1000, 100, 18_000)
    latest["avg_daily_traffic"] = np.clip(
        18_000 + latest["ev_density_per_km2"] * 7.5 + rng.normal(0, 5_000, n_rows),
        4_000,
        120_000,
    )
    latest["dwell_time_pct"] = np.clip(rng.normal(32, 12, n_rows) + latest["ev_density_per_km2"] / 320, 8, 82)
    latest["income_decile"] = rng.integers(1, 11, n_rows)
    latest["solar_irradiance_annual"] = latest["annual_solar"].fillna(latest["annual_solar"].median()) * 365 * 24 / 1000.0

    latest["ev_density_score"] = percentile_score(latest["ev_density_per_km2"])
    latest["grid_headroom_score"] = percentile_score(latest["available_headroom_kva"])
    latest["traffic_dwell_score"] = (
        0.55 * percentile_score(latest["avg_daily_traffic"]) + 0.45 * percentile_score(latest["dwell_time_pct"])
    )
    latest["coverage_gap_score"] = percentile_score(latest["nearest_evcs_km"])
    latest["land_feasibility_score"] = percentile_score(latest["nearest_substation_km"], higher_is_better=False)
    latest["equity_score"] = percentile_score(latest["income_decile"], higher_is_better=False)
    latest["renewable_score"] = percentile_score(latest["solar_irradiance_annual"])

    return latest[
        [
            "ward_id",
            "ward_name",
            "zone_id",
            "latitude",
            "longitude",
            "ev_density_score",
            "grid_headroom_score",
            "traffic_dwell_score",
            "coverage_gap_score",
            "land_feasibility_score",
            "equity_score",
            "renewable_score",
            "nearest_evcs_km",
            "nearest_substation_km",
            "available_headroom_kva",
            "avg_daily_traffic",
            "dwell_time_pct",
            "income_decile",
            "solar_irradiance_annual",
        ]
    ]


def correlation_preview(forecast: pd.DataFrame) -> None:
    logger.info("Computing correlation preview against load_mw_next_1h")
    numeric = forecast.select_dtypes(include=[np.number])
    sample = numeric.sample(n=min(750_000, len(numeric)), random_state=SEED)
    correlations = (
        sample.corr(numeric_only=True)["load_mw_next_1h"]
        .drop(labels=["load_mw_next_1h", "load_mw_next_4h", "load_mw_next_24h"], errors="ignore")
        .dropna()
        .abs()
        .sort_values(ascending=False)
        .head(20)
    )
    print("\nFeature importance preview by absolute correlation with load_mw_next_1h:")
    for name, value in correlations.items():
        print(f"  {name}: {value:.4f}")


def manifest_entry(df: pd.DataFrame, path: Path) -> dict:
    return {
        "path": str(path),
        "row_count": int(len(df)),
        "feature_count": int(len(df.columns)),
        "features": [
            {
                "name": column,
                "type": str(df[column].dtype),
                "null_count": int(df[column].isna().sum()),
            }
            for column in df.columns
        ],
    }


def write_feature_manifest(outputs: dict[str, tuple[pd.DataFrame, Path]], cadence_minutes: int) -> None:
    manifest = {
        "project": "VIDYUT AI",
        "source_dir": str(RAW_DIR),
        "processed_dir": str(PROCESSED_DIR),
        "feeder_cadence_minutes": cadence_minutes,
        "outputs": {
            name: manifest_entry(df, path)
            for name, (df, path) in outputs.items()
        },
    }
    with MANIFEST_OUT.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    logger.info("Saved feature manifest to {}", MANIFEST_OUT)


def main() -> None:
    logger.remove()
    logger.add(lambda message: print(message, end=""), level="INFO")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Starting VIDYUT AI feature engineering")
    forecast, cadence_minutes = build_forecast_features()
    correlation_preview(forecast)
    save_parquet(forecast, FORECAST_OUT)

    scheduler = build_scheduler_features(forecast)
    save_parquet(scheduler, SCHEDULER_OUT)

    site_scoring = build_site_scoring_features(forecast)
    save_parquet(site_scoring, SITE_OUT)

    write_feature_manifest(
        {
            "forecast_features.parquet": (forecast, FORECAST_OUT),
            "scheduler_features.parquet": (scheduler, SCHEDULER_OUT),
            "site_scoring_features.parquet": (site_scoring, SITE_OUT),
        },
        cadence_minutes,
    )

    print("\nFeature engineering complete.")
    print(f"  {FORECAST_OUT}")
    print(f"  {SCHEDULER_OUT}")
    print(f"  {SITE_OUT}")
    print(f"  {MANIFEST_OUT}")


if __name__ == "__main__":
    main()
