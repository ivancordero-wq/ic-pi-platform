"""
Screen 4 Task 2: SME Portal - Parameter Ranking (theta)
========================================================
Magic-link access. SMEs rank survived parameters by importance.
Rankings feed into theta gate variance computation.
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import jwt
import os
from datetime import datetime

from app.database import SessionLocal
from app.models import (
    Discovery, Process, Parameter, SME,
    ParameterRanking, ThetaGate
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SECRET_KEY = os.getenv("SECRET_KEY", "ic-pi-secret-key-change-in-prod")


def generate_ranking_token(sme_id: str, discovery_id: str) -> str:
    """Generate a magic-link JWT for SME ranking task."""
    payload = {
        "sme_id": str(sme_id),
        "discovery_id": str(discovery_id),
        "type": "sme_ranking_link",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_ranking_token(token: str) -> dict:
    """Decode and validate an SME ranking token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "sme_ranking_link":
            return None
        return payload
    except (jwt.InvalidTokenError, jwt.DecodeError):
        return None


@router.get("/sme/rank/{token}", response_class=HTMLResponse)
async def sme_ranking_form(request: Request, token: str):
    """Ranking form: SME assigns ordinal ranks to parameters."""
    payload = decode_ranking_token(token)
    if not payload:
        return templates.TemplateResponse(
            "sme_error.html",
            {"request": request, "message": "Invalid or expired link."},
        )

    db = SessionLocal()
    try:
        sme = db.query(SME).filter(SME.id == payload["sme_id"]).first()
        discovery = db.query(Discovery).filter(Discovery.id == payload["discovery_id"]).first()

        if not sme or not discovery:
            return templates.TemplateResponse(
                "sme_error.html",
                {"request": request, "message": "Discovery not found."},
            )

        process = db.query(Process).filter(Process.discovery_id == discovery.id).first()
        if not process:
            return templates.TemplateResponse(
                "sme_error.html",
                {"request": request, "message": "Process not configured."},
            )

        # Get theta gate to know current round
        theta = db.query(ThetaGate).filter(ThetaGate.process_id == process.id).first()
        if not theta or theta.current_round == 0:
            return templates.TemplateResponse(
                "sme_error.html",
                {"request": request, "message": "Ranking has not been opened yet. Please wait for the consultant to start Round 1."},
            )

        current_round = theta.current_round

        # Check if SME already ranked in this round
        existing = db.query(ParameterRanking).filter(
            ParameterRanking.sme_id == sme.id,
            ParameterRanking.process_id == process.id,
            ParameterRanking.round_number == current_round
        ).first()

        if existing:
            return templates.TemplateResponse(
                "sme_complete.html",
                {
                    "request": request,
                    "sme_name": sme.name,
                    "message": "You have already submitted your rankings for this round. You will be notified if another round is triggered.",
                },
            )

        # Get parameters to rank
        parameters = db.query(Parameter).filter(Parameter.process_id == process.id).all()

        # Build parameter data with previous round averages (for Delphi)
        param_data = []
        for param in parameters:
            p_info = {
                "id": str(param.id),
                "name": param.name,
                "description": param.description or "",
                "source": param.source or "standard",
                "prev_avg": None,
            }

            # If round > 1, show previous round's average rank
            if current_round > 1:
                prev_rankings = db.query(ParameterRanking).filter(
                    ParameterRanking.parameter_id == param.id,
                    ParameterRanking.round_number == current_round - 1
                ).all()
                if prev_rankings:
                    avg = sum(r.rank_position for r in prev_rankings) / len(prev_rankings)
                    p_info["prev_avg"] = round(avg, 1)

            param_data.append(p_info)

        client_name = discovery.name.split(" - ")[-1] if " - " in discovery.name else "Client"

        return templates.TemplateResponse(
            "sme_theta_rank.html",
            {
                "request": request,
                "sme_name": sme.name,
                "process_name": process.name,
                "client_name": client_name,
                "parameters": param_data,
                "param_count": len(param_data),
                "current_round": current_round,
                "token": token,
            },
        )
    finally:
        db.close()


@router.post("/sme/rank/{token}", response_class=HTMLResponse)
async def sme_submit_rankings(request: Request, token: str):
    """Submit parameter rankings."""
    payload = decode_ranking_token(token)
    if not payload:
        return templates.TemplateResponse(
            "sme_error.html",
            {"request": request, "message": "Invalid or expired link."},
        )

    db = SessionLocal()
    try:
        sme = db.query(SME).filter(SME.id == payload["sme_id"]).first()
        discovery = db.query(Discovery).filter(Discovery.id == payload["discovery_id"]).first()

        if not sme or not discovery:
            return templates.TemplateResponse(
                "sme_error.html",
                {"request": request, "message": "Discovery not found."},
            )

        process = db.query(Process).filter(Process.discovery_id == discovery.id).first()
        parameters = db.query(Parameter).filter(Parameter.process_id == process.id).all()

        # Get current round from theta gate
        theta = db.query(ThetaGate).filter(ThetaGate.process_id == process.id).first()
        current_round = theta.current_round if theta else 1

        # Check for duplicate submission
        existing = db.query(ParameterRanking).filter(
            ParameterRanking.sme_id == sme.id,
            ParameterRanking.process_id == process.id,
            ParameterRanking.round_number == current_round
        ).first()

        if existing:
            return templates.TemplateResponse(
                "sme_complete.html",
                {
                    "request": request,
                    "sme_name": sme.name,
                    "message": "You have already submitted your rankings for this round.",
                },
            )

        # Parse form data
        form_data = await request.form()

        for param in parameters:
            rank_value = form_data.get(f"rank_{param.id}")
            if rank_value:
                ranking = ParameterRanking(
                    sme_id=sme.id,
                    parameter_id=param.id,
                    process_id=process.id,
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
                "message": "Your rankings have been recorded. Thank you for your expertise.",
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


@router.get("/sme/generate-ranking-links/{discovery_id}", response_class=HTMLResponse)
async def generate_ranking_links(request: Request, discovery_id: str):
    """
    Utility for consultant: generates magic links for SME ranking task.
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

        smes = db.query(SME).filter(SME.discovery_id == discovery.id).all()
        base_url = os.getenv("BASE_URL", "https://ic-pi-platform-production.up.railway.app")

        links = []
        for sme in smes:
            sme_token = generate_ranking_token(str(sme.id), str(discovery.id))
            link = f"{base_url}/sme/rank/{sme_token}"
            links.append({"name": sme.name, "email": sme.email, "link": link})

        html = f"<html><body style='background:#1e293b;color:white;padding:40px;font-family:sans-serif;'>"
        html += f"<h2>Ranking Links for: {discovery.name}</h2>"
        html += "<p>Share each link with the corresponding SME for parameter ranking (theta):</p><br>"
        for item in links:
            html += f"<div style='margin-bottom:20px;padding:16px;background:#334155;border-radius:8px;'>"
            html += f"<strong>{item['name']}</strong> ({item['email']})<br>"
            html += f"<input type='text' value='{item['link']}' readonly style='width:100%;margin-top:8px;padding:8px;background:#1e293b;color:#67e8f9;border:1px solid #475569;border-radius:4px;font-size:12px;'>"
            html += f"</div>"
        html += "</body></html>"

        return HTMLResponse(html)
    finally:
        db.close()
