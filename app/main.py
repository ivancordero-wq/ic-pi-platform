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
# ---------------------------------------------------------------------------
# Create database tables on startup (dev convenience; use Alembic for prod)
# ---------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)
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
app.include_router(rho_gate_router)

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
    
