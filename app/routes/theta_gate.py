"""
Screen 3C: Theta Gate (Parameter Weighting + Variance Validation)
Consultant control panel for Level 1 weights.
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import (
    Discovery, Process, Parameter, SME, SMEVote,
    ParameterRanking, ThetaGate, ParameterWeight
)
from app.auth import decode_access_token
from datetime import datetime
import statistics

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_auth(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_access_token(token)
    return payload


def compute_variance(ranks):
    """Compute population variance of a list of rank positions."""
    if len(ranks) < 2:
        return 0.0
    mean = sum(ranks) / len(ranks)
    return sum((r - mean) ** 2 for r in ranks) / len(ranks)


def compute_theta_data(process_id, db, theta_threshold, current_round):
    """
    Compute variance and convergence for all survived parameters.
    Returns list of dicts with parameter info, avg rank, variance, convergence status.
    """
    parameters = db.query(Parameter).filter(
        Parameter.process_id == process_id
    ).all()

    process = db.query(Process).filter(Process.id == process_id).first()
    smes = db.query(SME).filter(SME.discovery_id == process.discovery_id).all()
    total_smes = len(smes)

    read_round = current_round if current_round > 0 else 1

    results = []
    for param in parameters:
        locked = db.query(ParameterWeight).filter(
            ParameterWeight.parameter_id == param.id
        ).first()

        if locked:
            results.append({
                "id": str(param.id),
                "name": param.name,
                "source": param.source,
                "avg_rank": None,
                "variance": 0.0,
                "converged": True,
                "locked": True,
                "weight": locked.weight_normalized,
                "responses": total_smes,
                "total_smes": total_smes,
            })
            continue

        rankings = db.query(ParameterRanking).filter(
            ParameterRanking.parameter_id == param.id,
            ParameterRanking.round_number == read_round
        ).all()

        rank_values = [r.rank_position for r in rankings]
        responses = len(rank_values)

        if responses == 0:
            results.append({
                "id": str(param.id),
                "name": param.name,
                "source": param.source,
                "avg_rank": None,
                "variance": None,
                "converged": False,
                "locked": False,
                "weight": None,
                "responses": 0,
                "total_smes": total_smes,
            })
            continue

        avg_rank = sum(rank_values) / len(rank_values)
        variance = compute_variance(rank_values)
        converged = variance <= theta_threshold

        results.append({
            "id": str(param.id),
            "name": param.name,
            "source": param.source,
            "avg_rank": round(avg_rank, 2),
            "variance": round(variance, 2),
            "converged": converged,
            "locked": False,
            "weight": None,
            "responses": responses,
            "total_smes": total_smes,
        })

    return results, parameters, total_smes


def normalize_weights(param_data):
    """
    Convert average ranks to normalized weights (W_i).
    Lower rank = higher importance = higher weight.
    Uses inverse-rank method.
    """
    converged = [p for p in param_data if p["converged"] and p["avg_rank"] is not None]
    if not converged:
        return param_data

    inverse_sum = sum(1.0 / p["avg_rank"] for p in converged if p["avg_rank"] > 0)

    if inverse_sum == 0:
        return param_data

    for p in param_data:
        if p["converged"] and p["avg_rank"] and p["avg_rank"] > 0:
            p["weight"] = round((1.0 / p["avg_rank"]) / inverse_sum, 4)

    return param_data


@router.get("/theta/{process_id}", response_class=HTMLResponse)
async def theta_gate_view(request: Request, process_id: str):
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = next(get_db())
    try:
        process = db.query(Process).filter(Process.id == process_id).first()
        if not process:
            return RedirectResponse(url="/dashboard", status_code=302)

        discovery = db.query(Discovery).filter(Discovery.id == process.discovery_id).first()

        theta = db.query(ThetaGate).filter(ThetaGate.process_id == process_id).first()
        if not theta:
            theta = ThetaGate(
                process_id=process_id,
                threshold=1.5,
                current_round=0,
                status="pending"
            )
            db.add(theta)
            db.commit()
            db.refresh(theta)

        param_data, parameters, total_smes = compute_theta_data(
            process_id, db, theta.threshold, theta.current_round
        )

        param_data = normalize_weights(param_data)

        converged_count = sum(1 for p in param_data if p["converged"])
        divergent_count = sum(1 for p in param_data if not p["converged"])
        total_params = len(param_data)
        all_converged = divergent_count == 0 and total_params > 0

        has_responses = any(p["responses"] > 0 for p in param_data)

        return templates.TemplateResponse("theta_gate.html", {
            "request": request,
            "process": process,
            "discovery": discovery,
            "theta": theta,
            "param_data": param_data,
            "converged_count": converged_count,
            "divergent_count": divergent_count,
            "total_params": total_params,
            "total_smes": total_smes,
            "all_converged": all_converged,
            "has_responses": has_responses,
        })
    finally:
        db.close()


@router.post("/theta/{process_id}/trigger-round")
async def trigger_rerank_round(request: Request, process_id: str):
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = next(get_db())
    try:
        theta = db.query(ThetaGate).filter(ThetaGate.process_id == process_id).first()
        if not theta:
            return RedirectResponse(url=f"/theta/{process_id}", status_code=302)

        if theta.current_round >= 3:
            return RedirectResponse(url=f"/theta/{process_id}", status_code=302)

        theta.current_round += 1
        theta.status = "active"
        db.commit()

        return RedirectResponse(url=f"/theta/{process_id}", status_code=302)
    finally:
        db.close()


@router.post("/theta/{process_id}/lock")
async def lock_theta_gate(request: Request, process_id: str):
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = next(get_db())
    try:
        theta = db.query(ThetaGate).filter(ThetaGate.process_id == process_id).first()
        if not theta:
            return RedirectResponse(url=f"/theta/{process_id}", status_code=302)

        param_data, parameters, total_smes = compute_theta_data(
            process_id, db, theta.threshold, theta.current_round
        )
        param_data = normalize_weights(param_data)

        for p in param_data:
            if p["converged"] and p["weight"] is not None:
                existing = db.query(ParameterWeight).filter(
                    ParameterWeight.parameter_id == p["id"]
                ).first()
                if not existing:
                    pw = ParameterWeight(
                        parameter_id=p["id"],
                        process_id=process_id,
                        weight_normalized=p["weight"],
                        locked_at=datetime.utcnow(),
                        locked_by_round=theta.current_round
                    )
                    db.add(pw)

        theta.status = "locked"
        theta.locked_at = datetime.utcnow()

        process = db.query(Process).filter(Process.id == process_id).first()
        discovery = db.query(Discovery).filter(Discovery.id == process.discovery_id).first()
        discovery.status = "theta_locked"

        db.commit()

        return RedirectResponse(url=f"/theta/{process_id}", status_code=302)
    finally:
        db.close()


@router.get("/discovery/{discovery_id}/theta-gate", response_class=HTMLResponse)
async def theta_gate_by_discovery(request: Request, discovery_id: str):
    """Convenience route: looks up process from discovery, then renders theta gate."""
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = next(get_db())
    try:
        process = db.query(Process).filter(Process.discovery_id == discovery_id).first()
        if not process:
            return RedirectResponse(url="/dashboard", status_code=302)
        return RedirectResponse(url=f"/theta/{process.id}", status_code=302)
    finally:
        db.close()
