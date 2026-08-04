"""
IC-pi Integration Test: DANA Case Study
Run: python tests/test_dana_case.py
"""

import sys
sys.path.insert(0, '.')

from engine.schemas import ProcessInput, SMEVote, KPIWeight
from engine.pipeline import run_discovery_engine


DISCOVERY_ID = "disc_seguros_levante_2024"
CLIENT_NAME = "Seguros Levante S.A."
SMES = ["sme_1", "sme_2", "sme_3", "sme_4", "sme_5"]
PARAMS = ["param_1", "param_2", "param_3", "param_4", "param_5", "param_6"]


def build_votes():
    round_1 = []
    vote_matrix = {
        "param_1": {"sme_1": True, "sme_2": True, "sme_3": True, "sme_4": True, "sme_5": True},
        "param_2": {"sme_1": True, "sme_2": True, "sme_3": True, "sme_4": True, "sme_5": True},
        "param_3": {"sme_1": True, "sme_2": True, "sme_3": True, "sme_4": True, "sme_5": False},
        "param_4": {"sme_1": True, "sme_2": True, "sme_3": False, "sme_4": True, "sme_5": True},
        "param_5": {"sme_1": True, "sme_2": True, "sme_3": True, "sme_4": False, "sme_5": True},
        "param_6": {"sme_1": True, "sme_2": False, "sme_3": None, "sme_4": True, "sme_5": True},
    }
    for param_id, sme_votes in vote_matrix.items():
        for sme_id, relevant in sme_votes.items():
            round_1.append(SMEVote(
                sme_id=sme_id,
                parameter_id=param_id,
                relevant=relevant,
                round_number=1,
            ))
    return [round_1]


def build_kpi_weights():
    weight_map = {
        ("kpi_1a", "param_1"): 9.0,
        ("kpi_1b", "param_1"): 8.0,
        ("kpi_2a", "param_2"): 8.0,
        ("kpi_2b", "param_2"): 7.0,
        ("kpi_3a", "param_3"): 9.0,
        ("kpi_3b", "param_3"): 6.0,
        ("kpi_4a", "param_4"): 7.0,
        ("kpi_4b", "param_4"): 7.0,
        ("kpi_5a", "param_5"): 6.0,
        ("kpi_5b", "param_5"): 5.0,
        ("kpi_6a", "param_6"): 5.0,
        ("kpi_6b", "param_6"): 5.0,
    }
    weights = []
    for sme_id in SMES:
        for (kpi_id, param_id), weight in weight_map.items():
            weights.append(KPIWeight(
                sme_id=sme_id, parameter_id=param_id,
                kpi_id=kpi_id, weight=weight,
            ))
    return weights


KPI_SCORES_MAP = {
    "kpi_1a": 0.00, "kpi_1b": 0.00,
    "kpi_2a": 0.35, "kpi_2b": 0.40,
    "kpi_3a": 0.25, "kpi_3b": 0.60,
    "kpi_4a": 0.30, "kpi_4b": 0.20,
    "kpi_5a": 0.45, "kpi_5b": 0.50,
    "kpi_6a": 0.35, "kpi_6b": 0.55,
}

ZONE_CONFIG = {"proc_claims_mgmt": {"green_target": 0.75, "red_floor": 0.25}}

CRITICAL_REGISTRY = {
    "proc_claims_mgmt": {
        "param_1": True, "param_2": False, "param_3": False,
        "param_4": False, "param_5": False, "param_6": False,
    }
}

THETA_CONFIG = {
    "proc_claims_mgmt": {
        "param_1": {"red_floor": 0.10, "green_target": 0.80, "band_width": 0.20},
        "param_2": {"red_floor": 0.25, "green_target": 0.80, "band_width": 0.25},
        "param_3": {"red_floor": 0.20, "green_target": 0.80, "band_width": 0.25},
        "param_4": {"red_floor": 0.15, "green_target": 0.75, "band_width": 0.30},
        "param_5": {"red_floor": 0.30, "green_target": 0.80, "band_width": 0.20},
        "param_6": {"red_floor": 0.30, "green_target": 0.80, "band_width": 0.20},
    }
}


def run_test():
    process_input = ProcessInput(
        process_id="proc_claims_mgmt",
        process_name="Gestion de Siniestros (Claims Management)",
        parameters=PARAMS,
        critical_parameters=["param_1"],
        kpi_weights=build_kpi_weights(),
        kpi_scores=[],
    )

    result = run_discovery_engine(
        discovery_id=DISCOVERY_ID,
        client_name=CLIENT_NAME,
        processes=[process_input],
        votes_by_round={"proc_claims_mgmt": build_votes()},
        kpi_scores={"proc_claims_mgmt": KPI_SCORES_MAP},
        zone_config=ZONE_CONFIG,
        critical_registry=CRITICAL_REGISTRY,
        theta_config=THETA_CONFIG,
        alpha_threshold=0.3,
        tau_threshold=0.75,
        max_rounds=3,
    )

    proc = result.processes[0]

    assert proc.tau_converged is True
    assert proc.tau_rounds == 1
    assert 0.28 <= proc.npi_score <= 0.32
    assert proc.alpha_triggered is True

    kill_switched = [p for p in proc.parameters if p.kill_switch_active]
    assert len(kill_switched) == 1
    assert kill_switched[0].parameter_id == "param_1"

    tripped = [p for p in proc.parameters if p.trip_wire_flag]
    tripped_ids = {p.parameter_id for p in tripped}
    assert "param_2" in tripped_ids
    assert "param_4" in tripped_ids

    assert proc.zone == "RED"
    assert result.overall_zone == "RED"
    assert len(proc.prescriptions) >= 3
    assert any("CRITICAL" in p for p in proc.prescriptions)
    assert any("PREVENTIVE" in p for p in proc.prescriptions)
    assert result.trust_gate_passed is True

    print("
" + "=" * 60)
    print("  IC-pi INTEGRATION TEST: DANA CASE STUDY")
    print("=" * 60)
    print(f"
  Client:        {result.client_name}")
    print(f"  Process:       {proc.process_name}")
    print(f"  NPI Score:     {proc.npi_score:.4f}")
    print(f"  Zone:          {proc.zone} {'(alpha forced)' if proc.alpha_triggered else ''}")
    print(f"  Trust Gate:    {'PASSED' if proc.tau_converged else 'FAILED'} (Round {proc.tau_rounds})")
    print(f"  Kill Switch:   {'ACTIVE' if proc.alpha_triggered else 'inactive'}")
    print(f"  Trip Wires:    {len(tripped)} triggered")
    print(f"  Prescriptions: {len(proc.prescriptions)} generated")
    print(f"
  PARAMETER BREAKDOWN:")
    print(f"  {'-' * 56}")

    for p in proc.parameters:
        flags = []
        if p.kill_switch_active:
            flags.append("KILL")
        if p.trip_wire_flag:
            flags.append("TRIP")
        flag_str = " ".join(flags) if flags else "ok"
        print(f"  {p.parameter_id:10s} | W={p.W_i:.3f} | KPI={p.kpi_composite:.3f} | C={p.contribution:.4f} | {flag_str}")

    print(f"
  PRESCRIPTIONS:")
    print(f"  {'-' * 56}")
    for i, rx in enumerate(proc.prescriptions, 1):
        print(f"  {i}. {rx}")

    print(f"
{'=' * 60}")
    print("  ALL ASSERTIONS PASSED")
    print(f"{'=' * 60}
")

    return result


if __name__ == "__main__":
    run_test()
