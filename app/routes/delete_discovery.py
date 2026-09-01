"""
Delete Discovery Route
=======================
Allows consultant to delete a discovery and all its related data.
Cascading delete: removes process, parameters, KPIs, scores,
weights, votes, rankings, tau designations, engine results, SMEs.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from app.database import SessionLocal
from app.models import (
    Discovery, Process, Parameter, KPI, KPIScore,
    ParameterWeight, KPIWeightLocked, TauDesignation,
    SME, SMEVote, ParameterRanking, KPIRanking, KPIWeight,
    ThetaGate, ThetaGateL2, EngineResult
)
from app.auth import decode_access_token

router = APIRouter()


def require_auth(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return decode_access_token(token)
    except Exception:
        return None


@router.post("/discovery/{discovery_id}/delete")
async def delete_discovery(request: Request, discovery_id: str):
    user = require_auth(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    db = SessionLocal()
    try:
        discovery = db.query(Discovery).filter(Discovery.id == discovery_id).first()
        if not discovery:
            return JSONResponse({"error": "Discovery not found"}, status_code=404)

        process = db.query(Process).filter(Process.discovery_id == discovery_id).first()

        if process:
            # Get all parameters
            parameters = db.query(Parameter).filter(Parameter.process_id == process.id).all()
            param_ids = [p.id for p in parameters]

            # Get all KPIs
            kpis = db.query(KPI).filter(KPI.parameter_id.in_(param_ids)).all() if param_ids else []
            kpi_ids = [k.id for k in kpis]

            # Delete KPI-level data
            if kpi_ids:
                db.query(KPIScore).filter(KPIScore.kpi_id.in_(kpi_ids)).delete(synchronize_session=False)
                db.query(KPIWeightLocked).filter(KPIWeightLocked.kpi_id.in_(kpi_ids)).delete(synchronize_session=False)
                db.query(KPIWeight).filter(KPIWeight.kpi_id.in_(kpi_ids)).delete(synchronize_session=False)
                db.query(KPIRanking).filter(KPIRanking.kpi_id.in_(kpi_ids)).delete(synchronize_session=False)
                db.query(TauDesignation).filter(TauDesignation.kpi_id.in_(kpi_ids)).delete(synchronize_session=False)

            # Delete KPIs
            if param_ids:
                db.query(KPI).filter(KPI.parameter_id.in_(param_ids)).delete(synchronize_session=False)

            # Delete parameter-level data
            if param_ids:
                db.query(ParameterWeight).filter(ParameterWeight.parameter_id.in_(param_ids)).delete(synchronize_session=False)
                db.query(ParameterRanking).filter(ParameterRanking.parameter_id.in_(param_ids)).delete(synchronize_session=False)
                db.query(ThetaGateL2).filter(ThetaGateL2.parameter_id.in_(param_ids)).delete(synchronize_session=False)
                db.query(SMEVote).filter(SMEVote.parameter_id.in_(param_ids)).delete(synchronize_session=False)

            # Delete parameters
            db.query(Parameter).filter(Parameter.process_id == process.id).delete(synchronize_session=False)

            # Delete theta gate
            db.query(ThetaGate).filter(ThetaGate.process_id == process.id).delete(synchronize_session=False)

            # Delete process
            db.query(Process).filter(Process.id == process.id).delete(synchronize_session=False)

        # Delete SMEs
        db.query(SME).filter(SME.discovery_id == discovery_id).delete(synchronize_session=False)

        # Delete engine results
        db.query(EngineResult).filter(EngineResult.discovery_id == discovery_id).delete(synchronize_session=False)

        # Delete discovery
        db.query(Discovery).filter(Discovery.id == discovery_id).delete(synchronize_session=False)

        db.commit()

        return RedirectResponse(url="/dashboard", status_code=303)

    except Exception as e:
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        db.close()
