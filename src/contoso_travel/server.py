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

from . import storage
from .models import City, Flight, Hotel

load_dotenv()

_MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
_MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))

mcp = FastMCP(
    "Contoso Travel",
    instructions=(
        "Contoso Travel provides read-only information about daily flights and hotels for "
        "10 destinations worldwide. Use the tools to look up cities, search flights between "
        "destinations, and find hotels in a city. This server does NOT handle bookings or "
        "payments - it is for information only."
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


def _enrich_city(c: City) -> CityInfo:
    now = datetime.now(ZoneInfo(c.timezone)).replace(microsecond=0)
    return CityInfo(**c.model_dump(), current_local_time=now.isoformat())


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_cities() -> list[City]:
    """List all 10 destinations served by Contoso Travel."""
    return storage.list_cities()


@mcp.tool()
def get_city_info(query: str) -> CityInfo | None:
    """Resolve a city by IATA code (e.g. 'AMS') or name (e.g. 'Amsterdam').

    Returns the city's IATA code, country, timezone, coordinates and the
    current local time at the destination. Returns null if the city is unknown.
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
        origin: Optional origin IATA code (e.g. 'JFK').
        destination: Optional destination IATA code (e.g. 'HND').
        max_duration_minutes: Optional cap on flight duration in minutes.

    All flights operate daily. Times are local to the origin / destination
    respectively; `arrival_day_offset` indicates if the flight lands the next
    (+1) or previous (-1) calendar day.
    """
    return storage.search_flights(
        origin=origin, destination=destination, max_duration_minutes=max_duration_minutes
    )


@mcp.tool()
def get_flight(flight_number: str) -> Flight | None:
    """Look up a single flight by its Contoso flight number (e.g. 'CT042')."""
    return storage.get_flight(flight_number)


@mcp.tool()
def search_hotels(
    city: str,
    min_stars: int | None = None,
    max_rate_usd: int | None = None,
) -> list[Hotel]:
    """List hotels in a given Contoso Travel city.

    Args:
        city: City IATA code (e.g. 'HKG'). Use list_cities to discover codes.
        min_stars: Optional minimum star rating (1-5).
        max_rate_usd: Optional maximum nightly rate in USD.
    """
    return storage.search_hotels(city=city, min_stars=min_stars, max_rate_usd=max_rate_usd)


@mcp.tool()
def get_hotel(hotel_id: str) -> Hotel | None:
    """Look up a single hotel by its id (e.g. 'HKG-03')."""
    return storage.get_hotel(hotel_id)


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
