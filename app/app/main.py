IC-pi Platform: FastAPI Application Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routes import clients, discoveries, engine_routes, blueprint

# Create all database tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="IC-pi Platform",
    description="IC Performance Index: Discovery Engine & Blueprint Generator",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clients.router, prefix="/clients", tags=["Clients"])
app.include_router(discoveries.router, prefix="/discoveries", tags=["Discoveries"])
app.include_router(engine_routes.router, prefix="/engine", tags=["Engine"])
app.include_router(blueprint.router, prefix="/blueprint", tags=["Blueprint"])


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "ic-pi-platform"}


@app.get("/")
def root():
    return {
        "message": "IC-pi Platform v1.0",
        "docs": "/docs",
        "health": "/health",
    }
