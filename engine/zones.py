"""
IC-pi Engine: Zone Classification Module
Translates NPI scores into RED/YELLOW/GREEN zone verdicts.
"""

from .schemas import ProcessResult


def classify_zone(
    npi_score: float,
    green_target: float,
    red_floor: float,
    alpha_triggered: bool,
) -> str:
    if alpha_triggered:
        return "RED"
    if npi_score >= green_target:
        return "GREEN"
    if npi_score <= red_floor:
        return "RED"
    return "YELLOW"


def classify_overall(process_zones: list[str]) -> str:
    if "RED" in process_zones:
        return "RED"
    if "YELLOW" in process_zones:
        return "YELLOW"
    return "GREEN"


def get_zone_summary(process_results: list[ProcessResult]) -> dict:
    zone_map = {
        "RED": [p.process_name for p in process_results if p.zone == "RED"],
        "YELLOW": [p.process_name for p in process_results if p.zone == "YELLOW"],
        "GREEN": [p.process_name for p in process_results if p.zone == "GREEN"],
    }

    return {
        "overall_zone": classify_overall([p.zone for p in process_results]),
        "zone_map": zone_map,
        "red_count": len(zone_map["RED"]),
        "yellow_count": len(zone_map["YELLOW"]),
        "green_count": len(zone_map["GREEN"]),
        "total_processes": len(process_results),
    }
