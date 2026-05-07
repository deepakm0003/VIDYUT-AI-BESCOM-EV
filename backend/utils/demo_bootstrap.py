from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


ZONES = ["whitefield", "koramangala", "yelahanka", "bommanahalli", "hebbal", "indiranagar"]


@dataclass(frozen=True)
class DemoPaths:
    processed_dir: Path
    forecast_parquet: Path
    site_rankings_json: Path
    carbon_history_json: Path


def demo_paths(backend_dir: Path) -> DemoPaths:
    processed_dir = backend_dir / "data" / "processed"
    return DemoPaths(
        processed_dir=processed_dir,
        forecast_parquet=processed_dir / "forecast_features.parquet",
        site_rankings_json=processed_dir / "site_rankings.json",
        carbon_history_json=processed_dir / "carbon_credits_history.json",
    )


def ensure_demo_artifacts(backend_dir: Path) -> dict[str, str]:
    """
    Creates small demo artifacts if they don't exist.
    This keeps GitHub clean (no big data committed) and makes Render deployments work.
    """
    paths = demo_paths(backend_dir)
    paths.processed_dir.mkdir(parents=True, exist_ok=True)

    created: dict[str, str] = {}

    if not paths.forecast_parquet.exists():
        _write_demo_forecast_parquet(paths.forecast_parquet)
        created["forecast_features.parquet"] = str(paths.forecast_parquet)

    if not paths.site_rankings_json.exists():
        _write_demo_site_rankings(paths.site_rankings_json)
        created["site_rankings.json"] = str(paths.site_rankings_json)

    if not paths.carbon_history_json.exists():
        _write_demo_carbon_history(paths.carbon_history_json)
        created["carbon_credits_history.json"] = str(paths.carbon_history_json)

    return created


def _write_demo_forecast_parquet(path: Path) -> None:
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    now = pd.Timestamp.utcnow().floor("15min")
    start = now - pd.Timedelta(days=7)
    idx = pd.date_range(start=start, end=now, freq="15min", inclusive="left")

    rows = []
    for i, zone in enumerate(ZONES, start=1):
        base = 9.5 + i * 0.75
        for ts in idx:
            hour = ts.hour + ts.minute / 60.0
            daily = 1.2 * np.sin((hour / 24.0) * 2 * np.pi - 1.0) + 1.0
            load = base * (0.75 + 0.25 * daily) * (1.05 if ts.dayofweek < 5 else 0.90)
            load = float(load * (1.0 + rng.normal(0, 0.03)))
            rows.append(
                {
                    "timestamp": ts,
                    "zone_id": f"zone_{i}",
                    "load_mw": max(0.0, round(load, 4)),
                    "temperature_c": float(24.0 + 6.0 * np.sin((ts.dayofyear / 365.0) * 2 * np.pi) + rng.normal(0, 0.8)),
                    "active_sessions_count": int(max(0, 18 + i * 4 + rng.normal(0, 6))),
                    "bmtc_buses_charging": int(max(0, (1 if 22 <= ts.hour or ts.hour <= 3 else 0) * (i % 2))),
                    "solar_irradiance_wm2": float(max(0.0, 850 * np.sin(((hour - 6) / 12) * np.pi))),
                    "load_mw_next_4h": 0.0,
                }
            )

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["zone_id", "timestamp"]).reset_index(drop=True)
    df["load_mw_next_4h"] = df.groupby("zone_id")["load_mw"].shift(-16).bfill()
    df.to_parquet(path, index=False, engine="pyarrow", compression="snappy")


def _write_demo_site_rankings(path: Path) -> None:
    rankings = {
        "metadata": {"total_sites": 10, "zones": ZONES},
        "sites": [
            {
                "rank": 1,
                "ward_id": "WF-047",
                "location_name": "Whitefield Metro Parking",
                "zone_id": "whitefield",
                "latitude": 12.9698,
                "longitude": 77.7497,
                "vidyut_score": 87,
                "top_driver": "EV demand density",
            },
            {
                "rank": 2,
                "ward_id": "KR-023",
                "location_name": "Koramangala 5th Block",
                "zone_id": "koramangala",
                "latitude": 12.9352,
                "longitude": 77.6245,
                "vidyut_score": 83,
                "top_driver": "Coverage gap + traffic",
            },
        ],
    }
    path.write_text(json.dumps(rankings, indent=2), encoding="utf-8")


def _write_demo_carbon_history(path: Path) -> None:
    history = {
        "summary": {
            "total_mwh_shifted": 4421.1,
            "total_co2_avoided_tonnes": 971.2,
            "total_carbon_revenue_crore": 6.11,
            "total_capex_savings_crore": 1.55,
        },
        "monthly_data": [
            {"month": "2026-01", "mwh_shifted": 425.3, "co2_avoided_tonnes": 93.56, "carbon_credits_revenue_crore": 0.608, "capex_savings_crore": 0.24},
            {"month": "2026-02", "mwh_shifted": 512.1, "co2_avoided_tonnes": 112.66, "carbon_credits_revenue_crore": 0.732, "capex_savings_crore": 0.29},
            {"month": "2026-03", "mwh_shifted": 598.4, "co2_avoided_tonnes": 131.68, "carbon_credits_revenue_crore": 0.856, "capex_savings_crore": 0.34},
            {"month": "2026-04", "mwh_shifted": 725.8, "co2_avoided_tonnes": 159.67, "carbon_credits_revenue_crore": 1.037, "capex_savings_crore": 0.42},
            {"month": "2026-05", "mwh_shifted": 1847.0, "co2_avoided_tonnes": 406.0, "carbon_credits_revenue_crore": 2.43, "capex_savings_crore": 1.08},
        ],
    }
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")

