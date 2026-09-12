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
import json
from app import models
from engine.schemas import EngineOutput, ProcessResult, ParameterScore

router = APIRouter()

templates = Environment(
    loader=FileSystemLoader("app/templates/blueprint"),
    autoescape=True,
)

def _adapt_engine_result(engine_result, discovery, client) -> EngineOutput:
    """Map the flat engine_run result dict onto the Blueprint EngineOutput schema."""
    raw = json.loads(engine_result.result_json)

    params = []
    for idx, p in enumerate(raw.get("parameter_results", [])):
        alpha = float(p.get("alpha", 1))
        params.append(ParameterScore(
            parameter_id=str(p.get("name", idx)),
            parameter_name=p.get("name", "Unnamed"),
            W_i=float(p.get("W_i", 0)) / 100.0,
            kpi_composite=float(p.get("composite_score", 0)) / 100.0,
            contribution=float(p.get("contribution", 0)) / 100.0,
            trip_wire_flag=(alpha == 0),
            kill_switch_active=(alpha == 0),
        ))

    zone = raw.get("zone", "RED")
    alerts = raw.get("alpha_alerts", [])

    proc = ProcessResult(
        process_id=str(discovery.id),
        process_name=discovery.name,
        npi_score=float(raw.get("npi_score", 0)) / 100.0,
        zone=zone,
        alpha_triggered=len(alerts) > 0,
        tau_converged=raw.get("tau_converged", False),
        tau_rounds=int(raw.get("tau_rounds", 0)),
        parameters=params,
        trip_wire_flags=[str(a) for a in alerts],
        prescriptions=raw.get("prescriptions", []),
    )

    return EngineOutput(
        discovery_id=str(discovery.id),
        client_name=client.name,
        process_count=1,
        processes=[proc],
        ai_prescriptions=raw.get("ai_prescriptions", []),
        overall_zone=zone,
        rho_gate_passed=True,
        timestamp=str(engine_result.generated_at),
    )
def _build_template_context(engine_output: EngineOutput, client_name: str, discovery_name: str) -> dict:
    processes_data = []
    for proc in engine_output.processes:
        sorted_params = sorted(proc.parameters, key=lambda p: p.contribution, reverse=True)
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
        "trust_gate_passed": not any(p.kill_switch_active for proc in engine_output.processes for p in proc.parameters),
        "process_count": len(engine_output.processes),
        "zone_counts": zone_counts,
        "processes": processes_data,
        "ai_prescriptions": engine_output.ai_prescriptions,
    }


@router.get("/{discovery_id}/executive-summary")
def generate_executive_summary(discovery_id: UUID, db: Session = Depends(get_db)):
    engine_result = db.query(models.EngineResult).filter(
        models.EngineResult.discovery_id == discovery_id
    ).order_by(models.EngineResult.generated_at.desc()).first()

    if not engine_result:
        raise HTTPException(404, "No engine results found. Run the engine first.")

    discovery = db.query(models.Discovery).filter(models.Discovery.id == discovery_id).first()
    client = db.query(models.Client).filter(models.Client.id == discovery.client_id).first()

    engine_output = _adapt_engine_result(engine_result, discovery, client)
    context = _build_template_context(engine_output, client.name, discovery.name)
    context["client_country"] = client.country or ""

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

    discovery = db.query(models.Discovery).filter(models.Discovery.id == discovery_id).first()
    client = db.query(models.Client).filter(models.Client.id == discovery.client_id).first()
    smes = db.query(models.SME).filter(models.SME.discovery_id == discovery.id).order_by(models.SME.name).all()
    sme_rows = []
    for s in smes:
        votes = db.query(models.SMEVote).filter(models.SMEVote.sme_id == s.id).all()
        sme_rows.append({
            "name": s.name,
            "role": s.role or "",
            "department": s.department or "",
            "votes_cast": len(votes),
            "relevant_marked": sum(1 for v in votes if v.relevant),
        })
    voted_params = {}
    for s in smes:
        for v in db.query(models.SMEVote).filter(models.SMEVote.sme_id == s.id).all():
            pid = str(v.parameter_id)
            voted_params[pid] = voted_params.get(pid, False) or bool(v.relevant)
    
    engine_output = _adapt_engine_result(engine_result, discovery, client)
    context = _build_template_context(engine_output, client.name, discovery.name)
    context["client_country"] = client.country or ""
    context["smes"] = sme_rows
    context["alpha_alerts"] = json.loads(engine_result.result_json).get("alpha_alerts", [])
    context["rho_total"] = len(voted_params)
    context["rho_survived"] = sum(1 for kept in voted_params.values() if kept)
    context["rho_removed"] = context["rho_total"] - context["rho_survived"]
    

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

    discovery = db.query(models.Discovery).filter(models.Discovery.id == discovery_id).first()
    client = db.query(models.Client).filter(models.Client.id == discovery.client_id).first()

    engine_output = _adapt_engine_result(engine_result, discovery, client)

    context = _build_template_context(engine_output, client.name, discovery.name)
    context["client_country"] = client.country or ""
    return context
