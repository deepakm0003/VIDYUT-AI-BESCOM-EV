"""
VIDYUT AI Alerts API Routes
Handles real-time feeder stress alerts via Server-Sent Events (SSE).
"""

import logging
import asyncio
import random
import json
from datetime import datetime
from uuid import uuid4
from typing import List, AsyncGenerator, Dict
from collections import deque

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.schemas import (
    AlertEvent, AlertHistory, FeederStatus, FeedersStatusResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory alert history (last 100 alerts)
alert_history = deque(maxlen=100)

# Mock feeder data (500 feeders across all zones)
FEEDERS_DATA = {
    f"F-{1000+i}": {
        "zone": ["whitefield", "koramangala", "yelahanka", "bommanahalli", "hebbal", "indiranagar"][i % 6],
        "capacity_mw": random.uniform(40, 150),
    }
    for i in range(500)
}

# Alert messages
ALERT_MESSAGES = [
    "Feeder load exceeds 85% headroom - load shifting in progress",
    "Critical voltage sag detected - curtailment signal sent",
    "Grid frequency drop below 49.5 Hz - emergency load shed triggered",
    "Feeder load normalized - curtailment signal revoked",
]


def generate_mock_alert() -> AlertEvent:
    """Generate a mock alert based on current feeder loads."""
    # Select a random feeder
    feeder_id = random.choice(list(FEEDERS_DATA.keys()))
    feeder = FEEDERS_DATA[feeder_id]
    
    # Simulate load (40-95% of capacity)
    current_load_pct = random.uniform(40, 95)
    headroom_pct = 100 - current_load_pct
    
    # Determine alert type based on headroom
    if headroom_pct < 8:
        alert_type = "CRITICAL"
        message = ALERT_MESSAGES[0]
    elif headroom_pct < 15:
        alert_type = "WARNING"
        message = ALERT_MESSAGES[1]
    elif current_load_pct < 60:
        alert_type = "INFO"
        message = "Load within normal range"
    else:
        alert_type = "RESOLVED"
        message = ALERT_MESSAGES[3]
    
    return AlertEvent(
        alert_id=uuid4(),
        alert_type=alert_type,
        feeder_id=feeder_id,
        message=message,
        load_pct=current_load_pct,
        timestamp=datetime.utcnow(),
        action_taken="Automatic load shifting" if alert_type in ["CRITICAL", "WARNING"] else None
    )


def get_current_feeder_status() -> Dict[str, float]:
    """Get current load % for all feeders."""
    return {
        feeder_id: random.uniform(40, 95)
        for feeder_id in FEEDERS_DATA.keys()
    }


@router.get("/stream")
async def alert_stream():
    """
    GET /api/alerts/stream
    Server-Sent Events endpoint for real-time alerts.
    Generates new alert every 10 seconds based on feeder loads.
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events."""
        while True:
            try:
                # Generate a new alert every 10 seconds
                alert = generate_mock_alert()
                
                # Add to history
                alert_history.append(alert)
                
                # Format as SSE
                alert_dict = {
                    "alert_id": str(alert.alert_id),
                    "type": alert.alert_type,
                    "feeder_id": alert.feeder_id,
                    "message": alert.message,
                    "load_pct": round(alert.load_pct, 2),
                    "timestamp": alert.timestamp.isoformat(),
                    "action_taken": alert.action_taken,
                }
                
                yield f"data: {alert_dict}\n\n"
                
                # Wait 10 seconds before next alert
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                logger.info("Alert stream cancelled")
                break
            except Exception as e:
                logger.error(f"Error in alert stream: {e}")
                yield f"data: {{'error': '{str(e)}'}}\n\n"
                await asyncio.sleep(5)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@router.get("/history", response_model=AlertHistory)
async def get_alert_history(limit: int = 100):
    """
    GET /api/alerts/history
    Returns last N alerts from in-memory buffer (up to 100).
    """
    # Get last N alerts from deque
    alerts = list(alert_history)[-limit:]
    
    return AlertHistory(
        alerts=alerts,
        total_count=len(alert_history),
        queried_at=datetime.utcnow()
    )


@router.get("/feeders/status", response_model=FeedersStatusResponse)
async def get_feeders_status():
    """
    GET /api/alerts/feeders/status
    Returns current load % and status for all feeders.
    Shows SAFE/WARNING/CRITICAL status based on headroom.
    """
    feeder_statuses = []
    critical_count = 0
    warning_count = 0
    safe_count = 0
    
    for feeder_id, feeder in FEEDERS_DATA.items():
        # Simulate current load
        current_load_pct = random.uniform(40, 95)
        headroom_pct = 100 - current_load_pct
        
        # Determine status
        if headroom_pct < 8:
            status = "CRITICAL"
            critical_count += 1
        elif headroom_pct < 15:
            status = "WARNING"
            warning_count += 1
        else:
            status = "SAFE"
            safe_count += 1
        
        feeder_statuses.append(FeederStatus(
            feeder_id=feeder_id,
            current_load_pct=round(current_load_pct, 2),
            headroom_pct=round(headroom_pct, 2),
            status=status,
            last_updated=datetime.utcnow()
        ))
    
    return FeedersStatusResponse(
        feeders=feeder_statuses,
        total_feeders=len(FEEDERS_DATA),
        critical_count=critical_count,
        warning_count=warning_count,
        safe_count=safe_count,
        queried_at=datetime.utcnow()
    )


@router.get("/summary")
async def get_alerts_summary():
    """
    GET /api/alerts/summary
    Returns summary statistics of recent alerts.
    """
    if not alert_history:
        return {
            "total_alerts": 0,
            "critical_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "resolved_count": 0,
            "last_alert_time": None,
            "most_affected_feeder": None,
        }
    
    critical_count = sum(1 for a in alert_history if a.alert_type == "CRITICAL")
    warning_count = sum(1 for a in alert_history if a.alert_type == "WARNING")
    info_count = sum(1 for a in alert_history if a.alert_type == "INFO")
    resolved_count = sum(1 for a in alert_history if a.alert_type == "RESOLVED")
    
    # Find most affected feeder
    feeder_counts = {}
    for alert in alert_history:
        feeder_counts[alert.feeder_id] = feeder_counts.get(alert.feeder_id, 0) + 1
    
    most_affected_feeder = max(feeder_counts.items(), key=lambda x: x[1])[0] if feeder_counts else None
    
    return {
        "total_alerts": len(alert_history),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "resolved_count": resolved_count,
        "last_alert_time": alert_history[-1].timestamp.isoformat() if alert_history else None,
        "most_affected_feeder": most_affected_feeder,
        "generated_at": datetime.utcnow().isoformat()
    }


@router.get("/feeders/{feeder_id}/timeline")
async def get_feeder_alert_timeline(feeder_id: str, hours: int = 24):
    """
    GET /api/alerts/feeders/{feeder_id}/timeline
    Returns alert timeline for a specific feeder over last N hours.
    """
    # Filter alerts for this feeder
    feeder_alerts = [a for a in alert_history if a.feeder_id == feeder_id]
    
    if not feeder_alerts:
        return {
            "feeder_id": feeder_id,
            "alerts": [],
            "total_count": 0,
            "timeline_hours": hours,
            "message": "No alerts recorded for this feeder"
        }
    
    return {
        "feeder_id": feeder_id,
        "alerts": [
            {
                "timestamp": a.timestamp.isoformat(),
                "type": a.alert_type,
                "message": a.message,
                "load_pct": a.load_pct,
            }
            for a in feeder_alerts
        ],
        "total_count": len(feeder_alerts),
        "timeline_hours": hours,
        "generated_at": datetime.utcnow().isoformat()
    }
