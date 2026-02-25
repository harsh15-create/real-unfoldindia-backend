"""
Route service: Nominatim geocoding (cached) + OSRM routing.
Safety scoring delegated to safety_engine module.
"""

import httpx
import re
from typing import Tuple, List, Dict, Any

from app.services.safety_engine import compute_safety, SafetyMode

# ──────────────────────────────────────────────
# In-memory geocode cache  (city name → coords)
# ──────────────────────────────────────────────
_geocode_cache: Dict[str, Tuple[float, float]] = {}

# Common Indian cities pre-seeded to reduce Nominatim calls
_SEED_CACHE: Dict[str, Tuple[float, float]] = {
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "bangalore": (12.9716, 77.5946),
    "bengaluru": (12.9716, 77.5946),
    "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639),
    "hyderabad": (17.3850, 78.4867),
    "pune": (18.5204, 73.8567),
    "jaipur": (26.9124, 75.7873),
    "ahmedabad": (23.0225, 72.5714),
    "lucknow": (26.8467, 80.9462),
    "agra": (27.1767, 78.0081),
    "varanasi": (25.3176, 82.9739),
    "goa": (15.2993, 74.1240),
    "udaipur": (24.5854, 73.7125),
    "jodhpur": (26.2389, 73.0243),
    "amritsar": (31.6340, 74.8723),
    "shimla": (31.1048, 77.1734),
    "manali": (32.2396, 77.1887),
    "rishikesh": (30.0869, 78.2676),
    "haridwar": (29.9457, 78.1642),
    "mysore": (12.2958, 76.6394),
    "mysuru": (12.2958, 76.6394),
    "kochi": (9.9312, 76.2673),
    "thiruvananthapuram": (8.5241, 76.9366),
    "chandigarh": (30.7333, 76.7794),
    "indore": (22.7196, 75.8577),
    "bhopal": (23.2599, 77.4126),
    "nagpur": (21.1458, 79.0882),
    "surat": (21.1702, 72.8311),
    "coimbatore": (11.0168, 76.9558),
    "visakhapatnam": (17.6868, 83.2185),
    "patna": (25.6093, 85.1376),
    "ranchi": (23.3441, 85.3096),
    "dehradun": (30.3165, 78.0322),
    "guwahati": (26.1445, 91.7362),
    "bhubaneswar": (20.2961, 85.8245),
    "trivandrum": (8.5241, 76.9366),
    "madurai": (9.9252, 78.1198),
    "jaisalmer": (26.9157, 70.9083),
    "pushkar": (26.4900, 74.5513),
    "mathura": (27.4924, 77.6737),
    "leh": (34.1526, 77.5771),
    "srinagar": (34.0837, 74.7973),
    "darjeeling": (27.0360, 88.2627),
    "gangtok": (27.3389, 88.6065),
    "ooty": (11.4102, 76.6950),
    "kodaikanal": (10.2381, 77.4892),
    "mount abu": (24.5926, 72.7156),
    "nainital": (29.3803, 79.4636),
    "mussoorie": (30.4598, 78.0644),
}

# Seed the cache
_geocode_cache.update(_SEED_CACHE)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

HIGHWAY_PATTERN = re.compile(
    r"\b(NH|SH|National Highway|State Highway|Expressway)\b",
    re.IGNORECASE,
)


async def geocode(place_name: str) -> Tuple[float, float]:
    """Convert a place name to (lat, lng). Uses in-memory cache."""
    key = place_name.strip().lower()

    if key in _geocode_cache:
        return _geocode_cache[key]

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            NOMINATIM_URL,
            params={
                "q": f"{place_name}, India",
                "format": "json",
                "limit": 1,
                "countrycodes": "in",
            },
            headers={"User-Agent": "UnfoldIndia/1.0 (travel-app)"},
        )
        resp.raise_for_status()
        data = resp.json()

    if not data:
        raise ValueError(f"Could not geocode '{place_name}'. Please check the city name.")

    lat = float(data[0]["lat"])
    lng = float(data[0]["lon"])

    _geocode_cache[key] = (lat, lng)
    return (lat, lng)


async def fetch_osrm_routes(
    from_lat: float, from_lng: float,
    to_lat: float, to_lng: float,
) -> List[Dict[str, Any]]:
    """Fetch 2–3 alternative routes from OSRM."""
    url = f"{OSRM_URL}/{from_lng},{from_lat};{to_lng},{to_lat}"
    params = {
        "alternatives": "true",
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM error: {data.get('message', 'Unknown error')}")

    return data.get("routes", [])


def classify_road_quality(route: Dict[str, Any]) -> str:
    """Estimate road quality from highway segment prevalence."""
    legs = route.get("legs", [])
    steps = []
    for leg in legs:
        steps.extend(leg.get("steps", []))

    highway_dist = 0.0
    total_dist = 0.0
    for step in steps:
        name = step.get("name", "")
        ref = step.get("ref", "")
        d = step.get("distance", 0)
        total_dist += d
        if HIGHWAY_PATTERN.search(f"{name} {ref}"):
            highway_dist += d

    if total_dist <= 0:
        return "Average"
    ratio = highway_dist / total_dist
    if ratio >= 0.6:
        return "Excellent"
    elif ratio >= 0.3:
        return "Good"
    return "Average"


def extract_navigation_steps(route: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract lean maneuver data from OSRM steps for navigation."""
    steps = []
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            m = step.get("maneuver", {})
            steps.append({
                "distance": step.get("distance", 0),
                "duration": step.get("duration", 0),
                "name": step.get("name", ""),
                "ref": step.get("ref", ""),
                "maneuver": {
                    "type": m.get("type", ""),
                    "modifier": m.get("modifier", ""),
                    "location": m.get("location", []),
                },
            })
    return steps


def extract_road_summary(route: Dict[str, Any]) -> str:
    """Extract the most prominent road name from steps."""
    legs = route.get("legs", [])
    road_distances: Dict[str, float] = {}

    for leg in legs:
        for step in leg.get("steps", []):
            name = step.get("name", "").strip()
            if name:
                road_distances[name] = road_distances.get(name, 0) + step.get("distance", 0)

    if not road_distances:
        return "Local Roads"

    # Try to find an NH/SH specifically
    for name, dist in sorted(road_distances.items(), key=lambda x: x[1], reverse=True):
        if HIGHWAY_PATTERN.search(name):
            return name

    # Fallback: longest road
    return max(road_distances, key=road_distances.get)  # type: ignore


async def get_routes(origin: str, destination: str, mode: SafetyMode = "day") -> Dict[str, Any]:
    """
    Full pipeline: geocode → OSRM → safety engine → structured response.
    """
    # 1. Geocode
    from_coords = await geocode(origin)
    to_coords = await geocode(destination)

    # 2. Fetch OSRM routes
    raw_routes = await fetch_osrm_routes(
        from_coords[0], from_coords[1],
        to_coords[0], to_coords[1],
    )

    if not raw_routes:
        raise RuntimeError("No routes found between these locations.")

    # 3. Process each route through safety engine
    processed = []
    for i, route in enumerate(raw_routes[:3]):  # cap at 3
        safety_result = compute_safety(route, mode=mode)

        distance_km = safety_result.distance_km
        duration_min = round(route["duration"] / 60, 0)
        quality = classify_road_quality(route)
        summary = extract_road_summary(route)
        geometry = route.get("geometry", {"type": "LineString", "coordinates": []})
        nav_steps = extract_navigation_steps(route)

        processed.append({
            "id": f"route_{i + 1}",
            "name": "",  # assigned below after sorting
            "distance_km": distance_km,
            "duration_minutes": duration_min,
            "safety_score": safety_result.score,
            "road_summary": summary,
            "traffic_level": safety_result.traffic_level,
            "road_quality": quality,
            "geometry": geometry,
            "steps": nav_steps,
            "route_summary": {
                "distance_km": safety_result.distance_km,
                "duration_hours": safety_result.duration_hours,
            },
            "breakdown": {
                "highway_ratio": safety_result.highway_ratio,
                "turn_density": safety_result.turn_density,
                "longest_isolated_segment_km": safety_result.longest_isolated_segment_km,
                "traffic_level": safety_result.traffic_level,
                "penalties": safety_result.penalties,
            },
        })

    # 4. Sort by safety descending
    processed.sort(key=lambda r: r["safety_score"], reverse=True)

    # 5. Assign names
    name_labels = ["Recommended Route", "Scenic Route", "Shortest Route"]
    for i, route in enumerate(processed):
        route["name"] = name_labels[i] if i < len(name_labels) else f"Route {i + 1}"

    return {
        "routes": processed,
        "origin_coords": {"lat": from_coords[0], "lng": from_coords[1]},
        "destination_coords": {"lat": to_coords[0], "lng": to_coords[1]},
        "status": "success",
    }
