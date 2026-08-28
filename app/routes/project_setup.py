from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Optional

from app.auth import decode_access_token
from app.database import SessionLocal
from app.models import Client, Discovery, SME, Process, Parameter
from app.services.ai_hybrid import disambiguate_process, generate_parameters

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Industry dropdown options
INDUSTRIES = [
    "Insurance", "Banking & Financial Services", "Healthcare",
    "Higher Education", "Manufacturing", "Retail & E-Commerce",
    "Energy & Utilities", "Oil & Gas", "Mining",
    "Telecommunications", "Technology & SaaS", "Logistics & Supply Chain",
    "Construction & Real Estate", "Pharmaceuticals", "Automotive",
    "Aerospace & Defense", "Agriculture & Food", "Media & Entertainment",
    "Government & Public Sector", "Legal Services",
    "Hospitality & Tourism", "Transportation", "Consulting & Professional Services",
    "Nonprofit & NGO", "Consumer Goods (CPG)", "Chemicals",
    "Textiles & Apparel", "Environmental Services", "Sports & Recreation",
    "Other",
]

# Countries (IC-Pi markets + major economies)
COUNTRIES = [
    "Argentina", "Australia", "Bolivia", "Brazil", "Canada", "Chile",
    "Colombia", "Costa Rica", "Dominican Republic", "Ecuador",
    "El Salvador", "France", "Germany", "Guatemala", "Honduras",
    "India", "Ireland", "Italy", "Japan", "Mexico", "Nicaragua",
    "Panama", "Paraguay", "Peru", "Portugal", "Puerto Rico",
    "Spain", "United Kingdom", "United States", "Uruguay", "Venezuela",
]

# Value-at-Stake bands (maps to pricing factor V)
VALUE_BANDS = [
    {"label": "< $5M", "factor": 1.0},
    {"label": "$5M - $50M", "factor": 1.3},
    {"label": "$50M - $200M", "factor": 1.6},
    {"label": "$200M+", "factor": 2.0},
]


@router.get("/project/new", response_class=HTMLResponse)
async def project_setup_form(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/", status_code=303)
    user_data = decode_access_token(token)
    if not user_data:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        "project_setup.html",
        {
            "request": request,
            "industries": INDUSTRIES,
            "countries": COUNTRIES,
            "value_bands": VALUE_BANDS,
            "consultant_name": "Maria Rodriguez",
        },
    )


@router.post("/project/validate-process", response_class=HTMLResponse)
async def validate_process(
    request: Request,
    process_name: str = Form(...),
    industry: str = Form(...),
    attempt: int = Form(1),
):
    """
    HTMX endpoint: receives process name + industry, returns disambiguation partial.
    Called each time the consultant clicks Validate or Rephrase.
    """
    token = request.cookies.get("access_token")
    if not token:
        return HTMLResponse("<p class='text-red-400'>Session expired.</p>", status_code=401)
    user_data = decode_access_token(token)
    if not user_data:
        return HTMLResponse("<p class='text-red-400'>Session expired.</p>", status_code=401)

    result = disambiguate_process(industry, process_name)

    if not result["matches"] and result.get("message"):
        # Industry not in catalog
        return templates.TemplateResponse(
            "partials/process_validation.html",
            {
                "request": request,
                "matches": [],
                "no_catalog": True,
                "original_input": process_name,
                "attempt": attempt,
            },
        )

    return templates.TemplateResponse(
        "partials/process_validation.html",
        {
            "request": request,
            "matches": result["matches"],
            "no_catalog": False,
            "confidence": result.get("confidence", "medium"),
            "original_input": process_name,
            "attempt": attempt,
        },
    )


@router.post("/project/new")
async def create_project(
    request: Request,
    client_name: str = Form(...),
    industry: str = Form(...),
    country: str = Form(...),
    contact_name: Optional[str] = Form(None),
    contact_email: Optional[str] = Form(None),
    process_name: str = Form(...),
    confirmed_process: Optional[str] = Form(None),
    process_description: Optional[str] = Form(None),
    value_at_stake: str = Form(...),
    theta: float = Form(...),
):
    # Auth guard
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/", status_code=303)
    user_data = decode_access_token(token)
    if not user_data:
        return RedirectResponse(url="/", status_code=303)

    # Use confirmed_process if disambiguation was completed, else raw input
    final_process_name = confirmed_process if confirmed_process else process_name

    # Get SME arrays from form
    form_data = await request.form()
    sme_names = form_data.getlist("sme_name[]")
    sme_emails = form_data.getlist("sme_email[]")
    sme_roles = form_data.getlist("sme_role[]")

    db = SessionLocal()
    try:
        # Create client
        client = Client(
            name=client_name,
            industry=industry,
            country=country,
            contact_name=contact_name or None,
            contact_email=contact_email or None,
        )
        db.add(client)
        db.flush()

        # Create discovery
        discovery = Discovery(
            client_id=client.id,
            name=f"{final_process_name} - {client_name}",
            status="active",
        )
        db.add(discovery)
        db.flush()

        # Create process record
        process = Process(
            discovery_id=discovery.id,
            name=final_process_name,
            description=process_description or None,
            green_target=0.80,
            red_floor=0.20,
        )
        db.add(process)
        db.flush()

        # Generate and insert AI-Hybrid parameters
        param_list = generate_parameters(final_process_name, industry)
        for p in param_list:
            param = Parameter(
                process_id=process.id,
                name=p["name"],
                description=p.get("description", ""),
                source=p.get("source", "ai"),
            )
            db.add(param)

        # Create SMEs
        for i in range(len(sme_names)):
            if sme_names[i].strip() and sme_emails[i].strip():
                sme = SME(
                    discovery_id=discovery.id,
                    name=sme_names[i].strip(),
                    email=sme_emails[i].strip(),
                    role=sme_roles[i].strip() if i < len(sme_roles) else None,
                )
                db.add(sme)

        db.commit()

        # Redirect to Rho Gate (Screen 3B) with the new discovery
        return RedirectResponse(
            url=f"/discovery/{discovery.id}/rho-gate",
            status_code=303,
        )
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
