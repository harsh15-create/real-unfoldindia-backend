"""
Safety Score Engine — Structured, weighted, deterministic scoring.

Accepts parsed OSRM route data and returns a normalized 0–10 score
with a full penalty breakdown.  No randomness, no AI.

Components & weights:
    A. Highway Ratio    — 30%
    B. Turn Density     — 20%
    C. Isolation Risk   — 20%
    D. Duration Risk    — 10%
    E. Traffic Modifier — 10%

Night mode multiplies isolation ×1.5 and rural ×1.3.
"""

import re
from typing import Any, Dict, List, Literal

# ─── Public types ────────────────────────────────────────────────

SafetyMode = Literal["day", "night"]

HIGHWAY_PATTERN = re.compile(
    r"\b(NH|SH|National Highway|State Highway|Expressway|motorway|trunk)\b",
    re.IGNORECASE,
)


class SafetyResult:
    """Immutable result object for one route's safety analysis."""

    __slots__ = (
        "score",
        "highway_ratio",
        "turn_density",
        "longest_isolated_segment_km",
        "traffic_level",
        "penalties",
        "distance_km",
        "duration_hours",
    )

    def __init__(
        self,
        *,
        score: float,
        highway_ratio: float,
        turn_density: float,
        longest_isolated_segment_km: float,
        traffic_level: str,
        penalties: Dict[str, int],
        distance_km: float,
        duration_hours: float,
    ):
        self.score = score
        self.highway_ratio = highway_ratio
        self.turn_density = turn_density
        self.longest_isolated_segment_km = longest_isolated_segment_km
        self.traffic_level = traffic_level
        self.penalties = penalties
        self.distance_km = distance_km
        self.duration_hours = duration_hours

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_summary": {
                "distance_km": self.distance_km,
                "duration_hours": self.duration_hours,
            },
            "safety_score": self.score,
            "breakdown": {
                "highway_ratio": self.highway_ratio,
                "turn_density": self.turn_density,
                "longest_isolated_segment_km": self.longest_isolated_segment_km,
                "traffic_level": self.traffic_level,
                "penalties": self.penalties,
            },
        }


# ─── Internal helpers ────────────────────────────────────────────

def _extract_steps(route: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten all steps from all legs."""
    steps: List[Dict[str, Any]] = []
    for leg in route.get("legs", []):
        steps.extend(leg.get("steps", []))
    return steps


def _compute_highway_ratio(steps: List[Dict[str, Any]], total_distance_m: float) -> float:
    """Fraction of route distance on highway / expressway / trunk."""
    if total_distance_m <= 0:
        return 0.0
    highway_dist = 0.0
    for step in steps:
        name = step.get("name", "")
        ref = step.get("ref", "")
        combined = f"{name} {ref}"
        if HIGHWAY_PATTERN.search(combined):
            highway_dist += step.get("distance", 0)
    return highway_dist / total_distance_m


def _compute_turn_density(steps: List[Dict[str, Any]], total_distance_km: float) -> float:
    """Non-trivial maneuvers per kilometre."""
    if total_distance_km <= 0:
        return 0.0
    skip = {"depart", "arrive"}
    turns = sum(
        1
        for s in steps
        if s.get("maneuver", {}).get("type", "") not in skip
    )
    return turns / total_distance_km


def _compute_isolation(steps: List[Dict[str, Any]]) -> float:
    """Longest continuous segment (km) with no named / major road."""
    current_run_m = 0.0
    longest_m = 0.0
    for step in steps:
        name = (step.get("name", "") or "").strip()
        ref = (step.get("ref", "") or "").strip()
        is_isolated = not name and not ref
        if is_isolated:
            current_run_m += step.get("distance", 0)
        else:
            if current_run_m > longest_m:
                longest_m = current_run_m
            current_run_m = 0.0
    # Final segment
    if current_run_m > longest_m:
        longest_m = current_run_m
    return longest_m / 1000.0


def _classify_traffic(duration_s: float, distance_m: float) -> str:
    """Speed-based traffic classification."""
    if distance_m <= 0 or duration_s <= 0:
        return "Moderate"
    avg_speed_kmh = (distance_m / 1000) / (duration_s / 3600)
    if avg_speed_kmh >= 70:
        return "Low"
    elif avg_speed_kmh >= 45:
        return "Moderate"
    return "High"


# ─── Public scoring function ─────────────────────────────────────

def compute_safety(
    route: Dict[str, Any],
    mode: SafetyMode = "day",
) -> SafetyResult:
    """
    Deterministic safety scoring.

    Returns a SafetyResult with a normalised 0–10 score and full breakdown.
    """
    total_distance_m = float(route.get("distance", 0))
    total_duration_s = float(route.get("duration", 0))
    total_distance_km = total_distance_m / 1000.0
    total_duration_h = total_duration_s / 3600.0

    steps = _extract_steps(route)

    # ── Metrics ──
    highway_ratio = _compute_highway_ratio(steps, total_distance_m)
    turn_density = _compute_turn_density(steps, total_distance_km)
    longest_isolated_km = _compute_isolation(steps)
    traffic_level = _classify_traffic(total_duration_s, total_distance_m)

    # ── Penalties (start from base 100) ──
    base = 100
    penalties: Dict[str, int] = {}

    # A.  Highway Ratio (30%)
    if highway_ratio > 0.7:
        penalties["road_type"] = 0
    elif highway_ratio >= 0.4:
        penalties["road_type"] = -5
    else:
        penalties["road_type"] = -10

    # B.  Turn Density (20%)
    if turn_density < 1:
        penalties["turn_density"] = 0
    elif turn_density <= 2:
        penalties["turn_density"] = -5
    else:
        penalties["turn_density"] = -10

    # C.  Isolation Risk (20%)
    iso_penalty = 0
    if longest_isolated_km > 50:
        iso_penalty = -15
    elif longest_isolated_km > 20:
        iso_penalty = -7
    else:
        iso_penalty = 0

    if mode == "night":
        iso_penalty = int(iso_penalty * 1.5)

    penalties["isolation"] = iso_penalty

    # D.  Duration Risk (10%)
    if total_duration_h > 8:
        penalties["duration"] = -10
    elif total_duration_h > 6:
        penalties["duration"] = -5
    else:
        penalties["duration"] = 0

    # E.  Traffic Modifier (10%)
    if traffic_level == "High":
        penalties["traffic"] = -10
    elif traffic_level == "Moderate":
        penalties["traffic"] = -5
    else:
        penalties["traffic"] = 0

    # Night mode rural multiplier on road_type penalty
    if mode == "night" and penalties["road_type"] < 0:
        penalties["road_type"] = int(penalties["road_type"] * 1.3)

    # ── Final score ──
    raw = base + sum(penalties.values())
    clamped = max(10, raw)  # floor at 10 (= 1.0 normalised)
    normalised = round(clamped / 10.0, 1)

    return SafetyResult(
        score=normalised,
        highway_ratio=round(highway_ratio, 3),
        turn_density=round(turn_density, 2),
        longest_isolated_segment_km=round(longest_isolated_km, 1),
        traffic_level=traffic_level,
        penalties=penalties,
        distance_km=round(total_distance_km, 1),
        duration_hours=round(total_duration_h, 2),
    )
