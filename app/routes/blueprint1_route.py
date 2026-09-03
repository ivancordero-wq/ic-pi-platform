"""
Blueprint 1 (Phase 1) Generation Route
========================================
Generates the Phase 1 Blueprint PDF: the MODEL only.
10 sections: no scores, no zones, no prescriptions.
Includes measurement formulas and data collection brief.

Scope rule: only the LOCKED model appears in the Blueprint.
- Parameters must hold a locked ParameterWeight with weight > 0
- KPIs must hold a locked KPIWeightLocked
Anything that did not make it into the final index is excluded.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from app.database import SessionLocal
from app.models import (
    Discovery, Process, Client, Parameter, KPI,
    ParameterWeight, KPIWeightLocked, TauDesignation, SME
)
from app.auth import decode_access_token
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def require_auth(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return decode_access_token(token)
    except Exception:
        return None


def gather_blueprint1_data(discovery_id: str):
    """Pull all Discovery data needed for Blueprint 1 (Phase 1: Model only)."""
    db = SessionLocal()
    try:
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        if not discovery:
            return None

        client = db.query(Client).filter(Client.id == discovery.client_id).first()
        process = db.query(Process).filter(Process.discovery_id == discovery_id).first()

        # Locked parameter weights define the final model (theta L1 output).
        # Zero-weight rows contribute nothing to the NPI and are excluded.
        param_weights = db.query(ParameterWeight).filter(
            ParameterWeight.process_id == process.id,
            ParameterWeight.weight_normalized > 0,
        ).order_by(ParameterWeight.weight_normalized.desc()).all()

        param_data = []
        for locked in param_weights:
            param = db.query(Parameter).filter(
                Parameter.id == locked.parameter_id
            ).first()
            if not param:
                continue

            w_i = locked.weight_normalized

            # Locked KPI weights define which KPIs are in the index (theta L2).
            locked_kpis = db.query(KPIWeightLocked).filter(
                KPIWeightLocked.parameter_id == param.id
            ).order_by(KPIWeightLocked.weight_normalized.desc()).all()

            kpi_list = []
            for locked_kpi in locked_kpis:
                kpi = db.query(KPI).filter(KPI.id == locked_kpi.kpi_id).first()
                if not kpi:
                    continue

                w_ij = locked_kpi.weight_normalized
                kpi_list.append({
                    "id": str(kpi.id),
                    "name": kpi.name,
                    "description": kpi.description or "",
                    "weight": round(w_ij * 100, 1) if w_ij else 0,
                    "formula": kpi.formula or "",
                    "formula_notes": kpi.formula_notes or "",
                    "unit": kpi.unit or "",
                })

            param_data.append({
                "id": str(param.id),
                "name": param.name,
                "source": param.source or "expert",
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
        sme_data = [
            {
                "name": s.name,
                "email": s.email,
                "role": s.role if hasattr(s, "role") else "SME",
            }
            for s in smes
        ]

        return {
            "discovery": discovery,
            "client_name": client.name if client else "Unknown",
            "process_name": process.name if process else "Unknown",
            "process": process,
            "parameters": param_data,
            "tau_designations": tau_data,
            "smes": sme_data,
            "generated_at": datetime.utcnow().strftime("%B %d, %Y"),
        }

    finally:
        db.close()


@router.get("/discovery/{discovery_id}/blueprint1", response_class=HTMLResponse)
async def preview_blueprint1(request: Request, discovery_id: str):
    """Preview Blueprint 1 (Phase 1) as HTML."""
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    data = gather_blueprint1_data(discovery_id)
    if not data:
        return RedirectResponse(url="/dashboard", status_code=302)

    return templates.TemplateResponse("blueprint1_pdf.html", {
        "request": request,
        **data,
    })


@router.get("/discovery/{discovery_id}/blueprint1/pdf")
async def download_blueprint1_pdf(request: Request, discovery_id: str):
    """Generate Blueprint 1 (Phase 1) as PDF via WeasyPrint."""
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    data = gather_blueprint1_data(discovery_id)
    if not data:
        return RedirectResponse(url="/dashboard", status_code=302)

    # Render HTML first
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("app/templates"))
    template = env.get_template("blueprint1_pdf.html")
    html_content = template.render(**data)

    # Convert to PDF
    from weasyprint import HTML
    pdf_bytes = HTML(string=html_content).write_pdf()

    filename = "IC-Pi_Blueprint1_" + data["client_name"].replace(" ", "_") + "_" + data["process_name"].replace(" ", "_") + ".pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=" + filename}
    )
