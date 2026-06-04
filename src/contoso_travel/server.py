"""Contoso Travel MCP server (FastMCP, SSE transport).

Exposes read-only tools for inspecting Contoso Travel's flight and hotel catalog.
This is for informational purposes only - no booking, no payments.
"""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field

from . import storage, trips
from .models import City, Flight, Hotel
from .trips import Trip, TripCreated

load_dotenv()

_MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
_MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))

mcp = FastMCP(
    "Contoso Travel",
    instructions=(
        "Contoso Travel is a fictional airline + hotel provider used for demos.\n"
        "It serves 10 cities with one daily flight in each direction between every "
        "city pair (90 flights total) and lists 10 partner hotels per city (100 "
        "hotels total).\n"
        "\n"
        "Destinations (IATA - city, country, timezone):\n"
        "  AMS - Amsterdam, Netherlands (Europe/Amsterdam)\n"
        "  BER - Berlin, Germany (Europe/Berlin)\n"
        "  BLR - Bengaluru, India (Asia/Kolkata)\n"
        "  EBB - Entebbe, Uganda (Africa/Kampala)\n"
        "  GIG - Rio de Janeiro, Brazil (America/Sao_Paulo)\n"
        "  HKG - Hong Kong, Hong Kong SAR (Asia/Hong_Kong)\n"
        "  HND - Tokyo, Japan (Asia/Tokyo)\n"
        "  JFK - New York, United States (America/New_York)\n"
        "  NBO - Nairobi, Kenya (Africa/Nairobi)\n"
        "  SFO - San Francisco, United States (America/Los_Angeles)\n"
        "\n"
        "Conventions:\n"
        "  - Flight numbers are 'CT001'..'CT090' (uppercase, case-insensitive on input).\n"
        "  - Hotel ids are '<IATA>-NN', e.g. 'HKG-03'.\n"
        "  - Flight times are LOCAL to each airport. `arrival_day_offset` is -1, 0, "
        "or +1 days relative to departure.\n"
        "  - All prices (flight `price_usd`, hotel `daily_rate_usd`) are indicative "
        "demo values in USD, NOT live fares.\n"
        "\n"
        "Scope: this server is INFORMATION ONLY. It does not handle bookings, "
        "payments, seat selection, availability, baggage policies, loyalty programs, "
        "or real-time disruptions. If a user asks for those, say so plainly."
    ),
    host=_MCP_HOST,
    port=_MCP_PORT,
    # Disable DNS-rebinding protection: this server is meant to be reachable
    # via arbitrary Host headers (Azure Container Apps fronts it with HTTPS).
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class CityInfo(City):
    current_local_time: str = Field(
        description="Current local wall-clock time at this city (ISO 8601)."
    )


class CurrentTime(BaseModel):
    timezone: str = Field(description="IANA timezone the time is expressed in.")
    iso: str = Field(description="Current local time in ISO 8601 with offset.")
    utc_iso: str = Field(description="Current UTC time in ISO 8601.")
    weekday: str = Field(description="Day of the week, e.g. 'Monday'.")
    date: str = Field(description="Local date (YYYY-MM-DD).")
    time: str = Field(description="Local 24h time (HH:MM:SS).")
    utc_offset: str = Field(description="Offset from UTC, e.g. '+02:00'.")
    city: str | None = Field(
        default=None,
        description="If resolved from a Contoso Travel city, that city's IATA code.",
    )


def _enrich_city(c: City) -> CityInfo:
    now = datetime.now(ZoneInfo(c.timezone)).replace(microsecond=0)
    return CityInfo(**c.model_dump(), current_local_time=now.isoformat())


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_cities() -> list[City]:
    """List all 10 destinations served by Contoso Travel.

    Returns the cities sorted alphabetically by name. The list is small and
    static for the lifetime of the conversation; no need to call repeatedly.
    """
    return storage.list_cities()


@mcp.tool()
def get_city_info(query: str) -> CityInfo | None:
    """Resolve a city by IATA code (e.g. 'AMS') or name (e.g. 'Amsterdam').

    Matching is case-insensitive. Returns the city's IATA code, country,
    timezone, coordinates and the current local time at the destination.
    Returns null if the city is not part of Contoso Travel's 10-city network.
    """
    c = storage.get_city(query)
    return _enrich_city(c) if c else None


@mcp.tool()
def search_flights(
    origin: str | None = None,
    destination: str | None = None,
    max_duration_minutes: int | None = None,
) -> list[Flight]:
    """Search Contoso Travel's daily flight schedule.

    Args:
        origin: Optional origin IATA code (e.g. 'JFK'). Case-insensitive.
        destination: Optional destination IATA code (e.g. 'HND'). Case-insensitive.
        max_duration_minutes: Optional cap on flight duration in minutes.

    All flights operate daily, with exactly ONE flight per directed city pair
    (so origin+destination yields at most one result). Times are local to the
    origin / destination respectively; `arrival_day_offset` indicates if the
    flight lands the next (+1) or previous (-1) calendar day. `price_usd` is
    an indicative one-way economy fare and is not bookable through this server.
    Results are sorted by (origin, destination). Calling with no filters returns
    the full 90-flight network.
    """
    return storage.search_flights(
        origin=origin, destination=destination, max_duration_minutes=max_duration_minutes
    )


@mcp.tool()
def get_flight(flight_number: str) -> Flight | None:
    """Look up a single flight by its Contoso flight number.

    Flight numbers are 'CT001' through 'CT090' (case-insensitive). Returns null
    if the number is outside that range or otherwise unknown.
    """
    return storage.get_flight(flight_number)


@mcp.tool()
def search_hotels(
    city: str,
    min_stars: int | None = None,
    max_rate_usd: int | None = None,
) -> list[Hotel]:
    """List hotels in a given Contoso Travel city.

    Args:
        city: City IATA code (e.g. 'HKG') or city name (e.g. 'Hong Kong').
            Case-insensitive. Use list_cities to discover valid cities.
        min_stars: Optional minimum star rating (1-5).
        max_rate_usd: Optional maximum nightly rate in USD.

    Each city has exactly 10 hotels. Results are sorted by stars descending,
    then by daily rate ascending. `daily_rate_usd` is indicative demo data.
    Returns an empty list if the city is unknown or no hotel matches the filters.
    """
    resolved = storage.get_city(city)
    iata = resolved.iata if resolved else city
    return storage.search_hotels(city=iata, min_stars=min_stars, max_rate_usd=max_rate_usd)


@mcp.tool()
def get_hotel(hotel_id: str) -> Hotel | None:
    """Look up a single hotel by its id.

    Hotel ids follow the pattern '<IATA>-NN', e.g. 'HKG-03', 'JFK-10'
    (case-insensitive). Returns null if no hotel matches.
    """
    return storage.get_hotel(hotel_id)


@mcp.tool()
def get_current_time(location: str | None = None) -> CurrentTime:
    """Return the current time.

    Args:
        location: Optional. A Contoso Travel city (IATA code like 'AMS' or
            name like 'Amsterdam') OR an IANA timezone (e.g. 'Europe/Berlin',
            'Asia/Tokyo'). If omitted, returns the server's UTC time.
    """
    from datetime import timezone as _tz

    city_iata: str | None = None

    if not location:
        tz_name = "UTC"
        tz: ZoneInfo | _tz = _tz.utc
    else:
        # First try resolving against the Contoso Travel city catalog.
        city = storage.get_city(location)
        if city is not None:
            tz_name = city.timezone
            city_iata = city.iata
            tz = ZoneInfo(tz_name)
        else:
            # Otherwise treat the input as an IANA timezone name.
            try:
                tz = ZoneInfo(location)
                tz_name = location
            except Exception as exc:
                raise ValueError(
                    f"Unknown location '{location}'. Pass a Contoso city "
                    f"(IATA or name) or an IANA timezone like 'Europe/Berlin'."
                ) from exc

    now_local = datetime.now(tz).replace(microsecond=0)
    now_utc = now_local.astimezone(_tz.utc)
    offset = now_local.strftime("%z") or "+0000"
    utc_offset = f"{offset[:3]}:{offset[3:]}"

    return CurrentTime(
        timezone=tz_name,
        iso=now_local.isoformat(),
        utc_iso=now_utc.isoformat(),
        weekday=now_local.strftime("%A"),
        date=now_local.strftime("%Y-%m-%d"),
        time=now_local.strftime("%H:%M:%S"),
        utc_offset=utc_offset,
        city=city_iata,
    )


# ---------------------------------------------------------------------------
# Trip planning tools
# ---------------------------------------------------------------------------

@mcp.tool()
def create_trip(name: str) -> TripCreated:
    """Create a new trip itinerary.

    Returns the trip `id` plus a secret `key`. The key MUST be supplied to
    `add_flight_to_trip` and `add_hotel_to_trip` to mutate this trip.
    Store the key for the rest of the conversation - it cannot be recovered.
    """
    return trips.create_trip(name)


@mcp.tool()
def add_flight_to_trip(
    trip_id: str,
    key: str,
    flight_number: str,
    departure_date: str,
) -> Trip:
    """Append a Contoso flight to an existing trip.

    Args:
        trip_id: The trip id returned by `create_trip`.
        key: The secret trip key returned by `create_trip`.
        flight_number: Contoso flight number (e.g. 'CT012').
        departure_date: Date of departure at origin (YYYY-MM-DD).

    Returns the full updated trip.
    """
    flight = storage.get_flight(flight_number)
    if flight is None:
        raise ValueError(f"Unknown flight '{flight_number}'.")
    return trips.add_flight(trip_id, key, flight, departure_date)


@mcp.tool()
def add_hotel_to_trip(
    trip_id: str,
    key: str,
    hotel_id: str,
    checkin: str,
    checkout: str,
) -> Trip:
    """Append a Contoso hotel stay to an existing trip.

    Args:
        trip_id: The trip id returned by `create_trip`.
        key: The secret trip key returned by `create_trip`.
        hotel_id: Hotel id (e.g. 'HKG-03').
        checkin: Check-in date (YYYY-MM-DD).
        checkout: Check-out date (YYYY-MM-DD), must be after checkin.

    Returns the full updated trip.
    """
    hotel = storage.get_hotel(hotel_id)
    if hotel is None:
        raise ValueError(f"Unknown hotel '{hotel_id}'.")
    return trips.add_hotel(trip_id, key, hotel, checkin, checkout)


@mcp.tool()
def get_trip(trip_id: str) -> Trip | None:
    """Return the current state of a trip (no key required for read).

    Returns null if the trip id is unknown.
    """
    return trips.get_trip(trip_id)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the MCP server exposing both SSE (/sse) and Streamable HTTP (/mcp)."""
    import contextlib

    import uvicorn
    from starlette.applications import Starlette

    sse_app = mcp.sse_app()
    http_app = mcp.streamable_http_app()

    # Combine the routes of both transport apps into one Starlette app so the
    # server exposes /sse + /messages/ AND /mcp side-by-side.
    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with http_app.router.lifespan_context(_app):
            yield

    app = Starlette(
        routes=[*sse_app.routes, *http_app.routes],
        lifespan=lifespan,
    )
    uvicorn.run(app, host=_MCP_HOST, port=_MCP_PORT)


if __name__ == "__main__":
    main()
