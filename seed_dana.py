import os
import uuid
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
db = Session()

import sys
sys.path.insert(0, '.')
from app.models import (
    Client, Discovery, Process, Parameter, KPI, SME,
    SMEVote, KPIWeight, KPIScore, Base
)

Base.metadata.create_all(bind=engine)

print("Seeding DANA Case Study data...")

client = Client(
    id=uuid.uuid4(),
    name="Seguros Levante S.A.",
    industry="Insurance",
    country="Spain",
    contact_name="COO Seguros Levante",
    contact_email="coo@seguroslevante.es",
)
db.add(client)
db.flush()
print(f"  Client: {client.name} ({client.id})")

discovery = Discovery(
    id=uuid.uuid4(),
    client_id=client.id,
    name="DANA Catastrophe: Claims Management Assessment",
    status="in_progress",
)
db.add(discovery)
db.flush()
print(f"  Discovery: {discovery.name} ({discovery.id})")

process = Process(
    id=uuid.uuid4(),
    discovery_id=discovery.id,
    name="Gestion de Siniestros (Claims Management)",
    description="End-to-end claims handling from FNOL to settlement",
    green_target=0.75,
    red_floor=0.25,
)
db.add(process)
db.flush()
print(f"  Process: {process.name} ({process.id})")

param_data = [
    ("Catastrophic Event Protocol", True, "ai", 0.10, 0.80, 0.20),
    ("Claims Cycle Time Management", False, "ai", 0.25, 0.80, 0.25),
    ("Fraud Detection & Prevention", False, "ai", 0.20, 0.80, 0.25),
    ("Resource Scalability", False, "sme", 0.15, 0.75, 0.30),
    ("Customer Communication", False, "ai", 0.30, 0.80, 0.20),
    ("Vendor/Contractor Network", False, "sme", 0.30, 0.80, 0.20),
]

params = []
for name, critical, source, rf, gt, bw in param_data:
    p = Parameter(
        id=uuid.uuid4(),
        process_id=process.id,
        name=name,
        is_critical=critical,
        source=source,
        theta_red_floor=rf,
        theta_green_target=gt,
        theta_band_width=bw,
    )
    db.add(p)
    db.flush()
    params.append(p)
    print(f"  Parameter: {p.name} ({p.id})")

kpi_data = [
    (params[0], "Documented protocol exists", "binary", 0.00),
    (params[0], "Protocol tested in drill", "binary", 0.00),
    (params[1], "Claims resolved within SLA", "%", 0.35),
    (params[1], "Avg days to first contact", "days", 0.40),
    (params[2], "Fraud detection rate", "%", 0.25),
    (params[2], "False positive rate inverse", "%", 0.60),
    (params[3], "Surge capacity ratio", "ratio", 0.30),
    (params[3], "Temp staffing activation time", "days", 0.20),
    (params[4], "Client satisfaction during event", "score", 0.45),
    (params[4], "Proactive update frequency", "score", 0.50),
    (params[5], "Contractor response time", "days", 0.35),
    (params[5], "Network coverage ratio", "%", 0.55),
]

kpis = []
for param, name, unit, score_val in kpi_data:
    kpi = KPI(
        id=uuid.uuid4(),
        parameter_id=param.id,
        name=name,
        unit=unit,
    )
    db.add(kpi)
    db.flush()
    kpis.append((kpi, score_val))
    print(f"  KPI: {kpi.name} ({kpi.id})")

sme_data = [
    ("Maria Lopez", "maria.lopez@seguroslevante.es", "Claims Director", "Operations"),
    ("Carlos Ruiz", "carlos.ruiz@seguroslevante.es", "Operations Manager", "Operations"),
    ("Ana Martinez", "ana.martinez@seguroslevante.es", "Fraud Analyst Lead", "Risk"),
    ("Javier Sanchez", "javier.sanchez@seguroslevante.es", "IT Systems Lead", "Technology"),
    ("Laura Garcia", "laura.garcia@seguroslevante.es", "CX Manager", "Customer Experience"),
]

smes = []
for name, email, role, dept in sme_data:
    sme = SME(
        id=uuid.uuid4(),
        discovery_id=discovery.id,
        name=name,
        email=email,
        role=role,
        department=dept,
    )
    db.add(sme)
    db.flush()
    smes.append(sme)
    print(f"  SME: {sme.name} ({sme.id})")

vote_matrix = [
    [True, True, True, True, True],
    [True, True, True, True, True],
    [True, True, True, True, False],
    [True, True, False, True, True],
    [True, True, True, False, True],
    [True, False, None, True, True],
]

for p_idx, votes in enumerate(vote_matrix):
    for s_idx, relevant in enumerate(votes):
        vote = SMEVote(
            id=uuid.uuid4(),
            sme_id=smes[s_idx].id,
            parameter_id=params[p_idx].id,
            round_number=1,
            relevant=relevant,
        )
        db.add(vote)

print("  Votes: 30 submitted")

weight_values = [9.0, 8.0, 8.0, 7.0, 9.0, 6.0, 7.0, 7.0, 6.0, 5.0, 5.0, 5.0]

for sme in smes:
    for k_idx, (kpi, _) in enumerate(kpis):
        w = KPIWeight(
            id=uuid.uuid4(),
            sme_id=sme.id,
            kpi_id=kpi.id,
            weight=weight_values[k_idx],
        )
        db.add(w)

print("  Weights: 60 submitted")

for kpi, score_val in kpis:
    score = KPIScore(
        id=uuid.uuid4(),
        kpi_id=kpi.id,
        score=score_val,
        measurement_label="discovery",
        evidence_note="Post-DANA measurement",
    )
    db.add(score)

print("  Scores: 12 submitted")

db.commit()
print("")
print("  DONE. All data committed.")
print(f"  Discovery ID: {discovery.id}")
print(f"  Run engine: POST /engine/run/{discovery.id}")
print(f"  Blueprint: GET /blueprint/{discovery.id}/executive-summary")

db.close()
