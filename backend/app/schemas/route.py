from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class RouteRequest(BaseModel):
    origin: str = Field(..., description="Origin city/place name, e.g. 'Delhi'")
    destination: str = Field(..., description="Destination city/place name, e.g. 'Jaipur'")
    mode: str = Field("day", description="Scoring mode: 'day' or 'night'")


class Coordinate(BaseModel):
    lat: float
    lng: float


class GeoJSONLineString(BaseModel):
    type: str = "LineString"
    coordinates: List[List[float]]  # [[lng, lat], ...]


class SafetyPenalties(BaseModel):
    road_type: int = 0
    turn_density: int = 0
    isolation: int = 0
    duration: int = 0
    traffic: int = 0


class SafetyBreakdown(BaseModel):
    highway_ratio: float = 0.0
    turn_density: float = 0.0
    longest_isolated_segment_km: float = 0.0
    traffic_level: str = "Moderate"
    penalties: SafetyPenalties = SafetyPenalties()


class RouteSummary(BaseModel):
    distance_km: float = 0.0
    duration_hours: float = 0.0


class RouteStepManeuver(BaseModel):
    type: str = ""
    modifier: str = ""
    location: List[float] = []   # [lng, lat] — OSRM order


class RouteStep(BaseModel):
    distance: float = 0.0
    duration: float = 0.0
    name: str = ""
    ref: str = ""
    maneuver: RouteStepManeuver = RouteStepManeuver()


class RouteInfo(BaseModel):
    id: str
    name: str
    distance_km: float
    duration_minutes: float
    safety_score: float
    road_summary: str
    traffic_level: str      # "Low", "Moderate", "High"
    road_quality: str       # "Excellent", "Good", "Average"
    geometry: GeoJSONLineString
    steps: List[RouteStep] = []    # OSRM navigation maneuvers
    route_summary: RouteSummary = RouteSummary()
    breakdown: SafetyBreakdown = SafetyBreakdown()


class RouteResponse(BaseModel):
    routes: List[RouteInfo]
    origin_coords: Coordinate
    destination_coords: Coordinate
    status: str = "success"
    error: Optional[str] = None
