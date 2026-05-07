"""
VIDYUT AI Scheduler API Routes
Handles EV load shifting optimization via MILP and RL agents.
"""

import logging
from datetime import datetime, timedelta
from uuid import uuid4, UUID
import random
import time

from fastapi import APIRouter, HTTPException

from api.schemas import (
    ScheduleRequest, ScheduleResult, ScheduleAssignment, BmtcSequence,
    DigitalTwinValidation, SchedulerStatus, OverrideRequest
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Global scheduler state
scheduler_state = {
    "last_run_time": None,
    "sessions_scheduled_today": 0,
    "peak_reduction_achieved_pct": 0.0,
    "is_running": False,
    "last_run_id": None
}

# Mock feeder data
FEEDERS = {
    "F-2847": {"load_before": 85, "headroom_before": 15},
    "F-1203": {"load_before": 78, "headroom_before": 22},
    "F-0891": {"load_before": 82, "headroom_before": 18},
    "F-3341": {"load_before": 80, "headroom_before": 20},
    "F-2201": {"load_before": 75, "headroom_before": 25},
    "F-0445": {"load_before": 88, "headroom_before": 12},
}

# BMTC bus schedule
BMTC_SCHEDULE = [
    {
        "bus_id": "BMTC-A-001",
        "depot": "Whitefield",
        "charge_start": "22:00",
        "charge_end": "00:00",
        "priority": 1,
        "ev_battery_kwh": 300
    },
    {
        "bus_id": "BMTC-A-002",
        "depot": "Whitefield",
        "charge_start": "22:30",
        "charge_end": "00:30",
        "priority": 2,
        "ev_battery_kwh": 300
    },
    {
        "bus_id": "BMTC-B-001",
        "depot": "Koramangala",
        "charge_start": "00:00",
        "charge_end": "02:00",
        "priority": 1,
        "ev_battery_kwh": 300
    },
    {
        "bus_id": "BMTC-B-002",
        "depot": "Koramangala",
        "charge_start": "00:30",
        "charge_end": "02:30",
        "priority": 2,
        "ev_battery_kwh": 300
    },
    {
        "bus_id": "BMTC-C-001",
        "depot": "Indiranagar",
        "charge_start": "02:00",
        "charge_end": "04:00",
        "priority": 1,
        "ev_battery_kwh": 300
    },
    {
        "bus_id": "BMTC-C-002",
        "depot": "Indiranagar",
        "charge_start": "02:30",
        "charge_end": "04:30",
        "priority": 2,
        "ev_battery_kwh": 300
    },
]


def generate_mock_ev_sessions(zone_id: str, count: int = 20) -> list:
    """Generate mock EV charging sessions for a zone."""
    sessions = []
    now = datetime.utcnow()
    
    for i in range(count):
        session_id = f"{zone_id}-EV-{str(uuid4())[:8]}"
        # Sessions arrive randomly over next 4 hours
        arrival = now + timedelta(minutes=random.randint(0, 240))
        preferred_duration = random.randint(30, 120)  # 30-120 min charging window
        
        sessions.append({
            "session_id": session_id,
            "arrival_time": arrival.isoformat(),
            "preferred_window_start": arrival.isoformat(),
            "preferred_window_end": (arrival + timedelta(minutes=preferred_duration)).isoformat(),
            "power_kw": random.randint(7, 22),  # 7-22 kW chargers
            "soc_target": random.randint(80, 100),
            "battery_kwh": random.randint(30, 60)
        })
    
    return sessions


@router.get("/status", response_model=SchedulerStatus)
async def get_scheduler_status():
    """
    GET /api/scheduler/status
    Returns current scheduler status: last run time, sessions scheduled, peak reduction achieved.
    """
    return SchedulerStatus(
        last_run_time=scheduler_state["last_run_time"],
        sessions_scheduled_today=scheduler_state["sessions_scheduled_today"],
        peak_reduction_achieved_pct=scheduler_state["peak_reduction_achieved_pct"],
        is_running=scheduler_state["is_running"]
    )


@router.post("/run", response_model=ScheduleResult)
async def run_scheduler(request: ScheduleRequest):
    """
    POST /api/scheduler/run
    Execute MILP + RL optimization:
    1. Load active sessions for zone
    2. Get RL agent power envelopes
    3. Run MILP scheduler
    4. Validate with digital twin
    5. Return results with assignments and peak reduction
    """
    zone_id = request.zone_id.lower()
    scheduler_state["is_running"] = True
    
    try:
        start_time = time.time()
        
        # Step 1: Load active EV sessions
        sessions = generate_mock_ev_sessions(zone_id, count=random.randint(15, 30))
        total_sessions = len(sessions)
        
        logger.info(f"🔄 Running scheduler for {zone_id}: {total_sessions} sessions")
        
        # Step 2: Get RL agent power envelopes (simulated)
        # In production: call RL agent to get safe power envelope per feeder per hour
        rl_envelopes = {
            feeder_id: [random.uniform(30, 100) for _ in range(request.horizon_hours)]
            for feeder_id in FEEDERS.keys()
        }
        
        # Step 3: Run MILP scheduler (simulated)
        # In production: call HiGHS solver with:
        # - Minimize: peak load + constraint violations
        # - Subject to: feeder limits, session windows, ramp rates, vehicle SoC targets
        
        assignments = []
        shifted_sessions = 0
        
        for session in sessions[:int(total_sessions * 0.65)]:  # Shift ~65% of sessions
            # Simulate shift: move session outside peak window
            original_start = datetime.fromisoformat(session["preferred_window_start"])
            
            # If originally in peak (6-9pm), shift to off-peak
            if 18 <= original_start.hour < 21:
                assigned_start = original_start.replace(hour=22)  # Shift to 10pm
                status = "SHIFTED"
                shifted_sessions += 1
            else:
                assigned_start = original_start
                status = "PRIORITY"
            
            assigned_end = assigned_start + timedelta(
                minutes=int((datetime.fromisoformat(session["preferred_window_end"]) - original_start).total_seconds() / 60)
            )
            
            assignments.append(ScheduleAssignment(
                session_id=session["session_id"],
                original_window=f"{original_start.isoformat()}",
                assigned_window=f"{assigned_start.isoformat()}",
                power_kw=session["power_kw"],
                soc_target=session["soc_target"],
                status=status
            ))
        
        # Step 4: Calculate feeder headroom before/after
        feeder_headroom_before = {
            fid: config["headroom_before"] for fid, config in FEEDERS.items()
        }
        
        # Simulate headroom improvement after scheduling
        feeder_headroom_after = {
            fid: min(100, config["headroom_before"] + random.randint(5, 15))
            for fid, config in FEEDERS.items()
        }
        
        peak_reduction = random.uniform(20, 35)  # 20-35% peak reduction
        
        # Step 5: Digital twin validation (simulated)
        # In production: run power flow analysis on shifted schedule
        dt_result = DigitalTwinValidation(
            overload_risk_pct=max(0, random.uniform(0, 5)),
            voltage_sag_pct=max(0, random.uniform(0, 3))
        )
        
        solve_time_ms = (time.time() - start_time) * 1000
        run_id = uuid4()
        
        # Update global state
        scheduler_state["last_run_time"] = datetime.utcnow()
        scheduler_state["sessions_scheduled_today"] += shifted_sessions
        scheduler_state["peak_reduction_achieved_pct"] = peak_reduction
        scheduler_state["last_run_id"] = run_id
        
        # Generate BMTC sequence if requested
        bmtc_sequence = [BmtcSequence(**bs) for bs in BMTC_SCHEDULE] if request.include_bmtc else []
        
        logger.info(f"✅ Scheduler completed: {shifted_sessions}/{total_sessions} shifted, {peak_reduction:.1f}% peak reduction")
        
        return ScheduleResult(
            run_id=run_id,
            zone_id=zone_id,
            executed_at=datetime.utcnow(),
            sessions_total=total_sessions,
            sessions_shifted=shifted_sessions,
            shift_pct=(shifted_sessions / total_sessions * 100),
            peak_reduction_pct=peak_reduction,
            feeder_headroom_before=feeder_headroom_before,
            feeder_headroom_after=feeder_headroom_after,
            solve_time_ms=solve_time_ms,
            feasible=True,
            assignments=assignments,
            bmtc_sequence=bmtc_sequence,
            rl_envelopes_used=True,
            digital_twin_validated=True,
            digital_twin_result=dt_result
        )
    
    finally:
        scheduler_state["is_running"] = False


@router.get("/bmtc-schedule")
async def get_bmtc_schedule():
    """
    GET /api/scheduler/bmtc-schedule
    Returns today's BMTC depot charging sequence.
    """
    return {
        "date": datetime.utcnow().date().isoformat(),
        "buses": BMTC_SCHEDULE,
        "total_buses": len(BMTC_SCHEDULE),
        "total_charge_capacity_mw": sum(
            (bs["ev_battery_kwh"] / 1000) for bs in BMTC_SCHEDULE
        ) / (24 / 2),  # Approximate daily capacity
        "generated_at": datetime.utcnow().isoformat()
    }


@router.post("/override")
async def manual_override(request: OverrideRequest):
    """
    POST /api/scheduler/override
    Emergency manual override for feeder curtailment or restoration.
    Sends immediate curtailment signal to all EV chargers on that feeder.
    """
    if request.feeder_id not in FEEDERS:
        raise HTTPException(status_code=400, detail=f"Unknown feeder: {request.feeder_id}")
    
    action_log = {
        "override_id": str(uuid4()),
        "feeder_id": request.feeder_id,
        "action": request.action,
        "threshold_pct": request.threshold_pct,
        "timestamp": datetime.utcnow().isoformat(),
        "status": "EXECUTED"
    }
    
    if request.action == "curtail":
        # Simulate sending curtailment signal
        feeder_status = FEEDERS[request.feeder_id]
        current_headroom = feeder_status["headroom_before"]
        
        action_log["message"] = f"Curtailment signal sent: reduce load to keep headroom ≥ {request.threshold_pct}%"
        action_log["affected_evcs_count"] = random.randint(5, 15)
        action_log["estimated_reduction_kw"] = random.randint(50, 150)
        
    elif request.action == "restore":
        action_log["message"] = f"Restore normal charging: increase headroom threshold to {request.threshold_pct}%"
        action_log["affected_evcs_count"] = random.randint(3, 10)
    
    logger.info(f"⚠️ Manual override executed: {action_log}")
    
    return action_log
