"""
VIDYUT AI Carbon Credits API Routes
Handles carbon credit calculations, certificates, and monetization.
"""

import logging
from datetime import datetime, timedelta
from uuid import uuid4
from typing import List, Optional, Dict
import json
import random

from fastapi import APIRouter, Query, HTTPException
from fastapi import Response
from io import BytesIO

try:
    from backend.api.schemas import (
        CarbonSummary, MonthlyBreakdown, MonthlyCarbonData, BeeCertificate,
        CarbonComputeRequest, CarbonComputeResult
    )
except ModuleNotFoundError:
    from api.schemas import (
        CarbonSummary, MonthlyBreakdown, MonthlyCarbonData, BeeCertificate,
        CarbonComputeRequest, CarbonComputeResult
    )

logger = logging.getLogger(__name__)
router = APIRouter()

# Mock carbon data history (Dec 2025 - May 2026)
CARBON_HISTORY = [
    {
        "month": "2025-12",
        "mwh_shifted": 312.5,
        "co2_avoided_tonnes": 68.75,
        "carbon_credits_revenue_crore": 0.447,
        "capex_savings_crore": 0.18,
    },
    {
        "month": "2026-01",
        "mwh_shifted": 425.3,
        "co2_avoided_tonnes": 93.56,
        "carbon_credits_revenue_crore": 0.608,
        "capex_savings_crore": 0.24,
    },
    {
        "month": "2026-02",
        "mwh_shifted": 512.1,
        "co2_avoided_tonnes": 112.66,
        "carbon_credits_revenue_crore": 0.732,
        "capex_savings_crore": 0.29,
    },
    {
        "month": "2026-03",
        "mwh_shifted": 598.4,
        "co2_avoided_tonnes": 131.68,
        "carbon_credits_revenue_crore": 0.856,
        "capex_savings_crore": 0.34,
    },
    {
        "month": "2026-04",
        "mwh_shifted": 725.8,
        "co2_avoided_tonnes": 159.67,
        "carbon_credits_revenue_crore": 1.037,
        "capex_savings_crore": 0.42,
    },
    {
        "month": "2026-05",
        "mwh_shifted": 1847.0,  # Current month cumulative (from frontend)
        "co2_avoided_tonnes": 406.0,
        "carbon_credits_revenue_crore": 2.43,
        "capex_savings_crore": 1.08,
    },
]


def get_historical_summary() -> CarbonSummary:
    """Calculate cumulative carbon summary across all months."""
    total_mwh = sum(m["mwh_shifted"] for m in CARBON_HISTORY)
    total_co2 = sum(m["co2_avoided_tonnes"] for m in CARBON_HISTORY)
    total_revenue = sum(m["carbon_credits_revenue_crore"] for m in CARBON_HISTORY)
    total_capex = sum(m["capex_savings_crore"] for m in CARBON_HISTORY)
    
    return CarbonSummary(
        total_mwh_shifted=total_mwh,
        total_co2_avoided_tonnes=total_co2,
        total_carbon_revenue_crore=total_revenue,
        total_capex_savings_crore=total_capex,
        months_tracked=len(CARBON_HISTORY),
        last_updated=datetime.utcnow()
    )


@router.get("/summary", response_model=CarbonSummary)
async def get_carbon_summary():
    """
    GET /api/carbon/summary
    Returns total carbon credits earned, CO2 avoided, and capex savings across all months.
    """
    return get_historical_summary()


@router.get("/monthly", response_model=MonthlyBreakdown)
async def get_monthly_breakdown(
    start_month: Optional[str] = Query(None, regex=r"^\d{4}-\d{2}$"),
    end_month: Optional[str] = Query(None, regex=r"^\d{4}-\d{2}$")
):
    """
    GET /api/carbon/monthly
    Returns monthly carbon breakdown with optional filtering.
    Query params: start_month (YYYY-MM), end_month (YYYY-MM)
    """
    monthly_data = []
    
    for entry in CARBON_HISTORY:
        month = entry["month"]
        
        # Filter by date range if specified
        if start_month and month < start_month:
            continue
        if end_month and month > end_month:
            continue
        
        monthly_data.append(MonthlyCarbonData(
            month=month,
            mwh_shifted=entry["mwh_shifted"],
            co2_avoided_tonnes=entry["co2_avoided_tonnes"],
            carbon_credits_revenue_crore=entry["carbon_credits_revenue_crore"],
            capex_savings_crore=entry["capex_savings_crore"]
        ))
    
    summary = get_historical_summary()
    
    return MonthlyBreakdown(
        summary=summary,
        monthly_data=monthly_data
    )


def _build_bee_certificate(month: str) -> BeeCertificate:
    month_data = next((m for m in CARBON_HISTORY if m["month"] == month), None)
    if not month_data:
        raise HTTPException(status_code=404, detail=f"No data for month {month}")
    year, _month_num = month.split("-")
    cert_number = f"BEE/{year}/VIDYUT/{str(int(month_data['mwh_shifted'])).zfill(4)}"
    issued_date = datetime.strptime(f"{month}-01", "%Y-%m-%d")
    valid_until = issued_date + timedelta(days=365)
    return BeeCertificate(
        certificate_number=cert_number,
        period=month,
        zone="All BESCOM",
        mwh_shifted=month_data["mwh_shifted"],
        co2_tonnes=month_data["co2_avoided_tonnes"],
        carbon_credits_value_crore=month_data["carbon_credits_revenue_crore"],
        capex_savings_crore=month_data["capex_savings_crore"],
        issued_at=issued_date,
        valid_until=valid_until,
        issuing_authority="Bureau of Energy Efficiency (BEE), Ministry of Power, Govt. of India",
    )


@router.get("/certificate/{month}.pdf")
async def get_bee_certificate_pdf(month: str):
    """
    GET /api/carbon/certificate/{month}.pdf
    Downloads the BEE certificate as a PDF file.
    """
    cert = _build_bee_certificate(month)

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 2.0 * cm
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2.0 * cm, y, "BEE Demand Response Certificate (Demo)")
    y -= 0.7 * cm

    c.setFont("Helvetica", 11)
    c.drawString(2.0 * cm, y, "Issuer: Bureau of Energy Efficiency (BEE), Ministry of Power, Govt. of India")
    y -= 0.9 * cm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.0 * cm, y, "Certificate Details")
    y -= 0.6 * cm

    c.setFont("Helvetica", 11)
    lines = [
        f"Certificate Number: {cert.certificate_number}",
        f"Utility / Zone: {cert.zone}",
        f"Period: {cert.period}",
        f"Issued At: {cert.issued_at.isoformat()}",
        f"Valid Until: {cert.valid_until.isoformat()}",
        "",
        "Verified Outcomes",
        f"MWh Shifted (off-peak alignment): {cert.mwh_shifted:.2f} MWh",
        f"CO2 Avoided: {cert.co2_tonnes:.2f} tonnes",
        f"Carbon Credit Value: {cert.carbon_credits_value_crore:.3f} Cr INR",
        f"CAPEX Savings: {cert.capex_savings_crore:.3f} Cr INR",
        "",
        "Notes",
        "This PDF is generated from VIDYUT AI demo data for hackathon submission purposes.",
        "All integrations are read-only and contain no user PII.",
    ]
    for line in lines:
        if y < 2.5 * cm:
            c.showPage()
            y = height - 2.0 * cm
            c.setFont("Helvetica", 11)
        c.drawString(2.0 * cm, y, line)
        y -= 0.5 * cm

    c.showPage()
    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()

    safe_month = month.replace("/", "-")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=BEE_Certificate_{safe_month}.pdf"},
    )


@router.get("/certificate/{month}", response_model=BeeCertificate)
async def get_bee_certificate(month: str):
    """
    GET /api/carbon/certificate/{month}
    Returns BEE certificate data for the specified month.
    Format: YYYY-MM (e.g., "2026-05")
    """
    return _build_bee_certificate(month)


@router.post("/compute", response_model=CarbonComputeResult)
async def compute_carbon_credits(request: CarbonComputeRequest):
    """
    POST /api/carbon/compute
    Triggers carbon credit calculation for a specific month.
    Returns result immediately (in production: async task with job_id).
    """
    month = request.month
    
    # Simulate computation
    logger.info(f"Computing carbon credits for {month}...")
    
    # Check if we have historical data
    month_data = next((m for m in CARBON_HISTORY if m["month"] == month), None)
    
    if month_data:
        result = MonthlyCarbonData(
            month=month,
            mwh_shifted=month_data["mwh_shifted"],
            co2_avoided_tonnes=month_data["co2_avoided_tonnes"],
            carbon_credits_revenue_crore=month_data["carbon_credits_revenue_crore"],
            capex_savings_crore=month_data["capex_savings_crore"]
        )
        
        return CarbonComputeResult(
            month=month,
            status="COMPLETED",
            result=result,
            error=None
        )
    else:
        # For future months: simulate pending computation
        return CarbonComputeResult(
            month=month,
            status="COMPUTING",
            result=None,
            error=None
        )


@router.get("/projections")
async def get_revenue_projections(years: int = 6):
    """
    GET /api/carbon/projections
    Returns revenue projections for carbon credits and capex savings over N years.
    Used for dashboard financial forecasting.
    """
    projections = []
    base_mwh = 1847.0  # Current month MWh shifted
    base_year = 2026
    
    # Project growth: EV penetration increases from 11% (current) to 30% by 2030
    penetration_start = 0.11
    penetration_end = 0.30
    
    for year_offset in range(years):
        year = base_year + year_offset
        
        # Linear interpolation of EV penetration
        penetration = penetration_start + (penetration_end - penetration_start) * (year_offset / years)
        
        # Assume MWh scales with penetration
        projected_mwh = base_mwh * (penetration / penetration_start)
        
        # CO2 avoided: 0.22 tonnes per MWh (peak - off-peak emissions delta)
        co2_tonnes = projected_mwh * 0.22
        
        # Revenue: ₹650/tonne of CO2 credits
        carbon_revenue = (co2_tonnes * 650) / 1e7  # Convert to crore
        
        # CAPEX savings: ₹585/MWh avoided peak load (feeder upgrade deferral)
        capex_savings = (projected_mwh * 585) / 1e7  # Convert to crore
        
        projections.append({
            "year": year,
            "ev_penetration_pct": round(penetration * 100, 1),
            "mwh_shifted": round(projected_mwh, 1),
            "co2_avoided_tonnes": round(co2_tonnes, 1),
            "carbon_credits_revenue_crore": round(carbon_revenue, 2),
            "capex_savings_crore": round(capex_savings, 2),
            "total_value_crore": round(carbon_revenue + capex_savings, 2)
        })
    
    return {
        "projections": projections,
        "assumptions": {
            "co2_factor_tonnes_per_mwh": 0.22,
            "carbon_credit_price_per_tonne": 650,
            "capex_savings_per_mwh": 585,
            "ev_penetration_baseline_pct": 11.0,
            "ev_penetration_target_pct": 30.0,
            "target_year": 2030
        },
        "generated_at": datetime.utcnow().isoformat()
    }


@router.get("/peer-comparison")
async def get_peer_comparison():
    """
    GET /api/carbon/peer-comparison
    Compares VIDYUT AI's carbon metrics against industry benchmarks and peer utilities.
    """
    return {
        "utility": "BESCOM (VIDYUT AI)",
        "region": "Bangalore",
        "metrics": {
            "carbon_avoidance_per_mwh": 0.22,  # tonnes CO2
            "capex_deferral_per_mwh": 585,  # rupees
            "carbon_credit_monetization_pct": 100,  # Fully realized
        },
        "peer_utilities": [
            {
                "name": "Tata Power (Delhi)",
                "carbon_per_mwh": 0.18,
                "capex_per_mwh": 520,
                "comment": "Lower emissions baseline (older coal mix)"
            },
            {
                "name": "CEPL (Pune)",
                "carbon_per_mwh": 0.24,
                "capex_per_mwh": 650,
                "comment": "Higher capex from newer infrastructure"
            },
            {
                "name": "CESC (Kolkata)",
                "carbon_per_mwh": 0.20,
                "capex_per_mwh": 580,
                "comment": "Industry average"
            },
        ],
        "vidyut_ranking": "Top 25th percentile in carbon avoidance, Top 10th percentile in capex deferral",
        "generated_at": datetime.utcnow().isoformat()
    }
