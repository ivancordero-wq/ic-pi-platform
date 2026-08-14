"""
IC-pi Platform: FastAPI Application Entry Point
================================================
Mounts all routers, serves static files and templates.

Routers:
- /auth/*          → Login, magic-link, session management (Screen 1)
- /clients/*       → Client CRUD
- /discoveries/*   → Discovery exercise management
- /engine/*        → NPI computation engine
- /blueprint/*     → PDF Blueprint generation

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

# ---------------------------------------------------------------------------
# Create database tables on startup (dev convenience; use Alembic for prod)
# ---------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# Application Instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="IC-pi Platform",
    description="IC Performance Index: Discovery Engine & Blueprint Generator",
    version="2.0.0",
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static Files (CSS, images, JS)
# ---------------------------------------------------------------------------
# Create static directory if it doesn't exist
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
# Screen 1: Auth (login page served at root "/")
app.include_router(auth_router, tags=["Auth"])

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
    return {"status": "healthy", "service": "ic-pi-platform", "version": "2.0.0"}
