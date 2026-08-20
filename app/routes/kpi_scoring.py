"""
Screen 3F: KPI Scoring
========================
Data entry screen where actual KPI scores are collected from client
operational data. Every score is evidence-based. Shows tau floor
comparison inline for critical KPIs.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

from app.database import SessionLocal
from app.models import (
    Discovery, Process, Parameter, KPI, KPIScore,
    ParameterWeight, KPIWeightLocked, TauDesignation
)
from app.auth import decode_access_token

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def require_auth(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_access_token(token)
    return payload


@router.get("/discovery/{discovery_id}/kpi-scoring", response_class=HTMLResponse)
async def kpi_scoring_view(request: Request, discovery_id: str):
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = SessionLocal()
    try:
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        if not discovery:
            return RedirectResponse(url="/dashboard", status_code=302)

        process = db.query(Process).filter(Process.discovery_id == discovery.id).first()
        if not process:
            return RedirectResponse(url="/dashboard", status_code=302)

        # Get locked parameters
        locked_params = db.query(ParameterWeight).filter(
            ParameterWeight.process_id == process.id
        ).all()

        param_ids = [lp.parameter_id for lp in locked_params]
        parameters = db.query(Parameter).filter(Parameter.id.in_(param_ids)).all()

        # Build scoring data
        param_data = []
        total_kpis = 0
        scored_count = 0
        below_tau_count = 0

        for param in parameters:
            pw = next((lp for lp in locked_params if str(lp.parameter_id) == str(param.id)), None)
            w_i = pw.weight_normalized if pw else 0

            kpis = db.query(KPI).filter(KPI.parameter_id == param.id).all()
            kpi_list = []

            for kpi in kpis:
                # Get locked weight
                kpi_weight = db.query(KPIWeightLocked).filter(
                    KPIWeightLocked.kpi_id == kpi.id
                ).first()
                w_ij = kpi_weight.weight_normalized if kpi_weight else None

                # Get tau designation
                tau = db.query(TauDesignation).filter(
                    TauDesignation.kpi_id == kpi.id
                ).first()

                # Get existing score (measurement_label = "discovery_baseline")
                existing_score = db.query(KPIScore).filter(
                    KPIScore.kpi_id == kpi.id,
                    KPIScore.measurement_label == "discovery_baseline"
                ).first()

                is_scored = existing_score is not None
                score_value = existing_score.score if existing_score else None
                evidence = existing_score.evidence_note if existing_score else None

                if is_scored:
                    scored_count += 1

                # Check tau breach
                below_tau = False
                if tau and score_value is not None:
                    if score_value < tau.tau_floor:
                        below_tau = True
                        below_tau_count += 1

                kpi_list.append({
                    "id": str(kpi.id),
                    "name": kpi.name,
                    "description": kpi.description or "",
                    "source": kpi.unit or "standard",
                    "w_ij": round(w_ij * 100, 1) if w_ij else None,
                    "has_tau": tau is not None,
                    "tau_floor": tau.tau_floor if tau else None,
                    "score": score_value,
                    "evidence": evidence or "",
                    "is_scored": is_scored,
                    "below_tau": below_tau,
                })
                total_kpis += 1

            param_data.append({
                "param_name": param.name,
                "w_i": round(w_i * 100, 1),
                "kpis": kpi_list,
            })

        all_scored = scored_count == total_kpis and total_kpis > 0

        return templates.TemplateResponse("kpi_scoring.html", {
            "request": request,
            "discovery": discovery,
            "process": process,
            "param_data": param_data,
            "total_kpis": total_kpis,
            "scored_count": scored_count,
            "below_tau_count": below_tau_count,
            "all_scored": all_scored,
        })
    finally:
        db.close()


@router.post("/discovery/{discovery_id}/kpi-scoring", response_class=HTMLResponse)
async def save_kpi_scores(request: Request, discovery_id: str):
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = SessionLocal()
    try:
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        process = db.query(Process).filter(Process.discovery_id == discovery.id).first()

        form_data = await request.form()

        parameters = db.query(Parameter).filter(Parameter.process_id == process.id).all()

        for param in parameters:
            kpis = db.query(KPI).filter(KPI.parameter_id == param.id).all()

            for kpi in kpis:
                kpi_id = str(kpi.id)
                score_value = form_data.get(f"score_{kpi_id}")
                evidence = form_data.get(f"evidence_{kpi_id}")

                if score_value:
                    try:
                        score_float = float(score_value)
                    except ValueError:
                        continue

                    # Upsert: update existing or create new
                    existing = db.query(KPIScore).filter(
                        KPIScore.kpi_id == kpi_id,
                        KPIScore.measurement_label == "discovery_baseline"
                    ).first()

                    if existing:
                        existing.score = score_float
                        existing.evidence_note = evidence or None
                        existing.scored_at = datetime.utcnow()
                    else:
                        new_score = KPIScore(
                            kpi_id=kpi_id,
                            score=score_float,
                            measurement_label="discovery_baseline",
                            evidence_note=evidence or None,
                        )
                        db.add(new_score)

        discovery.status = "scored"
        db.commit()

        return RedirectResponse(
            url=f"/discovery/{discovery_id}/kpi-scoring",
            status_code=302
        )
    finally:
        db.close()
