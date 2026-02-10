# api/helpers/hotel_city_resolver.py

import csv
from pathlib import Path
from difflib import get_close_matches

CITY_LOOKUP = {}

CITY_ALIASES = {
    "mecca": "makkah",
    "makka": "makkah",
    "madina": "madinah",
    "medina": "madinah",
}

CSV_PATH = Path(__file__).parent.parent / "data" / "hotel_city_list.csv"


def load_hotel_cities():
    global CITY_LOOKUP
    if CITY_LOOKUP:
        return

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
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

    raw = city_name.strip().lower()

    # 1️⃣ Alias handling
    raw = CITY_ALIASES.get(raw, raw)

    # 2️⃣ Exact match
    if raw in CITY_LOOKUP:
        return CITY_LOOKUP[raw]

    # 3️⃣ Fuzzy match (near names)
    matches = get_close_matches(
        raw,
        CITY_LOOKUP.keys(),
        n=1,
        cutoff=0.8
    )

    if matches:
        return CITY_LOOKUP[matches[0]]

    return None


def suggest_hotel_cities(partial: str, limit: int = 5):
    load_hotel_cities()
    partial = partial.lower()

    return [
        name.title()
        for name in get_close_matches(
            partial,
            CITY_LOOKUP.keys(),
            n=limit,
            cutoff=0.6
        )
    ]
