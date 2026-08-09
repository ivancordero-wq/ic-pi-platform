"""
IC-pi Engine: Kill Switch Module (α — alpha)
=============================================

Non-compensatory logic. If a critical KPI breaches its τ_ij floor,
α_i drops to 0 → entire parent parameter collapses to RED.
No amount of good performance elsewhere can compensate.

Trigger: KPI_ij < τ_ij → α_i = 0 → Parameter_i forced RED.
τ floors are defined by leadership (operational) or regulators (legal).
"""

from .schemas import ParameterScore


def identify_critical_parameters(
    parameter_ids: list[str],
    critical_registry: dict[str, bool],
) -> list[str]:
    return [pid for pid in parameter_ids if critical_registry.get(pid, False)]


def apply_alpha(
    parameter_scores: list[ParameterScore],
    critical_registry: dict[str, bool],
    tau_floors: dict[str, float] | None = None,
    alpha_threshold: float = 0.3,
) -> tuple[bool, list[ParameterScore]]:
    """
    Apply kill switch (α) to critical parameters.

    Args:
        parameter_scores: scored parameters from NPI calculation
        critical_registry: which parameters are critical (True/False)
        tau_floors: per-parameter τ floors (if available). Keys = parameter_id, values = floor.
        alpha_threshold: fallback threshold if no τ floor defined for a parameter (default 0.30)

    Logic:
        For each critical parameter, check if its KPI composite is below
        its τ floor (or the default threshold). If yes → α fires.
    """
    alpha_triggered = False
    updated_scores: list[ParameterScore] = []

    for param in parameter_scores:
        is_critical = critical_registry.get(param.parameter_id, False)

        # Use per-parameter τ floor if available, otherwise fallback
        floor = alpha_threshold
        if tau_floors and param.parameter_id in tau_floors:
            floor = tau_floors[param.parameter_id]

        failed = is_critical and param.kpi_composite < floor

        if failed:
            alpha_triggered = True

        updated_scores.append(
            param.model_copy(update={"kill_switch_active": failed})
        )

    return alpha_triggered, updated_scores


def get_kill_switch_summary(
    alpha_triggered: bool,
    parameter_scores: list[ParameterScore],
) -> dict:
    triggered_params = [
        {
            "parameter_id": p.parameter_id,
            "parameter_name": p.parameter_name,
            "score": p.kpi_composite,
        }
        for p in parameter_scores
        if p.kill_switch_active
    ]

    return {
        "alpha_triggered": alpha_triggered,
        "critical_failures": triggered_params,
        "message": (
            f"KILL SWITCH ACTIVE: {len(triggered_params)} critical parameter(s) "
            f"below τ floor. Process forced to RED zone."
            if alpha_triggered
            else "All critical parameters above τ floors. No override."
        ),
    }
