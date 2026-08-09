"""
IC-pi Platform: Blueprint PDF Generation Routes
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from uuid import UUID
from io import BytesIO
from datetime import datetime

from weasyprint import HTML
from jinja2 import Environment, FileSystemLoader

from app.database import get_db
from app import models
from engine.schemas import EngineOutput

router = APIRouter()

templates = Environment(
    loader=FileSystemLoader("app/templates/blueprint"),
    autoescape=True,
)


def _build_template_context(engine_output: EngineOutput, client_name: str, discovery_name: str) -> dict:
    processes_data = []
    for proc in engine_output.processes:
        sorted_params = sorted(proc.parameters, key=lambda p: p.contribution)
        processes_data.append({
            "name": proc.process_name,
            "npi_score": proc.npi_score,
            "npi_percent": round(proc.npi_score * 100, 1),
            "zone": proc.zone,
            "zone_color": {"RED": "#DC2626", "YELLOW": "#F59E0B", "GREEN": "#10B981"}[proc.zone],
            "alpha_triggered": proc.alpha_triggered,
            "tau_converged": proc.tau_converged,
            "tau_rounds": proc.tau_rounds,
            "parameters": [
                {
                    "name": p.parameter_name,
                    "weight": round(p.W_i * 100, 1),
                    "kpi_score": round(p.kpi_composite * 100, 1),
                    "contribution": round(p.contribution * 100, 2),
                    "trip_wire": p.trip_wire_flag,
                    "kill_switch": p.kill_switch_active,
                }
                for p in sorted_params
            ],
            "prescriptions": proc.prescriptions,
            "trip_wire_count": sum(1 for p in proc.parameters if p.trip_wire_flag),
            "kill_switch_count": sum(1 for p in proc.parameters if p.kill_switch_active),
        })

    zone_counts = {"RED": 0, "YELLOW": 0, "GREEN": 0}
    for proc in engine_output.processes:
        zone_counts[proc.zone] += 1

    return {
        "client_name": client_name,
        "discovery_name": discovery_name,
        "generated_at": datetime.utcnow().strftime("%B %d, %Y"),
        "overall_zone": engine_output.overall_zone,
        "overall_zone_color": {"RED": "#DC2626", "YELLOW": "#F59E0B", "GREEN": "#10B981"}[engine_output.overall_zone],
        "trust_gate_passed": engine_output.rho_gate_passed,
        "process_count": len(engine_output.processes),
        "zone_counts": zone_counts,
        "processes": processes_data,
    }


@router.get("/{discovery_id}/executive-summary")
def generate_executive_summary(discovery_id: UUID, db: Session = Depends(get_db)):
    engine_result = db.query(models.EngineResult).filter(
        models.EngineResult.discovery_id == discovery_id
    ).order_by(models.EngineResult.generated_at.desc()).first()

    if not engine_result:
        raise HTTPException(404, "No engine results found. Run the engine first.")

    engine_output = EngineOutput.model_validate_json(engine_result.result_json)
    discovery = db.query(models.Discovery).filter(models.Discovery.id == discovery_id).first()
    client = db.query(models.Client).filter(models.Client.id == discovery.client_id).first()

    context = _build_template_context(engine_output, client.name, discovery.name)

    template = templates.get_template("executive_summary.html")
    html_content = template.render(**context)
    pdf_bytes = HTML(string=html_content).write_pdf()

    filename = f"IC-Pi_Blueprint_Executive_{client.name}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{discovery_id}/full")
def generate_full_blueprint(discovery_id: UUID, db: Session = Depends(get_db)):
    engine_result = db.query(models.EngineResult).filter(
        models.EngineResult.discovery_id == discovery_id
    ).order_by(models.EngineResult.generated_at.desc()).first()

    if not engine_result:
        raise HTTPException(404, "No engine results found. Run the engine first.")

    engine_output = EngineOutput.model_validate_json(engine_result.result_json)
    discovery = db.query(models.Discovery).filter(models.Discovery.id == discovery_id).first()
    client = db.query(models.Client).filter(models.Client.id == discovery.client_id).first()

    context = _build_template_context(engine_output, client.name, discovery.name)

    template = templates.get_template("full_blueprint.html")
    html_content = template.render(**context)
    pdf_bytes = HTML(string=html_content).write_pdf()

    filename = f"IC-Pi_Blueprint_Full_{client.name}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{discovery_id}/preview")
def preview_blueprint(discovery_id: UUID, db: Session = Depends(get_db)):
    engine_result = db.query(models.EngineResult).filter(
        models.EngineResult.discovery_id == discovery_id
    ).order_by(models.EngineResult.generated_at.desc()).first()

    if not engine_result:
        raise HTTPException(404, "No engine results found. Run the engine first.")

    engine_output = EngineOutput.model_validate_json(engine_result.result_json)
    discovery = db.query(models.Discovery).filter(models.Discovery.id == discovery_id).first()
    client = db.query(models.Client).filter(models.Client.id == discovery.client_id).first()

    context = _build_template_context(engine_output, client.name, discovery.name)
    return context
