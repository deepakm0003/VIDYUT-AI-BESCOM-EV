from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:
    class _FallbackEnv:
        metadata: dict = {}

        def reset(self, *, seed=None):
            return None

    class _FallbackBox:
        def __init__(self, low, high, shape, dtype):
            self.low = low
            self.high = high
            self.shape = shape
            self.dtype = dtype

    class _FallbackSpaces:
        Box = _FallbackBox

    class _FallbackGym:
        Env = _FallbackEnv

    gym = _FallbackGym()
    spaces = _FallbackSpaces()


EPISODE_STEPS = 96
STEP_HOURS = 0.25
STATION_TYPES = ("slow", "fast", "bmtc")


@dataclass
class FeederDayProfile:
    timestamp: pd.DatetimeIndex
    base_load_mw: np.ndarray
    forecast_4h_mw: np.ndarray
    temperature_c: np.ndarray
    renewable_pct: np.ndarray
    active_sessions: np.ndarray
    bmtc_returns: np.ndarray


class BESCOMFeederEnv(gym.Env):
    """Gymnasium environment for strategic EV charging control in one BESCOM feeder zone."""

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        zone_id: str = "zone_1",
        feeder_capacity_mw: float = 18.0,
        profiles: list[FeederDayProfile] | None = None,
        seed: int | None = None,
        render_mode: str | None = None,
    ) -> None:
        super().__init__()
        self.zone_id = zone_id
        self.feeder_capacity_mw = feeder_capacity_mw
        self.profiles = profiles or []
        self.render_mode = render_mode
        self.rng = np.random.default_rng(seed)
        self.observation_space = spaces.Box(low=0.0, high=1.5, shape=(14,), dtype=np.float32)
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)

        self.current_step = 0
        self.current_profile = self._synthetic_profile()
        self.current_load_mw = 0.0
        self.avg_soc_active_sessions = 0.55
        self.soc_violations = 0
        self.overload_events = 0
        self.off_peak_sessions = 0
        self.total_sessions = 1
        self.disrupted_sessions = 0
        self.last_info: dict[str, Any] = {}

    @classmethod
    def from_processed_features(
        cls,
        processed_path: Path,
        zone_id: str = "zone_1",
        max_days: int = 180,
        seed: int | None = 42,
    ) -> "BESCOMFeederEnv":
        profiles: list[FeederDayProfile] = []
        if processed_path.exists():
            columns = [
                "timestamp",
                "zone_id",
                "load_mw",
                "temperature_c",
                "active_sessions_count",
                "bmtc_buses_charging",
                "solar_irradiance_wm2",
                "load_mw_next_4h",
            ]
            df = pd.read_parquet(processed_path, columns=columns)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            zone_df = df[df["zone_id"].astype(str) == zone_id].copy()
            if not zone_df.empty:
                zone_df["date"] = zone_df["timestamp"].dt.date
                daily = (
                    zone_df.groupby(["date", "timestamp"], as_index=False)
                    .agg(
                        load_mw=("load_mw", "mean"),
                        temperature_c=("temperature_c", "mean"),
                        active_sessions_count=("active_sessions_count", "mean"),
                        bmtc_buses_charging=("bmtc_buses_charging", "mean"),
                        solar_irradiance_wm2=("solar_irradiance_wm2", "mean"),
                        load_mw_next_4h=("load_mw_next_4h", "mean"),
                    )
                    .sort_values("timestamp")
                )
                for _, day in daily.groupby("date", sort=False):
                    if len(day) < EPISODE_STEPS:
                        continue
                    sample = day.iloc[:EPISODE_STEPS]
                    load = sample["load_mw"].to_numpy(dtype=float)
                    forecast = np.vstack(
                        [
                            np.roll(sample["load_mw_next_4h"].to_numpy(dtype=float), -offset)
                            for offset in range(4)
                        ]
                    ).T
                    renewable = np.clip(sample["solar_irradiance_wm2"].to_numpy(dtype=float) / 900.0, 0.0, 1.0)
                    profiles.append(
                        FeederDayProfile(
                            timestamp=pd.DatetimeIndex(sample["timestamp"]),
                            base_load_mw=load,
                            forecast_4h_mw=forecast,
                            temperature_c=sample["temperature_c"].to_numpy(dtype=float),
                            renewable_pct=renewable,
                            active_sessions=sample["active_sessions_count"].to_numpy(dtype=float),
                            bmtc_returns=sample["bmtc_buses_charging"].to_numpy(dtype=float),
                        )
                    )
                    if len(profiles) >= max_days:
                        break
        return cls(zone_id=zone_id, profiles=profiles, seed=seed)

    def _synthetic_profile(self) -> FeederDayProfile:
        steps = np.arange(EPISODE_STEPS)
        hour = steps / 4.0
        base = (
            7.5
            + 1.4 * np.exp(-0.5 * ((hour - 8.0) / 1.8) ** 2)
            + 4.1 * np.exp(-0.5 * ((hour - 19.5) / 2.0) ** 2)
            - 1.2 * np.exp(-0.5 * ((hour - 3.0) / 1.6) ** 2)
        )
        density_scale = self.rng.choice([0.85, 1.0, 1.18], p=[0.25, 0.5, 0.25])
        base = base * density_scale + self.rng.normal(0.0, 0.18, EPISODE_STEPS)
        temperature = 26.0 + 4.0 * np.sin((hour - 7.0) / 24.0 * 2.0 * np.pi) + self.rng.normal(0, 0.5, EPISODE_STEPS)
        renewable = np.clip(np.maximum(0.0, np.sin(np.pi * (hour - 6.0) / 12.0)), 0.0, 1.0)
        sessions = self.rng.poisson(4 + 8 * np.exp(-0.5 * ((hour - 19.5) / 2.5) ** 2), EPISODE_STEPS)
        bmtc = self.rng.poisson(2.5 * np.exp(-0.5 * ((hour - 23.0) / 1.8) ** 2), EPISODE_STEPS)
        forecast = np.vstack([np.roll(base, -offset * 4) for offset in range(1, 5)]).T
        return FeederDayProfile(
            timestamp=pd.date_range("2025-01-01", periods=EPISODE_STEPS, freq="15min"),
            base_load_mw=base,
            forecast_4h_mw=forecast,
            temperature_c=temperature,
            renewable_pct=renewable,
            active_sessions=sessions.astype(float),
            bmtc_returns=bmtc.astype(float),
        )

    def _observation(self) -> np.ndarray:
        step = min(self.current_step, EPISODE_STEPS - 1)
        hour = step / 4.0
        load_pct = self.current_load_mw / self.feeder_capacity_mw
        headroom = max(self.feeder_capacity_mw - self.current_load_mw, 0.0)
        forecast = self.current_profile.forecast_4h_mw[step] / self.feeder_capacity_mw
        obs = np.array(
            [
                hour / 24.0,
                np.clip(load_pct, 0.0, 1.5),
                np.clip(headroom / self.feeder_capacity_mw, 0.0, 1.5),
                np.clip(self.current_profile.active_sessions[step] / 50.0, 0.0, 1.5),
                np.clip(self.avg_soc_active_sessions, 0.0, 1.0),
                *np.clip(forecast, 0.0, 1.5).tolist(),
                np.clip(float(np.max(forecast)), 0.0, 1.5),
                np.clip(self.current_profile.bmtc_returns[step] / 20.0, 0.0, 1.5),
                np.clip(self.current_profile.renewable_pct[step], 0.0, 1.0),
                np.clip((self.current_profile.temperature_c[step] - 18.0) / 20.0, 0.0, 1.0),
                1.0 if 18 <= hour < 21 else 0.0,
            ],
            dtype=np.float32,
        )
        return obs

    def reset(self, *, seed: int | None = None, options: dict | None = None) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.current_step = 0
        self.current_profile = self.rng.choice(self.profiles) if self.profiles else self._synthetic_profile()
        density_multiplier = self.rng.choice([0.92, 1.0, 1.08], p=[0.25, 0.5, 0.25])
        self.current_profile.base_load_mw = self.current_profile.base_load_mw * density_multiplier
        self.feeder_capacity_mw = float(np.clip(np.nanmax(self.current_profile.base_load_mw) / 0.82, 10.0, 24.0))
        self.current_load_mw = float(self.current_profile.base_load_mw[0])
        self.avg_soc_active_sessions = float(self.rng.uniform(0.35, 0.7))
        self.soc_violations = 0
        self.overload_events = 0
        self.off_peak_sessions = 0
        self.total_sessions = 1
        self.disrupted_sessions = 0
        self.last_info = {}
        return self._observation(), {"zone_id": self.zone_id, "capacity_mw": self.feeder_capacity_mw}

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict]:
        action = np.clip(np.asarray(action, dtype=float), 0.0, 1.0)
        slow_curtail, fast_curtail, bmtc_curtail, incentive_signal = action
        step = self.current_step
        hour = step / 4.0
        is_peak = 18 <= hour < 21
        is_off_peak = hour < 6 or hour >= 22

        active_sessions = float(self.current_profile.active_sessions[step] + self.rng.poisson(2.0 + 4.0 * is_peak))
        bmtc_sessions = float(self.current_profile.bmtc_returns[step])
        voluntary_shift_prob = 1.0 / (1.0 + np.exp(-8.0 * (incentive_signal - 0.48)))
        shifted_sessions = self.rng.binomial(max(int(active_sessions), 0), voluntary_shift_prob * (1.0 if is_peak else 0.25))

        slow_power = max(active_sessions - bmtc_sessions, 0.0) * 0.012 * (1.0 - slow_curtail)
        fast_power = active_sessions * 0.030 * (1.0 - fast_curtail)
        bmtc_power = bmtc_sessions * 0.095 * (1.0 - bmtc_curtail)
        charging_load_mw = slow_power + fast_power + bmtc_power
        shifted_load_reduction = shifted_sessions * 0.010
        noise = self.rng.normal(0.0, 0.12)
        self.current_load_mw = max(
            0.0,
            float(self.current_profile.base_load_mw[step] + charging_load_mw - shifted_load_reduction + noise),
        )

        load_pct = self.current_load_mw / self.feeder_capacity_mw
        reward = 0.0
        overload_severity = max(0.0, load_pct - 0.90)
        if load_pct > 0.90:
            reward -= 10.0 * overload_severity
            self.overload_events += 1
        if load_pct > 0.85:
            reward -= 2.0

        self.total_sessions += max(active_sessions, 1.0)
        if is_off_peak:
            self.off_peak_sessions += active_sessions
        reward += (active_sessions if is_off_peak else shifted_sessions) / max(active_sessions, 1.0) * 5.0

        soc_gain = charging_load_mw / max(active_sessions + bmtc_sessions, 1.0) * 0.20
        self.avg_soc_active_sessions = np.clip(self.avg_soc_active_sessions + soc_gain - 0.015, 0.0, 1.0)
        soc_violation = bool((hour >= 6.0) and bmtc_sessions > 0 and self.avg_soc_active_sessions < 0.72)
        if soc_violation:
            reward -= 8.0
            self.soc_violations += 1

        renewable_bonus = 1.0 if self.current_profile.renewable_pct[step] > 0.65 and charging_load_mw > 0.2 else 0.0
        reward += renewable_bonus

        disrupted = int(shifted_sessions * (1.0 if incentive_signal < 0.75 else 0.45))
        self.disrupted_sessions += disrupted
        reward -= 0.5 * disrupted

        self.current_step += 1
        terminated = self.current_step >= EPISODE_STEPS
        truncated = False
        info = {
            "feeder_load_mw": self.current_load_mw,
            "feeder_load_pct": load_pct,
            "headroom_mw": self.feeder_capacity_mw - self.current_load_mw,
            "active_sessions": active_sessions,
            "shifted_sessions": shifted_sessions,
            "off_peak_sessions": self.off_peak_sessions,
            "soc_violation": soc_violation,
            "overload_events": self.overload_events,
            "renewable_alignment_bonus": renewable_bonus,
            "user_disruption_penalty": -0.5 * disrupted,
        }
        self.last_info = info
        return self._observation(), float(reward), terminated, truncated, info

    def render(self) -> None:
        load_pct = self.last_info.get("feeder_load_pct", self.current_load_mw / self.feeder_capacity_mw)
        width = 40
        filled = int(np.clip(load_pct, 0, 1.2) / 1.2 * width)
        bar = "#" * filled + "-" * (width - filled)
        print(
            f"[{bar}] {load_pct * 100:5.1f}% load | "
            f"headroom {self.last_info.get('headroom_mw', 0.0):.2f} MW | "
            f"overloads {self.overload_events}"
        )
