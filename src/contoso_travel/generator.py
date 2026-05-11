"""Deterministic generators for Contoso Travel flight and hotel data."""

from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .cities import CITIES, CityDef
from .models import Flight, Hotel

SEED = "contoso-travel"


# ---------------------------------------------------------------------------
# Geometry / time helpers
# ---------------------------------------------------------------------------

def haversine_km(a: CityDef, b: CityDef) -> float:
    r = 6371.0
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat = lat2 - lat1
    dlon = math.radians(b.longitude - a.longitude)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def pick_aircraft(distance_km: float, rng: random.Random) -> str:
    if distance_km < 1500:
        return rng.choice(["Airbus A320neo", "Boeing 737 MAX 8"])
    if distance_km < 6000:
        return rng.choice(["Airbus A321XLR", "Boeing 787-9 Dreamliner"])
    return rng.choice(["Boeing 777-300ER", "Airbus A350-900"])


def _stable_int(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def _departure_local(origin: str, destination: str) -> tuple[int, int]:
    """Pick a deterministic departure hour (06..22) and minute (00/15/30/45)."""
    n = _stable_int(origin, destination)
    hour = 6 + (n % 17)            # 6..22 inclusive
    minute = ((n // 17) % 4) * 15  # 0, 15, 30, 45
    return hour, minute


def _format_hhmm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


# ---------------------------------------------------------------------------
# Flights
# ---------------------------------------------------------------------------

def generate_flights(cities: tuple[CityDef, ...] = CITIES) -> list[Flight]:
    rng = random.Random(SEED + ":flights")

    # Stable ordering of directed pairs to keep flight numbers reproducible.
    pairs: list[tuple[CityDef, CityDef]] = []
    for o in cities:
        for d in cities:
            if o.iata == d.iata:
                continue
            pairs.append((o, d))
    pairs.sort(key=lambda p: (p[0].iata, p[1].iata))

    # Use an arbitrary reference date just to compute timezone-aware arrival times.
    # The schedule itself is "daily" - we only expose HH:MM + day offset.
    ref_date = datetime(2026, 1, 5)  # a Monday

    flights: list[Flight] = []
    for idx, (origin, dest) in enumerate(pairs, start=1):
        distance = haversine_km(origin, dest)
        duration_min = 30 + round(distance / 14)  # cruise ~840 km/h + ~30 min taxi
        aircraft = pick_aircraft(distance, rng)
        dep_h, dep_m = _departure_local(origin.iata, dest.iata)

        dep_local = datetime(
            ref_date.year, ref_date.month, ref_date.day, dep_h, dep_m,
            tzinfo=ZoneInfo(origin.timezone),
        )
        arr_local = (dep_local + timedelta(minutes=duration_min)).astimezone(
            ZoneInfo(dest.timezone)
        )
        day_offset = (arr_local.date() - dep_local.date()).days

        flights.append(
            Flight(
                flight_number=f"CT{idx:03d}",
                origin=origin.iata,
                destination=dest.iata,
                departure_time_local=_format_hhmm(dep_h, dep_m),
                arrival_time_local=_format_hhmm(arr_local.hour, arr_local.minute),
                arrival_day_offset=day_offset,
                origin_timezone=origin.timezone,
                destination_timezone=dest.timezone,
                duration_minutes=duration_min,
                distance_km=round(distance),
                aircraft=aircraft,
                frequency="daily",
            )
        )
    return flights


# ---------------------------------------------------------------------------
# Hotels
# ---------------------------------------------------------------------------

_ADJECTIVES = (
    "Grand", "Royal", "Imperial", "Coastal", "Urban", "Sunset", "Riverside",
    "Skyline", "Garden", "Heritage", "Metropolitan", "Continental", "Pacific",
    "Atlantic", "Crescent",
)
_NOUNS = (
    "Plaza", "Tower", "Court", "Residence", "House", "Suites", "Park", "Gardens",
    "Quarter", "Harbor", "Square", "Terrace", "Lodge", "Manor", "Pavilion",
)
_CHAINS = (
    "Contoso", "Fabrikam", "Northwind", "Litware", "Adventure Works", "Tailspin",
    "Wide World", "Proseware", "Relecloud", "Trey",
)
_STREET_NAMES = (
    "Market", "King", "Queen", "Park", "River", "Garden", "Cathedral", "Station",
    "Harbor", "Palace", "Liberty", "Union", "Maple", "Elm", "Cedar", "Lakeshore",
    "Orchard", "Sunset", "Highland", "Old Town",
)
_STREET_SUFFIX = ("Street", "Avenue", "Boulevard", "Road", "Lane", "Way", "Plaza")


_CITY_PRICE_FACTOR = {
    "JFK": 1.6,   # New York
    "AMS": 1.2,
    "BER": 1.0,
    "SFO": 1.5,
    "BLR": 0.6,
    "EBB": 0.5,
    "GIG": 0.8,
    "NBO": 0.6,
    "HKG": 1.4,
    "HND": 1.3,
}

_BASE_RATE_BY_STARS = {3: 110, 4: 180, 5: 320}


def generate_hotels(cities: tuple[CityDef, ...] = CITIES) -> list[Hotel]:
    rng = random.Random(SEED + ":hotels")
    hotels: list[Hotel] = []

    for city in cities:
        factor = _CITY_PRICE_FACTOR.get(city.iata, 1.0)
        used_names: set[str] = set()
        for i in range(1, 11):
            # Unique name per city
            while True:
                name = f"{rng.choice(_ADJECTIVES)} {rng.choice(_NOUNS)} {rng.choice(_CHAINS)}"
                if name not in used_names:
                    used_names.add(name)
                    break

            stars = rng.choices([3, 4, 5], weights=[3, 5, 2], k=1)[0]
            base = _BASE_RATE_BY_STARS[stars]
            jitter = rng.uniform(0.85, 1.15)
            rate = int(round(base * factor * jitter / 5.0) * 5)  # round to nearest $5

            number = rng.randint(1, 350)
            street = f"{number} {rng.choice(_STREET_NAMES)} {rng.choice(_STREET_SUFFIX)}"
            address = f"{street}, {city.name}, {city.country}"

            description = (
                f"A {stars}-star property in {city.name} offering comfortable rooms, "
                f"on-site dining and easy access to the city centre."
            )

            hotels.append(
                Hotel(
                    hotel_id=f"{city.iata}-{i:02d}",
                    city=city.iata,
                    name=name,
                    address=address,
                    stars=stars,
                    daily_rate_usd=rate,
                    description=description,
                )
            )
    return hotels
