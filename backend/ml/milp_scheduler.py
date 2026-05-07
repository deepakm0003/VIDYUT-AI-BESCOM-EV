from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np


SLOT_MINUTES = 15


@dataclass
class Session:
    session_id: str
    station_id: str
    feeder_id: str
    energy_needed_kwh: float
    max_power_kw: float
    arrival_slot: int = 0
    departure_slot: int = 16
    preferred_start_slot: int = 0
    preferred_end_slot: int = 16
    priority_score: float = 1.0


@dataclass
class ScheduleResult:
    assignments: dict[str, dict[int, float]]
    shifted_sessions: int
    peak_reduction_pct: float
    solve_time_ms: float
    feasible: bool
    infeasibility_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class MILPScheduler:
    def __init__(
        self,
        peak_load_weight: float = 1.0,
        preference_weight: float = 0.35,
        green_weight: float = 0.20,
        envelope_penalty: float = 2.0,
        solver_time_limit_ms: int = 200,
    ) -> None:
        self.peak_load_weight = peak_load_weight
        self.preference_weight = preference_weight
        self.green_weight = green_weight
        self.envelope_penalty = envelope_penalty
        self.solver_time_limit_ms = solver_time_limit_ms

    def solve(
        self,
        sessions: list[Session],
        feeder_headroom: dict[int, float],
        rl_envelopes: dict[str, list[float]],
        renewable_forecast: list[float],
        horizon_minutes: int = 240,
    ) -> ScheduleResult:
        started = time.perf_counter()
        slots = max(1, horizon_minutes // SLOT_MINUTES)
        if not sessions:
            return ScheduleResult({}, 0, 0.0, 0.0, True)

        original_peak = self._original_peak_kw(sessions, slots)
        try:
            result = self._solve_highs(sessions, feeder_headroom, rl_envelopes, renewable_forecast, slots, started)
            if result.feasible and result.solve_time_ms <= self.solver_time_limit_ms:
                result.peak_reduction_pct = self._peak_reduction(result.assignments, original_peak)
                return result
            reason = result.infeasibility_reason or "solver exceeded real-time budget"
        except Exception as exc:  # HiGHS API/version issues should not block dispatch.
            reason = f"HiGHS failed: {exc}"

        fallback = self._greedy_schedule(sessions, feeder_headroom, rl_envelopes, renewable_forecast, slots)
        fallback.solve_time_ms = (time.perf_counter() - started) * 1000.0
        fallback.infeasibility_reason = reason
        fallback.peak_reduction_pct = self._peak_reduction(fallback.assignments, original_peak)
        return fallback

    def _solve_highs(
        self,
        sessions: list[Session],
        feeder_headroom: dict[int, float],
        rl_envelopes: dict[str, list[float]],
        renewable_forecast: list[float],
        slots: int,
        started: float,
    ) -> ScheduleResult:
        import highspy

        highs = highspy.Highs()
        highs.setOptionValue("time_limit", self.solver_time_limit_ms / 1000.0)
        highs.setOptionValue("output_flag", False)

        p_index: dict[tuple[int, int], int] = {}
        x_index: dict[tuple[int, int], int] = {}
        slack_index: dict[tuple[int, int], int] = {}

        def add_col(lower: float, upper: float, cost: float = 0.0) -> int:
            col = highs.getNumCol()
            highs.addVar(float(lower), float(upper))
            highs.changeColCost(col, float(cost))
            return col

        for i, session in enumerate(sessions):
            for t in range(slots):
                feasible_window = session.arrival_slot <= t < min(session.departure_slot, slots)
                p_ub = session.max_power_kw if feasible_window else 0.0
                renewable = renewable_forecast[t] if t < len(renewable_forecast) else 0.0
                preference_cost = 0.0 if session.preferred_start_slot <= t < session.preferred_end_slot else self.preference_weight
                peak_cost = self.peak_load_weight * (1.0 + (slots - feeder_headroom.get(t, 0.0) / max(max(feeder_headroom.values()), 1.0)))
                cost = peak_cost + preference_cost - self.green_weight * renewable
                p_col = add_col(0.0, p_ub, cost)
                p_index[(i, t)] = p_col

                x_col = add_col(0.0, 1.0, 0.001)
                highs.changeColIntegrality(x_col, highspy.HighsVarType.kInteger)
                x_index[(i, t)] = x_col

                slack_col = add_col(0.0, session.max_power_kw, self.envelope_penalty)
                slack_index[(i, t)] = slack_col

                highs.addRow(
                    -highspy.kHighsInf,
                    0.0,
                    2,
                    np.array([p_col, x_col], dtype=np.int32),
                    np.array([1.0, -session.max_power_kw], dtype=np.float64),
                )

                envelope = self._envelope_for(session.station_id, rl_envelopes, t, session.max_power_kw)
                highs.addRow(
                    -highspy.kHighsInf,
                    float(envelope),
                    2,
                    np.array([p_col, slack_col], dtype=np.int32),
                    np.array([1.0, -1.0], dtype=np.float64),
                )

        for i, session in enumerate(sessions):
            indices = [p_index[(i, t)] for t in range(slots)]
            values = [0.25 for _ in range(slots)]
            highs.addRow(
                float(session.energy_needed_kwh),
                highspy.kHighsInf,
                len(indices),
                np.array(indices, dtype=np.int32),
                np.array(values, dtype=np.float64),
            )

        for t in range(slots):
            indices = [p_index[(i, t)] for i in range(len(sessions))]
            values = [1.0 for _ in sessions]
            highs.addRow(
                -highspy.kHighsInf,
                float(feeder_headroom.get(t, 0.0)),
                len(indices),
                np.array(indices, dtype=np.int32),
                np.array(values, dtype=np.float64),
            )

        highs.run()
        status = highs.getModelStatus()
        solve_time_ms = (time.perf_counter() - started) * 1000.0
        if status != highspy.HighsModelStatus.kOptimal:
            return ScheduleResult({}, 0, 0.0, solve_time_ms, False, f"HiGHS status: {status}")

        solution = highs.getSolution().col_value
        assignments: dict[str, dict[int, float]] = {}
        shifted_sessions = 0
        for i, session in enumerate(sessions):
            session_assignments = {}
            shifted = False
            for t in range(slots):
                power = float(solution[p_index[(i, t)]])
                if power > 1e-3:
                    session_assignments[t] = round(power, 3)
                    if not (session.preferred_start_slot <= t < session.preferred_end_slot):
                        shifted = True
            assignments[session.session_id] = session_assignments
            shifted_sessions += int(shifted)

        return ScheduleResult(assignments, shifted_sessions, 0.0, solve_time_ms, True, metadata={"solver": "highspy"})

    def _greedy_schedule(
        self,
        sessions: list[Session],
        feeder_headroom: dict[int, float],
        rl_envelopes: dict[str, list[float]],
        renewable_forecast: list[float],
        slots: int,
    ) -> ScheduleResult:
        remaining_headroom = {slot: float(feeder_headroom.get(slot, 0.0)) for slot in range(slots)}
        assignments: dict[str, dict[int, float]] = {session.session_id: {} for session in sessions}
        shifted_sessions = 0

        ordered_sessions = sorted(sessions, key=lambda item: (-item.priority_score, item.departure_slot, item.energy_needed_kwh))
        for session in ordered_sessions:
            remaining_energy = session.energy_needed_kwh
            feasible_slots = list(range(max(session.arrival_slot, 0), min(session.departure_slot, slots)))
            feasible_slots.sort(
                key=lambda slot: (
                    0 if session.preferred_start_slot <= slot < session.preferred_end_slot else 1,
                    -renewable_forecast[slot] if slot < len(renewable_forecast) else 0.0,
                    remaining_headroom[slot],
                )
            )
            shifted = False
            for slot in feasible_slots:
                envelope = self._envelope_for(session.station_id, rl_envelopes, slot, session.max_power_kw)
                power = min(session.max_power_kw, envelope, remaining_headroom[slot], remaining_energy / 0.25)
                if power <= 1e-6:
                    continue
                assignments[session.session_id][slot] = round(power, 3)
                remaining_headroom[slot] -= power
                remaining_energy -= power * 0.25
                if not (session.preferred_start_slot <= slot < session.preferred_end_slot):
                    shifted = True
                if remaining_energy <= 1e-3:
                    break
            if remaining_energy > 1e-3:
                return ScheduleResult(
                    assignments,
                    shifted_sessions,
                    0.0,
                    0.0,
                    False,
                    f"greedy fallback could not satisfy energy for {session.session_id}",
                    metadata={"solver": "greedy"},
                )
            shifted_sessions += int(shifted)

        return ScheduleResult(assignments, shifted_sessions, 0.0, 0.0, True, metadata={"solver": "greedy"})

    def _envelope_for(self, station_id: str, rl_envelopes: dict[str, list[float]], slot: int, default_kw: float) -> float:
        station_type = "bmtc" if "BMTC" in station_id.upper() or "DEP" in station_id.upper() else "fast"
        if station_type not in rl_envelopes and station_id in rl_envelopes:
            envelope = rl_envelopes[station_id]
        else:
            envelope = rl_envelopes.get(station_type, rl_envelopes.get("fast", []))
        if slot < len(envelope):
            return float(envelope[slot])
        return float(default_kw)

    def _original_peak_kw(self, sessions: list[Session], slots: int) -> float:
        load = np.zeros(slots)
        for session in sessions:
            for slot in range(max(session.arrival_slot, 0), min(session.departure_slot, slots)):
                load[slot] += session.max_power_kw
        return float(np.max(load)) if len(load) else 0.0

    def _peak_reduction(self, assignments: dict[str, dict[int, float]], original_peak: float) -> float:
        if original_peak <= 0:
            return 0.0
        optimized_load: dict[int, float] = {}
        for session_slots in assignments.values():
            for slot, power in session_slots.items():
                optimized_load[slot] = optimized_load.get(slot, 0.0) + power
        optimized_peak = max(optimized_load.values()) if optimized_load else 0.0
        return float((original_peak - optimized_peak) / original_peak)
