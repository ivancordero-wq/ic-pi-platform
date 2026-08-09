"""
IC-pi Platform: Engine Execution Routes
Runs the IC-pi engine for a discovery and stores results.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
import json

from app.database import get_db
from app import models
from engine.schemas import ProcessInput, SMEVote, KPIWeight, KPIScore
from engine.pipeline import run_discovery_engine

router = APIRouter()


@router.post("/run/{discovery_id}")
def run_engine(discovery_id: UUID, measurement_label: str = "discovery", db: Session = Depends(get_db)):
    """
    Run the IC-pi engine for a discovery.
    Pulls all data from the database, executes the pipeline, stores results.
    """
    discovery = db.query(models.Discovery).filter(models.Discovery.id == discovery_id).first()
    if not discovery:
        raise HTTPException(404, "Discovery not found")

    client = db.query(models.Client).filter(models.Client.id == discovery.client_id).first()

    db_processes = db.query(models.Process).filter(models.Process.discovery_id == discovery_id).all()
    if not db_processes:
        raise HTTPException(400, "No processes found for this discovery")

    processes = []
    votes_by_round = {}
    kpi_scores_map = {}
    zone_config = {}
    critical_registry = {}
    theta_config = {}

    for proc in db_processes:
        pid = str(proc.id)

        db_params = db.query(models.Parameter).filter(models.Parameter.process_id == proc.id).all()
        param_ids = [str(p.id) for p in db_params]
        critical_params = [str(p.id) for p in db_params if p.is_critical]

        all_kpi_weights = []
        for param in db_params:
            db_kpis = db.query(models.KPI).filter(models.KPI.parameter_id == param.id).all()
            for kpi in db_kpis:
                db_weights = db.query(models.KPIWeight).filter(models.KPIWeight.kpi_id == kpi.id).all()
                for w in db_weights:
                    all_kpi_weights.append(KPIWeight(
                        sme_id=str(w.sme_id),
                        parameter_id=str(param.id),
                        kpi_id=str(kpi.id),
                        weight=w.weight,
                    ))

                db_score = db.query(models.KPIScore).filter(
                    models.KPIScore.kpi_id == kpi.id,
                    models.KPIScore.measurement_label == measurement_label,
                ).first()
                if db_score:
                    if pid not in kpi_scores_map:
                        kpi_scores_map[pid] = {}
                    kpi_scores_map[pid][str(kpi.id)] = db_score.score

        process_votes_by_round = []
        max_round = db.query(models.SMEVote).filter(
            models.SMEVote.parameter_id.in_([p.id for p in db_params])
        ).with_entities(models.SMEVote.round_number).distinct().all()

        for (round_num,) in sorted(max_round):
            round_votes = []
            db_votes = db.query(models.SMEVote).filter(
                models.SMEVote.parameter_id.in_([p.id for p in db_params]),
                models.SMEVote.round_number == round_num,
            ).all()
            for v in db_votes:
                round_votes.append(SMEVote(
                    sme_id=str(v.sme_id),
                    parameter_id=str(v.parameter_id),
                    relevant=v.relevant,
                    round_number=v.round_number,
                ))
            process_votes_by_round.append(round_votes)

        votes_by_round[pid] = process_votes_by_round

        processes.append(ProcessInput(
            process_id=pid,
            process_name=proc.name,
            parameters=param_ids,
            parameter_names={str(p.id): p.name for p in db_params},
            critical_parameters=critical_params,
            kpi_weights=all_kpi_weights,
            kpi_scores=[],
        ))

        zone_config[pid] = {
            "green_target": proc.green_target,
            "red_floor": proc.red_floor,
        }

        critical_registry[pid] = {str(p.id): p.is_critical for p in db_params}

        theta_config[pid] = {
            str(p.id): {
                "red_floor": p.theta_red_floor,
                "green_target": p.theta_green_target,
                "band_width": p.theta_band_width,
            }
            for p in db_params
        }

    result = run_discovery_engine(
        discovery_id=str(discovery_id),
        client_name=client.name,
        processes=processes,
        votes_by_round=votes_by_round,
        kpi_scores=kpi_scores_map,
        zone_config=zone_config,
        critical_registry=critical_registry,
        theta_config=theta_config,
    )

    engine_result = models.EngineResult(
        discovery_id=discovery_id,
        measurement_label=measurement_label,
        overall_zone=result.overall_zone,
        trust_gate_passed=result.trust_gate_passed,
        result_json=result.model_dump_json(),
    )
    db.add(engine_result)
    db.commit()

    discovery.status = "completed"
    discovery.completed_at = datetime.utcnow()
    db.commit()

    return {
        "discovery_id": str(discovery_id),
        "overall_zone": result.overall_zone,
        "trust_gate_passed": result.trust_gate_passed,
        "processes": [
            {
                "name": p.process_name,
                "npi_score": p.npi_score,
                "zone": p.zone,
                "alpha_triggered": p.alpha_triggered,
                "tau_converged": p.tau_converged,
                "trip_wires": len([x for x in p.parameters if x.trip_wire_flag]),
                "prescriptions": p.prescriptions,
            }
            for p in result.processes
        ],
    }
