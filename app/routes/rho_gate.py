"""
Screen 3B: Rho Gate (Relevance Voting) - Consultant View
=========================================================
Displays parameter universe with real-time SME voting results.
Fully algorithmic: no human override on survival logic.

Rules:
1. Survived: >=1 SME voted YES (relevant=True)
2. Unresolved: 0 YES votes in current round
3. Max 3 rounds. After round 3, 0 YES = Removed
4. Gate locks when 0 unresolved remain
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.auth import decode_access_token
from app.database import SessionLocal
from app.models import Discovery, Process, Parameter, SME, SMEVote

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def compute_parameter_status(parameter, votes_by_param, current_round):
    """
    Apply rho gate rules to determine parameter status.
    Returns dict with status, vote counts, and display info.
    """
    param_votes = votes_by_param.get(str(parameter.id), [])

    # Count votes across all rounds
    total_yes = sum(1 for v in param_votes if v.relevant is True)
    total_no = sum(1 for v in param_votes if v.relevant is False)
    total_unsure = sum(1 for v in param_votes if v.relevant is None)

    # Current round votes
    current_votes = [v for v in param_votes if v.round_number == current_round]
    current_yes = sum(1 for v in current_votes if v.relevant is True)
    current_no = sum(1 for v in current_votes if v.relevant is False)
    current_unsure = sum(1 for v in current_votes if v.relevant is None)
    current_total = len(current_votes)

    # Apply rules
    if total_yes >= 1:
        status = "survived"
        badge_class = "bg-green-600"
        row_class = "border-green-500/30"
    elif current_round > 3:
        # After round 3 with 0 yes = removed
        status = "removed"
        badge_class = "bg-slate-600"
        row_class = "opacity-50"
    elif current_round >= 1 and total_yes == 0 and current_total > 0:
        # Has votes but 0 yes
        if current_round >= 3:
            status = "removed"
            badge_class = "bg-slate-600"
            row_class = "opacity-50"
        else:
            status = "unresolved"
            badge_class = "bg-yellow-600"
            row_class = "border-yellow-500/30"
    else:
        # No votes yet in this round
        status = "pending"
        badge_class = "bg-slate-500"
        row_class = "border-slate-600"

    return {
        "id": str(parameter.id),
        "name": parameter.name,
        "source": parameter.source or "standard",
        "description": parameter.description or "",
        "status": status,
        "badge_class": badge_class,
        "row_class": row_class,
        "yes": total_yes,
        "no": total_no,
        "unsure": total_unsure,
        "current_yes": current_yes,
        "current_no": current_no,
        "current_unsure": current_unsure,
        "current_total": current_total,
        "next_round": current_round + 1,
    }


@router.get("/discovery/{discovery_id}/rho-gate", response_class=HTMLResponse)
async def rho_gate_view(request: Request, discovery_id: str):
    """Render the Rho Gate consultant control panel."""
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/", status_code=303)
    user_data = decode_access_token(token)
    if not user_data:
        return RedirectResponse(url="/", status_code=303)

    db = SessionLocal()
    try:
        # Load discovery + related data
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        if not discovery:
            return RedirectResponse(url="/dashboard", status_code=303)

        process = db.query(Process).filter(Process.discovery_id == discovery.id).first()
        if not process:
            return RedirectResponse(url="/dashboard", status_code=303)

        parameters = db.query(Parameter).filter(Parameter.process_id == process.id).all()
        smes = db.query(SME).filter(SME.discovery_id == discovery.id).all()

        # Load all votes for these parameters
        param_ids = [p.id for p in parameters]
        all_votes = db.query(SMEVote).filter(SMEVote.parameter_id.in_(param_ids)).all()

        # Group votes by parameter
        votes_by_param = {}
        for vote in all_votes:
            key = str(vote.parameter_id)
            if key not in votes_by_param:
                votes_by_param[key] = []
            votes_by_param[key].append(vote)

        # Determine current round (max round_number in votes, or 1 if none)
        if all_votes:
            current_round = max(v.round_number for v in all_votes)
        else:
            current_round = 1

        # Compute status for each parameter
        param_statuses = []
        for param in parameters:
            status = compute_parameter_status(param, votes_by_param, current_round)
            param_statuses.append(status)

        # Summary counts
        survived_count = sum(1 for p in param_statuses if p["status"] == "survived")
        unresolved_count = sum(1 for p in param_statuses if p["status"] in ("unresolved", "pending"))
        removed_count = sum(1 for p in param_statuses if p["status"] == "removed")

        # SME response tracking
        total_smes = len(smes)
        smes_responded = len(set(v.sme_id for v in all_votes if v.round_number == current_round))

        # Gate can lock when 0 unresolved
        can_lock = unresolved_count == 0 and survived_count > 0
        # Can trigger next round when there are unresolved and current_round < 3
        can_trigger_next = unresolved_count > 0 and current_round < 3

        # Check if gate is already locked
        gate_locked = discovery.status == "rho_locked"

        return templates.TemplateResponse(
            "rho_gate.html",
            {
                "request": request,
                "discovery": discovery,
                "process": process,
                "parameters": param_statuses,
                "current_round": current_round,
                "total_smes": total_smes,
                "smes_responded": smes_responded,
                "survived_count": survived_count,
                "unresolved_count": unresolved_count,
                "removed_count": removed_count,
                "can_lock": can_lock,
                "can_trigger_next": can_trigger_next,
                "gate_locked": gate_locked,
                "consultant_name": "Maria Rodriguez",
            },
        )
    finally:
        db.close()


@router.post("/discovery/{discovery_id}/rho-gate/trigger-round", response_class=HTMLResponse)
async def trigger_next_round(request: Request, discovery_id: str):
    """Trigger next voting round for unresolved parameters."""
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/", status_code=303)
    user_data = decode_access_token(token)
    if not user_data:
        return RedirectResponse(url="/", status_code=303)

    # In production: send magic links to SMEs for re-voting on unresolved params
    # For now: redirect back to rho-gate (round increments when new votes come in)
    return RedirectResponse(
        url=f"/discovery/{discovery_id}/rho-gate",
        status_code=303,
    )


@router.post("/discovery/{discovery_id}/rho-gate/lock", response_class=HTMLResponse)
async def lock_rho_gate(request: Request, discovery_id: str):
    """Lock the rho gate. Only survived parameters proceed to weighting."""
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/", status_code=303)
    user_data = decode_access_token(token)
    if not user_data:
        return RedirectResponse(url="/", status_code=303)

    db = SessionLocal()
    try:
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        if discovery:
            discovery.status = "rho_locked"
            db.commit()
    finally:
        db.close()

    # Redirect to Screen 3C (Parameter Weighting) - placeholder for now
    return RedirectResponse(
        url=f"/discovery/{discovery_id}/rho-gate",
        status_code=303,
    )
