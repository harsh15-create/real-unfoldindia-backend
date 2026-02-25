from fastapi import APIRouter, HTTPException
from app.schemas.route import RouteRequest, RouteResponse
from app.services.route_service import get_routes

router = APIRouter()


@router.post("/route", response_model=RouteResponse)
async def route_endpoint(request: RouteRequest):
    """
    Compute driving routes between two Indian cities.
    Uses OSRM for routing and Nominatim for geocoding.
    Returns 2-3 alternative routes with structured safety scores.

    Accepts optional 'mode' field: "day" (default) or "night".
    Night mode increases penalties for isolation and rural segments.
    """
    if not request.origin.strip() or not request.destination.strip():
        raise HTTPException(status_code=422, detail="Origin and destination are required.")

    # Validate mode
    mode = request.mode.strip().lower() if request.mode else "day"
    if mode not in ("day", "night"):
        raise HTTPException(status_code=422, detail="Mode must be 'day' or 'night'.")

    try:
        result = await get_routes(request.origin.strip(), request.destination.strip(), mode=mode)
        return result
    except ValueError as e:
        # Geocoding failure (bad city name)
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        # OSRM failure
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
