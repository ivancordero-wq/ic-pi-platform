
"""
IC-pi Engine: Trip Wire Module (τ — tau)
==========================================

Per-KPI critical floors. τ_ij is an array: one value per critical KPI.
If KPI_ij < τ_ij → α fires → parameter collapses to RED.
Defined by leadership (operational) or imposed by regulators (legal).
"""

from .schemas import ParameterScore

def calculate_tau_band(
    red_floor: float,
    green_target: float,
    band_width: float = 0.20,
) -> float:
    gap = green_target - red_floor
    tau = red_floor + (gap * band_width)
    return round(tau, 4)



def check_trip_wires(
    parameter_scores: list[ParameterScore],
    tau_config: dict[str, dict],
) -> tuple[list[str], list[ParameterScore]]:
    flagged_ids: list[str] = []
    updated_scores: list[ParameterScore] = []

    for param in parameter_scores:
        config = tau_config.get(param.parameter_id)
        tripped = False

        if config:
            tau = calculate_tau_band(
                red_floor=config["red_floor"],
                green_target=config["green_target"],
                band_width=config.get("band_width", 0.20),
            )

            if config["red_floor"] < param.kpi_composite <= tau:
                tripped = True
                flagged_ids.append(param.parameter_id)

        updated_scores.append(
            param.model_copy(update={"trip_wire_flag": tripped})
        )

    return flagged_ids, updated_scores


def get_trip_wire_summary(
    flagged_ids: list[str],
    parameter_scores: list[ParameterScore],
    tau_config: dict[str, dict],
) -> dict:
    flagged_details = []
    for param in parameter_scores:
        if param.trip_wire_flag:
            config = tau_config.get(param.parameter_id, {})
            tau = calculate_tau_band(
                config.get("red_floor", 0),
                config.get("green_target", 1),
                config.get("band_width", 0.20),
            )
            flagged_details.append({
                "parameter_id": param.parameter_id,
                "parameter_name": param.parameter_name,
                "current_score": param.kpi_composite,
                "tau_threshold": tau,
                "proximity_to_red": round(param.kpi_composite - config.get("red_floor", 0), 4),
            })

    return {
        "trip_wires_triggered": len(flagged_ids),
        "flagged_parameters": flagged_details,
        "message": (
            f"WARNING: {len(flagged_ids)} parameter(s) approaching critical levels. "
            f"Preventive action recommended."
            if flagged_ids
            else "No parameters in warning band. All clear."
        ),
    }
