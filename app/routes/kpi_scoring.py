"""
Screen 3F: KPI Scoring (with auto-normalization)
==================================================
Consultant enters: Best value, Worst value, Actual value per KPI.
System auto-computes normalized score (0-100) using:
  Score = (actual - worst) / (best - worst) * 100
No manual conversion needed. Works for any unit.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

from app.database import SessionLocal
from app.models import (
    Discovery, Process, Parameter, KPI, KPIScore,
    ParameterWeight, KPIWeightLocked, TauDesignation, KPIAnchor
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


def compute_normalized_score(actual, best, worst):
    """
    Normalize any raw value to 0-100 performance score.
    Works regardless of direction (higher/lower is better).
    Score = (actual - worst) / (best - worst) * 100
    Clamped to 0-100.
    """
    if best == worst:
        return 50.0
    score = (actual - worst) / (best - worst) * 100.0
    return max(0.0, min(100.0, round(score, 1)))


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

        locked_params = db.query(ParameterWeight).filter(
            ParameterWeight.process_id == process.id
        ).all()

        param_ids = [lp.parameter_id for lp in locked_params]
        parameters = db.query(Parameter).filter(Parameter.id.in_(param_ids)).all()

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
                kpi_weight = db.query(KPIWeightLocked).filter(
                    KPIWeightLocked.kpi_id == kpi.id
                ).first()
                w_ij = kpi_weight.weight_normalized if kpi_weight else None

                tau = db.query(TauDesignation).filter(
                    TauDesignation.kpi_id == kpi.id
                ).first()

                anchor = db.query(KPIAnchor).filter(
                    KPIAnchor.kpi_id == kpi.id
                ).first()

                existing_score = db.query(KPIScore).filter(
                    KPIScore.kpi_id == kpi.id,
                    KPIScore.measurement_label == "discovery_baseline"
                ).first()

                # Get actual value from evidence_note (we store raw there now)
                actual_value = None
                normalized_score = None
                evidence = ""

                if existing_score:
                    normalized_score = existing_score.score
                    evidence = existing_score.evidence_note or ""
                    # Try to parse actual from evidence (stored as first token)
                    try:
                        actual_value = float(evidence.split("|")[0].strip()) if "|" in evidence else None
                    except (ValueError, IndexError):
                        actual_value = None

                is_scored = normalized_score is not None
                if is_scored:
                    scored_count += 1

                # Check tau breach using normalized score
                below_tau = False
                if tau and normalized_score is not None:
                    # With anchors, tau breach = normalized score < tau threshold mapped to 0-100
                    # Simple: if anchor exists, convert tau_floor to normalized scale
                    if anchor:
                        tau_normalized = compute_normalized_score(tau.tau_floor, anchor.best_value, anchor.worst_value)
                        if normalized_score < tau_normalized:
                            below_tau = True
                            below_tau_count += 1
                    else:
                        # Fallback: direct comparison (legacy)
                        direction = tau.direction if hasattr(tau, 'direction') and tau.direction else "higher_is_better"
                        if direction == "lower_is_better":
                            if actual_value and actual_value > tau.tau_floor:
                                below_tau = True
                                below_tau_count += 1
                        else:
                            if normalized_score < tau.tau_floor:
                                below_tau = True
                                below_tau_count += 1

                kpi_list.append({
                    "id": str(kpi.id),
                    "name": kpi.name,
                    "description": kpi.description or "",
                    "w_ij": round(w_ij * 100, 1) if w_ij else None,
                    "has_tau": tau is not None,
                    "tau_floor": tau.tau_floor if tau else None,
                    "best_value": anchor.best_value if anchor else None,
                    "worst_value": anchor.worst_value if anchor else None,
                    "actual_value": actual_value,
                    "normalized_score": normalized_score,
                    "evidence": evidence,
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
                best_val = form_data.get(f"best_{kpi_id}")
                worst_val = form_data.get(f"worst_{kpi_id}")
                actual_val = form_data.get(f"actual_{kpi_id}")
                evidence = form_data.get(f"evidence_{kpi_id}")

                # Save/update anchors
                if best_val and worst_val:
                    try:
                        best_float = float(best_val)
                        worst_float = float(worst_val)
                    except ValueError:
                        continue

                    existing_anchor = db.query(KPIAnchor).filter(
                        KPIAnchor.kpi_id == kpi_id
                    ).first()

                    if existing_anchor:
                        existing_anchor.best_value = best_float
                        existing_anchor.worst_value = worst_float
                    else:
                        new_anchor = KPIAnchor(
                            kpi_id=kpi_id,
                            best_value=best_float,
                            worst_value=worst_float,
                        )
                        db.add(new_anchor)

                # Compute and save score
                if actual_val and best_val and worst_val:
                    try:
                        actual_float = float(actual_val)
                        best_float = float(best_val)
                        worst_float = float(worst_val)
                    except ValueError:
                        continue

                    normalized = compute_normalized_score(actual_float, best_float, worst_float)

                    # Store actual value in evidence_note (prefixed)
                    evidence_text = f"{actual_float} | {evidence}" if evidence else str(actual_float)

                    existing_score = db.query(KPIScore).filter(
                        KPIScore.kpi_id == kpi_id,
                        KPIScore.measurement_label == "discovery_baseline"
                    ).first()

                    if existing_score:
                        existing_score.score = normalized
                        existing_score.evidence_note = evidence_text
                        existing_score.scored_at = datetime.utcnow()
                    else:
                        new_score = KPIScore(
                            kpi_id=kpi_id,
                            score=normalized,
                            measurement_label="discovery_baseline",
                            evidence_note=evidence_text,
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
