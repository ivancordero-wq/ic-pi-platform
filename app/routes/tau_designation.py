"""
Screen 3E: Tau Designation (Trip Wire Floors)
==============================================
Consultant designates which KPIs are critical and sets minimum
acceptable floors (tau). Not iterative. No Delphi. Leadership decision.
If KPI < tau at run-time, alpha fires and parameter collapses to RED.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

from app.database import SessionLocal
from app.models import (
    Discovery, Process, Parameter, KPI,
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


@router.get("/discovery/{discovery_id}/tau-designation", response_class=HTMLResponse)
async def tau_designation_view(request: Request, discovery_id: str):
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

        # Build data structure: parameters with their KPIs and any existing tau
        param_data = []
        total_kpis = 0
        total_designated = 0

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

                # Check existing tau designation
                tau = db.query(TauDesignation).filter(
                    TauDesignation.kpi_id == kpi.id
                ).first()

                if tau:
                    total_designated += 1

                kpi_list.append({
                    "id": str(kpi.id),
                    "name": kpi.name,
                    "description": kpi.description or "",
                    "source": kpi.unit or "standard",
                    "w_ij": round(w_ij * 100, 1) if w_ij else None,
                    "has_tau": tau is not None,
                    "tau_floor": tau.tau_floor if tau else None,
                    "tau_rationale": tau.rationale if tau else None,
                    "tau_designated_by": tau.designated_by if tau else None,
                })
                total_kpis += 1

            param_data.append({
                "param_id": str(param.id),
                "param_name": param.name,
                "w_i": round(w_i * 100, 1),
                "kpis": kpi_list,
            })

        return templates.TemplateResponse("tau_designation.html", {
            "request": request,
            "discovery": discovery,
            "process": process,
            "param_data": param_data,
            "total_kpis": total_kpis,
            "total_designated": total_designated,
        })
    finally:
        db.close()


@router.post("/discovery/{discovery_id}/tau-designation", response_class=HTMLResponse)
async def save_tau_designations(request: Request, discovery_id: str):
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = SessionLocal()
    try:
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        process = db.query(Process).filter(Process.discovery_id == discovery.id).first()

        form_data = await request.form()

        # Get all KPIs for this process
        parameters = db.query(Parameter).filter(Parameter.process_id == process.id).all()

        for param in parameters:
            kpis = db.query(KPI).filter(KPI.parameter_id == param.id).all()

            for kpi in kpis:
                kpi_id = str(kpi.id)
                is_critical = form_data.get(f"critical_{kpi_id}")
                tau_value = form_data.get(f"tau_{kpi_id}")
                rationale = form_data.get(f"rationale_{kpi_id}")
                designated_by = form_data.get(f"designated_by_{kpi_id}")

                # Check existing
                existing = db.query(TauDesignation).filter(
                    TauDesignation.kpi_id == kpi_id
                ).first()

                if is_critical and tau_value:
                    try:
                        tau_float = float(tau_value)
                    except ValueError:
                        continue

                    if existing:
                        existing.tau_floor = tau_float
                        existing.rationale = rationale or None
                        existing.designated_by = designated_by or "leadership"
                        existing.designated_at = datetime.utcnow()
                    else:
                        tau = TauDesignation(
                            kpi_id=kpi_id,
                            parameter_id=str(param.id),
                            process_id=str(process.id),
                            tau_floor=tau_float,
                            rationale=rationale or None,
                            designated_by=designated_by or "leadership",
                        )
                        db.add(tau)
                else:
                    # Unchecked: remove tau if it existed
                    if existing:
                        db.delete(existing)

        discovery.status = "tau_designated"
        db.commit()

        return RedirectResponse(
            url=f"/discovery/{discovery_id}/tau-designation",
            status_code=302
        )
    finally:
        db.close()
