"""
Screen 2: Consultant Dashboard
================================
Pulls real discoveries from the database.
Shows project cards with live status, zone, and step progress.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import SessionLocal
from app.models import Discovery, Process, Client, EngineResult, ParameterWeight
try:
    from app.models import SME
except ImportError:
    SME = None
from app.auth import decode_access_token

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def compute_forms_completed(discovery, db):
    """Determine how many of the 7 steps are complete based on discovery status."""
    status = discovery.status or "draft"
    status_map = {
        "draft": 0,
        "setup_complete": 1,
        "rho_complete": 2,
        "theta_complete": 3,
        "kpi_weighted": 4,
        "tau_complete": 5,
        "scored": 6,
        "engine_complete": 7,
    }
    # Direct match
    if status in status_map:
        return status_map[status]

    # Fallback: check what data exists
    process = db.query(Process).filter(Process.discovery_id == discovery.id).first()
    if not process:
        return 0

    # Check if engine ran
    engine = db.query(EngineResult).filter(EngineResult.discovery_id == discovery.id).first()
    if engine:
        return 7

    # Check if parameter weights exist (theta complete)
    weights = db.query(ParameterWeight).filter(ParameterWeight.process_id == process.id).first()
    if weights:
        return 3

    return 1  # At least setup done if process exists


def get_zone(discovery_id, db):
    """Get the zone from the latest engine result."""
    engine = db.query(EngineResult).filter(
        EngineResult.discovery_id == discovery_id
    ).order_by(EngineResult.generated_at.desc()).first()
    if engine:
        return engine.overall_zone or "TBD"
    return "TBD"


@router.get("/dashboard", response_class=HTMLResponse)
async def consultant_dashboard(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/", status_code=303)

    user_data = decode_access_token(token)
    if not user_data:
        return RedirectResponse(url="/", status_code=303)

    db = SessionLocal()
    try:
        # Pull all discoveries with their clients and processes
        discoveries = db.query(Discovery).all()
        projects = []

        for disc in discoveries:
            client = db.query(Client).filter(Client.id == disc.client_id).first()
            process = db.query(Process).filter(Process.discovery_id == disc.id).first()
            sme_count = db.query(SME).filter(SME.discovery_id == disc.id).count() if SME else 0

            forms_completed = compute_forms_completed(disc, db)
            zone = get_zone(disc.id, db)

            # Determine stage
            if forms_completed >= 7:
                stage = "Complete"
            elif forms_completed > 0:
                stage = "Active"
            else:
                stage = "Prospect"

            # Tau status
            tau_status = "Not Set"
            if forms_completed >= 5:
                tau_status = "Active"
            elif forms_completed >= 4:
                tau_status = "Pending"

            projects.append({
                "id": str(disc.id),
                "discovery_id": str(disc.id),
                "client": client.name if client else "Unknown",
                "process": process.name if process else "No process",
                "stage": stage,
                "zone": zone,
                "forms_completed": forms_completed,
                "sme_count": sme_count,
                "start_date": disc.created_at.strftime("%Y-%m-%d") if disc.created_at else None,
                "tau_status": tau_status,
            })

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "consultant_name": getattr(user_data, "full_name", None) or getattr(user_data, "sub", "Consultant"),
                "projects": projects,
                "active_filter": "All",
            },
        )
    finally:
        db.close()
