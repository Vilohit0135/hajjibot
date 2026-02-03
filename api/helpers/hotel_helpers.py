import json
import requests
from datetime import datetime
from flask import current_app as app
from typing import List, Dict

from api.data.hotel_city_resolver import (
    resolve_hotel_city,
    suggest_hotel_cities,
)


def format_single_hotel(hotel: dict, index: int) -> str:
    name = hotel.get("HotelName", "Unknown Hotel")
    rating = hotel.get("StarRating", "N/A")
    address = hotel.get("HotelAddress", "Address not available")
    image = hotel.get("HotelPicture")
    price = hotel.get("Price", {})

    offered_price = price.get("OfferedPrice") or price.get("PublishedPrice")
    currency = "INR"

    lines = [
        f" Hotel Option {index}",
        f" Name: {name}",
        f" Rating: {int(rating) if isinstance(rating, int) else rating}",
        f" Address: {address}",
        f" Price: {currency} {round(offered_price, 2) if offered_price else 'N/A'}",
    ]

    if image:
        lines.append(f" Image: {image}")

    return "\n".join(lines)

def _format_hotels_summary(api_response: dict) -> str:
    results = api_response.get("Result", [])

    if not results:
        return "No hotels found for the selected criteria."

    # Sort by cheapest offered price
    def get_price(h):
        price = h.get("Price", {})
        return price.get("OfferedPrice") or price.get("PublishedPrice") or float("inf")

    hotels_sorted = sorted(results, key=get_price)
    top_5 = hotels_sorted[:5]

    lines = [" Top hotel options:\n"]

    for idx, hotel in enumerate(top_5, start=1):
        lines.append(format_single_hotel(hotel, idx))
        lines.append("")

    return "\n".join(lines)


def _fetch_hotel_data(
    check_in: str,
    check_out: str,
    city_name: str,
    rooms: int,
    room_guests: List[Dict],
    guest_nationality: str,
    username: str,
    password: str,
    min_rating: int = 1,
    max_rating: int = 5,
) -> dict:
    """Call external hotel search API with retry + timeout"""

    if not username or not password:
        raise EnvironmentError(
            "Hotel API credentials not configured (PUBLIC_TTS_API_USERNAME/PUBLIC_TTS_API_PASSWORD)"
        )

    city_info = resolve_hotel_city(city_name)
    if not city_info:
        suggestions = suggest_hotel_cities(city_name)
        raise ValueError(
            f"City not recognized for hotels.\n"
            f"Suggestions: {suggestions}"
        )

    city_id = city_info["city_id"]
    country_code = city_info["country_code"]

    try:
        check_in_date = datetime.fromisoformat(check_in).date()
        check_out_date = datetime.fromisoformat(check_out).date()
        no_of_nights = (check_out_date - check_in_date).days
    except Exception:
        raise ValueError("Invalid check-in or check-out date format.")

    url = "https://api.bdsd.technology/api/hotelservice/rest/search"

    body = {
        "CheckInDate": check_in_date.isoformat(),
        "CheckOutDate": check_out_date.isoformat(),
        "NoOfNights": no_of_nights,
        "CountryCode": country_code,
        "DestinationCityId": city_id,
        "ResultCount": None,
        "GuestNationality": guest_nationality,
        "NoOfRooms": rooms,
        "RoomGuests": room_guests,
        "MinRating": min_rating,
        "MaxRating": max_rating,
        "UserIp": "117.99.10.7",
    }

    headers = {
        "Content-Type": "application/json",
        "Username": username,
        "Password": password,
    }

    app.logger.info("FINAL HOTEL REQUEST →\n%s", json.dumps(body, indent=2))

    for attempt in range(1, 4):
        try:
            response = requests.post(
                url,
                json=body,
                headers=headers,
                timeout=30,
            )

            app.logger.info(
                "hotel_api attempt=%s status=%s",
                attempt,
                response.status_code,
            )

            response.raise_for_status()
            payload = response.json()

            app.logger.info("HOTEL API RESPONSE RECEIVED (attempt %s)", attempt)
            return payload

        except requests.exceptions.Timeout:
            app.logger.warning(
                "Hotel API timeout on attempt %s/3",
                attempt,
            )

        except requests.exceptions.RequestException as exc:
            app.logger.error(
                "Hotel API error on attempt %s: %s",
                attempt,
                exc,
            )

            if exc.response is not None:
                app.logger.error("Status Code: %s", exc.response.status_code)
                app.logger.error("Response Text: %s", exc.response.text)

            break

    raise TimeoutError("Hotel API timed out after 3 attempts")
