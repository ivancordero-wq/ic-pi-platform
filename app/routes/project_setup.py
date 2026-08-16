from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import decode_access_token

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Industry dropdown options (30 industries matching iccommerce.us)
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

# Value-at-Stake bands (maps to pricing factor V)
VALUE_BANDS = [
    {"label": "< $5M", "factor": 1.0},
    {"label": "$5M - $50M", "factor": 1.3},
    {"label": "$50M - $200M", "factor": 1.6},
    {"label": "$200M+", "factor": 2.0},
]


@router.get("/project/new", response_class=HTMLResponse)
async def project_setup_form(request: Request):
    # Auth guard
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
            "value_bands": VALUE_BANDS,
            "consultant_name": "Maria Rodriguez",
        },
    )
