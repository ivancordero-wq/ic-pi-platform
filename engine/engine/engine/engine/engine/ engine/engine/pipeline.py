"""
IC-pi Engine: Pipeline Orchestrator
Single entry point: run_discovery_engine()
Sequences: tau -> NPI -> alpha -> theta -> Zones -> Prescriptions
"""

from datetime import datetime

from .schemas import ProcessInput, ProcessResult, EngineOutput, SMEVote
from .npi import calculate_npi
from .trust_gate import check_convergence
from .kill_switch import apply_alpha
from .trip_wire import check_trip_wires
from .zones import classify_zone


def _generate_prescriptions(
    process_name: str,
    parameter_scores: list,
    zone: str,
    alpha_triggered: bool,
) -> list[str]:
    prescriptions = []

    kill_switched = [p for p in parameter_scores if p.kill_switch_active]
    for p in kill_switched:
        prescriptions.append(
            f"CRITICAL: Immediate remediation project for '{p.parameter_name}' "
            f"(score: {p.kpi_composite}, below survival threshold)"
        )

    tripped = [p for p in parameter_scores if p.trip_wire_flag and not p.kill_switch_active]
    for p in tripped:
        prescriptions.append(
            f"PREVENTIVE: Sprint to address '{p.parameter_name}' "
            f"(score: {p.kpi_composite}, approaching critical)"
        )

    if zone == "YELLOW":
        sorted_params = sorted(
            [p for p in parameter_scores if not p.kill_switch_active and not p.trip_wire_flag],
            key=lambda x: x.contribution
        )
        for p in sorted_params[:3]:
            prescriptions.append(
                f"IMPROVE: Targeted sprint for '{p.parameter_name}' "
                f"(contribution: {p.contribution}, below process average)"
            )

    if zone == "GREEN" and not tripped:
        prescriptions.append(
            f"MAINTAIN: '{process_name}' performing at target. "
            f"Recommend quarterly monitoring cycle."
        )

    return prescriptions


def run_discovery_engine(
    discovery_id: str,
    client_name: str,
    processes: list[ProcessInput],
    votes_by_round: dict[str, list[list[SMEVote]]],
    kpi_scores: dict[str, dict[str, float]],
    zone_config: dict[str, dict],
    critical_registry: dict[str, dict[str, bool]],
    theta_config: dict[str, dict[str, dict]],
    alpha_threshold: float = 0.3,
    tau_threshold: float = 0.75,
    max_rounds: int = 3,
) -> EngineOutput:
    results: list[ProcessResult] = []

    for process in processes:
        pid = process.process_id

        process_votes = votes_by_round.get(pid, [])
        tau_converged, tau_rounds, validated_params, contested = check_convergence(
            votes_by_round=process_votes,
            parameter_ids=process.parameters,
            tau_threshold=tau_threshold,
            max_rounds=max_rounds,
        )

        if not validated_params:
            results.append(ProcessResult(
                process_id=pid,
                process_name=process.process_name,
                npi_score=0.0,
                zone="RED",
                alpha_triggered=False,
                tau_converged=False,
                tau_rounds=tau_rounds,
                parameters=[],
                prescriptions=["BLOCKED: Trust Gate failed. No consensus on parameters."],
            ))
            continue

        process_kpi_scores = kpi_scores.get(pid, {})
        npi_score, parameter_scores = calculate_npi(
            process=process,
            validated_params=validated_params,
            kpi_scores=process_kpi_scores,
        )

        process_critical = critical_registry.get(pid, {})
        alpha_triggered, parameter_scores = apply_alpha(
            parameter_scores=parameter_scores,
            critical_registry=process_critical,
            alpha_threshold=alpha_threshold,
        )

        process_theta = theta_config.get(pid, {})
        flagged_ids, parameter_scores = check_trip_wires(
            parameter_scores=parameter_scores,
            theta_config=process_theta,
        )

        process_zone_config = zone_config.get(pid, {"green_target": 0.8, "red_floor": 0.4})
        zone = classify_zone(
            npi_score=npi_score,
            green_target=process_zone_config["green_target"],
            red_floor=process_zone_config["red_floor"],
            alpha_triggered=alpha_triggered,
        )

        prescriptions = _generate_prescriptions(
            process_name=process.process_name,
            parameter_scores=parameter_scores,
            zone=zone,
            alpha_triggered=alpha_triggered,
        )

        results.append(ProcessResult(
            process_id=pid,
            process_name=process.process_name,
            npi_score=npi_score,
            zone=zone,
            alpha_triggered=alpha_triggered,
            tau_converged=tau_converged,
            tau_rounds=tau_rounds,
            parameters=parameter_scores,
            trip_wire_flags=flagged_ids,
            prescriptions=prescriptions,
        ))

zone_priority = {"RED": 0, "YELLOW": 1, "GREEN": 2}
    overall_zone = min(
        (r.zone for r in results),
        key=lambda z: zone_priority.get(z, 99),
        default="RED"
    )

    overall_tau = all(r.tau_converged for r in results)

    return EngineOutput(
        discovery_id=discovery_id,
        client_name=client_name,
        process_count=len(results),
        processes=results,
        overall_zone=overall_zone,
        trust_gate_passed=overall_tau,
        timestamp=datetime.utcnow().isoformat(),
    )
