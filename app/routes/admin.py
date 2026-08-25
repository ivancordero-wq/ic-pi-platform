"""
Admin Debug Page
================
Lists all discoveries with direct links to every screen.
Consultant-auth protected.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import SessionLocal
from app.models import Discovery, Process, Parameter, KPI, TauDesignation
from app.auth import decode_access_token

admin_router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def require_auth(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        return payload
    except Exception:
        return None


@admin_router.get("/admin/discoveries", response_class=HTMLResponse)
async def admin_discoveries(request: Request):
    """List all discoveries with direct links to every screen."""
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = SessionLocal()
    try:
        discoveries = db.query(Discovery).order_by(Discovery.created_at.desc()).all()

        discovery_list = []
        for d in discoveries:
            process = db.query(Process).filter(Process.discovery_id == d.id).first()
            
            # Count some stats
            param_count = 0
            kpi_count = 0
            tau_count = 0
            if process:
                param_count = db.query(Parameter).filter(Parameter.process_id == process.id).count()
                kpi_count = db.query(KPI).filter(KPI.parameter_id.in_(
                    db.query(Parameter.id).filter(Parameter.process_id == process.id)
                )).count()
                tau_count = db.query(TauDesignation).filter(TauDesignation.process_id == process.id).count()

            discovery_list.append({
                "id": d.id,
                "client_name": d.client_name if hasattr(d, 'client_name') else "Unknown",
                "process_name": process.name if process else "No process",
                "status": d.status if hasattr(d, 'status') else "unknown",
                "created_at": str(d.created_at)[:10] if d.created_at else "?",
                "param_count": param_count,
                "kpi_count": kpi_count,
                "tau_count": tau_count,
            })

        return templates.TemplateResponse("admin_discoveries.html", {
            "request": request,
            "discoveries": discovery_list,
        })

    finally:
        db.close()
