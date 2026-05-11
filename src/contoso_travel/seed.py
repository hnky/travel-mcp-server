"""Seed Azure Table Storage with Contoso Travel data.

Usage:
    python -m contoso_travel.seed              # idempotent upsert
    python -m contoso_travel.seed --reset      # delete tables, recreate, seed
"""

from __future__ import annotations

import argparse
import sys
import time

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from dotenv import load_dotenv

from .cities import CITIES
from .generator import generate_flights, generate_hotels
from .models import City
from .storage import (
    CITIES_TABLE,
    FLIGHTS_TABLE,
    HOTELS_TABLE,
    city_to_entity,
    flight_to_entity,
    hotel_to_entity,
    service_client,
)

TABLES = (CITIES_TABLE, FLIGHTS_TABLE, HOTELS_TABLE)


def _city_models() -> list[City]:
    return [
        City(
            iata=c.iata, name=c.name, country=c.country, timezone=c.timezone,
            latitude=c.latitude, longitude=c.longitude,
        )
        for c in CITIES
    ]


def _delete_tables(svc) -> None:
    for t in TABLES:
        try:
            svc.delete_table(table_name=t)
            print(f"  deleted table {t}")
        except ResourceNotFoundError:
            pass
        except HttpResponseError as e:  # already-deleting in flight, etc.
            print(f"  warning deleting {t}: {e.message}", file=sys.stderr)
    # Azure Table Storage requires a short delay before re-creating a deleted table.
    time.sleep(2)


def _create_tables(svc) -> None:
    for t in TABLES:
        # create_table_if_not_exists handles the "in-flight delete" retry for us.
        for attempt in range(10):
            try:
                svc.create_table_if_not_exists(table_name=t)
                print(f"  ensured table {t}")
                break
            except HttpResponseError as e:
                if "TableBeingDeleted" in str(e) and attempt < 9:
                    time.sleep(3)
                    continue
                raise


def seed(reset: bool = False) -> None:
    svc = service_client()

    if reset:
        print("Resetting tables...")
        _delete_tables(svc)

    print("Creating tables (if not exists)...")
    _create_tables(svc)

    cities = _city_models()
    flights = generate_flights()
    hotels = generate_hotels()

    print(f"Seeding {len(cities)} cities, {len(flights)} flights, {len(hotels)} hotels...")

    c_client = svc.get_table_client(CITIES_TABLE)
    for c in cities:
        c_client.upsert_entity(city_to_entity(c))

    f_client = svc.get_table_client(FLIGHTS_TABLE)
    for f in flights:
        f_client.upsert_entity(flight_to_entity(f))

    h_client = svc.get_table_client(HOTELS_TABLE)
    for h in hotels:
        h_client.upsert_entity(hotel_to_entity(h))

    # Verify counts
    n_cities = sum(1 for _ in c_client.list_entities())
    n_flights = sum(1 for _ in f_client.list_entities())
    n_hotels = sum(1 for _ in h_client.list_entities())
    print(f"Done. Cities={n_cities} Flights={n_flights} Hotels={n_hotels}")

    expected = (10, 90, 100)
    if (n_cities, n_flights, n_hotels) != expected:
        raise SystemExit(
            f"Unexpected row counts: got {(n_cities, n_flights, n_hotels)}, expected {expected}"
        )


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Seed Contoso Travel data into Azure Table Storage")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate tables before seeding.")
    args = parser.parse_args()
    seed(reset=args.reset)


if __name__ == "__main__":
    main()
