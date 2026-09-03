"""
SME Prior Initiatives Review
============================
Magic-link screen for capturing the client's improvement history per KPI.
Task 6: completed before Phase 2 prescriptions are generated.

Scope rule: this screen shows ONLY the locked model.
- Parameters that survived rho AND received a locked theta weight (ParameterWeight)
- KPIs that survived theta L2 and received a locked weight (KPIWeightLocked)
Anything that did not make it into the final index is never shown to the SME.
"""

import uuid

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import SessionLocal
from app.models import (
    Discovery,
    Process,
    Parameter,
    ParameterWeight,
    KPI,
    KPIWeightLocked,
    SME,
)
from app.prior_initiatives_model import PriorInitiative
from app.routes.sme_portal import decode_sme_token

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

VALID_ACTIONS = ("failed", "partial", "successful")


def get_context(token):
    payload = decode_sme_token(token)
    if not payload:
        return None

    db = SessionLocal()
    try:
        sme = db.query(SME).filter(SME.id == payload["sme_id"]).first()
        discovery = db.query(Discovery).filter(
            Discovery.id == payload["discovery_id"]
        ).first()
        if not sme or not discovery:
            return None

        process = db.query(Process).filter(
            Process.discovery_id == discovery.id
        ).first()
        if not process:
            return None

        # Locked parameter weights define the final model (theta output).
        locked_params = db.query(ParameterWeight).filter(
            ParameterWeight.process_id == process.id
        ).order_by(ParameterWeight.weight_normalized.desc()).all()

        parameter_data = []
        for locked in locked_params:
            parameter = db.query(Parameter).filter(
                Parameter.id == locked.parameter_id
            ).first()
            if not parameter:
                continue

            # Locked KPI weights define which KPIs are in the index (theta L2).
            locked_kpis = db.query(KPIWeightLocked).filter(
                KPIWeightLocked.parameter_id == parameter.id
            ).order_by(KPIWeightLocked.weight_normalized.desc()).all()

            kpi_data = []
            for locked_kpi in locked_kpis:
                kpi = db.query(KPI).filter(KPI.id == locked_kpi.kpi_id).first()
                if not kpi:
                    continue

                prior = db.query(PriorInitiative).filter(
                    PriorInitiative.kpi_id == kpi.id,
                    PriorInitiative.sme_id == sme.id,
                ).first()

                kpi_data.append({
                    "id": str(kpi.id),
                    "name": kpi.name,
                    "description": kpi.description or "",
                    "unit": kpi.unit or "",
                    "prior_action": (prior.outcome_type if prior else "") or "",
                    "prior_description": (prior.description if prior else "") or "",
                    "prior_outcome": (prior.outcome if prior else "") or "",
                    "prior_when": (prior.tried_when if prior else "") or "",
                })

            if kpi_data:
                parameter_data.append({
                    "name": parameter.name,
                    "weight": round(locked.weight_normalized * 100, 1),
                    "kpis": kpi_data,
                })

        return {
            "sme": sme,
            "discovery": discovery,
            "process": process,
            "parameters": parameter_data,
            "token": token,
        }
    finally:
        db.close()


@router.get("/sme/prior-initiatives/{token}", response_class=HTMLResponse)
async def prior_initiatives_form(request: Request, token: str):
    context = get_context(token)
    if not context:
        return templates.TemplateResponse(
            "sme_error.html",
            {"request": request, "message": "Invalid or expired link."},
        )
    return templates.TemplateResponse(
        "sme_prior_initiatives.html",
        {"request": request, **context},
    )


@router.post("/sme/prior-initiatives/{token}", response_class=HTMLResponse)
async def save_prior_initiatives(request: Request, token: str):
    context = get_context(token)
    if not context:
        return templates.TemplateResponse(
            "sme_error.html",
            {"request": request, "message": "Invalid or expired link."},
        )

    form = await request.form()
    db = SessionLocal()
    try:
        sme_id = context["sme"].id
        discovery_id = context["discovery"].id

        for parameter in context["parameters"]:
            for kpi in parameter["kpis"]:
                kpi_uuid = uuid.UUID(kpi["id"])

                action = str(form.get("action_" + kpi["id"], "none")).strip()
                description = str(form.get("description_" + kpi["id"], "")).strip()
                outcome = str(form.get("outcome_" + kpi["id"], "")).strip()
                tried_when = str(form.get("tried_when_" + kpi["id"], "")).strip()

                existing = db.query(PriorInitiative).filter(
                    PriorInitiative.kpi_id == kpi_uuid,
                    PriorInitiative.sme_id == sme_id,
                ).first()

                # "No prior action" clears any previous entry by this SME.
                if action not in VALID_ACTIONS:
                    if existing:
                        db.delete(existing)
                    continue

                # An attempt was reported. Never discard the classification,
                # even when the SME left the description blank.
                if not description:
                    description = "Attempt reported without details."

                if existing:
                    existing.outcome_type = action
                    existing.description = description
                    existing.outcome = outcome
                    existing.tried_when = tried_when
                    existing.discovery_id = discovery_id
                else:
                    db.add(PriorInitiative(
                        discovery_id=discovery_id,
                        kpi_id=kpi_uuid,
                        sme_id=sme_id,
                        outcome_type=action,
                        description=description,
                        outcome=outcome,
                        tried_when=tried_when,
                    ))

        db.commit()
        return templates.TemplateResponse(
            "sme_complete.html",
            {
                "request": request,
                "sme_name": context["sme"].name,
                "message": "Your prior initiative history has been recorded. Thank you.",
            },
        )
    except Exception:
        db.rollback()
        return templates.TemplateResponse(
            "sme_error.html",
            {"request": request, "message": "An error occurred. Please try again."},
        )
    finally:
        db.close()
