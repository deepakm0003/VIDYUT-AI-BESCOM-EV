"""
Pydantic v2 schemas for VIDYUT AI API endpoints.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Literal
from datetime import datetime
from uuid import UUID


# ==================== FORECAST SCHEMAS ====================

class PredictionPoint(BaseModel):
    timestamp: str
    load_mw: float
    confidence_lower: float
    confidence_upper: float


class ShapFeature(BaseModel):
    feature: str
    contribution: float


class ForecastDecomposition(BaseModel):
    trend: float
    seasonality: float
    ev_component: float
    anomaly: float


class PeakRiskWindow(BaseModel):
    start: str
    end: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class PredictRequest(BaseModel):
    zone_id: str
    horizon_hours: Literal[1, 4, 24, 48]
    feeder_id: Optional[str] = None

    @field_validator("zone_id")
    @classmethod
    def validate_zone(cls, v):
        valid_zones = ["whitefield", "koramangala", "yelahanka", "bommanahalli", "hebbal", "indiranagar"]
        if v.lower() not in valid_zones:
            raise ValueError(f"Invalid zone_id. Must be one of {valid_zones}")
        return v.lower()


class PredictResponse(BaseModel):
    zone_id: str
    generated_at: datetime
    horizon_hours: int
    predictions: List[PredictionPoint]
    model_weights: Dict[str, float]  # lstm, xgb, prophet
    mape_current: float
    shap_top_features: List[ShapFeature]
    forecast_decomposition: ForecastDecomposition
    natural_language_summary: str
    peak_risk_window: PeakRiskWindow


class ZoneStatus(BaseModel):
    zone_id: str
    current_load_mw: float
    capacity_mw: float
    headroom_pct: float
    status: Literal["SAFE", "WARNING", "CRITICAL"]


class ZoneListResponse(BaseModel):
    zones: List[ZoneStatus]
    generated_at: datetime


class AccuracyMetrics(BaseModel):
    model: str
    zone_id: str
    mape: float
    rmse: float
    mae: float


class AccuracyResponse(BaseModel):
    metrics: List[AccuracyMetrics]
    updated_at: datetime


class FeederForecast(BaseModel):
    feeder_id: str
    zone_id: str
    forecast_24h: List[PredictionPoint]
    headroom_timeline: List[Dict[str, float]]  # {timestamp: headroom_pct}
    current_headroom_pct: float


# ==================== SCHEDULER SCHEMAS ====================

class ScheduleRequest(BaseModel):
    zone_id: str
    horizon_hours: int = 4
    include_bmtc: bool = False

    @field_validator("horizon_hours")
    @classmethod
    def validate_horizon(cls, v):
        if v not in [1, 4, 24, 48]:
            raise ValueError("horizon_hours must be 1, 4, 24, or 48")
        return v


class ScheduleAssignment(BaseModel):
    session_id: str
    original_window: str
    assigned_window: str
    power_kw: float
    soc_target: float
    status: Literal["SHIFTED", "PRIORITY", "CONFLICT"]


class BmtcSequence(BaseModel):
    bus_id: str
    depot: str
    charge_start: str
    charge_end: str
    priority: int


class DigitalTwinValidation(BaseModel):
    overload_risk_pct: float
    voltage_sag_pct: float


class ScheduleResult(BaseModel):
    run_id: UUID
    zone_id: str
    executed_at: datetime
    sessions_total: int
    sessions_shifted: int
    shift_pct: float
    peak_reduction_pct: float
    feeder_headroom_before: Dict[str, float]
    feeder_headroom_after: Dict[str, float]
    solve_time_ms: float
    feasible: bool
    assignments: List[ScheduleAssignment]
    bmtc_sequence: List[BmtcSequence]
    rl_envelopes_used: bool
    digital_twin_validated: bool
    digital_twin_result: DigitalTwinValidation


class SchedulerStatus(BaseModel):
    last_run_time: Optional[datetime]
    sessions_scheduled_today: int
    peak_reduction_achieved_pct: float
    is_running: bool


class OverrideRequest(BaseModel):
    feeder_id: str
    threshold_pct: float
    action: Literal["curtail", "restore"]

    @field_validator("threshold_pct")
    @classmethod
    def validate_threshold(cls, v):
        if not (70 <= v <= 100):
            raise ValueError("threshold_pct must be between 70 and 100")
        return v


# ==================== SITES SCHEMAS ====================

class FactorScore(BaseModel):
    factor_name: str
    score: float
    weight: float


class SiteRanking(BaseModel):
    rank: int
    ward_id: str
    location_name: str
    vidyut_score: float
    factors: List[FactorScore]
    grid_upgrade_cost_crore: float
    year1_utilization_pct: float
    top_driver: str


class SiteRankingsResponse(BaseModel):
    rankings: List[SiteRanking]
    total_sites: int
    queried_at: datetime


class SiteDetail(BaseModel):
    ward_id: str
    location_name: str
    latitude: float
    longitude: float
    vidyut_score: float
    factors: List[FactorScore]
    grid_upgrade_cost_crore: float
    year1_utilization_pct: float
    year5_utilization_pct: float
    ev_density_per_sqkm: float
    traffic_index: float
    renewable_potential_pct: float


class GeoFeature(BaseModel):
    type: str = "Feature"
    properties: Dict
    geometry: Dict  # GeoJSON geometry


class GeoJsonResponse(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoFeature]


class CoverageGap(BaseModel):
    ward_id: str
    location_name: str
    latitude: float
    longitude: float
    ev_density_per_sqkm: float
    nearest_evcs_distance_km: float
    policy_gap: bool


class CoverageGapsResponse(BaseModel):
    gaps: List[CoverageGap]
    total_gap_count: int
    queried_at: datetime


class RescoreJob(BaseModel):
    job_id: UUID
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
    progress_pct: int
    created_at: datetime
    completed_at: Optional[datetime] = None


# ==================== CARBON SCHEMAS ====================

class MonthlyCarbonData(BaseModel):
    month: str  # "2025-12", "2026-01", etc.
    mwh_shifted: float
    co2_avoided_tonnes: float
    carbon_credits_revenue_crore: float
    capex_savings_crore: float


class CarbonSummary(BaseModel):
    total_mwh_shifted: float
    total_co2_avoided_tonnes: float
    total_carbon_revenue_crore: float
    total_capex_savings_crore: float
    months_tracked: int
    last_updated: datetime


class MonthlyBreakdown(BaseModel):
    summary: CarbonSummary
    monthly_data: List[MonthlyCarbonData]


class BeeCertificate(BaseModel):
    certificate_number: str
    period: str
    zone: str
    mwh_shifted: float
    co2_tonnes: float
    carbon_credits_value_crore: float
    capex_savings_crore: float
    issued_at: datetime
    valid_until: datetime
    issuing_authority: str


class CarbonComputeRequest(BaseModel):
    month: str

    @field_validator("month")
    @classmethod
    def validate_month(cls, v):
        import re
        if not re.match(r"^\d{4}-\d{2}$", v):
            raise ValueError("month must be in format YYYY-MM")
        return v


class CarbonComputeResult(BaseModel):
    month: str
    status: Literal["COMPUTING", "COMPLETED", "FAILED"]
    result: Optional[MonthlyCarbonData] = None
    error: Optional[str] = None


# ==================== ALERTS SCHEMAS ====================

class AlertEvent(BaseModel):
    alert_id: UUID
    alert_type: Literal["CRITICAL", "WARNING", "INFO", "RESOLVED"]
    feeder_id: str
    message: str
    load_pct: float
    timestamp: datetime
    action_taken: Optional[str] = None


class AlertHistory(BaseModel):
    alerts: List[AlertEvent]
    total_count: int
    queried_at: datetime


class FeederStatus(BaseModel):
    feeder_id: str
    current_load_pct: float
    headroom_pct: float
    status: Literal["SAFE", "WARNING", "CRITICAL"]
    last_updated: datetime


class FeedersStatusResponse(BaseModel):
    feeders: List[FeederStatus]
    total_feeders: int
    critical_count: int
    warning_count: int
    safe_count: int
    queried_at: datetime


# ==================== HEALTH CHECK SCHEMA ====================

class HealthCheckResponse(BaseModel):
    status: str
    version: str
    models_loaded: int
    components: Dict[str, bool]  # {ensemble_forecaster, rl_agent, site_rankings, carbon_history}
    timestamp: datetime
