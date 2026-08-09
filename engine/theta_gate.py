"""
IC-pi Engine: Disagreement Tolerance Module (θ — theta)
========================================================

Validates that SME weight rankings are statistically aligned.
θ is set by leadership BEFORE the exercise. If the variance (σ²)
of SME rankings on a parameter or KPI exceeds θ, a Delphi re-rank
round is triggered.

Applied at BOTH levels:
  - Level 1: Parameter weights (W_i)
  - Level 2: KPI weights within each parameter (w_ij)

Max 3 rounds. If σ² > θ persists → Legitimate Divergence → escalate to leadership.
"""

from collections import defaultdict


def calculate_variance(values: list[float]) -> float:
    """Calculate population variance (σ²) of a list of rankings."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return round(variance, 4)


def check_weight_convergence(
    sme_rankings: dict[str, dict[str, float]],
    theta: float,
) -> tuple[dict[str, float], list[str], list[str]]:
    """
    Check whether SME weight rankings converge within θ tolerance.

    Args:
        sme_rankings: {sme_id: {item_id: rank_value}} where item_id is
                      a parameter_id (Level 1) or kpi_id (Level 2)
        theta: leadership-defined max acceptable variance

    Returns:
        tuple of:
        - variances: {item_id: σ² value}
        - accepted: list of item_ids where σ² ≤ θ
        - divergent: list of item_ids where σ² > θ
    """
    # Collect all rankings per item
    item_rankings: dict[str, list[float]] = defaultdict(list)

    for sme_id, rankings in sme_rankings.items():
        for item_id, rank_value in rankings.items():
            item_rankings[item_id].append(rank_value)

    variances: dict[str, float] = {}
    accepted: list[str] = []
    divergent: list[str] = []

    for item_id, values in item_rankings.items():
        sigma_sq = calculate_variance(values)
        variances[item_id] = sigma_sq

        if sigma_sq <= theta:
            accepted.append(item_id)
        else:
            divergent.append(item_id)

    return variances, accepted, divergent


def run_theta_validation(
    rounds_data: list[dict[str, dict[str, float]]],
    theta: float,
    max_rounds: int = 3,
) -> dict:
    """
    Run iterative θ validation across multiple Delphi rounds.

    Args:
        rounds_data: list of sme_rankings dicts, one per round conducted.
                     Each dict is {sme_id: {item_id: rank_value}}
        theta: leadership-defined tolerance
        max_rounds: maximum rounds allowed (default 3)

    Returns:
        Summary dict with convergence status, rounds used, and item details.
    """
    rounds_used = 0
    final_variances = {}
    final_accepted = []
    final_divergent = []

    for round_idx, sme_rankings in enumerate(rounds_data):
        rounds_used = round_idx + 1
        variances, accepted, divergent = check_weight_convergence(
            sme_rankings=sme_rankings,
            theta=theta,
        )
        final_variances = variances
        final_accepted = accepted
        final_divergent = divergent

        # All items converged
        if not divergent:
            break

        # Max rounds reached
        if rounds_used >= max_rounds:
            break

    return {
        "theta_value": theta,
        "converged": len(final_divergent) == 0,
        "rounds_used": rounds_used,
        "items_accepted": len(final_accepted),
        "items_divergent": len(final_divergent),
        "accepted_list": final_accepted,
        "divergent_list": final_divergent,
        "variances": final_variances,
        "recommendation": (
            "All weight rankings within θ tolerance. Proceed to scoring."
            if not final_divergent
            else f"Legitimate Divergence: {len(final_divergent)} item(s) exceed θ. "
                 f"Escalate to leadership for resolution."
        ),
    }
