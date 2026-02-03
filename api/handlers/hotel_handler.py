from flask import current_app as app
from typing import Optional
import os
import re

from api.helpers.hotel_helpers import (
    _fetch_hotel_data,
    _format_hotels_summary,
)
from api.data.hotel_city_resolver import (
    resolve_hotel_city,
    suggest_hotel_cities,
)


def _get_next_hotel_question(question_index: int) -> Optional[str]:
    questions = [
        "What is your check-in date? (YYYY-MM-DD format)",
        "What is your check-out date? (YYYY-MM-DD format)",
        "Which city are you looking for a hotel in?",
        "How many rooms do you need?",
        "How many adults and children per room? (e.g. 2 adults, 1 child)",
    ]
    return questions[question_index] if question_index < len(questions) else None


def _handle_hotel(state):
    """
    Handle hotel booking multi-turn conversation
    """

    question = state["question"]
    hotel_context = state.get("hotel_context") or {}
    hotel_question_index = state.get("hotel_question_index", 0)

    app.logger.info(
        "HOTEL STATE | index=%s | context=%s",
        hotel_question_index,
        hotel_context,
    )

    # Initialize hotel context
    hotel_context.setdefault("active", True)
    hotel_context.setdefault("check_in", None)
    hotel_context.setdefault("check_out", None)
    hotel_context.setdefault("city_name", None)
    hotel_context.setdefault("city_id", None)
    hotel_context.setdefault("country_code", None)
    hotel_context.setdefault("rooms", None)
    hotel_context.setdefault("room_guests", [])

    state["hotel_context"] = hotel_context
    text = question.strip().lower()
    
    
    if hotel_question_index == 0 and hotel_context["check_in"] is None:
        m = re.search(r"\d{4}-\d{2}-\d{2}", question)
        if m:
            hotel_context["check_in"] = m.group()
            state["hotel_question_index"] = 1
            state["answer"] = _get_next_hotel_question(1)
            return state

        state["answer"] = _get_next_hotel_question(0)
        return state
    
    if hotel_question_index == 1 and hotel_context["check_out"] is None:
        m = re.search(r"\d{4}-\d{2}-\d{2}", question)
        if m:
            hotel_context["check_out"] = m.group()
            state["hotel_question_index"] = 2
            state["answer"] = _get_next_hotel_question(2)
            return state

        state["answer"] = _get_next_hotel_question(1)
        return state


    if hotel_question_index == 2 and hotel_context["city_id"] is None:
        city_info = resolve_hotel_city(question)

        if not city_info:
            suggestions = suggest_hotel_cities(question)
            state["answer"] = (
                f"I couldn't find that city for hotels. "
                f"Did you mean: {', '.join(suggestions)}?"
                if suggestions else
                "Please enter a valid city name."
            )
            return state

        hotel_context["city_name"] = question.strip()
        hotel_context["city_id"] = city_info["city_id"]
        hotel_context["country_code"] = city_info["country_code"]

        state["hotel_question_index"] = 3
        state["answer"] = _get_next_hotel_question(3)
        return state


    if hotel_question_index == 3 and hotel_context["rooms"] is None:
        for w in text.split():
            if w.isdigit():
                hotel_context["rooms"] = int(w)
                state["hotel_question_index"] = 4
                state["answer"] = _get_next_hotel_question(4)
                return state

        state["answer"] = _get_next_hotel_question(3)
        return state


    if hotel_question_index == 4 and not hotel_context["room_guests"]:
        adults = 0
        children = 0

        nums = re.findall(r"\d+", text)
        if nums:
            adults = int(nums[0])
            if len(nums) > 1:
                children = int(nums[1])

            hotel_context["room_guests"] = [
                {
                    "Adult": adults,
                    "Child": children,
                    "ChildAge": [],
                }
            ]

            # 🔥 CALL HOTEL API
            api_response = _fetch_hotel_data(
                check_in=hotel_context["check_in"],
                check_out=hotel_context["check_out"],
                city_name=hotel_context["city_name"],
                rooms=hotel_context["rooms"],
                room_guests=hotel_context["room_guests"],
                guest_nationality="IN",
                username=os.getenv("PUBLIC_TTS_API_USERNAME"),
                password=os.getenv("PUBLIC_TTS_API_PASSWORD"),
            )

            state["answer"] = (
                f"🏨 Here are the best hotel options in "
                f"{hotel_context['city_name']}:\n\n"
                f"{_format_hotels_summary(api_response)}"
            )

            # 🧹 CLEAN EXIT
            state["hotel_context"] = None
            state["hotel_question_index"] = 0
            return state

        state["answer"] = _get_next_hotel_question(4)
        return state
    
    if "answer" not in state or state["answer"] is None:
        next_q = _get_next_hotel_question(
            state.get("hotel_question_index", 0)
        )
        state["answer"] = next_q or "Please continue, I’m processing your hotel request."

    return state
