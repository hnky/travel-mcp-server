"""Canonical list of cities served by Contoso Travel.

Each city has a single representative airport (IATA code), an IANA timezone,
and latitude/longitude (used by the deterministic flight generator).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CityDef:
    iata: str
    name: str
    country: str
    timezone: str
    latitude: float
    longitude: float


CITIES: tuple[CityDef, ...] = (
    CityDef("JFK", "New York", "United States", "America/New_York", 40.6413, -73.7781),
    CityDef("AMS", "Amsterdam", "Netherlands", "Europe/Amsterdam", 52.3105, 4.7683),
    CityDef("BER", "Berlin", "Germany", "Europe/Berlin", 52.3667, 13.5033),
    CityDef("SFO", "San Francisco", "United States", "America/Los_Angeles", 37.6213, -122.3790),
    CityDef("BLR", "Bengaluru", "India", "Asia/Kolkata", 13.1986, 77.7066),
    CityDef("EBB", "Entebbe", "Uganda", "Africa/Kampala", 0.0424, 32.4435),
    CityDef("GIG", "Rio de Janeiro", "Brazil", "America/Sao_Paulo", -22.8099, -43.2505),
    CityDef("NBO", "Nairobi", "Kenya", "Africa/Nairobi", -1.3192, 36.9278),
    CityDef("HKG", "Hong Kong", "Hong Kong SAR", "Asia/Hong_Kong", 22.3080, 113.9185),
    CityDef("HND", "Tokyo", "Japan", "Asia/Tokyo", 35.5494, 139.7798),
)


CITY_BY_IATA: dict[str, CityDef] = {c.iata: c for c in CITIES}


def find_city(query: str) -> CityDef | None:
    """Resolve a city by IATA code or (case-insensitive) name."""
    if not query:
        return None
    q = query.strip()
    if q.upper() in CITY_BY_IATA:
        return CITY_BY_IATA[q.upper()]
    q_low = q.lower()
    for c in CITIES:
        if c.name.lower() == q_low:
            return c
    return None
