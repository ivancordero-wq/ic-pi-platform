"""
IC-pi Engine: Relevance Gate Module (ρ — rho)
==============================================

Determines whether SME consensus on parameter relevance has converged.
ρ is the FIRST gate in the Discovery flow. Each SME votes Yes/No/Unsure
on each AI-proposed parameter. If ≥70% of decisive votes agree on a
parameter, it passes. If overall agreement across all parameters meets
the convergence threshold, the gate passes.

Applied DURING Discovery (before scoring).
Max 3 voting rounds. If consensus not reached → Facilitator review.
"""

from .schemas import SMEVote
from collections import defaultdict


def _calculate_agreement_ratio(
    votes: list[SMEVote], parameter_ids: list[str]
) -> tuple[float, dict[str, str]]:
    """Calculate per-parameter agreement and overall ratio."""
    param_votes: dict[str, dict[str, int]] = defaultdict(lambda: {"yes": 0, "no": 0})

    for vote in votes:
        if vote.parameter_id in parameter_ids and vote.relevant is not None:
            key = "yes" if vote.relevant else "no"
            param_votes[vote.parameter_id][key] += 1

    agreed_count = 0
    verdicts: dict[str, str] = {}

    for param_id in parameter_ids:
        counts = param_votes.get(param_id, {"yes": 0, "no": 0})
        total_decisive = counts["yes"] + counts["no"]

        if total_decisive == 0:
            verdicts[param_id] = "CONTESTED"
            continue

        majority = max(counts["yes"], counts["no"])
        ratio = majority / total_decisive

        if ratio >= 0.70:
            agreed_count += 1
            verdicts[param_id] = "YES" if counts["yes"] >= counts["no"] else "NO"
        else:
            verdicts[param_id] = "CONTESTED"

    overall = agreed_count / len(parameter_ids) if parameter_ids else 0.0
    return overall, verdicts


def check_convergence(
    votes_by_round: list[list[SMEVote]],
    parameter_ids: list[str],
    rho_threshold: float = 0.75,
    max_rounds: int = 3,
) -> tuple[bool, int, list[str], list[str]]:
    """
    Run ρ gate: iterative relevance voting across SME rounds.

    Args:
        votes_by_round: list of vote lists, one per round conducted
        parameter_ids: all candidate parameter IDs
        rho_threshold: minimum overall agreement ratio to pass (default 0.75)
        max_rounds: maximum voting rounds allowed (default 3)

    Returns:
        tuple of (converged, rounds_used, validated_params, contested_params)
    """
    validated: list[str] = []
    contested: list[str] = []
    rounds_used = 0

    for round_idx, votes in enumerate(votes_by_round):
        rounds_used = round_idx + 1
        agreement_ratio, verdicts = _calculate_agreement_ratio(votes, parameter_ids)

        validated = [pid for pid, v in verdicts.items() if v == "YES"]
        contested = [pid for pid, v in verdicts.items() if v == "CONTESTED"]

        if agreement_ratio >= rho_threshold:
            return True, rounds_used, validated, contested

        if rounds_used >= max_rounds:
            break

    return False, rounds_used, validated, contested


def get_rho_gate_summary(
    converged: bool, rounds_used: int, validated: list[str], contested: list[str]
) -> dict:
    """Generate human-readable summary of ρ gate results."""
    return {
        "rho_gate_passed": converged,
        "rounds_conducted": rounds_used,
        "parameters_validated": len(validated),
        "parameters_contested": len(contested),
        "contested_list": contested,
        "recommendation": (
            "Relevance consensus reached. Proceed to weight ranking (θ gate)."
            if converged
            else "Convergence not achieved. Facilitator review required."
        ),
    }
