"""Azure Table Storage access layer (read-only at runtime)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from azure.data.tables import TableClient, TableServiceClient

from .cities import CITIES, CITY_BY_IATA
from .models import City, Flight, Hotel

CITIES_TABLE = "Cities"
FLIGHTS_TABLE = "Flights"
HOTELS_TABLE = "Hotels"

CITIES_PK = "city"


def _connection_string() -> str:
    cs = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not cs:
        raise RuntimeError(
            "AZURE_STORAGE_CONNECTION_STRING is not set. Copy .env.example to .env "
            "or export the variable before running."
        )
    return cs


@lru_cache(maxsize=1)
def service_client() -> TableServiceClient:
    return TableServiceClient.from_connection_string(_connection_string())


def table_client(name: str) -> TableClient:
    return service_client().get_table_client(table_name=name)


# ---------------------------------------------------------------------------
# Entity <-> model conversion
# ---------------------------------------------------------------------------

def city_to_entity(city: City) -> dict:
    return {
        "PartitionKey": CITIES_PK,
        "RowKey": city.iata,
        "name": city.name,
        "country": city.country,
        "timezone": city.timezone,
        "latitude": city.latitude,
        "longitude": city.longitude,
    }


def entity_to_city(e: dict) -> City:
    return City(
        iata=e["RowKey"],
        name=e["name"],
        country=e["country"],
        timezone=e["timezone"],
        latitude=float(e["latitude"]),
        longitude=float(e["longitude"]),
    )


def flight_to_entity(flight: Flight) -> dict:
    d = flight.model_dump()
    d["PartitionKey"] = flight.origin
    d["RowKey"] = flight.flight_number
    return d


def entity_to_flight(e: dict) -> Flight:
    return Flight(
        flight_number=e["flight_number"],
        origin=e["origin"],
        destination=e["destination"],
        departure_time_local=e["departure_time_local"],
        arrival_time_local=e["arrival_time_local"],
        arrival_day_offset=int(e["arrival_day_offset"]),
        origin_timezone=e["origin_timezone"],
        destination_timezone=e["destination_timezone"],
        duration_minutes=int(e["duration_minutes"]),
        distance_km=int(e["distance_km"]),
        aircraft=e["aircraft"],
        frequency=e.get("frequency", "daily"),
    )


def hotel_to_entity(hotel: Hotel) -> dict:
    d = hotel.model_dump()
    d["PartitionKey"] = hotel.city
    d["RowKey"] = hotel.hotel_id
    return d


def entity_to_hotel(e: dict) -> Hotel:
    return Hotel(
        hotel_id=e["hotel_id"],
        city=e["city"],
        name=e["name"],
        address=e["address"],
        stars=int(e["stars"]),
        daily_rate_usd=int(e["daily_rate_usd"]),
        description=e["description"],
    )


# ---------------------------------------------------------------------------
# Query helpers (read-only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FlightFilter:
    origin: str | None = None
    destination: str | None = None
    max_duration_minutes: int | None = None


def list_cities() -> list[City]:
    try:
        rows = list(table_client(CITIES_TABLE).list_entities())
    except Exception:
        rows = []
    if not rows:
        # Fall back to the static definition if the table hasn't been seeded.
        return [
            City(
                iata=c.iata, name=c.name, country=c.country, timezone=c.timezone,
                latitude=c.latitude, longitude=c.longitude,
            )
            for c in CITIES
        ]
    return sorted((entity_to_city(r) for r in rows), key=lambda c: c.name)


def get_city(query: str) -> City | None:
    if not query:
        return None
    q = query.strip().upper()
    if q in CITY_BY_IATA:
        for c in list_cities():
            if c.iata == q:
                return c
    q_low = query.strip().lower()
    for c in list_cities():
        if c.name.lower() == q_low:
            return c
    return None


def _query_flights_raw(f: FlightFilter) -> list[Flight]:
    filters: list[str] = []
    params: dict[str, object] = {}
    if f.origin:
        filters.append("PartitionKey eq @origin")
        params["origin"] = f.origin.upper()
    if f.destination:
        filters.append("destination eq @destination")
        params["destination"] = f.destination.upper()

    client = table_client(FLIGHTS_TABLE)
    if filters:
        rows = client.query_entities(" and ".join(filters), parameters=params)
    else:
        rows = client.list_entities()

    flights = [entity_to_flight(r) for r in rows]
    if f.max_duration_minutes is not None:
        flights = [x for x in flights if x.duration_minutes <= f.max_duration_minutes]
    flights.sort(key=lambda x: (x.origin, x.destination))
    return flights


def search_flights(
    origin: str | None = None,
    destination: str | None = None,
    max_duration_minutes: int | None = None,
) -> list[Flight]:
    return _query_flights_raw(
        FlightFilter(
            origin=origin.upper() if origin else None,
            destination=destination.upper() if destination else None,
            max_duration_minutes=max_duration_minutes,
        )
    )


def get_flight(flight_number: str) -> Flight | None:
    fn = flight_number.strip().upper()
    # We don't know the origin (PartitionKey) up front - query by RowKey.
    rows = list(
        table_client(FLIGHTS_TABLE).query_entities(
            "RowKey eq @rk", parameters={"rk": fn}
        )
    )
    if not rows:
        return None
    return entity_to_flight(rows[0])


def search_hotels(
    city: str,
    min_stars: int | None = None,
    max_rate_usd: int | None = None,
) -> list[Hotel]:
    pk = city.strip().upper()
    rows = table_client(HOTELS_TABLE).query_entities(
        "PartitionKey eq @pk", parameters={"pk": pk}
    )
    hotels = [entity_to_hotel(r) for r in rows]
    if min_stars is not None:
        hotels = [h for h in hotels if h.stars >= min_stars]
    if max_rate_usd is not None:
        hotels = [h for h in hotels if h.daily_rate_usd <= max_rate_usd]
    hotels.sort(key=lambda h: (-h.stars, h.daily_rate_usd))
    return hotels


def get_hotel(hotel_id: str) -> Hotel | None:
    hid = hotel_id.strip().upper()
    rows = list(
        table_client(HOTELS_TABLE).query_entities(
            "RowKey eq @rk", parameters={"rk": hid}
        )
    )
    if not rows:
        return None
    return entity_to_hotel(rows[0])
