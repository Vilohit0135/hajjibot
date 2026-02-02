import json
import requests
from datetime import datetime
from typing import Any
from flask import current_app as app

from api.data.visa_data import CITY_TO_IATA
from flask import Flask, request, jsonify






def extract_first_flight(api_response: dict) -> dict | None:
    try:
        return api_response["Result"][0][0]
    except (KeyError, IndexError, TypeError):
        return None


def extract_all_flights(api_response: dict) -> list[dict]:
    """
    Extract all flight itineraries from the nested Result structure
    """
    flights = []
    try:
        for group in api_response.get("Result", []):
            for flight in group:
                if flight.get("FareList") and flight.get("Segments"):
                    flights.append(flight)
    except Exception:
        pass
    return flights



def extract_baggage(fare: dict) -> dict:
    """
    Extract cabin & check-in baggage safely from FareList
    """
    try:
        baggage = fare.get("SeatBaggage", [[]])[0][0]
        return {
            "cabin": baggage.get("Cabin", "Not specified"),
            "check_in": baggage.get("CheckIn", "Not specified"),
        }
    except Exception:
        return {
            "cabin": "Not specified",
            "check_in": "Not specified",
        }
    


def _find_list_in_response(obj: Any) -> list:
    """Recursively search for the first non-empty list of dicts that looks like flight entries."""
    if isinstance(obj, list):
        if obj and all(isinstance(i, dict) for i in obj):
            return obj
        # search inside list items
        for item in obj:
            found = _find_list_in_response(item)
            if found:
                return found
    if isinstance(obj, dict):
        # common keys
        for key in ("flights", "results", "airOptions", "pricedItineraries", "data", "itineraries"):
            if key in obj and isinstance(obj[key], list) and obj[key]:
                return obj[key]
        for v in obj.values():
            found = _find_list_in_response(v)
            if found:
                return found
    return []


def _is_empty_flight_snippet(api_response: dict) -> bool:
    flight = extract_first_flight(api_response)
    if not flight:
        return True

    return not flight.get("FareList") or not flight.get("Segments")


def normalize_city_to_iata(city: str) -> str:
    if not city:
        return city
    city_clean = city.strip().lower()
    return CITY_TO_IATA.get(city_clean, city.upper())

def extract_passenger_fares(fare: dict) -> dict:
    breakdown = fare.get("FareBreakdown", {})
    result = {}

    if "ADT" in breakdown:
        adt = breakdown["ADT"]
        result["Adult"] = {
            "count": adt.get("PassengerCount", 0),
            "base": adt.get("BaseFare", 0),
            "tax": adt.get("Tax", 0),
            "total": adt.get("BaseFare", 0) + adt.get("Tax", 0),
        }

    if "CHD" in breakdown:
        chd = breakdown["CHD"]
        result["Child"] = {
            "count": chd.get("PassengerCount", 0),
            "base": chd.get("BaseFare", 0),
            "tax": chd.get("Tax", 0),
            "total": chd.get("BaseFare", 0) + chd.get("Tax", 0),
        }

    if "INF" in breakdown:
        inf = breakdown["INF"]
        result["Infant"] = {
            "count": inf.get("PassengerCount", 0),
            "base": inf.get("BaseFare", 0),
            "tax": inf.get("Tax", 0),
            "total": inf.get("BaseFare", 0) + inf.get("Tax", 0),
        }

    return result


def format_single_flight(flight: dict, index: int) -> str:
    all_trips = flight.get("Segments", [])
    fares = flight["FareList"]

    lines = [f"✈️ Flight Option {index}"]

    for trip_idx, segments in enumerate(all_trips):
        trip_type = "Outbound" if trip_idx == 0 else "Return"
        lines.append(f"\n🛫 {trip_type} Journey:")

        first_seg = segments[0]
        last_seg = segments[-1]

        airline = first_seg["Airline"]["AirlineName"]
        origin = first_seg["Origin"]["CityCode"]
        destination = last_seg["Destination"]["CityCode"]
        duration = first_seg["TotalDuration"]

        stops = len(segments) - 1
        if stops == 0:
            stop_text = "Direct"
            via_text = ""
        else:
            via_cities = [seg["Destination"]["CityName"] for seg in segments[:-1]]
            stop_text = f"{stops} stop(s)"
            via_text = f"via {', '.join(via_cities)}"

        lines.extend([
            f" Airline: {airline}",
            f" Route: {origin} → {destination}",
            f" Stops: {stop_text} {via_text}".strip(),
            f" Duration: {duration // 60}h {duration % 60}m",
        ])

    #  Fare details (combined fare for round trip)
    cheapest_fare = min(fares, key=lambda f: f["PublishedPrice"])
    baggage = extract_baggage(cheapest_fare)
    passenger_fares = extract_passenger_fares(cheapest_fare)

    lines.append("\n Baggage:")
    lines.append(f" Cabin: {baggage['cabin']} | Check-in: {baggage['check_in']}")

    lines.append("\n Fare breakup:")
    for ptype, info in passenger_fares.items():
        lines.append(
            f" - {ptype} x{info['count']}: INR {info['total']} "
            f"(Base {info['base']} + Tax {info['tax']})"
        )

    lines.append(
        f"\n Total Price: INR {cheapest_fare['PublishedPrice']} ({cheapest_fare['FareType']})"
    )

    return "\n".join(lines)




def _format_flights_summary(api_response: dict) -> str:
    flights = extract_all_flights(api_response)

    if not flights:
        return "No flights found."

    # Sort flights by cheapest PublishedPrice
    flights_sorted = sorted(
        flights,
        key=lambda f: min(fare["PublishedPrice"] for fare in f["FareList"])
    )

    top_5 = flights_sorted[:5]

    lines = [" Cheapest 5 flight options:\n"]

    for idx, flight in enumerate(top_5, start=1):
        lines.append(format_single_flight(flight, idx))
        lines.append("")  # spacing between flights

    return "\n".join(lines)




def _fetch_flight_data(
    adults: int,
    children: int,
    infants: int,
    departure_date: str,
    origin: str,
    destination: str,
    username: str,
    password: str,
    trip_type: str = "one-way",
    return_date: str | None = None,
) -> dict:
    """Call the external flight search API with retry + timeout + normalization"""

    if not username or not password:
        raise EnvironmentError(
            "Flight API credentials not configured (PUBLIC_TTS_API_USERNAME/PUBLIC_TTS_API_PASSWORD)"
        )

    url = "https://api.bdsd.technology/api/airservice/rest/search"

    #  Normalize cities → IATA
    origin_iata = normalize_city_to_iata(origin)
    destination_iata = normalize_city_to_iata(destination)

    try:
        departure_date = datetime.fromisoformat(departure_date).date().isoformat()
    except Exception:
        pass

    app.logger.info(
        "CITY NORMALIZATION → %s → %s | %s → %s",
        origin, origin_iata,
        destination, destination_iata
    )

    # Build AirSegments dynamically
    air_segments = [
        {
            "Origin": origin_iata,
            "Destination": destination_iata,
            "PreferredTime": f"{departure_date}T00:00:00",
        }
    ]

    journey_type = 1

    # Add return segment if round trip
    if trip_type == "two-way" and return_date:
        journey_type = 2
        air_segments.append(
            {
                "Origin": destination_iata,
                "Destination": origin_iata,
                "PreferredTime": f"{return_date}T00:00:00",
            }
        )

    body = {
        "UserIp": "122.161.64.143",
        "Adult": adults,
        "Child": children,
        "Infant": infants,
        "DirectFlight": False,
        "JourneyType": journey_type,
        "PreferredCarriers": [],
        "CabinClass": 1,
        "SeriesFare": None,
        "AirSegments": air_segments,
    }


    headers = {
        "Content-Type": "application/json",
        "Username": username,
        "Password": password,
    }

    #  Log final request
    app.logger.info("FINAL FLIGHT REQUEST →\n%s", json.dumps(body, indent=2))

    for attempt in range(1, 4):
        try:
            response = requests.post(
                url,
                json=body,
                headers=headers,
                timeout=30
            )

            app.logger.info(
                "flight_api attempt=%s status=%s",
                attempt,
                response.status_code
            )

            response.raise_for_status()
            payload = response.json()

            app.logger.info("FLIGHT API RESPONSE RECEIVED (attempt %s)", attempt)

            return payload

        except requests.exceptions.Timeout:
            app.logger.warning(
                "Flight API timeout on attempt %s/3",
                attempt
            )

        except requests.exceptions.RequestException as exc:
            app.logger.error(
                "Flight API error on attempt %s: %s",
                attempt,
                exc
            )

            if exc.response is not None:
                app.logger.error("Status Code: %s", exc.response.status_code)
                app.logger.error("Response Text: %s", exc.response.text)

            break

    #  All retries failed
    raise TimeoutError("Flight API timed out after 3 attempts")