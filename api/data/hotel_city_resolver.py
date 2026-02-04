# api/helpers/hotel_city_resolver.py

import csv
from pathlib import Path

CITY_LOOKUP = {}

CSV_PATH = Path(__file__).parent.parent / "data" / "hotel_city_list.csv"


def load_hotel_cities():
    global CITY_LOOKUP
    if CITY_LOOKUP:
        return

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # ✅ Correct keys from CSV
            city_name = row["destination"].strip().lower()
            city_id = int(row["city_id"])
            country_code = row["country_code"].strip().upper()

            CITY_LOOKUP[city_name] = {
                "city_id": city_id,
                "country_code": country_code,
            }


def resolve_hotel_city(city_name: str):
    if not city_name:
        return None

    load_hotel_cities()
    return CITY_LOOKUP.get(city_name.strip().lower())


def suggest_hotel_cities(partial: str, limit: int = 5):
    load_hotel_cities()
    partial = partial.lower()

    return [
        name.title()
        for name in CITY_LOOKUP.keys()
        if partial in name
    ][:limit]
