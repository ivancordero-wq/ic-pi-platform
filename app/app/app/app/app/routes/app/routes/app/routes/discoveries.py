IC-pi Platform: Discovery, Process, Parameter, KPI, SME Routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

from app.database import get_db
from app import models

router = APIRouter()


# ---- Schemas ----

class DiscoveryCreate(BaseModel):
    client_id: UUID
    name: str


class ProcessCreate(BaseModel):
    discovery_id: UUID
    name: str
    description: Optional[str] = None
    green_target: float
    red_floor: float


class ParameterCreate(BaseModel):
    process_id: UUID
    name: str
    description: Optional[str] = None
    is_critical: bool = False
    source: str = "ai"
    theta_red_floor: float = 0.20
    theta_green_target: float = 0.80
    theta_band_width: float = 0.20


class KPICreate(BaseModel):
    parameter_id: UUID
    name: str
    description: Optional[str] = None
    unit: Optional[str] = None


class SMECreate(BaseModel):
    discovery_id: UUID
    name: str
    email: str
    role: Optional[str] = None
    department: Optional[str] = None


class VoteCreate(BaseModel):
    sme_id: UUID
    parameter_id: UUID
    round_number: int
    relevant: Optional[bool] = None


class WeightCreate(BaseModel):
    sme_id: UUID
    kpi_id: UUID
    weight: float


class ScoreCreate(BaseModel):
    kpi_id: UUID
    score: float
    measurement_label: str = "discovery"
    evidence_note: Optional[str] = None


# ---- Discovery Routes ----

@router.post("/")
def create_discovery(data: DiscoveryCreate, db: Session = Depends(get_db)):
    discovery = models.Discovery(**data.model_dump())
    db.add(discovery)
    db.commit()
    db.refresh(discovery)
    return {"id": str(discovery.id), "name": discovery.name, "status": discovery.status}


@router.get("/{discovery_id}")
def get_discovery(discovery_id: UUID, db: Session = Depends(get_db)):
    d = db.query(models.Discovery).filter(models.Discovery.id == discovery_id).first()
    if not d:
        raise HTTPException(404, "Discovery not found")
    return {
        "id": str(d.id),
        "client_id": str(d.client_id),
        "name": d.name,
        "status": d.status,
        "processes": [{"id": str(p.id), "name": p.name} for p in d.processes],
        "smes": [{"id": str(s.id), "name": s.name} for s in d.smes],
    }


# ---- Process Routes ----

@router.post("/processes")
def create_process(data: ProcessCreate, db: Session = Depends(get_db)):
    process = models.Process(**data.model_dump())
    db.add(process)
    db.commit()
    db.refresh(process)
    return {"id": str(process.id), "name": process.name}


# ---- Parameter Routes ----

@router.post("/parameters")
def create_parameter(data: ParameterCreate, db: Session = Depends(get_db)):
    param = models.Parameter(**data.model_dump())
    db.add(param)
    db.commit()
    db.refresh(param)
    return {"id": str(param.id), "name": param.name, "is_critical": param.is_critical}


@router.post("/parameters/batch")
def create_parameters_batch(data: list[ParameterCreate], db: Session = Depends(get_db)):
    created = []
    for item in data:
        param = models.Parameter(**item.model_dump())
        db.add(param)
        db.flush()
        created.append({"id": str(param.id), "name": param.name})
    db.commit()
    return created


# ---- KPI Routes ----

@router.post("/kpis")
def create_kpi(data: KPICreate, db: Session = Depends(get_db)):
    kpi = models.KPI(**data.model_dump())
    db.add(kpi)
    db.commit()
    db.refresh(kpi)
    return {"id": str(kpi.id), "name": kpi.name}


@router.post("/kpis/batch")
def create_kpis_batch(data: list[KPICreate], db: Session = Depends(get_db)):
    created = []
    for item in data:
        kpi = models.KPI(**item.model_dump())
        db.add(kpi)
        db.flush()
        created.append({"id": str(kpi.id), "name": kpi.name})
    db.commit()
    return created

# ---- SME Routes ----

@router.post("/smes")
def create_sme(data: SMECreate, db: Session = Depends(get_db)):
    sme = models.SME(**data.model_dump())
    db.add(sme)
    db.commit()
    db.refresh(sme)
    return {"id": str(sme.id), "name": sme.name}


@router.post("/smes/batch")
def create_smes_batch(data: list[SMECreate], db: Session = Depends(get_db)):
    created = []
    for item in data:
        sme = models.SME(**item.model_dump())
        db.add(sme)
        db.flush()
        created.append({"id": str(sme.id), "name": sme.name})
    db.commit()
    return created


# ---- Vote Routes ----

@router.post("/votes")
def submit_vote(data: VoteCreate, db: Session = Depends(get_db)):
    vote = models.SMEVote(**data.model_dump())
    db.add(vote)
    db.commit()
    db.refresh(vote)
    return {"id": str(vote.id), "submitted": True}


@router.post("/votes/batch")
def submit_votes_batch(data: list[VoteCreate], db: Session = Depends(get_db)):
    for item in data:
        vote = models.SMEVote(**item.model_dump())
        db.add(vote)
    db.commit()
    return {"submitted": len(data)}


# ---- Weight Routes ----

@router.post("/weights")
def submit_weight(data: WeightCreate, db: Session = Depends(get_db)):
    weight = models.KPIWeight(**data.model_dump())
    db.add(weight)
    db.commit()
    db.refresh(weight)
    return {"id": str(weight.id), "submitted": True}


@router.post("/weights/batch")
def submit_weights_batch(data: list[WeightCreate], db: Session = Depends(get_db)):
    for item in data:
        weight = models.KPIWeight(**item.model_dump())
        db.add(weight)
    db.commit()
    return {"submitted": len(data)}


# ---- Score Routes ----

@router.post("/scores")
def submit_score(data: ScoreCreate, db: Session = Depends(get_db)):
    score = models.KPIScore(**data.model_dump())
    db.add(score)
    db.commit()
    db.refresh(score)
    return {"id": str(score.id), "submitted": True}


@router.post("/scores/batch")
def submit_scores_batch(data: list[ScoreCreate], db: Session = Depends(get_db)):
    for item in data:
        score = models.KPIScore(**item.model_dump())
        db.add(score)
    db.commit()
    return {"submitted": len(data)}
