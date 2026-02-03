import json
import re
from pathlib import Path
from flask import current_app as app

# Load airports.json
AIRPORTS_RAW: dict[str, str] = {}

file_path = Path(__file__).parent / "airports.json"

with open(file_path, "r", encoding="utf-8") as f:
    AIRPORTS_RAW = json.load(f)

# Lookup table: user_input -> IATA
AIRPORT_LOOKUP: dict[str, str] = {}

for label, iata in AIRPORTS_RAW.items():
    label_lower = label.lower()

    # Full label
    AIRPORT_LOOKUP[label_lower] = iata

    # City name only (before comma)
    city = label_lower.split(",")[0].strip()
    AIRPORT_LOOKUP[city] = iata

    # Airport code itself
    AIRPORT_LOOKUP[iata.lower()] = iata


# Common typo aliases (assist mode helpers)
ALIASES = {
    "banglore": "BLR",
    "bengaluru": "BLR",
    "blr": "BLR",
    "jeddha": "JED",
    "jedha": "JED",
    "jed": "JED",
}

AIRPORT_LOOKUP.update(ALIASES)


def resolve_city_to_iata(city: str) -> str | None:
    if not city:
        return None

    text = city.strip().lower()
    text = re.sub(r"[-_]", " ", text)

    if text in AIRPORT_LOOKUP:
        return AIRPORT_LOOKUP[text]

    return None



def suggest_cities(city: str, limit: int = 3) -> list[str]:
    if not city:
        return []

    text = city.strip().lower()
    results = []

    for label in AIRPORTS_RAW.keys():
        if text in label.lower():
            results.append(label)

        if len(results) >= limit:
            break

    return results

