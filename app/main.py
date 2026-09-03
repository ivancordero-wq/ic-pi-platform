"""
IC-pi Platform: FastAPI Application Entry Point
================================================
Mounts all routers, serves static files and templates.

Routers:
- /auth/* -> Login, magic-link, session management (Screen 1)
- /dashboard -> Consultant Dashboard (Screen 2)
- /project/* -> Project Setup + Process Validation (Screen 3A)
- /discovery/*/rho-gate -> Rho Gate (Screen 3B)
- /clients/* -> Client CRUD
- /discoveries/* -> Discovery exercise management
- /engine/* -> NPI computation engine
- /blueprint/* -> PDF Blueprint generation

Entry point for uvicorn: app.main:app
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import engine, Base
from app.routes import clients, discoveries, engine_routes, blueprint
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.project_setup import router as project_setup_router
from app.routes.rho_gate import router as rho_gate_router
from app.routes.sme_portal import router as sme_portal_router
from app.routes.theta_gate import router as theta_gate_router
from app.routes.sme_ranking import router as sme_ranking_router
from app.routes.formula_generation import router as formula_generation_router
from app.routes.data_template import router as data_template_router
from app.routes.template_upload import router as template_upload_router
from app.routes.blueprint1_route import router as blueprint1_router
from app.routes.delete_discovery import router as delete_discovery_router
from app.routes.kpi_weighting import router as kpi_weighting_router
from app.routes.sme_kpi_ranking import router as sme_kpi_ranking_router
from app.routes.tau_designation import router as tau_designation_router
from app.routes.kpi_scoring import router as kpi_scoring_router
from app.routes.engine_run import router as engine_run_router
from app.routes.sme_tau import sme_tau_router
from app.routes.admin import admin_router
from app.routes.output_engine import output_engine_router
from app.routes.prior_initiatives import router as prior_initiatives_router


# ---------------------------------------------------------------------------
# Create database tables on startup (dev convenience; use Alembic for prod)
# ---------------------------------------------------------------------------
from app.prior_initiatives_model import PriorInitiative
Base.metadata.create_all(bind=engine)
# Migration: add assigned_sme_id to tau_designations_v2 if missing
from sqlalchemy import text
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE tau_designations_v2 ADD COLUMN IF NOT EXISTS assigned_sme_id VARCHAR"))
        conn.execute(text("ALTER TABLE prior_initiatives ADD COLUMN IF NOT EXISTS outcome_type VARCHAR(20)"))
        conn.execute(text("ALTER TABLE prior_initiatives ADD COLUMN IF NOT EXISTS discovery_id UUID"))
        conn.commit()
    except Exception:
        pass
from app.seed_users import seed_default_users
seed_default_users()
# ---------------------------------------------------------------------------
# Application Instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="IC-pi Platform",
    description="IC Performance Index: Discovery Engine & Blueprint Generator",
    version="2.1.0",
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static Files (CSS, images, JS)
# ---------------------------------------------------------------------------
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router, tags=["Auth"])
app.include_router(dashboard_router)
app.include_router(project_setup_router)
app.include_router(sme_portal_router)         # Screen 4: SME Portal
app.include_router(rho_gate_router)
app.include_router(theta_gate_router)
app.include_router(sme_ranking_router)
app.include_router(formula_generation_router)
app.include_router(data_template_router)
app.include_router(template_upload_router)
app.include_router(blueprint1_router)
app.include_router(delete_discovery_router)
app.include_router(kpi_weighting_router)
app.include_router(sme_kpi_ranking_router)
app.include_router(tau_designation_router)
app.include_router(kpi_scoring_router)
app.include_router(engine_run_router)
app.include_router(sme_tau_router)
app.include_router(admin_router)
app.include_router(output_engine_router)
app.include_router(prior_initiatives_router)

# API routes
app.include_router(clients.router, prefix="/clients", tags=["Clients"])
app.include_router(discoveries.router, prefix="/discoveries", tags=["Discoveries"])
app.include_router(engine_routes.router, prefix="/engine", tags=["Engine"])
app.include_router(blueprint.router, prefix="/blueprint", tags=["Blueprint"])

# ---------------------------------------------------------------------------
# Health Check (used by Railway for deployment monitoring)
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "ic-pi-platform", "version": "2.1.0"}
    
