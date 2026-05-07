"""
VIDYUT AI Sites API Routes
Handles site selection, GIS scoring, and coverage gap analysis.
"""

import logging
from datetime import datetime
from uuid import uuid4
from typing import List, Optional, Dict
import random
import json

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse

try:
    from backend.api.schemas import (
        SiteRanking, SiteRankingsResponse, SiteDetail, GeoJsonResponse, GeoFeature,
        CoverageGap, CoverageGapsResponse, FactorScore, RescoreJob
    )
except ModuleNotFoundError:
    from api.schemas import (
        SiteRanking, SiteRankingsResponse, SiteDetail, GeoJsonResponse, GeoFeature,
        CoverageGap, CoverageGapsResponse, FactorScore, RescoreJob
    )

logger = logging.getLogger(__name__)
router = APIRouter()

# Mock site data: 50 candidate sites across 6 zones
MOCK_SITES = [
    {
        "rank": 1,
        "ward_id": "WF-047",
        "location_name": "Whitefield Metro Parking",
        "latitude": 12.9698,
        "longitude": 77.7497,
        "vidyut_score": 87,
        "zone_id": "whitefield",
        "ev_density_per_sqkm": 45.3,
        "factors": [
            {"factor_name": "EV Demand", "score": 95, "weight": 0.25},
            {"factor_name": "Grid Headroom", "score": 88, "weight": 0.22},
            {"factor_name": "Traffic", "score": 82, "weight": 0.18},
            {"factor_name": "Coverage Gap", "score": 85, "weight": 0.15},
            {"factor_name": "Land Availability", "score": 90, "weight": 0.10},
            {"factor_name": "Equity", "score": 78, "weight": 0.05},
            {"factor_name": "Renewable Potential", "score": 75, "weight": 0.05},
        ],
        "grid_upgrade_cost_crore": 2.3,
        "year1_utilization_pct": 68.5,
        "year5_utilization_pct": 87.2,
        "top_driver": "🏆 High EV Density",
        "nearest_competitor_km": 1.2,
    },
    {
        "rank": 2,
        "ward_id": "KR-023",
        "location_name": "Koramangala 5th Block",
        "latitude": 12.9352,
        "longitude": 77.6245,
        "vidyut_score": 83,
        "zone_id": "koramangala",
        "ev_density_per_sqkm": 42.8,
        "factors": [
            {"factor_name": "EV Demand", "score": 92, "weight": 0.25},
            {"factor_name": "Grid Headroom", "score": 80, "weight": 0.22},
            {"factor_name": "Traffic", "score": 88, "weight": 0.18},
            {"factor_name": "Coverage Gap", "score": 82, "weight": 0.15},
            {"factor_name": "Land Availability", "score": 85, "weight": 0.10},
            {"factor_name": "Equity", "score": 80, "weight": 0.05},
            {"factor_name": "Renewable Potential", "score": 72, "weight": 0.05},
        ],
        "grid_upgrade_cost_crore": 1.8,
        "year1_utilization_pct": 65.2,
        "year5_utilization_pct": 84.5,
        "top_driver": "📍 Strategic Location",
        "nearest_competitor_km": 0.8,
    },
    {
        "rank": 3,
        "ward_id": "YN-061",
        "location_name": "Yelahanka New Town",
        "latitude": 13.0811,
        "longitude": 77.5920,
        "vidyut_score": 79,
        "zone_id": "yelahanka",
        "ev_density_per_sqkm": 38.5,
        "factors": [
            {"factor_name": "EV Demand", "score": 85, "weight": 0.25},
            {"factor_name": "Grid Headroom", "score": 78, "weight": 0.22},
            {"factor_name": "Traffic", "score": 75, "weight": 0.18},
            {"factor_name": "Coverage Gap", "score": 88, "weight": 0.15},
            {"factor_name": "Land Availability", "score": 92, "weight": 0.10},
            {"factor_name": "Equity", "score": 82, "weight": 0.05},
            {"factor_name": "Renewable Potential", "score": 68, "weight": 0.05},
        ],
        "grid_upgrade_cost_crore": 1.5,
        "year1_utilization_pct": 58.3,
        "year5_utilization_pct": 76.8,
        "top_driver": "🏗️ Land Available",
        "nearest_competitor_km": 2.1,
    },
    {
        "rank": 4,
        "ward_id": "BM-195",
        "location_name": "Bommanahalli Ward 195",
        "latitude": 12.8353,
        "longitude": 77.6245,
        "vidyut_score": 74,
        "zone_id": "bommanahalli",
        "ev_density_per_sqkm": 35.2,
        "factors": [
            {"factor_name": "EV Demand", "score": 80, "weight": 0.25},
            {"factor_name": "Grid Headroom", "score": 72, "weight": 0.22},
            {"factor_name": "Traffic", "score": 70, "weight": 0.18},
            {"factor_name": "Coverage Gap", "score": 80, "weight": 0.15},
            {"factor_name": "Land Availability", "score": 75, "weight": 0.10},
            {"factor_name": "Equity", "score": 75, "weight": 0.05},
            {"factor_name": "Renewable Potential", "score": 65, "weight": 0.05},
        ],
        "grid_upgrade_cost_crore": 1.2,
        "year1_utilization_pct": 52.1,
        "year5_utilization_pct": 71.5,
        "top_driver": "💰 Low Cost",
        "nearest_competitor_km": 1.5,
    },
    {
        "rank": 5,
        "ward_id": "HB-089",
        "location_name": "Hebbal Flyover Complex",
        "latitude": 13.0078,
        "longitude": 77.5896,
        "vidyut_score": 71,
        "zone_id": "hebbal",
        "ev_density_per_sqkm": 32.8,
        "factors": [
            {"factor_name": "EV Demand", "score": 75, "weight": 0.25},
            {"factor_name": "Grid Headroom", "score": 68, "weight": 0.22},
            {"factor_name": "Traffic", "score": 92, "weight": 0.18},
            {"factor_name": "Coverage Gap", "score": 72, "weight": 0.15},
            {"factor_name": "Land Availability", "score": 70, "weight": 0.10},
            {"factor_name": "Equity", "score": 72, "weight": 0.05},
            {"factor_name": "Renewable Potential", "score": 60, "weight": 0.05},
        ],
        "grid_upgrade_cost_crore": 2.0,
        "year1_utilization_pct": 48.7,
        "year5_utilization_pct": 68.2,
        "top_driver": "🚗 High Traffic",
        "nearest_competitor_km": 0.6,
    },
]

# Generate additional mock sites for other zones
def generate_all_sites() -> List[Dict]:
    """Generate full mock site dataset."""
    sites = MOCK_SITES.copy()
    
    # Add more mock sites for variety
    additional_sites = [
        {
            "rank": 6, "ward_id": "IND-034", "location_name": "Indiranagar Forum Mall",
            "latitude": 12.9716, "longitude": 77.6412, "vidyut_score": 68, "zone_id": "indiranagar",
            "ev_density_per_sqkm": 28.5, "grid_upgrade_cost_crore": 1.9, "year1_utilization_pct": 45.3,
        },
        {
            "rank": 7, "ward_id": "WF-056", "location_name": "Whitefield Tech Park",
            "latitude": 12.9656, "longitude": 77.7542, "vidyut_score": 65, "zone_id": "whitefield",
            "ev_density_per_sqkm": 25.2, "grid_upgrade_cost_crore": 2.5, "year1_utilization_pct": 42.8,
        },
    ]
    
    sites.extend(additional_sites)
    return sites


@router.get("/rankings", response_model=SiteRankingsResponse)
async def get_site_rankings(
    zone_id: Optional[str] = Query(None),
    top_n: int = Query(20, ge=1, le=100),
    min_score: float = Query(0, ge=0, le=100)
):
    """
    GET /api/sites/rankings
    Returns ranked site list with filtering options.
    Query params: zone_id (optional), top_n (default 20), min_score (default 0)
    """
    all_sites = generate_all_sites()
    
    # Filter by zone if specified
    if zone_id:
        all_sites = [s for s in all_sites if s["zone_id"].lower() == zone_id.lower()]
    
    # Filter by minimum score
    all_sites = [s for s in all_sites if s["vidyut_score"] >= min_score]
    
    # Sort by score (descending)
    all_sites.sort(key=lambda s: s["vidyut_score"], reverse=True)
    
    # Take top N
    all_sites = all_sites[:top_n]
    
    # Convert to response schema
    rankings = []
    for site in all_sites:
        factors = [
            FactorScore(
                factor_name=f["factor_name"],
                score=f.get("score", random.randint(60, 95)),
                weight=f["weight"]
            )
            for f in site.get("factors", [])
        ]
        
        rankings.append(SiteRanking(
            rank=site["rank"],
            ward_id=site["ward_id"],
            location_name=site["location_name"],
            vidyut_score=site["vidyut_score"],
            factors=factors,
            grid_upgrade_cost_crore=site["grid_upgrade_cost_crore"],
            year1_utilization_pct=site["year1_utilization_pct"],
            top_driver=site.get("top_driver", "Strategic Location")
        ))
    
    return SiteRankingsResponse(
        rankings=rankings,
        total_sites=len(all_sites),
        queried_at=datetime.utcnow()
    )


@router.get("/geojson", response_model=GeoJsonResponse)
async def get_geojson():
    """
    GET /api/sites/geojson
    Returns GeoJSON FeatureCollection for map rendering.
    Each feature includes: ward_id, score, lat, lng, top_driver, grid_upgrade_needed
    """
    all_sites = generate_all_sites()
    features = []
    
    for site in all_sites:
        feature = GeoFeature(
            type="Feature",
            properties={
                "ward_id": site["ward_id"],
                "location_name": site["location_name"],
                "score": site["vidyut_score"],
                "zone": site["zone_id"],
                "top_driver": site.get("top_driver", "Strategic Site"),
                "grid_upgrade_cost_crore": site["grid_upgrade_cost_crore"],
                "utilization_pct": site["year1_utilization_pct"],
                "ev_density_per_sqkm": site["ev_density_per_sqkm"],
            },
            geometry={
                "type": "Point",
                "coordinates": [site["longitude"], site["latitude"]]
            }
        )
        features.append(feature)
    
    return GeoJsonResponse(
        type="FeatureCollection",
        features=features
    )


@router.post("/rescore")
async def trigger_rescore():
    """
    POST /api/sites/rescore
    Triggers site scoring algorithm (background task).
    Returns job_id for polling progress.
    """
    job_id = uuid4()
    
    return RescoreJob(
        job_id=job_id,
        status="QUEUED",
        progress_pct=0,
        created_at=datetime.utcnow(),
        completed_at=None
    ).model_dump()


@router.get("/coverage-gaps", response_model=CoverageGapsResponse)
async def get_coverage_gaps():
    """
    GET /api/sites/coverage-gaps
    Returns wards with high EV density but no EVCS within 3km.
    Identifies Karnataka policy gaps for new site selection.
    """
    # Mock coverage gap data
    gaps = [
        CoverageGap(
            ward_id="KR-056",
            location_name="Kalyan Nagar Central",
            latitude=12.9752,
            longitude=77.6412,
            ev_density_per_sqkm=52.3,
            nearest_evcs_distance_km=3.8,
            policy_gap=True
        ),
        CoverageGap(
            ward_id="WF-078",
            location_name="Whitefield Junction",
            latitude=12.9612,
            longitude=77.7623,
            ev_density_per_sqkm=48.5,
            nearest_evcs_distance_km=3.2,
            policy_gap=True
        ),
        CoverageGap(
            ward_id="HB-112",
            location_name="Hebbal Industrial Area",
            latitude=13.0234,
            longitude=77.5756,
            ev_density_per_sqkm=45.1,
            nearest_evcs_distance_km=4.1,
            policy_gap=True
        ),
    ]
    
    return CoverageGapsResponse(
        gaps=gaps,
        total_gap_count=len(gaps),
        queried_at=datetime.utcnow()
    )


@router.get("/{ward_id}", response_model=SiteDetail)
async def get_site_detail(ward_id: str):
    """
    GET /api/sites/{ward_id}
    Returns full site detail with all 7 factor scores, upgrade costs, and utilization forecast.
    """
    all_sites = generate_all_sites()
    site = next((s for s in all_sites if s["ward_id"] == ward_id), None)

    if not site:
        raise HTTPException(status_code=404, detail=f"Site {ward_id} not found")

    factors = [
        FactorScore(
            factor_name=f["factor_name"],
            score=f.get("score", random.randint(60, 95)),
            weight=f["weight"]
        )
        for f in site.get("factors", [])
    ]

    return SiteDetail(
        ward_id=site["ward_id"],
        location_name=site["location_name"],
        latitude=site["latitude"],
        longitude=site["longitude"],
        vidyut_score=site["vidyut_score"],
        factors=factors,
        grid_upgrade_cost_crore=site["grid_upgrade_cost_crore"],
        year1_utilization_pct=site["year1_utilization_pct"],
        year5_utilization_pct=site.get("year5_utilization_pct", site["year1_utilization_pct"] + 20),
        ev_density_per_sqkm=site["ev_density_per_sqkm"],
        traffic_index=random.uniform(0.3, 0.95),
        renewable_potential_pct=random.uniform(15, 60)
    )
