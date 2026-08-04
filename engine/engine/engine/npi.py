"""
IC-pi Engine: NPI Calculation Module
Formula: NPI = Sum[W_i x Sum(w_ij x KPI_ij)]
"""

from .schemas import ProcessInput, KPIWeight, ParameterScore
from collections import defaultdict


def _aggregate_sme_weights(
    kpi_weights: list[KPIWeight], parameter_id: str
) -> dict[str, float]:
    totals: dict[str, list[float]] = defaultdict(list)

    for kw in kpi_weights:
        if kw.parameter_id == parameter_id:
            totals[kw.kpi_id].append(kw.weight)

    return {kpi_id: sum(vals) / len(vals) for kpi_id, vals in totals.items()}


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total == 0:
        n = len(weights)
        return {k: 1.0 / n for k in weights} if n > 0 else {}
    return {k: v / total for k, v in weights.items()}


def _compute_parameter_weight(
    kpi_weights: list[KPIWeight], parameter_id: str
) -> float:
    raw = _aggregate_sme_weights(kpi_weights, parameter_id)
    return sum(raw.values())


def calculate_npi(
    process: ProcessInput,
    validated_params: list[str],
    kpi_scores: dict[str, float],
) -> tuple[float, list[ParameterScore]]:
    # Step 1: Raw parameter importance weights
    raw_param_weights: dict[str, float] = {}
    for param_id in validated_params:
        raw_param_weights[param_id] = _compute_parameter_weight(
            process.kpi_weights, param_id
        )

    # Step 2: Normalize so Sum W_i = 1.0
    normalized_W = _normalize(raw_param_weights)

    # Step 3: KPI composite per parameter
    parameter_scores: list[ParameterScore] = []
    npi_total = 0.0

    for param_id in validated_params:
        W_i = normalized_W.get(param_id, 0.0)

        raw_kpi_weights = _aggregate_sme_weights(process.kpi_weights, param_id)
        norm_kpi_weights = _normalize(raw_kpi_weights)

        kpi_composite = 0.0
        for kpi_id, w_ij in norm_kpi_weights.items():
            score = kpi_scores.get(kpi_id, 0.0)
            kpi_composite += w_ij * score

        contribution = W_i * kpi_composite
        npi_total += contribution

        parameter_scores.append(
            ParameterScore(
                parameter_id=param_id,
                parameter_name=param_id,
                W_i=round(W_i, 4),
                kpi_composite=round(kpi_composite, 4),
                contribution=round(contribution, 4),
                trip_wire_flag=False,
                kill_switch_active=False,
            )
        )

    return round(npi_total, 4), parameter_scores
