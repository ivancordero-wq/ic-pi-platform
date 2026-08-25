from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from app.database import SessionLocal
from app.models import SME, Discovery, Process, Parameter, KPI, SmeTauProposal
from app.auth import decode_access_token
import jwt

sme_tau_router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SME_TAU_SECRET = "sme_tau_secret_icpi2026"


def generate_tau_link(sme_id: str, discovery_id: str, base_url: str) -> str:
    """Generate a magic link for SME tau floor proposal."""
    import jwt as pyjwt
    token = pyjwt.encode(
        {"sme_id": sme_id, "discovery_id": discovery_id, "type": "sme_tau_link"},
        SME_TAU_SECRET,
        algorithm="HS256"
    )
    return f"{base_url}/sme/tau?token={token}"


@sme_tau_router.get("/sme/tau", response_class=HTMLResponse)
async def sme_tau_form(request: Request, token: str = None):
    """SME tau floor proposal form."""
    if not token:
        return templates.TemplateResponse("sme_error.html", {
            "request": request,
            "message": "No access token provided."
        })

    try:
        payload = jwt.decode(token, SME_TAU_SECRET, algorithms=["HS256"])
        if payload.get("type") != "sme_tau_link":
            raise Exception("Invalid token type")
    except Exception:
        return templates.TemplateResponse("sme_error.html", {
            "request": request,
            "message": "Invalid or expired link."
        })

    sme_id = payload["sme_id"]
    discovery_id = payload["discovery_id"]

    db = SessionLocal()
    try:
        # Get discovery and process info
        discovery = db.execute(
            select(Discovery).where(Discovery.id == discovery_id)
        ).scalar_one_or_none()

        if not discovery:
            return templates.TemplateResponse("sme_error.html", {
                "request": request,
                "message": "Discovery not found."
            })

        process = db.execute(
            select(Process).where(Process.discovery_id == discovery_id)
        ).scalar_one_or_none()

        # Get SME info
        sme = db.execute(
            select(SME).where(SME.id == sme_id)
        ).scalar_one_or_none()

        # Get critical KPIs (those with tau designations)
        from app.models import TauDesignation
        tau_designations = db.execute(
            select(TauDesignation).where(TauDesignation.process_id == process.id)
        ).scalars().all()

        # Build list of critical KPIs with their parameter names
        critical_kpis = []
        for td in tau_designations:
            kpi = db.execute(
                select(KPI).where(KPI.id == td.kpi_id)
            ).scalar_one_or_none()
            parameter = db.execute(
                select(Parameter).where(Parameter.id == kpi.parameter_id)
            ).scalar_one_or_none()
            critical_kpis.append({
                "kpi_id": kpi.id,
                "kpi_name": kpi.name,
                "parameter_name": parameter.name,
                "direction": td.direction,
            })

        # Check if this SME already submitted
        existing = db.execute(
            select(SmeTauProposal).where(
                SmeTauProposal.sme_id == sme_id,
                SmeTauProposal.discovery_id == discovery_id
            )
        ).scalars().all()

        if existing:
            return templates.TemplateResponse("sme_complete.html", {
                "request": request,
                "message": "You have already submitted your floor proposals."
            })

    finally:
        db.close()

    return templates.TemplateResponse("sme_tau_propose.html", {
        "request": request,
        "token": token,
        "sme_name": sme.name if sme else "Expert",
        "process_name": process.name if process else "",
        "client_name": discovery.client_name if hasattr(discovery, 'client_name') else "",
        "critical_kpis": critical_kpis,
    })


@sme_tau_router.post("/sme/tau/submit", response_class=HTMLResponse)
async def sme_tau_submit(request: Request):
    """Process SME tau floor proposal submission."""
    form_data = await request.form()
    token = form_data.get("token")

    if not token:
        return templates.TemplateResponse("sme_error.html", {
            "request": request,
            "message": "No access token provided."
        })

    try:
        payload = jwt.decode(token, SME_TAU_SECRET, algorithms=["HS256"])
        if payload.get("type") != "sme_tau_link":
            raise Exception("Invalid token type")
    except Exception:
        return templates.TemplateResponse("sme_error.html", {
            "request": request,
            "message": "Invalid or expired link."
        })

    sme_id = payload["sme_id"]
    discovery_id = payload["discovery_id"]

    db = SessionLocal()
    try:
        process = db.execute(
            select(Process).where(Process.discovery_id == discovery_id)
        ).scalar_one_or_none()

        # Parse form: each KPI has floor_{kpi_id}, source_{kpi_id}, justification_{kpi_id}
        from app.models import TauDesignation
        tau_designations = db.execute(
            select(TauDesignation).where(TauDesignation.process_id == process.id)
        ).scalars().all()

        for td in tau_designations:
            floor_value = form_data.get(f"floor_{td.kpi_id}")
            source_type = form_data.get(f"source_{td.kpi_id}")
            justification = form_data.get(f"justification_{td.kpi_id}")

            if floor_value:
                proposal = SmeTauProposal(
                    discovery_id=discovery_id,
                    process_id=process.id,
                    kpi_id=td.kpi_id,
                    sme_id=sme_id,
                    proposed_floor=float(floor_value),
                    source_type=source_type or "operational",
                    justification=justification
                )
                db.add(proposal)

        db.commit()
    finally:
        db.close()

    return templates.TemplateResponse("sme_complete.html", {
        "request": request,
        "message": "Your floor proposals have been submitted. Thank you!"
    })


@sme_tau_router.get("/discovery/{discovery_id}/generate-tau-links", response_class=HTMLResponse)
async def generate_tau_links(request: Request, discovery_id: str):
    """Consultant utility: generate magic links for SME tau proposals."""
    # Check consultant auth
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/")
    try:
        decode_access_token(token)
    except Exception:
        return RedirectResponse(url="/")

    db = SessionLocal()
    try:
        smes = db.execute(
            select(SME).where(SME.discovery_id == discovery_id)
        ).scalars().all()

        base_url = str(request.base_url).rstrip("/")
        links = []
        for sme in smes:
            link = generate_tau_link(sme.id, discovery_id, base_url)
            links.append({"name": sme.name, "email": sme.email, "link": link})
    finally:
        db.close()

    return templates.TemplateResponse("sme_tau_links.html", {
        "request": request,
        "links": links,
        "discovery_id": discovery_id,
    })
