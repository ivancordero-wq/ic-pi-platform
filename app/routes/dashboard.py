from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from app.auth import get_current_user

router = APIRouter()

# Sample data for Screen 2 (will connect to DB later)
SAMPLE_PROJECTS = [
    {
        "id": "PRJ-001",
        "client": "Seguros Banorte",
        "process": "Claims Management",
        "stage": "Active",
        "zone": "YELLOW",
        "forms_completed": 4,
        "sme_count": 6,
        "start_date": "2026-07-15",
        "tau_status": "Not Set",
    },
    {
        "id": "PRJ-002",
        "client": "MAPFRE Panama",
        "process": "Underwriting Risk",
        "stage": "Prospect",
        "zone": "TBD",
        "forms_completed": 0,
        "sme_count": 4,
        "start_date": None,
        "tau_status": "N/A",
    },
    {
        "id": "PRJ-003",
        "client": "Bravo Ordnance",
        "process": "Supply Chain QC",
        "stage": "Complete",
        "zone": "GREEN",
        "forms_completed": 7,
        "sme_count": 3,
        "start_date": "2026-03-10",
        "tau_status": "Active",
    },
]


@router.get("/dashboard", response_class=HTMLResponse)
async def consultant_dashboard(request: Request, user: dict = Depends(get_current_user)):
    return request.app.state.templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "consultant_name": "Maria Rodriguez",
            "projects": SAMPLE_PROJECTS,
            "active_filter": "All",
        },
    )
