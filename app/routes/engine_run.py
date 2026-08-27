"""
Screen 3G: Engine Run + Results
================================
The grand finale. Computes NPI, checks alpha kill switches,
classifies zones, shows parameter breakdown and prescriptions.

Formula: NPI = SUM(W_i * alpha_i * SUM(w_ij * KPI_ij))
Where KPI_ij = score / 100 (normalized to 0-1)
"""

import os
from openai import OpenAI
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import json

from app.database import SessionLocal
from app.models import (
    Discovery, Process, Parameter, KPI, KPIScore,
    ParameterWeight, KPIWeightLocked, TauDesignation, EngineResult, KPIAnchor
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

        kpis = db.query(KPI).filter(KPI.parameter_id == param.id).all()

        # Check alpha (tau breach using normalized comparison)
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
                    anchor = db.query(KPIAnchor).filter(
                        KPIAnchor.kpi_id == kpi.id
                    ).first()

                    if anchor and anchor.best_value != anchor.worst_value:
                        # Normalize tau_floor to 0-100 scale using same anchors
                        tau_normalized = (tau.tau_floor - anchor.worst_value) / (anchor.best_value - anchor.worst_value) * 100.0
                        tau_normalized = max(0.0, min(100.0, tau_normalized))
                        # Breach = normalized score below normalized tau
                        if score_record.score < tau_normalized:
                            alpha_i = 0.0
                            breached_kpi = {
                                "kpi_name": kpi.name,
                                "score": round(score_record.score, 1),
                                "tau_floor": round(tau_normalized, 1),
                                "raw_tau": tau.tau_floor,
                            }
                    else:
                        # No anchors: direct comparison (legacy fallback)
                        if score_record.score < tau.tau_floor:
                            alpha_i = 0.0
                            breached_kpi = {
                                "kpi_name": kpi.name,
                                "score": score_record.score,
                                "tau_floor": tau.tau_floor,
                                "raw_tau": tau.tau_floor,
                            }

        # Compute parameter composite: SUM(w_ij * KPI_ij)
        inner_sum = 0.0
        kpi_details = []

        for kpi in kpis:
            kpi_weight = db.query(KPIWeightLocked).filter(
                KPIWeightLocked.kpi_id == kpi.id
            ).first()
            w_ij = kpi_weight.weight_normalized if kpi_weight else 0.0

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
                "raw_tau": breached_kpi.get("raw_tau", breached_kpi["tau_floor"]),
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

    # Generate prescriptions (weighted gap method)
    prescriptions = []

    # CRITICAL tier: tau breaches (fix these first or NPI stays collapsed)
    for alert in alpha_alerts:
        prescriptions.append({
            "tier": "CRITICAL",
            "text": f"URGENT: {alert['kpi_name']} in {alert['parameter']} has breached its trip wire floor "
                    f"(score: {alert['score']}%, floor: {alert['tau_floor']}%). "
                    f"This parameter's entire {alert['impact']}% weight is zeroed out. "
                    f"Identify root cause and restore {alert['kpi_name']} above threshold before any other initiative.",
            "parameter": alert["parameter"],
            "kpi": alert["kpi_name"],
            "weighted_gap": alert["impact"] / 100.0,
        })

    # HIGH IMPACT tier: top parameters by weighted gap (W_i * (1 - composite))
    gaps = []
    for pr in parameter_results:
        if pr["alpha"] == 1.0 and pr["composite_score"] < 100:
            composite_decimal = pr["composite_score"] / 100.0
            w_i_decimal = pr["W_i"] / 100.0
            weighted_gap = w_i_decimal * (1 - composite_decimal)
            gaps.append({
                "name": pr["name"],
                "W_i": pr["W_i"],
                "composite": pr["composite_score"],
                "weighted_gap": round(weighted_gap * 100, 1),
                "kpi_details": pr["kpi_details"],
            })

    # Sort by weighted gap descending
    gaps.sort(key=lambda x: x["weighted_gap"], reverse=True)

    # Take top 3 parameters for HIGH IMPACT prescriptions
    for g in gaps[:3]:
        if g["weighted_gap"] <= 0:
            continue

        # Find the worst KPI within this parameter
        worst_kpi = None
        worst_kpi_gap = 0
        for kpi in g["kpi_details"]:
            if kpi["score"] is not None:
                kpi_score_decimal = kpi["score"] / 100.0
                w_ij_decimal = kpi["w_ij"] / 100.0
                kpi_gap = w_ij_decimal * (1 - kpi_score_decimal)
                if kpi_gap > worst_kpi_gap:
                    worst_kpi_gap = kpi_gap
                    worst_kpi = kpi

        if worst_kpi:
            potential_npi_gain = round(g["weighted_gap"] * 0.5, 1)
            prescriptions.append({
                "tier": "HIGH IMPACT",
                "text": f"Target '{worst_kpi['name']}' within {g['name']} (weight: {g['W_i']}%, "
                        f"current composite: {g['composite']}%). "
                        f"This KPI (w_ij: {worst_kpi['w_ij']}%, score: {worst_kpi['score']}%) "
                        f"has the largest gap in the highest-priority parameter. "
                        f"Improving it to 70% would add approximately {potential_npi_gain} points to NPI.",
                "parameter": g["name"],
                "kpi": worst_kpi["name"],
                "weighted_gap": g["weighted_gap"],
            })
        else:
            prescriptions.append({
                "tier": "HIGH IMPACT",
                "text": f"Parameter '{g['name']}' (weight: {g['W_i']}%, composite: {g['composite']}%) "
                        f"has a weighted gap of {g['weighted_gap']} points. "
                        f"Score all KPIs in this parameter to identify the specific improvement target.",
                "parameter": g["name"],
                "kpi": "unscored",
                "weighted_gap": g["weighted_gap"],
            })

    # PREVENTIVE tier: parameters performing OK but approaching risk
    for pr in parameter_results:
        if pr["alpha"] == 1.0 and 40 <= pr["composite_score"] <= 70:
            already_prescribed = any(p["parameter"] == pr["name"] for p in prescriptions)
            if not already_prescribed:
                prescriptions.append({
                    "tier": "PREVENTIVE",
                    "text": f"Monitor '{pr['name']}' closely (composite: {pr['composite_score']}%, weight: {pr['W_i']}%). "
                            f"Performance is acceptable but trending toward the critical zone. "
                            f"Identify early warning indicators and establish intervention triggers.",
                    "parameter": pr["name"],
                    "kpi": "multiple",
                    "weighted_gap": 0,
                })
                 # AI-Generated Project Suggestions (Prescriptions)
    ai_prescriptions = []
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key and prescriptions:
        try:
            client = OpenAI(api_key=openai_key)
            top_gaps = [p for p in prescriptions if p["tier"] == "HIGH IMPACT"][:3]
            if not top_gaps:
                top_gaps = prescriptions[:3]

            for gap in top_gaps:
                prompt = (
                    f"You are a senior management consultant specializing in process improvement. "
                    f"A client is running a process called '{process_name}'. "
                    f"The performance model identified that the KPI '{gap['kpi']}' in the parameter "
                    f"'{gap['parameter']}' has the largest performance gap. "
                    f"Suggest 2 concrete improvement projects that a leadership team would fund. "
                    f"Each project should be specific, actionable, and name what will be done "
                    f"(not abstract like 'improve this KPI'). "
                    f"Format: one project per line, starting with a dash. Keep each under 40 words."
                )
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=200,
                    temperature=0.7,
                )
                ai_text = response.choices[0].message.content.strip()
                ai_prescriptions.append({
                    "parameter": gap["parameter"],
                    "kpi": gap["kpi"],
                    "projects": ai_text,
                })
        except Exception:
            pass
    return {
        "npi_score": npi_score,
        "zone": zone,
        "red_floor": red_floor,
        "green_target": green_target,
        "parameter_results": parameter_results,
        "alpha_alerts": alpha_alerts,
        "prescriptions": prescriptions,
        "ai_prescriptions": ai_prescriptions,
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
