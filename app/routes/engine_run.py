"""
Screen 3G: Engine Run + Results
================================
The grand finale. Computes NPI, checks alpha kill switches,
classifies zones, shows parameter breakdown and prescriptions.

Formula: NPI = SUM(W_i * alpha_i * SUM(w_ij * KPI_ij))
Where KPI_ij = score / 100 (normalized to 0-1)
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import json

from app.database import SessionLocal
from app.models import (
    Discovery, Process, Parameter, KPI, KPIScore,
    ParameterWeight, KPIWeightLocked, TauDesignation, EngineResult
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


def compute_npi(process_id, db):
    """
    Compute the full NPI formula:
    NPI = SUM(W_i * alpha_i * SUM(w_ij * KPI_ij))
    
    Returns dict with NPI score, zone, parameter breakdown, alpha alerts.
    """
    # Get locked parameter weights
    param_weights = db.query(ParameterWeight).filter(
        ParameterWeight.process_id == process_id
    ).all()

    if not param_weights:
        return None

    process = db.query(Process).filter(Process.id == process_id).first()

    parameter_results = []
    alpha_alerts = []
    npi_sum = 0.0

    for pw in param_weights:
        param = db.query(Parameter).filter(Parameter.id == pw.parameter_id).first()
        W_i = pw.weight_normalized

        # Get KPIs for this parameter
        kpis = db.query(KPI).filter(KPI.parameter_id == param.id).all()

        # Check alpha (tau breach)
        alpha_i = 1.0
        breached_kpi = None

        for kpi in kpis:
            tau = db.query(TauDesignation).filter(
                TauDesignation.kpi_id == kpi.id
            ).first()

            if tau:
                score_record = db.query(KPIScore).filter(
                    KPIScore.kpi_id == kpi.id,
                    KPIScore.measurement_label == "discovery_baseline"
                ).first()

                if score_record:
                    direction = tau.direction if hasattr(tau, 'direction') and tau.direction else "higher_is_better"
                    if direction == "lower_is_better":
                        if score_record.score > tau.tau_floor:
                            alpha_i = 0.0
                            breached_kpi = {
                                "kpi_name": kpi.name,
                                "score": score_record.score,
                                "tau_floor": tau.tau_floor,
                                "direction": direction,
                            }
                    else:
                        if score_record.score < tau.tau_floor:
                            alpha_i = 0.0
                            breached_kpi = {
                                "kpi_name": kpi.name,
                                "score": score_record.score,
                                "tau_floor": tau.tau_floor,
                                "direction": direction,
                            }

        # Compute parameter composite: SUM(w_ij * KPI_ij)
        inner_sum = 0.0
        kpi_details = []
        has_all_scores = True

        for kpi in kpis:
            # Get w_ij
            kpi_weight = db.query(KPIWeightLocked).filter(
                KPIWeightLocked.kpi_id == kpi.id
            ).first()
            w_ij = kpi_weight.weight_normalized if kpi_weight else 0.0

            # Get score
            score_record = db.query(KPIScore).filter(
                KPIScore.kpi_id == kpi.id,
                KPIScore.measurement_label == "discovery_baseline"
            ).first()

            if score_record:
                kpi_ij = score_record.score / 100.0
                contribution = w_ij * kpi_ij
                inner_sum += contribution
                kpi_details.append({
                    "name": kpi.name,
                    "w_ij": round(w_ij * 100, 1),
                    "score": score_record.score,
                    "contribution": round(contribution * 100, 2),
                })
            else:
                has_all_scores = False
                kpi_details.append({
                    "name": kpi.name,
                    "w_ij": round(w_ij * 100, 1) if w_ij else 0,
                    "score": None,
                    "contribution": 0,
                })

        # Parameter contribution to NPI
        param_contribution = W_i * alpha_i * inner_sum
        npi_sum += param_contribution

        # Signal
        if alpha_i == 0:
            signal = "KILL"
        elif inner_sum < 0.4:
            signal = "Low"
        else:
            signal = "OK"

        param_result = {
            "name": param.name,
            "W_i": round(W_i * 100, 1),
            "alpha": alpha_i,
            "composite_score": round(inner_sum * 100, 1),
            "contribution": round(param_contribution * 100, 2),
            "signal": signal,
            "kpi_details": kpi_details,
        }
        parameter_results.append(param_result)

        if alpha_i == 0 and breached_kpi:
            alpha_alerts.append({
                "parameter": param.name,
                "W_i": round(W_i * 100, 1),
                "kpi_name": breached_kpi["kpi_name"],
                "score": breached_kpi["score"],
                "tau_floor": breached_kpi["tau_floor"],
                "direction": breached_kpi["direction"],
                "impact": round(W_i * 100, 1),
            })

    # Final NPI (as percentage)
    npi_score = round(npi_sum * 100, 1)

    # Zone classification
    red_floor = process.red_floor * 100 if process.red_floor else 20
    green_target = process.green_target * 100 if process.green_target else 80

    if alpha_alerts:
        zone = "RED"
    elif npi_score >= green_target:
        zone = "GREEN"
    elif npi_score <= red_floor:
        zone = "RED"
    else:
        zone = "YELLOW"

    # Generate prescriptions
    prescriptions = []
    for alert in alpha_alerts:
        prescriptions.append({
            "tier": "CRITICAL",
            "text": f"Immediate remediation for '{alert['kpi_name']}' in {alert['parameter']} (score: {alert['score']}, below survival threshold {alert['tau_floor']}). Alpha kill switch active.",
        })

    for pr in parameter_results:
        if pr["signal"] == "Low" and pr["alpha"] == 1.0:
            prescriptions.append({
                "tier": "PREVENTIVE",
                "text": f"Sprint to address '{pr['name']}' (composite score: {pr['composite_score']}%, approaching critical zone).",
            })

    return {
        "npi_score": npi_score,
        "zone": zone,
        "red_floor": red_floor,
        "green_target": green_target,
        "parameter_results": parameter_results,
        "alpha_alerts": alpha_alerts,
        "prescriptions": prescriptions,
    }


@router.get("/discovery/{discovery_id}/engine-run", response_class=HTMLResponse)
async def engine_run_view(request: Request, discovery_id: str):
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

        # Compute NPI
        result = compute_npi(str(process.id), db)

        if not result:
            return templates.TemplateResponse("engine_run.html", {
                "request": request,
                "discovery": discovery,
                "process": process,
                "result": None,
                "error": "No locked parameter weights found. Complete Steps 3-6 first.",
            })

        # Save result to DB
        existing = db.query(EngineResult).filter(
            EngineResult.discovery_id == discovery_id,
            EngineResult.measurement_label == "discovery_baseline"
        ).first()

        if existing:
            existing.overall_zone = result["zone"]
            existing.trust_gate_passed = len(result["alpha_alerts"]) == 0
            existing.result_json = json.dumps(result)
            existing.generated_at = datetime.utcnow()
        else:
            engine_result = EngineResult(
                discovery_id=discovery_id,
                measurement_label="discovery_baseline",
                overall_zone=result["zone"],
                trust_gate_passed=len(result["alpha_alerts"]) == 0,
                result_json=json.dumps(result),
            )
            db.add(engine_result)

        discovery.status = "engine_complete"
        db.commit()

        return templates.TemplateResponse("engine_run.html", {
            "request": request,
            "discovery": discovery,
            "process": process,
            "result": result,
            "error": None,
        })
    finally:
        db.close()
