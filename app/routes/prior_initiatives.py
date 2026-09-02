"""
SME Prior Initiatives Review
============================
Magic-link screen for capturing the client's improvement history per KPI.
Task 6: completed before Phase 2 prescriptions are generated.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import SessionLocal
from app.models import Discovery, Process, Parameter, KPI, SME, SMEVote
from app.prior_initiatives_model import PriorInitiative
from app.routes.sme_portal import decode_sme_token

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_context(token):
    payload = decode_sme_token(token)
    if not payload:
        return None

    db = SessionLocal()
    try:
        sme = db.query(SME).filter(SME.id == payload["sme_id"]).first()
        discovery = db.query(Discovery).filter(Discovery.id == payload["discovery_id"]).first()
        if not sme or not discovery:
            return None

        process = db.query(Process).filter(Process.discovery_id == discovery.id).first()
        if not process:
            return None

        parameters = db.query(Parameter).filter(Parameter.process_id == process.id).all()
        parameter_data = []
        for parameter in parameters:
            kpis = db.query(KPI).filter(KPI.parameter_id == parameter.id).all()
            kpi_data = []
            for kpi in kpis:
                prior = db.query(PriorInitiative).filter(
                    PriorInitiative.kpi_id == kpi.id,
                    PriorInitiative.sme_id == sme.id,
                ).first()
                kpi_data.append({
                    "id": str(kpi.id),
                    "name": kpi.name,
                    "description": kpi.description or "",
                    "prior": prior,
                })
            parameter_data.append({"name": parameter.name, "kpis": kpi_data})

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
        for parameter in context["parameters"]:
            for kpi in parameter["kpis"]:
                kpi_id = kpi["id"]
                action = str(form.get("action_" + kpi_id, "none"))
                description = str(form.get("description_" + kpi_id, "")).strip()
                outcome = str(form.get("outcome_" + kpi_id, "")).strip()
                tried_when = str(form.get("tried_when_" + kpi_id, "")).strip()

                existing = db.query(PriorInitiative).filter(
                    PriorInitiative.kpi_id == kpi_id,
                    PriorInitiative.sme_id == sme_id,
                ).first()

                if action == "none":
                    if existing:
                        db.delete(existing)
                    continue

                if not description:
                    continue

                if existing:
                    existing.description = description
                    existing.outcome = outcome or action
                    existing.tried_when = tried_when
                else:
                    db.add(PriorInitiative(
                        kpi_id=kpi_id,
                        sme_id=sme_id,
                        description=description,
                        outcome=outcome or action,
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
