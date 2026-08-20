"""
Screen 4 Task 3: SME Portal - KPI Ranking (theta Level 2)
==========================================================
Magic-link access. SMEs rank KPIs within a specific parameter.
Rankings feed into theta gate L2 variance computation.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import jwt
import os
from datetime import datetime

from app.database import SessionLocal
from app.models import (
    Discovery, Process, Parameter, KPI, SME,
    KPIRanking, ThetaGateL2
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SECRET_KEY = os.getenv("SECRET_KEY", "ic-pi-secret-key-change-in-prod")


def generate_kpi_ranking_token(sme_id: str, discovery_id: str, parameter_id: str) -> str:
    """Generate a magic-link JWT for SME KPI ranking task."""
    payload = {
        "sme_id": str(sme_id),
        "discovery_id": str(discovery_id),
        "parameter_id": str(parameter_id),
        "type": "sme_kpi_ranking_link",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_kpi_ranking_token(token: str) -> dict:
    """Decode and validate an SME KPI ranking token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "sme_kpi_ranking_link":
            return None
        return payload
    except (jwt.InvalidTokenError, jwt.DecodeError):
        return None


@router.get("/sme/rank-kpi/{token}", response_class=HTMLResponse)
async def sme_kpi_ranking_form(request: Request, token: str):
    """KPI ranking form: SME assigns ordinal ranks to KPIs within a parameter."""
    payload = decode_kpi_ranking_token(token)
    if not payload:
        return templates.TemplateResponse(
            "sme_error.html",
            {"request": request, "message": "Invalid or expired link."},
        )

    db = SessionLocal()
    try:
        sme = db.query(SME).filter(SME.id == payload["sme_id"]).first()
        discovery = db.query(Discovery).filter(Discovery.id == payload["discovery_id"]).first()
        parameter = db.query(Parameter).filter(Parameter.id == payload["parameter_id"]).first()

        if not sme or not discovery or not parameter:
            return templates.TemplateResponse(
                "sme_error.html",
                {"request": request, "message": "Discovery or parameter not found."},
            )

        process = db.query(Process).filter(Process.discovery_id == discovery.id).first()
        if not process:
            return templates.TemplateResponse(
                "sme_error.html",
                {"request": request, "message": "Process not configured."},
            )

        # Get theta gate L2 to know current round
        theta_l2 = db.query(ThetaGateL2).filter(ThetaGateL2.parameter_id == parameter.id).first()
        if not theta_l2 or theta_l2.current_round == 0:
            return templates.TemplateResponse(
                "sme_error.html",
                {"request": request, "message": "KPI ranking has not been opened yet. Please wait for the consultant to start Round 1."},
            )

        current_round = theta_l2.current_round

        # Check if SME already ranked in this round
        existing = db.query(KPIRanking).filter(
            KPIRanking.sme_id == sme.id,
            KPIRanking.parameter_id == parameter.id,
            KPIRanking.round_number == current_round
        ).first()

        if existing:
            return templates.TemplateResponse(
                "sme_complete.html",
                {
                    "request": request,
                    "sme_name": sme.name,
                    "message": "You have already submitted your KPI rankings for this parameter in this round. You will be notified if another round is triggered.",
                },
            )

        # Get KPIs for this parameter
        kpis = db.query(KPI).filter(KPI.parameter_id == parameter.id).all()

        # Build KPI data with previous round averages (for Delphi)
        kpi_data = []
        for kpi in kpis:
            k_info = {
                "id": str(kpi.id),
                "name": kpi.name,
                "description": kpi.description or "",
                "source": kpi.unit or "standard",
                "prev_avg": None,
            }

            if current_round > 1:
                prev_rankings = db.query(KPIRanking).filter(
                    KPIRanking.kpi_id == kpi.id,
                    KPIRanking.round_number == current_round - 1
                ).all()
                if prev_rankings:
                    avg = sum(r.rank_position for r in prev_rankings) / len(prev_rankings)
                    k_info["prev_avg"] = round(avg, 1)

            kpi_data.append(k_info)

        client_name = discovery.name.split(" - ")[-1] if " - " in discovery.name else "Client"

        return templates.TemplateResponse(
            "sme_kpi_rank.html",
            {
                "request": request,
                "sme_name": sme.name,
                "parameter_name": parameter.name,
                "process_name": process.name,
                "client_name": client_name,
                "kpis": kpi_data,
                "kpi_count": len(kpi_data),
                "current_round": current_round,
                "token": token,
            },
        )
    finally:
        db.close()


@router.post("/sme/rank-kpi/{token}", response_class=HTMLResponse)
async def sme_submit_kpi_rankings(request: Request, token: str):
    """Submit KPI rankings."""
    payload = decode_kpi_ranking_token(token)
    if not payload:
        return templates.TemplateResponse(
            "sme_error.html",
            {"request": request, "message": "Invalid or expired link."},
        )

    db = SessionLocal()
    try:
        sme = db.query(SME).filter(SME.id == payload["sme_id"]).first()
        discovery = db.query(Discovery).filter(Discovery.id == payload["discovery_id"]).first()
        parameter = db.query(Parameter).filter(Parameter.id == payload["parameter_id"]).first()

        if not sme or not discovery or not parameter:
            return templates.TemplateResponse(
                "sme_error.html",
                {"request": request, "message": "Discovery or parameter not found."},
            )

        # Get current round from theta gate L2
        theta_l2 = db.query(ThetaGateL2).filter(ThetaGateL2.parameter_id == parameter.id).first()
        current_round = theta_l2.current_round if theta_l2 else 1

        # Check for duplicate submission
        existing = db.query(KPIRanking).filter(
            KPIRanking.sme_id == sme.id,
            KPIRanking.parameter_id == parameter.id,
            KPIRanking.round_number == current_round
        ).first()

        if existing:
            return templates.TemplateResponse(
                "sme_complete.html",
                {
                    "request": request,
                    "sme_name": sme.name,
                    "message": "You have already submitted your KPI rankings for this round.",
                },
            )

        # Get KPIs
        kpis = db.query(KPI).filter(KPI.parameter_id == parameter.id).all()

        # Parse form data
        form_data = await request.form()

        for kpi in kpis:
            rank_value = form_data.get(f"rank_{kpi.id}")
            if rank_value:
                ranking = KPIRanking(
                    sme_id=sme.id,
                    kpi_id=kpi.id,
                    parameter_id=parameter.id,
                    round_number=current_round,
                    rank_position=int(rank_value),
                )
                db.add(ranking)

        db.commit()

        return templates.TemplateResponse(
            "sme_complete.html",
            {
                "request": request,
                "sme_name": sme.name,
                "message": "Your KPI rankings have been recorded. Thank you for your expertise.",
            },
        )
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse(
            "sme_error.html",
            {"request": request, "message": "An error occurred. Please try again."},
        )
    finally:
        db.close()


@router.get("/sme/generate-kpi-ranking-links/{discovery_id}/{parameter_id}", response_class=HTMLResponse)
async def generate_kpi_ranking_links(request: Request, discovery_id: str, parameter_id: str):
    """
    Utility for consultant: generates magic links for SME KPI ranking task.
    Auth-protected.
    """
    from app.auth import decode_access_token

    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/", status_code=303)
    user_data = decode_access_token(token)
    if not user_data:
        return RedirectResponse(url="/", status_code=303)

    db = SessionLocal()
    try:
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        if not discovery:
            return HTMLResponse("<p>Discovery not found.</p>")

        parameter = db.query(Parameter).filter(Parameter.id == parameter_id).first()
        if not parameter:
            return HTMLResponse("<p>Parameter not found.</p>")

        smes = db.query(SME).filter(SME.discovery_id == discovery.id).all()
        base_url = os.getenv("BASE_URL", "https://ic-pi-platform-production.up.railway.app")

        links = []
        for sme in smes:
            sme_token = generate_kpi_ranking_token(str(sme.id), str(discovery.id), str(parameter.id))
            link = f"{base_url}/sme/rank-kpi/{sme_token}"
            links.append({"name": sme.name, "email": sme.email, "link": link})

        html = f"<html><body style='background:#1e293b;color:white;padding:40px;font-family:sans-serif;'>"
        html += f"<h2>KPI Ranking Links for: {parameter.name}</h2>"
        html += f"<p style='color:#94a3b8;'>Discovery: {discovery.name}</p>"
        html += "<p>Share each link with the corresponding SME for KPI ranking (theta L2):</p><br>"
        for item in links:
            html += f"<div style='margin-bottom:20px;padding:16px;background:#334155;border-radius:8px;'>"
            html += f"<strong>{item['name']}</strong> ({item['email']})<br>"
            html += f"<input type='text' value='{item['link']}' readonly style='width:100%;margin-top:8px;padding:8px;background:#1e293b;color:#67e8f9;border:1px solid #475569;border-radius:4px;font-size:12px;'>"
            html += f"</div>"
        html += "</body></html>"

        return HTMLResponse(html)
    finally:
        db.close()
