"""
Screen 3D: KPI Mapping + Weighting + Theta Level 2
====================================================
Consultant control panel. Accordion layout: one block per parameter.
Each parameter shows its KPIs with variance, convergence, and w_ij weights.
Same Modified Delphi logic as Screen 3C, applied one level down.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import (
    Discovery, Process, Parameter, KPI, SME,
    ParameterWeight, KPIRanking, ThetaGateL2, KPIWeightLocked
)
from app.auth import decode_access_token
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# KPI catalog: 5 KPIs per generic parameter (Miller's Law)
GENERIC_KPI_CATALOG = {
    "Process Cycle Time": [
        {"name": "Average End-to-End Duration", "description": "Mean time from trigger to completion", "source": "standard"},
        {"name": "90th Percentile Duration", "description": "Time within which 90% of cases complete", "source": "standard"},
        {"name": "Wait Time Ratio", "description": "Non-value-added wait vs total cycle time", "source": "standard"},
        {"name": "Rework Loop Frequency", "description": "Percentage of cases requiring re-processing", "source": "standard"},
        {"name": "SLA Compliance Rate", "description": "Percentage completed within agreed timeframe", "source": "regulation"},
    ],
    "First-Pass Yield": [
        {"name": "Right-First-Time Rate", "description": "Percentage completed without errors on first attempt", "source": "standard"},
        {"name": "Error Detection Rate", "description": "Errors caught before output delivery", "source": "standard"},
        {"name": "Rejection Rate", "description": "Outputs rejected by downstream consumer", "source": "standard"},
        {"name": "Correction Turnaround", "description": "Time to fix identified errors", "source": "standard"},
        {"name": "Quality Audit Score", "description": "Score from periodic quality sampling", "source": "regulation"},
    ],
    "Cost per Transaction": [
        {"name": "Direct Labor Cost", "description": "Staff time cost per unit processed", "source": "standard"},
        {"name": "Technology Cost per Unit", "description": "System/license cost allocated per transaction", "source": "standard"},
        {"name": "Overhead Allocation", "description": "Indirect costs per transaction", "source": "standard"},
        {"name": "Exception Handling Cost", "description": "Additional cost for non-standard cases", "source": "standard"},
        {"name": "Cost Trend (MoM)", "description": "Month-over-month cost trajectory", "source": "ai"},
    ],
    "Error/Defect Rate": [
        {"name": "Defects per Thousand Units", "description": "Total errors per 1000 outputs", "source": "standard"},
        {"name": "Critical vs Minor Ratio", "description": "Proportion of severe vs cosmetic defects", "source": "standard"},
        {"name": "Root Cause Concentration", "description": "Top 3 root causes as % of all defects", "source": "ai"},
        {"name": "Escape Rate", "description": "Defects reaching end customer undetected", "source": "standard"},
        {"name": "Corrective Action Closure Rate", "description": "Percentage of CAPAs closed on time", "source": "regulation"},
    ],
    "Resource Utilization": [
        {"name": "Staff Utilization Rate", "description": "Productive hours vs available hours", "source": "standard"},
        {"name": "Peak Load Coverage", "description": "Capacity vs demand during peak periods", "source": "standard"},
        {"name": "Cross-Training Index", "description": "Percentage of staff qualified for multiple roles", "source": "ai"},
        {"name": "Overtime Ratio", "description": "Overtime hours as percentage of total", "source": "standard"},
        {"name": "Vacancy Impact Score", "description": "Output degradation per unfilled position", "source": "ai"},
    ],
    "Customer Satisfaction Score": [
        {"name": "Net Promoter Score (NPS)", "description": "Likelihood to recommend on -100 to +100 scale", "source": "standard"},
        {"name": "First Contact Resolution", "description": "Issues resolved in single interaction", "source": "standard"},
        {"name": "Complaint Rate", "description": "Formal complaints per 1000 interactions", "source": "standard"},
        {"name": "Response Time Satisfaction", "description": "Customer rating of speed", "source": "standard"},
        {"name": "Effort Score (CES)", "description": "Customer-perceived effort to get resolution", "source": "ai"},
    ],
    "Compliance Adherence Rate": [
        {"name": "Regulatory Audit Pass Rate", "description": "Percentage of audit items with zero findings", "source": "regulation"},
        {"name": "Policy Exception Rate", "description": "Cases processed outside approved policy", "source": "regulation"},
        {"name": "Documentation Completeness", "description": "Required records present and accurate", "source": "regulation"},
        {"name": "Training Currency Rate", "description": "Staff with up-to-date compliance training", "source": "regulation"},
        {"name": "Incident Reporting Timeliness", "description": "Regulatory incidents reported within deadline", "source": "regulation"},
    ],
    "Backlog Volume": [
        {"name": "Aging Backlog (>SLA)", "description": "Items exceeding service level threshold", "source": "standard"},
        {"name": "Inflow vs Outflow Ratio", "description": "New items arriving vs items completed daily", "source": "standard"},
        {"name": "Priority Distribution", "description": "Percentage of backlog in high/medium/low priority", "source": "standard"},
        {"name": "Backlog Growth Trend", "description": "Week-over-week backlog trajectory", "source": "ai"},
        {"name": "Oldest Item Age", "description": "Days since oldest unresolved item was created", "source": "standard"},
    ],
    "Automation Coverage": [
        {"name": "Straight-Through Processing Rate", "description": "Percentage completed without human touch", "source": "standard"},
        {"name": "Automation Candidate Ratio", "description": "Manual steps eligible for automation", "source": "ai"},
        {"name": "Bot Accuracy Rate", "description": "Automated decisions matching expert judgment", "source": "ai"},
        {"name": "Exception Escalation Rate", "description": "Automated cases requiring human override", "source": "standard"},
        {"name": "Automation ROI", "description": "Cost saved vs automation investment", "source": "ai"},
    ],
    "Escalation Rate": [
        {"name": "Escalation Frequency", "description": "Percentage of cases requiring management intervention", "source": "standard"},
        {"name": "Escalation Resolution Time", "description": "Average time to resolve escalated cases", "source": "standard"},
        {"name": "Repeat Escalation Rate", "description": "Same issue escalated more than once", "source": "standard"},
        {"name": "Escalation Root Cause Mix", "description": "Top reasons for escalation", "source": "ai"},
        {"name": "De-escalation Success Rate", "description": "Escalated cases resolved without further elevation", "source": "standard"},
    ],
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_auth(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_access_token(token)
    return payload


def compute_variance(ranks):
    if len(ranks) < 2:
        return 0.0
    mean = sum(ranks) / len(ranks)
    return sum((r - mean) ** 2 for r in ranks) / len(ranks)


def generate_kpis_for_parameter(parameter_name, db, parameter_id):
    """Generate 5 KPIs for a parameter if none exist yet."""
    existing = db.query(KPI).filter(KPI.parameter_id == parameter_id).all()
    if existing:
        return existing

    # Look up catalog
    kpi_list = GENERIC_KPI_CATALOG.get(parameter_name, None)

    if not kpi_list:
        # Generic fallback: 5 generic KPIs
        kpi_list = [
            {"name": f"{parameter_name} - Efficiency", "description": "Output per unit of input", "source": "ai"},
            {"name": f"{parameter_name} - Quality", "description": "Error-free rate", "source": "ai"},
            {"name": f"{parameter_name} - Timeliness", "description": "Completion within target", "source": "ai"},
            {"name": f"{parameter_name} - Compliance", "description": "Adherence to standards", "source": "regulation"},
            {"name": f"{parameter_name} - Trend", "description": "Period-over-period trajectory", "source": "ai"},
        ]

    created = []
    for k in kpi_list[:5]:
        kpi = KPI(
            parameter_id=parameter_id,
            name=k["name"],
            description=k.get("description", ""),
            unit=k.get("source", "standard"),
        )
        db.add(kpi)
        created.append(kpi)

    db.flush()
    return created


@router.get("/discovery/{discovery_id}/kpi-weighting", response_class=HTMLResponse)
async def kpi_weighting_view(request: Request, discovery_id: str):
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = next(get_db())
    try:
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        if not discovery:
            return RedirectResponse(url="/dashboard", status_code=302)

        process = db.query(Process).filter(Process.discovery_id == discovery.id).first()
        if not process:
            return RedirectResponse(url="/dashboard", status_code=302)

        # Get locked parameters (from theta gate L1)
        locked_params = db.query(ParameterWeight).filter(
            ParameterWeight.process_id == process.id
        ).all()

        param_ids = [lp.parameter_id for lp in locked_params]
        parameters = db.query(Parameter).filter(Parameter.id.in_(param_ids)).all()

        # Get SMEs
        smes = db.query(SME).filter(SME.discovery_id == discovery.id).all()
        total_smes = len(smes)

        # Build accordion data
        accordion_data = []
        total_kpis = 0
        total_converged_kpis = 0
        total_divergent_kpis = 0
        all_params_locked = True

        for param in parameters:
            # Get W_i for this parameter
            pw = next((lp for lp in locked_params if str(lp.parameter_id) == str(param.id)), None)
            w_i = pw.weight_normalized if pw else 0

            # Generate KPIs if not yet created
            kpis = generate_kpis_for_parameter(param.name, db, param.id)

            # Get or create theta gate L2 for this parameter
            theta_l2 = db.query(ThetaGateL2).filter(ThetaGateL2.parameter_id == param.id).first()
            if not theta_l2:
                theta_l2 = ThetaGateL2(
                    parameter_id=param.id,
                    threshold=1.5,
                    current_round=0,
                    status="pending"
                )
                db.add(theta_l2)
                db.flush()

            # Compute KPI data
            kpi_data = []
            param_converged = 0
            param_divergent = 0

            read_round = theta_l2.current_round if theta_l2.current_round > 0 else 1

            for kpi in kpis:
                # Check if locked
                locked_kpi = db.query(KPIWeightLocked).filter(
                    KPIWeightLocked.kpi_id == kpi.id
                ).first()

                if locked_kpi:
                    kpi_data.append({
                        "id": str(kpi.id),
                        "name": kpi.name,
                        "description": kpi.description or "",
                        "source": kpi.unit or "standard",
                        "avg_rank": None,
                        "variance": 0.0,
                        "converged": True,
                        "locked": True,
                        "weight": locked_kpi.weight_normalized,
                        "responses": total_smes,
                    })
                    param_converged += 1
                    continue

                # Get rankings
                rankings = db.query(KPIRanking).filter(
                    KPIRanking.kpi_id == kpi.id,
                    KPIRanking.round_number == read_round
                ).all()

                rank_values = [r.rank_position for r in rankings]
                responses = len(rank_values)

                if responses == 0:
                    kpi_data.append({
                        "id": str(kpi.id),
                        "name": kpi.name,
                        "description": kpi.description or "",
                        "source": kpi.unit or "standard",
                        "avg_rank": None,
                        "variance": None,
                        "converged": False,
                        "locked": False,
                        "weight": None,
                        "responses": 0,
                    })
                    param_divergent += 1
                    continue

                avg_rank = sum(rank_values) / len(rank_values)
                variance = compute_variance(rank_values)
                converged = variance <= theta_l2.threshold

                if converged:
                    param_converged += 1
                else:
                    param_divergent += 1

                kpi_data.append({
                    "id": str(kpi.id),
                    "name": kpi.name,
                    "description": kpi.description or "",
                    "source": kpi.unit or "standard",
                    "avg_rank": round(avg_rank, 2),
                    "variance": round(variance, 2),
                    "converged": converged,
                    "locked": False,
                    "weight": None,
                    "responses": responses,
                })

            # Normalize weights for converged KPIs
            converged_kpis = [k for k in kpi_data if k["converged"] and k["avg_rank"] is not None]
            if converged_kpis:
                inverse_sum = sum(1.0 / k["avg_rank"] for k in converged_kpis if k["avg_rank"] > 0)
                if inverse_sum > 0:
                    for k in kpi_data:
                        if k["converged"] and k["avg_rank"] and k["avg_rank"] > 0:
                            k["weight"] = round((1.0 / k["avg_rank"]) / inverse_sum, 4)

            total_kpis += len(kpi_data)
            total_converged_kpis += param_converged
            total_divergent_kpis += param_divergent

            param_all_converged = param_divergent == 0 and len(kpi_data) > 0
            if not param_all_converged and theta_l2.status != "locked":
                all_params_locked = False

            accordion_data.append({
                "param_id": str(param.id),
                "param_name": param.name,
                "w_i": round(w_i * 100, 1),
                "kpi_count": len(kpi_data),
                "converged": param_converged,
                "divergent": param_divergent,
                "all_converged": param_all_converged,
                "theta_l2": theta_l2,
                "kpis": kpi_data,
            })

        db.commit()

        return templates.TemplateResponse("kpi_weighting.html", {
            "request": request,
            "discovery": discovery,
            "process": process,
            "accordion_data": accordion_data,
            "total_params": len(parameters),
            "total_kpis": total_kpis,
            "total_converged_kpis": total_converged_kpis,
            "total_divergent_kpis": total_divergent_kpis,
            "total_smes": total_smes,
            "all_params_locked": all_params_locked,
        })
    finally:
        db.close()


@router.post("/discovery/{discovery_id}/kpi-weighting/{param_id}/trigger-round")
async def trigger_kpi_round(request: Request, discovery_id: str, param_id: str):
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = next(get_db())
    try:
        theta_l2 = db.query(ThetaGateL2).filter(ThetaGateL2.parameter_id == param_id).first()
        if not theta_l2:
            return RedirectResponse(url=f"/discovery/{discovery_id}/kpi-weighting", status_code=302)

        if theta_l2.current_round >= 3:
            return RedirectResponse(url=f"/discovery/{discovery_id}/kpi-weighting", status_code=302)

        theta_l2.current_round += 1
        theta_l2.status = "active"
        db.commit()

        return RedirectResponse(url=f"/discovery/{discovery_id}/kpi-weighting", status_code=302)
    finally:
        db.close()


@router.post("/discovery/{discovery_id}/kpi-weighting/{param_id}/lock")
async def lock_kpi_weights(request: Request, discovery_id: str, param_id: str):
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = next(get_db())
    try:
        theta_l2 = db.query(ThetaGateL2).filter(ThetaGateL2.parameter_id == param_id).first()
        if not theta_l2:
            return RedirectResponse(url=f"/discovery/{discovery_id}/kpi-weighting", status_code=302)

        kpis = db.query(KPI).filter(KPI.parameter_id == param_id).all()
        read_round = theta_l2.current_round if theta_l2.current_round > 0 else 1

        # Compute and lock weights
        kpi_ranks = {}
        for kpi in kpis:
            rankings = db.query(KPIRanking).filter(
                KPIRanking.kpi_id == kpi.id,
                KPIRanking.round_number == read_round
            ).all()
            if rankings:
                avg = sum(r.rank_position for r in rankings) / len(rankings)
                kpi_ranks[str(kpi.id)] = avg

        if kpi_ranks:
            inverse_sum = sum(1.0 / v for v in kpi_ranks.values() if v > 0)
            if inverse_sum > 0:
                for kpi_id, avg_rank in kpi_ranks.items():
                    if avg_rank > 0:
                        weight = (1.0 / avg_rank) / inverse_sum
                        existing = db.query(KPIWeightLocked).filter(
                            KPIWeightLocked.kpi_id == kpi_id
                        ).first()
                        if not existing:
                            kw = KPIWeightLocked(
                                kpi_id=kpi_id,
                                parameter_id=param_id,
                                weight_normalized=round(weight, 4),
                                locked_at=datetime.utcnow(),
                                locked_by_round=theta_l2.current_round
                            )
                            db.add(kw)

        theta_l2.status = "locked"
        theta_l2.locked_at = datetime.utcnow()
        db.commit()

        return RedirectResponse(url=f"/discovery/{discovery_id}/kpi-weighting", status_code=302)
    finally:
        db.close()


@router.post("/discovery/{discovery_id}/kpi-weighting/lock-all")
async def lock_all_kpi_weights(request: Request, discovery_id: str):
    """Lock all parameter KPI weights at once (when all have converged)."""
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = next(get_db())
    try:
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        process = db.query(Process).filter(Process.discovery_id == discovery.id).first()

        # Get all theta L2 gates
        locked_params = db.query(ParameterWeight).filter(
            ParameterWeight.process_id == process.id
        ).all()

        for lp in locked_params:
            theta_l2 = db.query(ThetaGateL2).filter(ThetaGateL2.parameter_id == lp.parameter_id).first()
            if theta_l2 and theta_l2.status != "locked":
                # Lock this parameter's KPIs
                kpis = db.query(KPI).filter(KPI.parameter_id == lp.parameter_id).all()
                read_round = theta_l2.current_round if theta_l2.current_round > 0 else 1

                kpi_ranks = {}
                for kpi in kpis:
                    rankings = db.query(KPIRanking).filter(
                        KPIRanking.kpi_id == kpi.id,
                        KPIRanking.round_number == read_round
                    ).all()
                    if rankings:
                        avg = sum(r.rank_position for r in rankings) / len(rankings)
                        kpi_ranks[str(kpi.id)] = avg

                if kpi_ranks:
                    inverse_sum = sum(1.0 / v for v in kpi_ranks.values() if v > 0)
                    if inverse_sum > 0:
                        for kpi_id, avg_rank in kpi_ranks.items():
                            if avg_rank > 0:
                                weight = (1.0 / avg_rank) / inverse_sum
                                existing = db.query(KPIWeightLocked).filter(
                                    KPIWeightLocked.kpi_id == kpi_id
                                ).first()
                                if not existing:
                                    kw = KPIWeightLocked(
                                        kpi_id=kpi_id,
                                        parameter_id=str(lp.parameter_id),
                                        weight_normalized=round(weight, 4),
                                        locked_at=datetime.utcnow(),
                                        locked_by_round=theta_l2.current_round
                                    )
                                    db.add(kw)

                theta_l2.status = "locked"
                theta_l2.locked_at = datetime.utcnow()

        discovery.status = "kpi_weights_locked"
        db.commit()

        return RedirectResponse(url=f"/discovery/{discovery_id}/kpi-weighting", status_code=302)
    finally:
        db.close()
