from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.preprocessing import MinMaxScaler


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = BACKEND_DIR / "data" / "processed"
DEFAULT_FEATURES_PATH = PROCESSED_DIR / "site_scoring_features.parquet"
DEFAULT_RANKINGS_PATH = PROCESSED_DIR / "site_rankings.parquet"


def minmax_score(values: pd.Series, default: float = 50.0) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").astype(float)
    if numeric.notna().sum() == 0 or numeric.max() == numeric.min():
        return pd.Series(default, index=values.index, dtype=float)
    filled = numeric.fillna(numeric.median())
    scaled = MinMaxScaler((0, 100)).fit_transform(filled.to_numpy().reshape(-1, 1)).ravel()
    return pd.Series(scaled, index=values.index, dtype=float)


def clamp_score(values: pd.Series | np.ndarray) -> pd.Series:
    return pd.Series(values).clip(0, 100).astype(float)


class VIDYUTSiteScorer:
    WEIGHTS = {
        "ev_demand_density": 0.25,
        "grid_capacity_headroom": 0.22,
        "traffic_dwell_time": 0.18,
        "coverage_gap": 0.15,
        "land_feasibility": 0.10,
        "socioeconomic_equity": 0.05,
        "renewable_colocation": 0.05,
    }

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.rankings_: pd.DataFrame | None = None

    def score_all_wards(self, site_features_df: pd.DataFrame) -> pd.DataFrame:
        df = site_features_df.copy().reset_index(drop=True)
        logger.info("Scoring {} candidate wards", len(df))

        ward_type = self._assign_ward_type(df)
        poi_bonus = self._poi_bonus(df, ward_type)
        land_class, setback_compliant, rooftop_solar_nearby = self._simulated_metadata(df, ward_type)

        ev_base = (
            minmax_score(df["ev_density_per_km2"])
            if "ev_density_per_km2" in df
            else df.get("ev_density_score", pd.Series(50.0, index=df.index)).astype(float)
        )
        yoy_growth_rate = self._estimate_yoy_growth(df, ev_base)
        forecast_sessions_per_day = self._forecast_sessions_per_day(df, ev_base, yoy_growth_rate)
        forecast_boost = minmax_score(pd.Series(forecast_sessions_per_day, index=df.index)) * 0.20
        growth_bonus = clamp_score(yoy_growth_rate * 100.0).clip(0, 20)
        df["ev_demand_density_score"] = clamp_score(ev_base * 0.80 + forecast_boost + growth_bonus)

        headroom = pd.to_numeric(df.get("available_headroom_kva", 0.0), errors="coerce").fillna(0.0)
        grid_score = minmax_score(headroom)
        substation_distance = pd.to_numeric(df.get("nearest_substation_km", 3.0), errors="coerce").fillna(3.0)
        grid_score = grid_score - np.where(substation_distance > 2.0, np.minimum((substation_distance - 2.0) * 12.0, 35.0), 0.0)
        grid_score = np.where(headroom < 50.0, 0.0, grid_score)
        df["grid_capacity_headroom_score"] = clamp_score(grid_score)

        traffic = minmax_score(df.get("avg_daily_traffic", pd.Series(0.0, index=df.index)))
        dwell = minmax_score(df.get("dwell_time_pct", pd.Series(0.0, index=df.index)))
        dwell_critical_bonus = np.where(pd.to_numeric(df.get("dwell_time_pct", 0), errors="coerce").fillna(0) > 20, 8.0, 0.0)
        df["traffic_dwell_time_score"] = clamp_score(traffic * 0.35 + dwell * 0.55 + poi_bonus + dwell_critical_bonus)

        nearest_evcs = pd.to_numeric(df.get("nearest_evcs_km", 0.0), errors="coerce").fillna(0.0)
        high_density_threshold = ev_base.quantile(0.75)
        directional_gap_bonus = np.where((ev_base >= high_density_threshold) & (nearest_evcs >= 2.0), 15.0, 0.0)
        df["coverage_gap_score"] = clamp_score(np.minimum(100.0, nearest_evcs * 20.0) + directional_gap_bonus)

        land_base = pd.Series(land_class, index=df.index).map(
            {"govt_owned": 100.0, "private_negotiable": 70.0, "private_contested": 30.0}
        )
        setback_adjustment = np.where(setback_compliant, 20.0, -40.0)
        df["land_feasibility_score"] = clamp_score(land_base + setback_adjustment)

        income_decile = pd.to_numeric(df.get("income_decile", 6), errors="coerce").fillna(6)
        df["socioeconomic_equity_score"] = clamp_score(np.maximum(0.0, (6.0 - income_decile) * 20.0))

        renewable_base = minmax_score(df.get("solar_irradiance_annual", pd.Series(0.0, index=df.index)))
        df["renewable_colocation_score"] = clamp_score(renewable_base + np.where(rooftop_solar_nearby, 15.0, 0.0))

        factor_columns = {
            "ev_demand_density": "ev_demand_density_score",
            "grid_capacity_headroom": "grid_capacity_headroom_score",
            "traffic_dwell_time": "traffic_dwell_time_score",
            "coverage_gap": "coverage_gap_score",
            "land_feasibility": "land_feasibility_score",
            "socioeconomic_equity": "socioeconomic_equity_score",
            "renewable_colocation": "renewable_colocation_score",
        }
        contributions = pd.DataFrame(
            {
                factor: df[column] * weight
                for factor, column in factor_columns.items()
                for weight in [self.WEIGHTS[factor]]
            }
        )
        df["composite_score"] = contributions.sum(axis=1).round(3)
        df["top_driver"] = contributions.idxmax(axis=1)
        df["grid_upgrade_needed"] = (headroom < 250.0) | (substation_distance > 2.0)
        df["estimated_upgrade_cost_inr"] = np.where(
            df["grid_upgrade_needed"],
            650_000 + np.maximum(0.0, substation_distance - 1.0) * 425_000 + np.maximum(0.0, 500.0 - headroom) * 750.0,
            0.0,
        ).round(0)
        df["estimated_y1_utilization_pct"] = clamp_score(
            20.0
            + df["ev_demand_density_score"] * 0.38
            + df["traffic_dwell_time_score"] * 0.22
            + df["coverage_gap_score"] * 0.12
        ).round(2)
        df["recommended_charger_type"] = np.select(
            [
                df["estimated_y1_utilization_pct"] >= 70,
                (df["traffic_dwell_time_score"] >= 65) & (headroom >= 500),
                df["grid_upgrade_needed"],
            ],
            ["150kW DC fast hub", "60kW mixed fast + AC", "22kW AC phased rollout"],
            default="30kW neighborhood charger",
        )

        output_columns = [
            "ward_id",
            "ward_name",
            "zone_id",
            "latitude",
            "longitude",
            "composite_score",
            "rank",
            "ev_demand_density_score",
            "grid_capacity_headroom_score",
            "traffic_dwell_time_score",
            "coverage_gap_score",
            "land_feasibility_score",
            "socioeconomic_equity_score",
            "renewable_colocation_score",
            "top_driver",
            "grid_upgrade_needed",
            "estimated_upgrade_cost_inr",
            "estimated_y1_utilization_pct",
            "recommended_charger_type",
        ]
        df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
        df["rank"] = np.arange(1, len(df) + 1)
        self.rankings_ = df[output_columns]
        return self.rankings_

    def save_rankings(self, output_path: str | Path = DEFAULT_RANKINGS_PATH) -> tuple[Path, Path]:
        if self.rankings_ is None:
            if not DEFAULT_FEATURES_PATH.exists():
                raise FileNotFoundError(f"Missing {DEFAULT_FEATURES_PATH}; run feature_engineering.py first.")
            self.score_all_wards(pd.read_parquet(DEFAULT_FEATURES_PATH))

        parquet_path = Path(output_path)
        json_path = parquet_path.with_suffix(".json")
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        self.rankings_.to_parquet(parquet_path, index=False)
        json_path.write_text(
            json.dumps(self.rankings_.to_dict(orient="records"), indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Saved site rankings to {} and {}", parquet_path, json_path)
        return parquet_path, json_path

    def _assign_ward_type(self, df: pd.DataFrame) -> np.ndarray:
        traffic = pd.to_numeric(df.get("avg_daily_traffic", 0), errors="coerce").fillna(0)
        dwell = pd.to_numeric(df.get("dwell_time_pct", 0), errors="coerce").fillna(0)
        types = np.full(len(df), "residential", dtype=object)
        types[traffic > traffic.quantile(0.75)] = "commercial"
        types[dwell > dwell.quantile(0.75)] = "mixed_use"
        return types

    def _poi_bonus(self, df: pd.DataFrame, ward_type: np.ndarray) -> np.ndarray:
        probability = np.where(ward_type == "commercial", 0.65, np.where(ward_type == "mixed_use", 0.55, 0.25))
        has_poi = self.rng.random(len(df)) < probability
        return np.where(has_poi, 10.0, 0.0)

    def _simulated_metadata(self, df: pd.DataFrame, ward_type: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        land_class = []
        for ward in ward_type:
            if ward == "commercial":
                probs = [0.18, 0.62, 0.20]
            elif ward == "mixed_use":
                probs = [0.28, 0.57, 0.15]
            else:
                probs = [0.38, 0.50, 0.12]
            land_class.append(self.rng.choice(["govt_owned", "private_negotiable", "private_contested"], p=probs))
        setback_compliant = self.rng.random(len(df)) < np.where(ward_type == "commercial", 0.68, 0.78)
        solar = pd.to_numeric(df.get("solar_irradiance_annual", 0), errors="coerce").fillna(0)
        solar_prob = 0.18 + minmax_score(solar).to_numpy() / 170.0
        rooftop_solar_nearby = self.rng.random(len(df)) < np.clip(solar_prob, 0.12, 0.75)
        return np.array(land_class), setback_compliant, rooftop_solar_nearby

    def _estimate_yoy_growth(self, df: pd.DataFrame, ev_base: pd.Series) -> pd.Series:
        zone_codes = df["zone_id"].astype(str).str.extract(r"(\d+)").fillna(1).astype(int)[0]
        ward_factor = (pd.to_numeric(df["ward_id"], errors="coerce").fillna(0) % 17) / 100.0
        growth = 0.12 + ev_base / 500.0 + zone_codes / 100.0 + ward_factor
        return growth.clip(0.08, 0.45)

    def _forecast_sessions_per_day(self, df: pd.DataFrame, ev_base: pd.Series, yoy_growth_rate: pd.Series) -> pd.Series:
        traffic = pd.to_numeric(df.get("avg_daily_traffic", 0), errors="coerce").fillna(0)
        dwell = pd.to_numeric(df.get("dwell_time_pct", 0), errors="coerce").fillna(0)
        baseline = 12.0 + ev_base * 0.9 + minmax_score(traffic) * 0.35 + minmax_score(dwell) * 0.25
        return baseline * (1.0 + yoy_growth_rate / 2.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate 7-factor VIDYUT ward site rankings.")
    parser.add_argument("--input", type=Path, default=DEFAULT_FEATURES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_RANKINGS_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger.info("Loading site features from {}", args.input)
    features = pd.read_parquet(args.input)
    scorer = VIDYUTSiteScorer()
    rankings = scorer.score_all_wards(features)
    scorer.save_rankings(args.output)
    print("\nTop 10 VIDYUT candidate sites")
    print(rankings.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
