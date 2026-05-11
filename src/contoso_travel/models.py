"""Pydantic models exposed by the MCP tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class City(BaseModel):
    iata: str = Field(description="IATA airport code.")
    name: str
    country: str
    timezone: str = Field(description="IANA timezone name, e.g. 'Europe/Amsterdam'.")
    latitude: float
    longitude: float


class Flight(BaseModel):
    flight_number: str = Field(description="Contoso flight number, e.g. 'CT012'.")
    origin: str = Field(description="Origin IATA code.")
    destination: str = Field(description="Destination IATA code.")
    departure_time_local: str = Field(description="Local departure time at origin (HH:MM, 24h).")
    arrival_time_local: str = Field(description="Local arrival time at destination (HH:MM, 24h).")
    arrival_day_offset: int = Field(
        description="Calendar day offset of arrival relative to departure (0, +1, or -1)."
    )
    origin_timezone: str
    destination_timezone: str
    duration_minutes: int
    distance_km: int
    aircraft: str
    price_usd: int = Field(description="Indicative one-way economy fare in USD.")
    frequency: str = Field(default="daily", description="Schedule frequency.")


class Hotel(BaseModel):
    hotel_id: str = Field(description="Stable hotel identifier, e.g. 'HKG-03'.")
    city: str = Field(description="City IATA code.")
    name: str
    address: str
    stars: int = Field(ge=1, le=5)
    daily_rate_usd: int = Field(description="Indicative nightly rate in USD.")
    description: str
