"""
Screen 4: SME Portal - Relevance Voting (rho)
===============================================
Magic-link access. Zero registration. Single-task focus.
SMEs vote YES/NO/NOT SURE on each parameter's relevance.
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
import jwt
import os
from datetime import datetime

from app.database import SessionLocal
from app.models import Discovery, Process, Parameter, SME, SMEVote

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SECRET_KEY = os.getenv("SECRET_KEY", "ic-pi-secret-key-change-in-prod")


def generate_sme_token(sme_id: str, discovery_id: str) -> str:
    """Generate a magic-link JWT for an SME."""
    payload = {
        "sme_id": str(sme_id),
        "discovery_id": str(discovery_id),
        "type": "sme_magic_link",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_sme_token(token: str) -> dict:
    """Decode and validate an SME magic-link token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "sme_magic_link":
            return None
        return payload
    except (jwt.InvalidTokenError, jwt.DecodeError):
        return None


@router.get("/sme/portal/{token}", response_class=HTMLResponse)
async def sme_welcome(request: Request, token: str):
    """Welcome briefing: first screen after magic-link click."""
    payload = decode_sme_token(token)
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
        client_name = discovery.name.split(" - ")[-1] if " - " in discovery.name else "Client"
        process_name = process.name if process else "Process"

        return templates.TemplateResponse(
            "sme_welcome.html",
            {
                "request": request,
                "sme_name": sme.name,
                "client_name": client_name,
                "process_name": process_name,
                "token": token,
            },
        )
    finally:
        db.close()


@router.get("/sme/vote/{token}", response_class=HTMLResponse)
async def sme_rho_vote_form(request: Request, token: str):
    """Rho vote screen: parameter list with YES/NO/NOT SURE toggles."""
    payload = decode_sme_token(token)
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

        parameters = db.query(Parameter).filter(Parameter.process_id == process.id).all()

        # Determine current round
        existing_votes = db.query(SMEVote).filter(
            SMEVote.sme_id == sme.id,
            SMEVote.parameter_id.in_([p.id for p in parameters])
        ).all()

        if existing_votes:
            max_round = max(v.round_number for v in existing_votes)
            current_round = max_round + 1
        else:
            current_round = 1

        # Check if SME already voted in current round
        already_voted = any(v.round_number == current_round for v in existing_votes)
        if already_voted:
            return templates.TemplateResponse(
                "sme_complete.html",
                {
                    "request": request,
                    "sme_name": sme.name,
                    "message": "You have already submitted your votes for this round. You will be notified if another round is triggered.",
                },
            )

        # Build parameter list with previous round aggregates (if round > 1)
        param_data = []
        for param in parameters:
            p_info = {
                "id": str(param.id),
                "name": param.name,
                "description": param.description or "",
                "source": param.source or "standard",
            }

            # Show anonymous aggregates from previous rounds (if any)
            if current_round > 1:
                prev_votes = [v for v in existing_votes if v.parameter_id == param.id]
                all_param_votes = db.query(SMEVote).filter(
                    SMEVote.parameter_id == param.id,
                    SMEVote.round_number == current_round - 1,
                ).all()
                total = len(all_param_votes)
                yes_count = sum(1 for v in all_param_votes if v.relevant is True)
                no_count = sum(1 for v in all_param_votes if v.relevant is False)
                unsure_count = sum(1 for v in all_param_votes if v.relevant is None)
                p_info["prev_yes"] = yes_count
                p_info["prev_no"] = no_count
                p_info["prev_unsure"] = unsure_count
                p_info["prev_total"] = total

            param_data.append(p_info)

        client_name = discovery.name.split(" - ")[-1] if " - " in discovery.name else "Client"

        return templates.TemplateResponse(
            "sme_rho_vote.html",
            {
                "request": request,
                "sme_name": sme.name,
                "process_name": process.name,
                "client_name": client_name,
                "parameters": param_data,
                "current_round": current_round,
                "token": token,
            },
        )
    finally:
        db.close()


@router.post("/sme/vote/{token}", response_class=HTMLResponse)
async def sme_submit_votes(request: Request, token: str):
    """Submit rho votes for all parameters."""
    payload = decode_sme_token(token)
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

        # Determine current round
        existing_votes = db.query(SMEVote).filter(
            SMEVote.sme_id == sme.id,
            SMEVote.parameter_id.in_([p.id for p in parameters])
        ).all()

        if existing_votes:
            current_round = max(v.round_number for v in existing_votes) + 1
        else:
            current_round = 1

        # Parse form data
        form_data = await request.form()

        for param in parameters:
            vote_value = form_data.get(f"vote_{param.id}")

            if vote_value == "yes":
                relevant = True
            elif vote_value == "no":
                relevant = False
            else:
                relevant = None  # NOT SURE

            vote = SMEVote(
                sme_id=sme.id,
                parameter_id=param.id,
                round_number=current_round,
                relevant=relevant,
            )
            db.add(vote)

        db.commit()

        return templates.TemplateResponse(
            "sme_complete.html",
            {
                "request": request,
                "sme_name": sme.name,
                "message": "Your votes have been recorded. Thank you for your expertise.",
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


@router.get("/sme/generate-links/{discovery_id}", response_class=HTMLResponse)
async def generate_magic_links(request: Request, discovery_id: str):
    """
    Utility endpoint for consultant: generates magic links for all SMEs in a discovery.
    Auth-protected (consultant only).
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
            sme_token = generate_sme_token(str(sme.id), str(discovery.id))
            link = f"{base_url}/sme/portal/{sme_token}"
            links.append({"name": sme.name, "email": sme.email, "link": link})

        # Simple HTML response showing the links
        html = f"<html><body style='background:#1e293b;color:white;padding:40px;font-family:sans-serif;'>"
        html += f"<h2>Magic Links for: {discovery.name}</h2>"
        html += "<p>Share each link with the corresponding SME:</p><br>"
        for item in links:
            html += f"<div style='margin-bottom:20px;padding:16px;background:#334155;border-radius:8px;'>"
            html += f"<strong>{item['name']}</strong> ({item['email']})<br>"
            html += f"<input type='text' value='{item['link']}' readonly style='width:100%;margin-top:8px;padding:8px;background:#1e293b;color:#67e8f9;border:1px solid #475569;border-radius:4px;font-size:12px;'>"
            html += f"</div>"
        html += "</body></html>"

        return HTMLResponse(html)
    finally:
        db.close()
