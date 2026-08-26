"""
Screen 6: Output Engine
========================
Blueprint generation, preview, and PDF download.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from app.database import SessionLocal
from app.models import (
    Discovery, Process, Client, Parameter, KPI,
    ParameterWeight, KPIWeightLocked, TauDesignation,
    SmeTauProposal, SME, EngineResult
)
from app.auth import decode_access_token
from datetime import datetime

output_engine_router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def require_auth(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return decode_access_token(token)
    except Exception:
        return None


def gather_blueprint_data(discovery_id: str):
    """Pull all Discovery data needed for Blueprint generation."""
    db = SessionLocal()
    try:
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        if not discovery:
            return None

        client = db.query(Client).filter(Client.id == discovery.client_id).first()
        process = db.query(Process).filter(Process.discovery_id == discovery_id).first()

        # Parameters with weights
        parameters = db.query(Parameter).filter(Parameter.process_id == process.id).all()
        param_weights = db.query(ParameterWeight).filter(ParameterWeight.process_id == process.id).all()
        weight_map = {str(pw.parameter_id): pw.weight_normalized for pw in param_weights}

        # KPIs with weights
        param_data = []
        for param in parameters:
            w_i = weight_map.get(str(param.id), 0)
            kpis = db.query(KPI).filter(KPI.parameter_id == param.id).all()

            kpi_weights = db.query(KPIWeightLocked).filter(
                KPIWeightLocked.parameter_id == param.id
            ).all()
            kpi_weight_map = {str(kw.kpi_id): kw.weight_normalized for kw in kpi_weights}

            kpi_list = []
            for kpi in kpis:
                w_ij = kpi_weight_map.get(str(kpi.id), 0)
                kpi_list.append({
                    "id": str(kpi.id),
                    "name": kpi.name,
                    "description": kpi.description if hasattr(kpi, 'description') else "",
                    "weight": round(w_ij * 100, 1) if w_ij else 0,
                })

            param_data.append({
                "id": str(param.id),
                "name": param.name,
                "source": param.source if hasattr(param, 'source') else "expert",
                "weight": round(w_i * 100, 1) if w_i else 0,
                "kpis": kpi_list,
            })

        # Tau designations
        tau_designations = db.query(TauDesignation).filter(
            TauDesignation.process_id == process.id
        ).all()
        tau_data = []
        for td in tau_designations:
            kpi = db.query(KPI).filter(KPI.id == td.kpi_id).first()
            tau_data.append({
                "kpi_name": kpi.name if kpi else "Unknown",
                "floor": td.tau_floor,
                "direction": td.direction,
                "designated_by": td.designated_by or "leadership",
            })

        # SME Panel
        smes = db.query(SME).filter(SME.discovery_id == discovery_id).all()
        sme_data = [{"name": s.name, "email": s.email, "role": s.role if hasattr(s, 'role') else "SME"} for s in smes]

        # Engine Result
        engine_result = db.query(EngineResult).filter(
            EngineResult.discovery_id == discovery_id
        ).order_by(EngineResult.created_at.desc()).first()

        engine_data = None
        if engine_result:
            import json
            engine_data = {
                "npi": engine_result.npi_score if hasattr(engine_result, 'npi_score') else None,
                "zone": engine_result.zone if hasattr(engine_result, 'zone') else None,
                "result_data": json.loads(engine_result.result_json) if hasattr(engine_result, 'result_json') and engine_result.result_json else {},
            }

        return {
            "discovery": discovery,
            "client_name": client.name if client else "Unknown",
            "process_name": process.name if process else "Unknown",
            "process": process,
            "parameters": param_data,
            "tau_designations": tau_data,
            "smes": sme_data,
            "engine": engine_data,
            "generated_at": datetime.utcnow().strftime("%B %d, %Y"),
        }

    finally:
        db.close()


@output_engine_router.get("/discovery/{discovery_id}/output", response_class=HTMLResponse)
async def output_engine_view(request: Request, discovery_id: str):
    """Output Engine control panel."""
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = SessionLocal()
    try:
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        if not discovery:
            return RedirectResponse(url="/dashboard", status_code=302)
        client = db.query(Client).filter(Client.id == discovery.client_id).first()
        process = db.query(Process).filter(Process.discovery_id == discovery_id).first()
        engine_result = db.query(EngineResult).filter(
            EngineResult.discovery_id == discovery_id
        ).order_by(EngineResult.created_at.desc()).first()
    finally:
        db.close()

    return templates.TemplateResponse("output_engine.html", {
        "request": request,
        "discovery": discovery,
        "client_name": client.name if client else "Unknown",
        "process_name": process.name if process else "Unknown",
        "has_engine_result": engine_result is not None,
        "discovery_id": discovery_id,
    })


@output_engine_router.get("/discovery/{discovery_id}/blueprint", response_class=HTMLResponse)
async def generate_blueprint(request: Request, discovery_id: str):
    """Generate and preview the full Blueprint HTML."""
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    data = gather_blueprint_data(discovery_id)
    if not data:
        return RedirectResponse(url="/dashboard", status_code=302)

    return templates.TemplateResponse("blueprint.html", {
        "request": request,
        **data,
    })


@output_engine_router.get("/discovery/{discovery_id}/blueprint/pdf")
async def download_blueprint_pdf(request: Request, discovery_id: str):
    """Generate Blueprint as PDF via WeasyPrint."""
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    data = gather_blueprint_data(discovery_id)
    if not data:
        return RedirectResponse(url="/dashboard", status_code=302)

    # Render HTML first
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("app/templates"))
    template = env.get_template("blueprint_pdf.html")
    html_content = template.render(**data)

    # Convert to PDF
    from weasyprint import HTML
    pdf_bytes = HTML(string=html_content).write_pdf()

    filename = f"IC-Pi_Blueprint_{data['client_name']}_{data['process_name']}.pdf".replace(" ", "_")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
