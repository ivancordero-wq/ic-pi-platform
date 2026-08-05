"""
IC-pi Engine: Kill Switch Module (alpha)
Non-compensatory logic. Prevents catastrophic failures from being
averaged away by strong performance elsewhere.
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
    alpha_threshold: float = 0.3,
) -> tuple[bool, list[ParameterScore]]:
    alpha_triggered = False
    updated_scores: list[ParameterScore] = []

    for param in parameter_scores:
        is_critical = critical_registry.get(param.parameter_id, False)
        failed = is_critical and param.kpi_composite < alpha_threshold

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
            f"below threshold. Process forced to RED zone."
            if alpha_triggered
            else "All critical parameters above threshold. No override."
        ),
    }
