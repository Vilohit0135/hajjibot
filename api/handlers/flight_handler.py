from flask import current_app as app
from typing import Optional
import os

from api.helpers.flight_helpers import (
    _format_flights_summary,
    _fetch_flight_data,
)

# handlers/flight_handler.py


def _get_next_flight_question(question_index: int, trip_type: str | None = None) -> Optional[str]:
    questions = [
        "Is this a one-way trip or a round trip?",
        "How many adults will be traveling?",
        "How many children will be traveling?",
        "What are the ages of the children? (comma-separated)",
        "What is your departure date? (YYYY-MM-DD format)",
        "Which city are you departing from?",
        "Which city are you traveling to?",
        "What is your return date? (YYYY-MM-DD format)",
    ]

    # 🚫 Never ask return date for one-way
    if trip_type == "one-way" and question_index == 7:
        return None

    return questions[question_index] if question_index < len(questions) else None


def _handle_flight(state):
    """Handle flight booking multi-turn conversation"""

    question = state["question"]
    flight_context = state.get("flight_context") or {}
    flight_question_index = state.get("flight_question_index", 0)

    app.logger.info(
        "FLIGHT STATE | index=%s | context=%s",
        flight_question_index,
        flight_context,
    )

    # Initialize context
    flight_context.setdefault("trip_type", None)
    flight_context.setdefault("return_date", None)
    flight_context.setdefault("adults", None)
    flight_context.setdefault("children", None)
    flight_context.setdefault("children_ages", [])
    flight_context.setdefault("departure_date", None)
    flight_context.setdefault("departure_city", None)
    flight_context.setdefault("arrival_city", None)

    state["flight_context"] = flight_context
    text = question.lower()

    # 0️⃣ Trip type
    if flight_question_index == 0 and flight_context["trip_type"] is None:
        if "one-way" in text or text.strip() == "one":
            flight_context["trip_type"] = "one-way"
        elif "two-way" in text or "round" in text:
            flight_context["trip_type"] = "two-way"
        else:
            state["answer"] = _get_next_flight_question(0)
            return state

        state["flight_question_index"] = 1
        state["answer"] = _get_next_flight_question(1)
        return state

    # 1️⃣ Adults
    if flight_question_index == 1 and flight_context["adults"] is None:
        for w in text.split():
            if w.isdigit():
                flight_context["adults"] = int(w)
                state["flight_question_index"] = 2
                state["answer"] = _get_next_flight_question(2)
                return state
        state["answer"] = _get_next_flight_question(1)
        return state

    # 2️⃣ Children
    if flight_question_index == 2 and flight_context["children"] is None:
        for w in text.split():
            if w.isdigit():
                flight_context["children"] = int(w)

                # ✅ Skip age question if 0 children
                if flight_context["children"] == 0:
                    flight_context["children_ages"] = []
                    state["flight_question_index"] = 4
                    state["answer"] = _get_next_flight_question(4)
                    return state

                state["flight_question_index"] = 3
                state["answer"] = _get_next_flight_question(3)
                return state

        state["answer"] = _get_next_flight_question(2)
        return state

    # 3️⃣ Children ages
    if (
        flight_question_index == 3
        and flight_context["children"] > 0
        and not flight_context["children_ages"]
    ):
        import re

        ages = re.findall(r"\d+", question)
        if ages:
            flight_context["children_ages"] = [int(a) for a in ages]
            state["flight_question_index"] = 4
            state["answer"] = _get_next_flight_question(4)
            return state

        state["answer"] = _get_next_flight_question(3)
        return state

    # 4️⃣ Departure date
    if flight_question_index == 4 and flight_context["departure_date"] is None:
        import re

        m = re.search(r"\d{4}-\d{2}-\d{2}", question)
        if m:
            flight_context["departure_date"] = m.group()
            state["flight_question_index"] = 5
            state["answer"] = _get_next_flight_question(5)
            return state

        state["answer"] = _get_next_flight_question(4)
        return state

    # 5️⃣ Departure city
    if flight_question_index == 5 and flight_context["departure_city"] is None:
        flight_context["departure_city"] = question.strip()
        state["flight_question_index"] = 6
        state["answer"] = _get_next_flight_question(6)
        return state

    # 6️⃣ Arrival city
    if flight_question_index == 6 and flight_context["arrival_city"] is None:
        flight_context["arrival_city"] = question.strip()

        children_ages = flight_context["children_ages"]
        total_children = flight_context["children"] or 0
        infants = min(sum(1 for a in children_ages if a < 2), total_children)
        child_param = total_children - infants

        # ✈️ ONE-WAY → FETCH & EXIT
        if flight_context["trip_type"] == "one-way":
            api_response = _fetch_flight_data(
                adults=flight_context["adults"],
                children=child_param,
                infants=infants,
                departure_date=flight_context["departure_date"],
                origin=flight_context["departure_city"],
                destination=flight_context["arrival_city"],
                username=os.getenv("PUBLIC_TTS_API_USERNAME"),
                password=os.getenv("PUBLIC_TTS_API_PASSWORD"),
                trip_type="one-way",
            )

            state["answer"] = (
                f"Perfect! Here's what I found for "
                f"{flight_context['departure_city']} → {flight_context['arrival_city']}:\n\n"
                f"{_format_flights_summary(api_response)}"
            )
            return state  # 🔒 critical return

        # 🔁 TWO-WAY → ASK RETURN DATE
        state["flight_question_index"] = 7
        state["answer"] = _get_next_flight_question(7, "two-way")
        return state

    # 7️⃣ Return date → FETCH round trip
    if (
        flight_question_index == 7
        and flight_context["trip_type"] == "two-way"
        and flight_context["return_date"] is None
    ):
        import re

        m = re.search(r"\d{4}-\d{2}-\d{2}", question)
        if not m:
            state["answer"] = _get_next_flight_question(7, "two-way")
            return state

        flight_context["return_date"] = m.group()

        children_ages = flight_context["children_ages"]
        total_children = flight_context["children"] or 0
        infants = min(sum(1 for a in children_ages if a < 2), total_children)
        child_param = total_children - infants

        api_response = _fetch_flight_data(
            adults=flight_context["adults"],
            children=child_param,
            infants=infants,
            departure_date=flight_context["departure_date"],
            origin=flight_context["departure_city"],
            destination=flight_context["arrival_city"],
            username=os.getenv("PUBLIC_TTS_API_USERNAME"),
            password=os.getenv("PUBLIC_TTS_API_PASSWORD"),
            trip_type="two-way",
            return_date=flight_context["return_date"],
        )

        state["answer"] = (
            f"Perfect! Here's what I found for "
            f"{flight_context['departure_city']} → {flight_context['arrival_city']} "
            f"(Round Trip):\n\n{_format_flights_summary(api_response)}"
        )
        return state
    # 🛑 FINAL SAFETY NET — NEVER RETURN NULL ANSWER
    if "answer" not in state or state["answer"] is None:
        next_q = _get_next_flight_question(
            state.get("flight_question_index", 0),
            flight_context.get("trip_type")
        )
        if next_q:
            state["answer"] = next_q
        else:
            state["answer"] = "Please continue, I’m processing your flight details."

    return state
