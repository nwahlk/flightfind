"""Helpers for normalizing flight records across sources."""

from datetime import date
from typing import Any, Dict


def normalize_flight_record(
    *,
    route_from: str,
    route_to: str,
    flight_date: date,
    flight_no: str,
    airline: str,
    price: int,
    source: str,
    departure_airport: str = "",
    arrival_airport: str = "",
    metadata: Dict[str, Any] | None = None,
    allow_empty_flight_no: bool = False,
) -> Dict[str, Any]:
    """Return a normalized flight record used by all crawlers."""

    normalized_flight_no = (flight_no or "").strip()
    if not normalized_flight_no and not allow_empty_flight_no:
        normalized_flight_no = "Unknown"

    return {
        "route_from": route_from,
        "route_to": route_to,
        "flight_date": flight_date,
        "flight_no": normalized_flight_no,
        "airline": (airline or "Unknown").strip(),
        "price": int(price),
        "source": (source or "unknown").strip(),
        "departure_airport": (departure_airport or "").strip(),
        "arrival_airport": (arrival_airport or "").strip(),
        "metadata": metadata or {},
    }
