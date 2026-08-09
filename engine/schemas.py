"""
IC-pi Engine: Data Schemas Module
All data structures used across engine modules.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class Zone(str, Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"

    def __str__(self):
        return self.value


class Relevance(str, Enum):
    YES = "YES"
    NO = "NO"
    UNSURE = "UNSURE"


# ---- INPUT SCHEMAS (from Discovery Forms) ----

class SMEVote(BaseModel):
    sme_id: str
    parameter_id: str
    relevant: Optional[bool] = None
    round_number: int = Field(ge=1)


class KPIWeight(BaseModel):
    sme_id: str
    parameter_id: str
    kpi_id: str
    weight: float = Field(ge=0.0, le=10.0)


class KPIScore(BaseModel):
    kpi_id: str
    parameter_id: str
    score: float = Field(ge=0.0, le=1.0)


class ProcessInput(BaseModel):
    process_id: str
    process_name: str
    parameters: list[str]
    parameter_names: dict[str, str] = {}  # {param_id: human_name}
    critical_parameters: list[str] = []
    sme_votes: list[SMEVote] = []
    kpi_weights: list[KPIWeight] = []
    kpi_scores: list[KPIScore] = []


class ZoneConfig(BaseModel):
    process_id: str
    green_target: float = Field(ge=0.0, le=1.0)
    red_floor: float = Field(ge=0.0, le=1.0)

class TauConfig(BaseModel):
    """τ_ij: Trip Wire floor for a critical KPI."""
    kpi_id: str
    parameter_id: str
    tau_floor: float = Field(ge=0.0, le=1.0)
    source: str = "leadership"  # "leadership", "regulatory", "contractual"


# ---- INTERNAL SCHEMAS (between engine modules) ----

class ParameterScore(BaseModel):
    parameter_id: str
    parameter_name: str
    W_i: float
    kpi_composite: float
    contribution: float
    trip_wire_flag: bool = False
    kill_switch_active: bool = False


class RelevanceGateResult(BaseModel):
    """ρ (rho): Result of SME relevance voting pre-filter."""
    converged: bool
    rounds_used: int
    validated_params: list[str]
    contested_params: list[str]


# ---- OUTPUT SCHEMAS (to Blueprint renderer) ----

class ProcessResult(BaseModel):
    process_id: str
    process_name: str
    npi_score: float = Field(ge=0.0, le=1.0)
    zone: Zone
    alpha_triggered: bool
    tau_converged: bool
    tau_rounds: int
    parameters: list[ParameterScore]
    trip_wire_flags: list[str] = []
    prescriptions: list[str] = []


class EngineOutput(BaseModel):
    discovery_id: str
    client_name: str
    process_count: int = 0
    processes: list[ProcessResult]
    overall_zone: Zone
    rho_gate_passed: bool = False
    timestamp: str = ""
