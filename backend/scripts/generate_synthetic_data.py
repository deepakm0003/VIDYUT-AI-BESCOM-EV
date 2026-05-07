from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm


SEED = 42
BACKEND_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BACKEND_DIR / "data" / "raw"

START_24M = pd.Timestamp("2024-01-01 00:00:00")
START_18M = pd.Timestamp("2024-01-01 00:00:00")

N_FEEDERS = 500
N_ZONES = 6
N_STATIONS = 200
N_WARDS = 198
N_BMTC_BUSES = 220

# The prompt's target total is 10-15M rows, while a complete 500 feeder x
# 24 month x 15-minute matrix is about 35M rows. This rotating telemetry panel
# uses every feeder ID across the full 24-month period and lands the feeder CSV
# near the requested 8.7M rows.
FEEDERS_PER_INTERVAL = 125
FEEDER_SHARDS = N_FEEDERS // FEEDERS_PER_INTERVAL

MONTHLY_TEMP_BASE_C = np.array(
    [24.0, 26.0, 29.0, 31.0, 30.5, 27.2, 25.5, 25.4, 26.0, 25.8, 24.3, 23.5]
)


def month_starts(start: pd.Timestamp, months: int) -> list[pd.Timestamp]:
    return [start + pd.DateOffset(months=offset) for offset in range(months)]


def reset_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()


def append_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, mode="a", index=False, header=not path.exists())


def round_frame(df: pd.DataFrame, decimals: dict[str, int]) -> pd.DataFrame:
    for column, places in decimals.items():
        df[column] = df[column].round(places)
    return df


def daily_load_shape(hour: np.ndarray) -> np.ndarray:
    morning_ramp = 0.15 * np.exp(-0.5 * ((hour - 8.0) / 1.7) ** 2)
    midday_plateau = 0.10 * np.exp(-0.5 * ((hour - 13.0) / 4.2) ** 2)
    evening_peak = 0.34 * np.exp(-0.5 * ((hour - 19.5) / 1.9) ** 2)
    valley = 0.13 * np.exp(-0.5 * ((hour - 3.0) / 1.5) ** 2)
    return 0.46 + morning_ramp + midday_plateau + evening_peak - valley


def ev_load_shape(hour: np.ndarray) -> np.ndarray:
    commute = 0.55 * np.exp(-0.5 * ((hour - 9.0) / 1.2) ** 2)
    evening = 1.20 * np.exp(-0.5 * ((hour - 19.5) / 1.8) ** 2)
    bus_depot = 0.80 * np.exp(-0.5 * ((hour - 23.5) / 2.2) ** 2)
    return 0.25 + commute + evening + bus_depot


def bengaluru_temperature(
    month: np.ndarray, hour: np.ndarray, rng: np.random.Generator, noise_scale: float = 1.1
) -> np.ndarray:
    seasonal = MONTHLY_TEMP_BASE_C[month - 1]
    diurnal = 4.1 * np.sin(((hour - 7.0) / 24.0) * 2.0 * np.pi)
    noise = rng.normal(0.0, noise_scale, len(month))
    return np.clip(seasonal + diurnal + noise, 18.0, 38.0)


def humidity_for_month(month: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    monsoon = np.isin(month, [6, 7, 8, 9, 10, 11])
    summer = np.isin(month, [3, 4, 5])
    base = np.where(monsoon, 78.0, np.where(summer, 46.0, 62.0))
    return np.clip(base + rng.normal(0.0, 8.0, len(month)), 25.0, 98.0)


def update_numeric_stats(stats: dict, df: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        values = df[column].to_numpy(dtype=float)
        column_stats = stats.setdefault(
            column,
            {"min": float("inf"), "max": float("-inf"), "sum": 0.0, "count": 0},
        )
        column_stats["min"] = min(column_stats["min"], float(np.min(values)))
        column_stats["max"] = max(column_stats["max"], float(np.max(values)))
        column_stats["sum"] += float(np.sum(values))
        column_stats["count"] += int(len(values))


def finalize_stats(stats: dict) -> dict:
    finalized = {}
    for column, values in stats.items():
        finalized[column] = {
            "min": round(values["min"], 4),
            "max": round(values["max"], 4),
            "mean": round(values["sum"] / values["count"], 4),
        }
    return finalized


def print_file_summary(name: str, meta: dict) -> None:
    print(f"\n{name}")
    print(f"  rows: {meta['row_count']:,}")
    if "date_start" in meta:
        print(f"  date range: {meta['date_start']} -> {meta['date_end']}")
    if "stats" in meta:
        for column, values in meta["stats"].items():
            print(
                f"  {column}: min={values['min']}, mean={values['mean']}, max={values['max']}"
            )
    for key in ("overload_rows", "rain_hours", "high_priority_rows"):
        if key in meta:
            print(f"  {key}: {meta[key]:,}")


def feeder_reference_data(rng: np.random.Generator) -> dict[str, np.ndarray]:
    feeder_ids = np.array([f"F-{idx + 1:04d}" for idx in range(N_FEEDERS)])
    zone_ids = np.array([f"zone_{idx % N_ZONES + 1}" for idx in range(N_FEEDERS)])
    capacities = rng.uniform(8.0, 22.0, N_FEEDERS)
    feeder_pressure = np.clip(rng.normal(1.0, 0.075, N_FEEDERS), 0.84, 1.18)
    return {
        "feeder_ids": feeder_ids,
        "zone_ids": zone_ids,
        "capacities": capacities,
        "feeder_pressure": feeder_pressure,
    }


def generate_feeder_load_data(manifest: dict) -> None:
    rng = np.random.default_rng(SEED)
    reference = feeder_reference_data(rng)
    path = RAW_DIR / "feeder_load_data.csv"
    reset_csv(path)

    row_count = 0
    overload_rows = 0
    stats: dict = {}

    month_points = month_starts(START_24M, 24)
    for month_index, month_start in enumerate(tqdm(month_points, desc="feeder_load_data")):
        month_end = month_start + pd.DateOffset(months=1)
        timestamps = pd.date_range(month_start, month_end - pd.Timedelta(minutes=15), freq="15min")
        shard_ids = np.arange(len(timestamps)) % FEEDER_SHARDS
        feeder_idx = (
            shard_ids[:, None] * FEEDERS_PER_INTERVAL + np.arange(FEEDERS_PER_INTERVAL)
        ).reshape(-1)

        repeated_ts = np.repeat(timestamps.to_numpy(), FEEDERS_PER_INTERVAL)
        dt = pd.DatetimeIndex(repeated_ts)
        hour = dt.hour.to_numpy() + dt.minute.to_numpy() / 60.0
        month = dt.month.to_numpy()
        weekday = dt.dayofweek.to_numpy() < 5

        capacity = reference["capacities"][feeder_idx]
        weekday_factor = np.where(weekday, rng.uniform(1.20, 1.30, len(dt)), rng.uniform(0.92, 1.02, len(dt)))
        summer_factor = np.where(np.isin(month, [3, 4, 5, 6]), 1.15, 1.0)
        ev_share = 0.08 + (0.14 - 0.08) * (month_index / 23.0)
        noise = rng.uniform(0.95, 1.05, len(dt))

        utilization = (
            daily_load_shape(hour)
            * weekday_factor
            * summer_factor
            * reference["feeder_pressure"][feeder_idx]
            + ev_share * ev_load_shape(hour)
        )
        load_mw = capacity * utilization * noise
        headroom_mw = capacity - load_mw
        load_ratio = load_mw / capacity
        overload_candidate = load_ratio > 0.95
        overload_probability = np.clip((load_ratio - 0.95) * 7.0 + 0.35, 0.0, 0.98)
        is_overload = overload_candidate & (rng.random(len(dt)) < overload_probability)

        temperature_c = bengaluru_temperature(month, hour, rng)
        voltage_pu = np.clip(1.035 - 0.085 * load_ratio + rng.normal(0.0, 0.006, len(dt)), 0.90, 1.05)

        df = pd.DataFrame(
            {
                "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "feeder_id": reference["feeder_ids"][feeder_idx],
                "zone_id": reference["zone_ids"][feeder_idx],
                "load_mw": load_mw,
                "headroom_mw": headroom_mw,
                "voltage_pu": voltage_pu,
                "temperature_c": temperature_c,
                "is_overload": is_overload.astype(int),
            }
        )
        df = round_frame(
            df,
            {
                "load_mw": 3,
                "headroom_mw": 3,
                "voltage_pu": 4,
                "temperature_c": 2,
            },
        )
        append_csv(df, path)

        row_count += len(df)
        overload_rows += int(is_overload.sum())
        update_numeric_stats(stats, df, ["load_mw", "headroom_mw", "voltage_pu", "temperature_c"])

    manifest["files"]["feeder_load_data.csv"] = {
        "row_count": row_count,
        "date_start": str(START_24M),
        "date_end": str(START_24M + pd.DateOffset(months=24) - pd.Timedelta(minutes=15)),
        "stats": finalize_stats(stats),
        "overload_rows": overload_rows,
        "notes": "Rotating 125-feeder telemetry panel across 500 feeder IDs to meet the requested 10-15M total row scale.",
    }


def station_reference_data(rng: np.random.Generator) -> pd.DataFrame:
    feeder_ids = np.array([f"F-{idx + 1:04d}" for idx in range(N_FEEDERS)])
    station_feeder_idx = rng.choice(np.arange(N_FEEDERS), size=N_STATIONS, replace=False)
    charger_kw = rng.choice([7, 11, 22, 50, 75, 150], size=N_STATIONS, p=[0.18, 0.24, 0.28, 0.16, 0.09, 0.05])
    depot_station = np.zeros(N_STATIONS, dtype=bool)
    depot_station[:30] = True
    rng.shuffle(depot_station)

    return pd.DataFrame(
        {
            "station_id": [f"EVCS-{idx + 1:03d}" for idx in range(N_STATIONS)],
            "feeder_id": feeder_ids[station_feeder_idx],
            "zone_id": [f"zone_{idx % N_ZONES + 1}" for idx in station_feeder_idx],
            "charger_kw": np.where(depot_station, rng.choice([75, 150], N_STATIONS), charger_kw),
            "is_depot_station": depot_station,
        }
    )


def choose_session_start_times(
    month_start: pd.Timestamp,
    month_end: pd.Timestamp,
    session_types: np.ndarray,
    rng: np.random.Generator,
) -> pd.DatetimeIndex:
    n_rows = len(session_types)
    days_in_month = (month_end - month_start).days
    day_offsets = rng.integers(0, days_in_month, n_rows)
    minutes = np.zeros(n_rows, dtype=int)

    private_mask = session_types == "private_ev"
    private_modes = rng.choice(["morning", "evening", "other"], size=private_mask.sum(), p=[0.24, 0.58, 0.18])
    private_minutes = np.empty(private_mask.sum(), dtype=int)
    private_minutes[private_modes == "morning"] = np.clip(
        rng.normal(9 * 60, 48, (private_modes == "morning").sum()), 8 * 60, 10 * 60
    ).astype(int)
    private_minutes[private_modes == "evening"] = np.clip(
        rng.normal(19.5 * 60, 70, (private_modes == "evening").sum()), 18 * 60, 21 * 60
    ).astype(int)
    private_minutes[private_modes == "other"] = rng.integers(10 * 60, 17 * 60, (private_modes == "other").sum())
    minutes[private_mask] = private_minutes

    commercial_mask = session_types == "commercial"
    minutes[commercial_mask] = rng.integers(9 * 60, 18 * 60, commercial_mask.sum())

    bus_mask = session_types == "bmtc_bus"
    bus_hours = rng.choice([22, 23, 0, 1, 2, 3], size=bus_mask.sum(), p=[0.24, 0.28, 0.20, 0.13, 0.09, 0.06])
    minutes[bus_mask] = bus_hours * 60 + rng.integers(0, 60, bus_mask.sum())

    return month_start + pd.to_timedelta(day_offsets, unit="D") + pd.to_timedelta(minutes, unit="m")


def generate_ev_sessions(manifest: dict) -> None:
    rng = np.random.default_rng(SEED + 1)
    path = RAW_DIR / "ev_sessions.csv"
    reset_csv(path)
    stations = station_reference_data(rng)
    depot_station_indices = np.where(stations["is_depot_station"].to_numpy())[0]

    row_count = 0
    stats: dict = {}
    session_counter = 1

    month_points = month_starts(START_18M, 18)
    for month_index, month_start in enumerate(tqdm(month_points, desc="ev_sessions")):
        month_end = month_start + pd.DateOffset(months=1)
        n_sessions = int(round(105_000 * (1.02 ** month_index)))
        session_types = rng.choice(
            ["private_ev", "bmtc_bus", "commercial"],
            size=n_sessions,
            p=[0.85, 0.10, 0.05],
        )

        station_idx = rng.integers(0, N_STATIONS, n_sessions)
        bus_mask = session_types == "bmtc_bus"
        station_idx[bus_mask] = rng.choice(depot_station_indices, size=bus_mask.sum(), replace=True)
        station_rows = stations.iloc[station_idx].reset_index(drop=True)

        start_times = choose_session_start_times(month_start, month_end, session_types, rng)
        energy_kwh = np.empty(n_sessions)
        energy_kwh[session_types == "private_ev"] = rng.uniform(5.0, 45.0, (session_types == "private_ev").sum())
        energy_kwh[bus_mask] = rng.uniform(80.0, 180.0, bus_mask.sum())
        energy_kwh[session_types == "commercial"] = rng.uniform(20.0, 80.0, (session_types == "commercial").sum())

        charger_kw = station_rows["charger_kw"].to_numpy(dtype=float)
        duration_minutes = np.clip(
            (energy_kwh / charger_kw) * 60.0 * rng.normal(1.12, 0.13, n_sessions) + rng.uniform(8.0, 22.0, n_sessions),
            18.0,
            900.0,
        )
        end_times = start_times + pd.to_timedelta(duration_minutes.round().astype(int), unit="m")

        vehicle_type = np.empty(n_sessions, dtype=object)
        private_mask = session_types == "private_ev"
        vehicle_type[private_mask] = rng.choice(["2w", "4w"], size=private_mask.sum(), p=[0.60, 0.40])
        vehicle_type[bus_mask] = "bmtc_bus"
        vehicle_type[session_types == "commercial"] = "commercial"

        soc_start = rng.uniform(15.0, 60.0, n_sessions)
        soc_end = np.maximum(rng.uniform(75.0, 100.0, n_sessions), soc_start + rng.uniform(12.0, 35.0, n_sessions))
        soc_end = np.clip(soc_end, 75.0, 100.0)

        session_ids = [f"SES-{idx:09d}" for idx in range(session_counter, session_counter + n_sessions)]
        user_hashes = [
            hashlib.sha256(f"vidyut-user-{idx % 450000:06d}".encode("utf-8")).hexdigest()
            for idx in range(session_counter, session_counter + n_sessions)
        ]
        session_counter += n_sessions

        df = pd.DataFrame(
            {
                "session_id": session_ids,
                "station_id": station_rows["station_id"].to_numpy(),
                "zone_id": station_rows["zone_id"].to_numpy(),
                "feeder_id": station_rows["feeder_id"].to_numpy(),
                "start_time": start_times.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": end_times.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_minutes": duration_minutes,
                "energy_kwh": energy_kwh,
                "user_token_hash": user_hashes,
                "vehicle_type": vehicle_type,
                "soc_start": soc_start,
                "soc_end": soc_end,
                "session_type": session_types,
            }
        )
        df = round_frame(
            df,
            {
                "duration_minutes": 1,
                "energy_kwh": 2,
                "soc_start": 1,
                "soc_end": 1,
            },
        )
        append_csv(df, path)

        row_count += len(df)
        update_numeric_stats(stats, df, ["duration_minutes", "energy_kwh", "soc_start", "soc_end"])

    manifest["files"]["ev_sessions.csv"] = {
        "row_count": row_count,
        "date_start": str(START_18M),
        "date_end": str(START_18M + pd.DateOffset(months=18) - pd.Timedelta(seconds=1)),
        "stats": finalize_stats(stats),
    }


def generate_weather_data(manifest: dict) -> None:
    rng = np.random.default_rng(SEED + 2)
    path = RAW_DIR / "weather_data.csv"
    reset_csv(path)

    end = START_24M + pd.DateOffset(months=24) - pd.Timedelta(hours=1)
    timestamps = pd.date_range(START_24M, end, freq="h")
    hour = timestamps.hour.to_numpy()
    month = timestamps.month.to_numpy()
    temperature_c = bengaluru_temperature(month, hour.astype(float), rng, noise_scale=0.85)
    humidity_pct = humidity_for_month(month, rng)
    monsoon = np.isin(month, [6, 7, 8, 9, 10, 11])
    rain_probability = np.where(monsoon, 0.34, np.where(np.isin(month, [3, 4, 5]), 0.08, 0.16))
    is_rain = rng.random(len(timestamps)) < rain_probability
    wind_speed_kmh = np.clip(rng.normal(np.where(monsoon, 13.0, 9.0), 3.2), 1.0, 32.0)
    daylight_curve = np.maximum(0.0, np.sin(np.pi * (hour - 6.0) / 12.0))
    cloud_factor = np.where(is_rain, rng.uniform(0.18, 0.45, len(timestamps)), rng.uniform(0.76, 1.04, len(timestamps)))
    monsoon_factor = np.where(monsoon, 0.72, 1.0)
    solar_irradiance_wm2 = np.clip(900.0 * daylight_curve * cloud_factor * monsoon_factor, 0.0, 980.0)
    feels_like_c = temperature_c + 0.045 * (humidity_pct - 55.0) - 0.035 * wind_speed_kmh

    df = pd.DataFrame(
        {
            "timestamp": timestamps.strftime("%Y-%m-%d %H:%M:%S"),
            "temperature_c": temperature_c,
            "humidity_pct": humidity_pct,
            "wind_speed_kmh": wind_speed_kmh,
            "solar_irradiance_wm2": solar_irradiance_wm2,
            "is_rain": is_rain.astype(int),
            "feels_like_c": feels_like_c,
        }
    )
    df = round_frame(
        df,
        {
            "temperature_c": 2,
            "humidity_pct": 1,
            "wind_speed_kmh": 2,
            "solar_irradiance_wm2": 1,
            "feels_like_c": 2,
        },
    )
    append_csv(df, path)

    stats: dict = {}
    update_numeric_stats(
        stats,
        df,
        ["temperature_c", "humidity_pct", "wind_speed_kmh", "solar_irradiance_wm2", "feels_like_c"],
    )
    manifest["files"]["weather_data.csv"] = {
        "row_count": len(df),
        "date_start": str(START_24M),
        "date_end": str(end),
        "stats": finalize_stats(stats),
        "rain_hours": int(is_rain.sum()),
    }


def generate_vahan_registrations(manifest: dict) -> None:
    rng = np.random.default_rng(SEED + 3)
    path = RAW_DIR / "vahan_ev_registrations.csv"
    reset_csv(path)

    ward_ids = np.arange(1, N_WARDS + 1)
    ward_names = np.array([f"BBMP Ward {ward_id:03d}" for ward_id in ward_ids], dtype=object)
    ward_names[83] = "Whitefield"
    ward_names[67] = "Koramangala"
    ward_names[148] = "JP Nagar"
    zone_ids = np.array([f"zone_{(ward_id - 1) % N_ZONES + 1}" for ward_id in ward_ids])
    ward_area = rng.uniform(1.1, 6.8, N_WARDS)

    weights = rng.gamma(shape=2.1, scale=1.0, size=N_WARDS)
    weights[83] *= 5.2
    weights[67] *= 4.8
    weights[148] *= 4.4
    weights = weights / weights.sum()

    cumulative_totals = np.geomspace(85_000, 180_000, 24)
    previous_counts = np.zeros(N_WARDS)
    rows = []

    for month_index, month_start in enumerate(tqdm(month_starts(START_24M, 24), desc="vahan_ev_registrations")):
        cumulative = np.round(cumulative_totals[month_index] * weights).astype(int)
        new_counts = np.maximum(cumulative - previous_counts.astype(int), 0)
        dominant_type = rng.choice(["2W", "4W", "commercial"], size=N_WARDS, p=[0.60, 0.28, 0.12])

        rows.append(
            pd.DataFrame(
                {
                    "month": month_start.strftime("%Y-%m"),
                    "ward_id": ward_ids,
                    "ward_name": ward_names,
                    "zone_id": zone_ids,
                    "ev_count_cumulative": cumulative,
                    "ev_count_new": new_counts,
                    "ev_density_per_km2": cumulative / ward_area,
                    "dominant_vehicle_type": dominant_type,
                }
            )
        )
        previous_counts = cumulative

    df = pd.concat(rows, ignore_index=True)
    df = round_frame(df, {"ev_density_per_km2": 2})
    append_csv(df, path)

    stats: dict = {}
    update_numeric_stats(stats, df, ["ev_count_cumulative", "ev_count_new", "ev_density_per_km2"])
    manifest["files"]["vahan_ev_registrations.csv"] = {
        "row_count": len(df),
        "date_start": START_24M.strftime("%Y-%m"),
        "date_end": (START_24M + pd.DateOffset(months=23)).strftime("%Y-%m"),
        "stats": finalize_stats(stats),
    }


def minutes_to_clock(minutes: np.ndarray) -> list[str]:
    normalized = np.mod(minutes.astype(int), 24 * 60)
    return [f"{minute // 60:02d}:{minute % 60:02d}" for minute in normalized]


def generate_bmtc_depot_schedule(manifest: dict) -> None:
    rng = np.random.default_rng(SEED + 4)
    path = RAW_DIR / "bmtc_depot_schedule.csv"
    reset_csv(path)

    depots = [
        ("DEP-01", "Shivajinagar"),
        ("DEP-02", "Kengeri"),
        ("DEP-03", "Yeshwantpur"),
        ("DEP-04", "Whitefield"),
        ("DEP-05", "Electronic City"),
    ]
    buses_per_depot = [44, 44, 44, 44, 44]
    bus_rows = []
    bus_number = 1
    for (depot_id, depot_name), n_buses in zip(depots, buses_per_depot):
        for _ in range(n_buses):
            bus_rows.append(
                {
                    "depot_id": depot_id,
                    "depot_name": depot_name,
                    "bus_id": f"BMTC-E{bus_number:04d}",
                    "route_id": f"R-{rng.integers(1, 340):03d}",
                }
            )
            bus_number += 1
    buses = pd.DataFrame(bus_rows)

    dates = pd.date_range(START_18M.date(), (START_18M + pd.DateOffset(months=18) - pd.Timedelta(days=1)).date(), freq="D")
    high_priority_rows = 0
    row_count = 0
    stats: dict = {}

    for schedule_date in tqdm(dates, desc="bmtc_depot_schedule"):
        n_rows = len(buses)
        return_minutes = np.clip(rng.normal(23.35 * 60, 58, n_rows), 22 * 60, 25 * 60).astype(int)
        departure_minutes = np.clip(rng.normal(7.0 * 60, 95, n_rows), 4.5 * 60, 10.5 * 60).astype(int)
        battery_pct = np.clip(rng.normal(37.0, 11.0, n_rows) - (return_minutes - 23 * 60) / 70.0, 8.0, 72.0)
        priority = np.where(departure_minutes < 6 * 60, "high", np.where(departure_minutes < 8 * 60, "medium", "low"))

        df = buses.copy()
        df.insert(0, "date", schedule_date.strftime("%Y-%m-%d"))
        df["departure_time_next_day"] = minutes_to_clock(departure_minutes)
        df["return_time"] = minutes_to_clock(return_minutes)
        df["ev_battery_pct_on_return"] = np.round(battery_pct, 1)
        df["charging_priority"] = priority
        append_csv(df, path)

        high_priority_rows += int((priority == "high").sum())
        row_count += len(df)
        update_numeric_stats(stats, df, ["ev_battery_pct_on_return"])

    manifest["files"]["bmtc_depot_schedule.csv"] = {
        "row_count": row_count,
        "date_start": str(dates.min().date()),
        "date_end": str(dates.max().date()),
        "stats": finalize_stats(stats),
        "high_priority_rows": high_priority_rows,
    }


def write_manifest(manifest: dict) -> None:
    manifest["total_rows"] = int(sum(item["row_count"] for item in manifest["files"].values()))
    manifest["generated_at"] = pd.Timestamp.utcnow().isoformat()
    path = RAW_DIR / "data_manifest.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)


def main() -> None:
    np.random.seed(SEED)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "project": "VIDYUT AI",
        "seed": SEED,
        "output_dir": str(RAW_DIR),
        "files": {},
    }

    generate_feeder_load_data(manifest)
    generate_ev_sessions(manifest)
    generate_weather_data(manifest)
    generate_vahan_registrations(manifest)
    generate_bmtc_depot_schedule(manifest)
    write_manifest(manifest)

    print("\nSynthetic data generation complete.")
    print(f"Output directory: {RAW_DIR}")
    print(f"Total rows: {manifest['total_rows']:,}")
    for filename, metadata in manifest["files"].items():
        print_file_summary(filename, metadata)
    print(f"\nManifest: {RAW_DIR / 'data_manifest.json'}")


if __name__ == "__main__":
    main()
