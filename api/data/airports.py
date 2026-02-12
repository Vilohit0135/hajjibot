import json
import re
from pathlib import Path
from flask import current_app as app
from difflib import get_close_matches


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

    # 1️⃣ Exact match
    if text in AIRPORT_LOOKUP:
        return AIRPORT_LOOKUP[text]

    # 2️⃣ Fuzzy match
    matches = get_close_matches(
        text,
        AIRPORT_LOOKUP.keys(),
        n=1,
        cutoff=0.8
    )

    if matches:
        return AIRPORT_LOOKUP[matches[0]]

    return None




def suggest_cities(city: str, limit: int = 3) -> list[str]:
    if not city:
        return []

    text = city.strip().lower()

    matches = get_close_matches(
        text,
        AIRPORT_LOOKUP.keys(),
        n=limit,
        cutoff=0.6
    )

    readable = []

    for match in matches:
        iata_code = AIRPORT_LOOKUP[match]

        # Find original airport label
        for label, code in AIRPORTS_RAW.items():
            if code == iata_code:
                readable.append(label)
                break

    return readable[:limit]


