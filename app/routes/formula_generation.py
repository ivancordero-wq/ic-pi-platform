"""
AI Formula Generation Route
============================
POST endpoint that calls GPT-4o-mini to generate measurement
formulas for all KPIs in a Discovery. Triggered by consultant
from Screen 3D ("Generate All Formulas" button).
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from app.database import SessionLocal
from app.models import Discovery, Process, Parameter, KPI, Client
from app.auth import decode_access_token
from app.services.formula_generator import generate_formulas_for_kpis

router = APIRouter()


def require_auth(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_access_token(token)
    return payload


@router.post("/discovery/{discovery_id}/generate-formulas")
async def generate_formulas(request: Request, discovery_id: str):
    user = require_auth(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    db = SessionLocal()
    try:
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        if not discovery:
            return JSONResponse({"error": "Discovery not found"}, status_code=404)

        process = db.query(Process).filter(Process.discovery_id == discovery.id).first()
        if not process:
            return JSONResponse({"error": "Process not found"}, status_code=404)

        # Get client industry
        client = db.query(Client).filter(Client.id == discovery.client_id).first()
        industry = client.industry if client and client.industry else "General"

        # Build KPI list with parameter context
        kpi_list = []
        parameters = db.query(Parameter).filter(Parameter.process_id == process.id).all()

        for param in parameters:
            kpis = db.query(KPI).filter(KPI.parameter_id == param.id).all()
            for kpi in kpis:
                kpi_list.append({
                    "id": str(kpi.id),
                    "name": kpi.name,
                    "description": kpi.description or "",
                    "parameter_name": param.name,
                    "unit": kpi.unit or "",
                })

        if not kpi_list:
            return JSONResponse({"error": "No KPIs found"}, status_code=400)

        # Call AI formula generator
        results = generate_formulas_for_kpis(industry, process.name, kpi_list)

        if not results:
            return JSONResponse({
                "error": "Formula generation failed. Check OPENAI_API_KEY.",
                "updated": 0
            }, status_code=500)

        # Update KPIs in DB
        updated = 0
        for item in results:
            kpi = db.query(KPI).filter(KPI.id == item["kpi_id"]).first()
            if kpi:
                kpi.formula = item["formula"]
                kpi.formula_notes = item.get("formula_notes", "")
                updated += 1

        db.commit()

        return JSONResponse({
            "success": True,
            "updated": updated,
            "total_kpis": len(kpi_list),
        })

    except Exception as e:
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()
