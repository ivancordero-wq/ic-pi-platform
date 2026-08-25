"""
IC-pi Platform: Database Models (Phase 1)
10 tables total.
"""

from sqlalchemy import (
    Column, String, Float, Boolean, Integer, DateTime,
    ForeignKey, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
import uuid


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    industry = Column(String(100))
    country = Column(String(50))
    contact_name = Column(String(150))
    contact_email = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    discoveries = relationship("Discovery", back_populates="client")


class Discovery(Base):
    __tablename__ = "discoveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    name = Column(String(300), nullable=False)
    status = Column(String(50), default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    client = relationship("Client", back_populates="discoveries")
    processes = relationship("Process", back_populates="discovery")
    smes = relationship("SME", back_populates="discovery")
    engine_results = relationship("EngineResult", back_populates="discovery")


class Process(Base):
    __tablename__ = "processes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    discovery_id = Column(UUID(as_uuid=True), ForeignKey("discoveries.id"), nullable=False)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    green_target = Column(Float, nullable=False)
    red_floor = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    discovery = relationship("Discovery", back_populates="processes")
    parameters = relationship("Parameter", back_populates="process")


class Parameter(Base):
    __tablename__ = "parameters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    process_id = Column(UUID(as_uuid=True), ForeignKey("processes.id"), nullable=False)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    is_critical = Column(Boolean, default=False)
    is_active_program = Column(Boolean, default=False)
    source = Column(String(50), default="ai")
    theta_red_floor = Column(Float, default=0.20)
    theta_green_target = Column(Float, default=0.80)
    theta_band_width = Column(Float, default=0.20)
    created_at = Column(DateTime, default=datetime.utcnow)

    process = relationship("Process", back_populates="parameters")
    kpis = relationship("KPI", back_populates="parameter")
    votes = relationship("SMEVote", back_populates="parameter")


class KPI(Base):
    __tablename__ = "kpis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parameter_id = Column(UUID(as_uuid=True), ForeignKey("parameters.id"), nullable=False)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    unit = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    parameter = relationship("Parameter", back_populates="kpis")
    weights = relationship("KPIWeight", back_populates="kpi")
    scores = relationship("KPIScore", back_populates="kpi")

class SME(Base):
    __tablename__ = "smes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    discovery_id = Column(UUID(as_uuid=True), ForeignKey("discoveries.id"), nullable=False)
    name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=False)
    role = Column(String(150), nullable=True)
    department = Column(String(150), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    discovery = relationship("Discovery", back_populates="smes")
    votes = relationship("SMEVote", back_populates="sme")
    kpi_weights = relationship("KPIWeight", back_populates="sme")


class SMEVote(Base):
    __tablename__ = "sme_votes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sme_id = Column(UUID(as_uuid=True), ForeignKey("smes.id"), nullable=False)
    parameter_id = Column(UUID(as_uuid=True), ForeignKey("parameters.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    relevant = Column(Boolean, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("sme_id", "parameter_id", "round_number", name="uq_vote_per_round"),
    )

    sme = relationship("SME", back_populates="votes")
    parameter = relationship("Parameter", back_populates="votes")


class KPIWeight(Base):
    __tablename__ = "kpi_weights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sme_id = Column(UUID(as_uuid=True), ForeignKey("smes.id"), nullable=False)
    kpi_id = Column(UUID(as_uuid=True), ForeignKey("kpis.id"), nullable=False)
    weight = Column(Float, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("sme_id", "kpi_id", name="uq_weight_per_sme_kpi"),
    )

    sme = relationship("SME", back_populates="kpi_weights")
    kpi = relationship("KPI", back_populates="weights")


class KPIScore(Base):
    __tablename__ = "kpi_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_id = Column(UUID(as_uuid=True), ForeignKey("kpis.id"), nullable=False)
    score = Column(Float, nullable=False)
    measurement_label = Column(String(50), nullable=False)
    evidence_note = Column(Text, nullable=True)
    scored_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("kpi_id", "measurement_label", name="uq_score_per_kpi_measurement"),
    )

    kpi = relationship("KPI", back_populates="scores")


class EngineResult(Base):
    __tablename__ = "engine_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    discovery_id = Column(UUID(as_uuid=True), ForeignKey("discoveries.id"), nullable=False)
    measurement_label = Column(String(50), nullable=False)
    overall_zone = Column(String(10), nullable=False)
    trust_gate_passed = Column(Boolean, nullable=False)
    result_json = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)
    version = Column(Integer, default=1)

    __table_args__ = (
        UniqueConstraint("discovery_id", "measurement_label", name="uq_result_per_measurement"),
    )

    discovery = relationship("Discovery", back_populates="engine_results")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(200), unique=True, nullable=False)
    hashed_password = Column(String(500), nullable=False)
    full_name = Column(String(200), nullable=False)
    role = Column(String(50), default="sme")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ParameterRanking(Base):
    __tablename__ = "parameter_rankings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sme_id = Column(UUID(as_uuid=True), ForeignKey("smes.id"), nullable=False)
    parameter_id = Column(UUID(as_uuid=True), ForeignKey("parameters.id"), nullable=False)
    process_id = Column(UUID(as_uuid=True), ForeignKey("processes.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    rank_position = Column(Integer, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("sme_id", "parameter_id", "round_number", name="uq_ranking_per_sme_param_round"),
    )

    sme = relationship("SME", backref="parameter_rankings")
    parameter = relationship("Parameter", backref="rankings")
    process = relationship("Process", backref="parameter_rankings")


class ThetaGate(Base):
    __tablename__ = "theta_gates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    process_id = Column(UUID(as_uuid=True), ForeignKey("processes.id"), nullable=False, unique=True)
    threshold = Column(Float, nullable=False, default=1.5)
    current_round = Column(Integer, default=0)
    status = Column(String(50), default="pending")
    locked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    process = relationship("Process", backref="theta_gate")


class ParameterWeight(Base):
    __tablename__ = "parameter_weights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parameter_id = Column(UUID(as_uuid=True), ForeignKey("parameters.id"), nullable=False, unique=True)
    process_id = Column(UUID(as_uuid=True), ForeignKey("processes.id"), nullable=False)
    weight_normalized = Column(Float, nullable=False)
    locked_at = Column(DateTime, default=datetime.utcnow)
    locked_by_round = Column(Integer, nullable=False)

    parameter = relationship("Parameter", backref="locked_weight")
    process = relationship("Process", backref="locked_weights")

class KPIRanking(Base):
    __tablename__ = "kpi_rankings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sme_id = Column(UUID(as_uuid=True), ForeignKey("smes.id"), nullable=False)
    kpi_id = Column(UUID(as_uuid=True), ForeignKey("kpis.id"), nullable=False)
    parameter_id = Column(UUID(as_uuid=True), ForeignKey("parameters.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    rank_position = Column(Integer, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("sme_id", "kpi_id", "round_number", name="uq_kpi_ranking_per_sme_kpi_round"),
    )

    sme = relationship("SME", backref="kpi_rankings")
    kpi = relationship("KPI", backref="rankings")
    parameter = relationship("Parameter", backref="kpi_rankings")


class ThetaGateL2(Base):
    __tablename__ = "theta_gates_l2"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parameter_id = Column(UUID(as_uuid=True), ForeignKey("parameters.id"), nullable=False, unique=True)
    threshold = Column(Float, nullable=False, default=1.5)
    current_round = Column(Integer, default=0)
    status = Column(String(50), default="pending")
    locked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    parameter = relationship("Parameter", backref="theta_gate_l2")


class KPIWeightLocked(Base):
    __tablename__ = "kpi_weights_locked"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_id = Column(UUID(as_uuid=True), ForeignKey("kpis.id"), nullable=False, unique=True)
    parameter_id = Column(UUID(as_uuid=True), ForeignKey("parameters.id"), nullable=False)
    weight_normalized = Column(Float, nullable=False)
    locked_at = Column(DateTime, default=datetime.utcnow)
    locked_by_round = Column(Integer, nullable=False)

    kpi = relationship("KPI", backref="locked_weight")
    parameter = relationship("Parameter", backref="locked_kpi_weights")

class TauDesignation(Base):
    __tablename__ = "tau_designations_v2"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_id = Column(UUID(as_uuid=True), ForeignKey("kpis.id"), nullable=False, unique=True)
    parameter_id = Column(UUID(as_uuid=True), ForeignKey("parameters.id"), nullable=False)
    process_id = Column(UUID(as_uuid=True), ForeignKey("processes.id"), nullable=False)
    tau_floor = Column(Float, nullable=False)
    direction = Column(String(20), default="higher_is_better")
    rationale = Column(String(500), nullable=True)
    designated_by = Column(String(100), default="leadership")
    designated_at = Column(DateTime, default=datetime.utcnow)

    kpi = relationship("KPI", backref="tau_designation_v2")
    parameter = relationship("Parameter", backref="tau_designations_v2")
    process = relationship("Process", backref="tau_designations_v2")

class KPIAnchor(Base):
    __tablename__ = "kpi_anchors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_id = Column(UUID(as_uuid=True), ForeignKey("kpis.id"), nullable=False, unique=True)
    best_value = Column(Float, nullable=False)
    worst_value = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    kpi = relationship("KPI", backref="anchor")

class SmeTauProposal(Base):
    __tablename__ = "sme_tau_proposals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    discovery_id = Column(String, nullable=False)
    process_id = Column(String, nullable=False)
    kpi_id = Column(String, nullable=False)
    sme_id = Column(String, nullable=False)
    proposed_floor = Column(Float, nullable=False)
    source_type = Column(String, nullable=False)  # "regulatory", "contractual", "operational"
    justification = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
