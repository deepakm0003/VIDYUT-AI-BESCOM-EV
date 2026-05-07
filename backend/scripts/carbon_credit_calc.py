from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from loguru import logger


BACKEND_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BACKEND_DIR / "data" / "raw"
PROCESSED_DIR = BACKEND_DIR / "data" / "processed"
DEFAULT_SESSIONS = RAW_DIR / "ev_sessions.csv"
DEFAULT_HISTORY_OUT = PROCESSED_DIR / "carbon_credits_history.parquet"


class CarbonCreditEngine:
    PEAK_EMISSION_FACTOR = 0.71
    OFFPEAK_EMISSION_FACTOR = 0.49
    CO2_DELTA_PER_KWH = 0.22
    CARBON_PRICE_INR_PER_TONNE = 650
    OVERLOAD_AVOIDANCE_COST_INR = 200000

    def __init__(
        self,
        ev_sessions_path: str | Path = DEFAULT_SESSIONS,
        schedule_results_path: str | Path | None = None,
        output_dir: str | Path = PROCESSED_DIR,
    ) -> None:
        self.ev_sessions_path = Path(ev_sessions_path)
        self.schedule_results_path = Path(schedule_results_path) if schedule_results_path else None
        self.output_dir = Path(output_dir)

    def compute_monthly_credits(
        self,
        ev_sessions_df: pd.DataFrame,
        schedule_results_df: pd.DataFrame | None,
        month: str,
    ) -> dict:
        sessions = ev_sessions_df.copy()
        sessions["start_time"] = pd.to_datetime(sessions["start_time"])
        sessions["month"] = sessions["start_time"].dt.strftime("%Y-%m")
        month_sessions = sessions[sessions["month"] == month].copy()

        if month_sessions.empty:
            return self._empty_month(month)

        schedule = self._month_schedule(schedule_results_df, month)
        shifted = self._identify_shifted_sessions(month_sessions, schedule)
        shifted_sessions = month_sessions[shifted].copy()

        kwh_shifted = float(shifted_sessions["energy_kwh"].sum())
        co2_avoided_tonnes = float(kwh_shifted * self.CO2_DELTA_PER_KWH / 1000.0)
        carbon_credits_inr = float(co2_avoided_tonnes * self.CARBON_PRICE_INR_PER_TONNE)
        overload_events_averted = self._count_overload_events_averted(schedule, month_sessions)
        capex_avoidance_inr = float(overload_events_averted * self.OVERLOAD_AVOIDANCE_COST_INR)

        zone_breakdown = {}
        for zone_id, group in shifted_sessions.groupby("zone_id"):
            zone_kwh = float(group["energy_kwh"].sum())
            zone_co2 = float(zone_kwh * self.CO2_DELTA_PER_KWH / 1000.0)
            zone_breakdown[str(zone_id)] = {
                "kwh": round(zone_kwh, 3),
                "co2": round(zone_co2, 6),
                "inr": round(zone_co2 * self.CARBON_PRICE_INR_PER_TONNE, 2),
            }

        total_value_inr = carbon_credits_inr + capex_avoidance_inr
        result = {
            "month": month,
            "kwh_shifted": round(kwh_shifted, 3),
            "co2_avoided_tonnes": round(co2_avoided_tonnes, 6),
            "carbon_credits_inr": round(carbon_credits_inr, 2),
            "overload_events_averted": int(overload_events_averted),
            "capex_avoidance_inr": round(capex_avoidance_inr, 2),
            "total_value_inr": round(total_value_inr, 2),
            "bee_certificate_eligible": bool(kwh_shifted > 100_000),
            "zone_breakdown": zone_breakdown,
            "annualized_projection_inr": round(total_value_inr * 12.0, 2),
        }
        return result

    def generate_bee_certificate(self, month_data: dict) -> dict:
        canonical = json.dumps(month_data, sort_keys=True, default=str)
        verification_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return {
            "certificate_id": f"VIDYUT-BEE-{month_data['month']}-{uuid4().hex[:8].upper()}",
            "issued_date": pd.Timestamp.today().date().isoformat(),
            "valid_under": "Energy Conservation (Amendment) Act 2022",
            "utility": "BESCOM, Bengaluru",
            "period": month_data["month"],
            "mwh_shifted": round(month_data["kwh_shifted"] / 1000.0, 3),
            "co2_avoided_tonnes": month_data["co2_avoided_tonnes"],
            "carbon_credits_value_inr": month_data["carbon_credits_inr"],
            "verification_hash": verification_hash,
        }

    def compute_all_months(self, start_date: str, end_date: str) -> list[dict]:
        sessions = self._load_sessions()
        schedule = self._load_schedule_results()
        months = pd.period_range(start=start_date, end=end_date, freq="M").astype(str).tolist()
        results = [self.compute_monthly_credits(sessions, schedule, month) for month in months]

        history_df = pd.DataFrame(
            [
                {key: value for key, value in result.items() if key != "zone_breakdown"}
                for result in results
            ]
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        history_df.to_parquet(DEFAULT_HISTORY_OUT, index=False)
        (self.output_dir / "carbon_credits_history.json").write_text(
            json.dumps(results, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Saved carbon credit history to {}", DEFAULT_HISTORY_OUT)
        return results

    def _load_sessions(self) -> pd.DataFrame:
        if not self.ev_sessions_path.exists():
            raise FileNotFoundError(f"Missing EV sessions: {self.ev_sessions_path}")
        return pd.read_csv(
            self.ev_sessions_path,
            usecols=[
                "session_id",
                "station_id",
                "zone_id",
                "feeder_id",
                "start_time",
                "end_time",
                "energy_kwh",
                "session_type",
            ],
        )

    def _load_schedule_results(self) -> pd.DataFrame | None:
        if self.schedule_results_path and self.schedule_results_path.exists():
            if self.schedule_results_path.suffix == ".parquet":
                return pd.read_parquet(self.schedule_results_path)
            return pd.read_csv(self.schedule_results_path)
        return None

    def _month_schedule(self, schedule_results_df: pd.DataFrame | None, month: str) -> pd.DataFrame | None:
        if schedule_results_df is None or schedule_results_df.empty:
            return None
        schedule = schedule_results_df.copy()
        if "month" in schedule:
            return schedule[schedule["month"].astype(str) == month]
        for column in ("assigned_start_time", "schedule_time", "start_time"):
            if column in schedule:
                schedule[column] = pd.to_datetime(schedule[column])
                return schedule[schedule[column].dt.strftime("%Y-%m") == month]
        return schedule

    def _identify_shifted_sessions(self, sessions: pd.DataFrame, schedule: pd.DataFrame | None) -> pd.Series:
        if schedule is not None and not schedule.empty and "session_id" in schedule:
            joined = sessions[["session_id"]].merge(schedule, on="session_id", how="left")
            if {"assigned_window", "preferred_window"}.issubset(joined.columns):
                return joined["assigned_window"].fillna("") != joined["preferred_window"].fillna("")
            if {"assigned_start_time", "preferred_window_start"}.issubset(joined.columns):
                assigned = pd.to_datetime(joined["assigned_start_time"], errors="coerce")
                preferred = pd.to_datetime(joined["preferred_window_start"], errors="coerce")
                return ((assigned - preferred).abs().dt.total_seconds() / 60.0).fillna(0) > 15

        start_hour = sessions["start_time"].dt.hour
        session_type = sessions["session_type"].astype(str)
        private_peak_shifted = session_type.eq("private_ev") & start_hour.between(18, 21)
        commercial_shifted = session_type.eq("commercial") & start_hour.between(17, 20)
        bmtc_optimized = session_type.eq("bmtc_bus") & (start_hour >= 22)
        return private_peak_shifted | commercial_shifted | bmtc_optimized

    def _count_overload_events_averted(self, schedule: pd.DataFrame | None, sessions: pd.DataFrame) -> int:
        if schedule is not None and not schedule.empty:
            required = {"scheduled_load_pct", "baseline_load_pct"}
            if required.issubset(schedule.columns):
                return int(((schedule["scheduled_load_pct"] < 0.90) & (schedule["baseline_load_pct"] > 0.95)).sum())
            if "overload_events_averted" in schedule:
                return int(schedule["overload_events_averted"].fillna(0).sum())

        peak_sessions = sessions[pd.to_datetime(sessions["start_time"]).dt.hour.between(18, 21)]
        shifted_kwh_proxy = peak_sessions["energy_kwh"].sum()
        return int(max(0, np.floor(shifted_kwh_proxy / 6_500.0)))

    def _empty_month(self, month: str) -> dict:
        return {
            "month": month,
            "kwh_shifted": 0.0,
            "co2_avoided_tonnes": 0.0,
            "carbon_credits_inr": 0.0,
            "overload_events_averted": 0,
            "capex_avoidance_inr": 0.0,
            "total_value_inr": 0.0,
            "bee_certificate_eligible": False,
            "zone_breakdown": {},
            "annualized_projection_inr": 0.0,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute VIDYUT AI carbon credits and BEE certificate data.")
    parser.add_argument("--start", default="2024-01", help="Start month YYYY-MM")
    parser.add_argument("--end", default="2025-06", help="End month YYYY-MM")
    parser.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS)
    parser.add_argument("--schedule-results", type=Path, default=None)
    parser.add_argument("--certificate-month", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    engine = CarbonCreditEngine(args.sessions, args.schedule_results)
    results = engine.compute_all_months(args.start, args.end)
    print("\nCarbon credit summary")
    print(pd.DataFrame([{k: v for k, v in row.items() if k != "zone_breakdown"} for row in results]).to_string(index=False))

    if args.certificate_month:
        month_data = next((item for item in results if item["month"] == args.certificate_month), None)
        if month_data is None:
            raise ValueError(f"Month {args.certificate_month} not in computed range.")
        certificate = engine.generate_bee_certificate(month_data)
        cert_path = PROCESSED_DIR / f"bee_certificate_{args.certificate_month}.json"
        cert_path.write_text(json.dumps(certificate, indent=2), encoding="utf-8")
        print(f"\nBEE certificate data saved to {cert_path}")


if __name__ == "__main__":
    main()
