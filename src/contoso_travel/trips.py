"""Trip planning: in-memory/JSON-file storage + webhook notifications.

Trips are NOT bookings - they are itinerary drafts compiled from the
read-only Contoso Travel catalog. Each trip is identified by a public
`id` plus a secret `key` that must be supplied to mutate it.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import urllib.error
import urllib.request
from datetime import date as _date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .models import Flight, Hotel

_TRIPS_FILE = Path(os.environ.get("TRIPS_FILE", "trips.json"))
_WEBHOOK_URL = os.environ.get("TRIP_WEBHOOK_URL", "").strip() or None
_WEBHOOK_TIMEOUT = float(os.environ.get("TRIP_WEBHOOK_TIMEOUT", "5"))

_lock = threading.Lock()


class TripFlight(Flight):
    departure_date: str = Field(description="Departure date at origin (YYYY-MM-DD).")


class TripHotel(Hotel):
    checkin: str = Field(description="Check-in date (YYYY-MM-DD).")
    checkout: str = Field(description="Check-out date (YYYY-MM-DD).")


class TripItem(BaseModel):
    type: Literal["flight", "hotel"]
    flight: TripFlight | None = None
    hotel: TripHotel | None = None

    model_config = {"json_schema_extra": {"description": "Either flight or hotel is set, not both."}}


class Trip(BaseModel):
    id: str
    name: str
    items: list[TripItem] = Field(default_factory=list)

    def model_dump(self, **kwargs):  # type: ignore[override]
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


class TripCreated(BaseModel):
    id: str
    name: str
    key: str = Field(description="Secret key required for subsequent add_* calls.")


# ---------------------------------------------------------------------------
# JSON-file persistence
# ---------------------------------------------------------------------------

def _load_all() -> dict:
    if not _TRIPS_FILE.exists():
        return {}
    try:
        return json.loads(_TRIPS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_all(data: dict) -> None:
    _TRIPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _TRIPS_FILE.with_suffix(_TRIPS_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(_TRIPS_FILE)


def _get_record(trip_id: str) -> dict | None:
    return _load_all().get(trip_id)


def _put_record(record: dict) -> None:
    data = _load_all()
    data[record["id"]] = record
    _save_all(data)


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

def _post_webhook(trip: Trip) -> None:
    if not _WEBHOOK_URL:
        return
    payload = json.dumps(trip.model_dump()).encode("utf-8")
    req = urllib.request.Request(
        _WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=_WEBHOOK_TIMEOUT).close()
    except (urllib.error.URLError, TimeoutError):
        # Webhook is best-effort; never fail the tool call because of it.
        pass


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_date(value: str, field: str) -> str:
    try:
        return _date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD).") from exc


def _authorize(trip_id: str, key: str) -> dict:
    record = _get_record(trip_id)
    if record is None:
        raise ValueError(f"Unknown trip id '{trip_id}'.")
    if not secrets.compare_digest(record.get("key", ""), key):
        raise ValueError("Invalid trip key.")
    return record


def _public_trip(record: dict) -> Trip:
    return Trip(id=record["id"], name=record["name"], items=record.get("items", []))


# ---------------------------------------------------------------------------
# Public API (used by MCP tools)
# ---------------------------------------------------------------------------

def create_trip(name: str) -> TripCreated:
    name = (name or "").strip()
    if not name:
        raise ValueError("Trip name must not be empty.")

    with _lock:
        trip_id = f"TRIP-{secrets.token_hex(4).upper()}"
        record = {
            "id": trip_id,
            "name": name,
            "key": secrets.token_urlsafe(16),
            "items": [],
        }
        _put_record(record)

    _post_webhook(_public_trip(record))
    return TripCreated(id=record["id"], name=record["name"], key=record["key"])


def add_flight(
    trip_id: str,
    key: str,
    flight: Flight,
    departure_date: str,
) -> Trip:
    departure_date = _validate_date(departure_date, "departure_date")
    with _lock:
        record = _authorize(trip_id, key)
        trip_flight = TripFlight(
            **flight.model_dump(), departure_date=departure_date
        )
        record.setdefault("items", []).append(
            {"type": "flight", "flight": trip_flight.model_dump()}
        )
        _put_record(record)

    trip = _public_trip(record)
    _post_webhook(trip)
    return trip


def add_hotel(
    trip_id: str,
    key: str,
    hotel: Hotel,
    checkin: str,
    checkout: str,
) -> Trip:
    checkin = _validate_date(checkin, "checkin")
    checkout = _validate_date(checkout, "checkout")
    if _date.fromisoformat(checkout) <= _date.fromisoformat(checkin):
        raise ValueError("checkout must be after checkin.")

    with _lock:
        record = _authorize(trip_id, key)
        trip_hotel = TripHotel(
            **hotel.model_dump(), checkin=checkin, checkout=checkout
        )
        record.setdefault("items", []).append(
            {"type": "hotel", "hotel": trip_hotel.model_dump()}
        )
        _put_record(record)

    trip = _public_trip(record)
    _post_webhook(trip)
    return trip


def get_trip(trip_id: str) -> Trip | None:
    record = _get_record(trip_id)
    return _public_trip(record) if record else None
