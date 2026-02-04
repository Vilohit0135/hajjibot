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
        "What is your check-in date? (YYYY-MM-DD format)",          # 0
        "What is your check-out date? (YYYY-MM-DD format)",         # 1
        "Which city are you looking for a hotel in?",               # 2
        "How many rooms do you need?",                              # 3
        "How many adults will be staying per room?",                # 4
        "How many children will be staying per room?",              # 5
        "What are the ages of the children? (comma-separated)",     # 6
        "What hotel rating do you prefer? (1 to 5)",                # 7
        "What is your nationality? (e.g. IN, PK, SA)",              # 8
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
    hotel_context.setdefault("adults", None)
    hotel_context.setdefault("children", None)
    hotel_context.setdefault("children_ages", [])
    hotel_context.setdefault("min_rating", 1)
    hotel_context.setdefault("max_rating", 5)
    hotel_context.setdefault("guest_nationality", None)

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

    # 4️⃣ Adults per room
    if hotel_question_index == 4 and hotel_context["adults"] is None:
        for w in text.split():
            if w.isdigit():
                hotel_context["adults"] = int(w)

                # move to children question
                state["hotel_question_index"] = 5
                state["answer"] = _get_next_hotel_question(5)
                return state

        # invalid input → ask again
        state["answer"] = _get_next_hotel_question(4)
        return state

    # 5️⃣ Children per room
    if hotel_question_index == 5 and hotel_context["children"] is None:
        for w in text.split():
            if w.isdigit():
                hotel_context["children"] = int(w)

                # ✅ No children → skip ages
                if hotel_context["children"] == 0:
                    hotel_context["children_ages"] = []
                    state["hotel_question_index"] = 7   # go to rating
                    state["answer"] = _get_next_hotel_question(7)
                    return state

                # children > 0 → ask ages
                state["hotel_question_index"] = 6
                state["answer"] = _get_next_hotel_question(6)
                return state

        # invalid input → ask again
        state["answer"] = _get_next_hotel_question(5)
        return state
    
    # 6️⃣ Children ages
    if (
        hotel_question_index == 6
        and hotel_context["children"] > 0
        and not hotel_context["children_ages"]
    ):
        ages = re.findall(r"\d+", text)

        if len(ages) != hotel_context["children"]:
            state["answer"] = (
                f"Please enter exactly {hotel_context['children']} age(s), "
                f"comma-separated."
            )
            return state

        hotel_context["children_ages"] = [int(a) for a in ages]

        # move to rating
        state["hotel_question_index"] = 7
        state["answer"] = _get_next_hotel_question(7)
        return state

    
    # 7️⃣ Hotel rating preference
    if hotel_question_index == 7 and hotel_context["max_rating"] == 5:
        for w in text.split():
            if w.isdigit():
                rating = int(w)

                if 1 <= rating <= 5:
                    hotel_context["min_rating"] = 1
                    hotel_context["max_rating"] = rating

                    # move to nationality
                    state["hotel_question_index"] = 8
                    state["answer"] = _get_next_hotel_question(8)
                    return state

        # invalid input → ask again
        state["answer"] = _get_next_hotel_question(7)
        return state

    # 8️⃣ Guest nationality
    if hotel_question_index == 8 and hotel_context["guest_nationality"] is None:
        code = text.strip().upper()

        # very basic validation: 2-letter country code
        if re.fullmatch(r"[A-Z]{2}", code):
            hotel_context["guest_nationality"] = code

            # 🔥 BUILD ROOM_GUESTS STRUCTURE
            hotel_context["room_guests"] = [
                {
                    "Adult": hotel_context["adults"],
                    "Child": hotel_context["children"],
                    "ChildAge": hotel_context["children_ages"],
                }
            ]

            # 🔥 CALL HOTEL API
            api_response = _fetch_hotel_data(
                check_in=hotel_context["check_in"],
                check_out=hotel_context["check_out"],
                city_name=hotel_context["city_name"],
                rooms=hotel_context["rooms"],
                room_guests=hotel_context["room_guests"],
                guest_nationality=hotel_context["guest_nationality"],
                min_rating=hotel_context["min_rating"],
                max_rating=hotel_context["max_rating"],
                username=os.getenv("PUBLIC_TTS_API_USERNAME"),
                password=os.getenv("PUBLIC_TTS_API_PASSWORD"),
            )

            state["answer"] = (
                f"Here are the best hotel options in "
                f"{hotel_context['city_name']}:\n\n"
                f"{_format_hotels_summary(api_response)}"
            )

            # 🧹 CLEAN EXIT
            state["hotel_context"] = None
            state["hotel_question_index"] = 0
            return state

        # invalid input → ask again
        state["answer"] = _get_next_hotel_question(8)
        return state

    # if hotel_question_index == 4 and not hotel_context["room_guests"]:
    #     adults = 0
    #     children = 0

    #     nums = re.findall(r"\d+", text)
    #     if nums:
    #         adults = int(nums[0])
    #         if len(nums) > 1:
    #             children = int(nums[1])

    #         hotel_context["room_guests"] = [
    #             {
    #                 "Adult": adults,
    #                 "Child": children,
    #                 "ChildAge": [],
    #             }
    #         ]

    #         # 🔥 CALL HOTEL API
    #         api_response = _fetch_hotel_data(
    #             check_in=hotel_context["check_in"],
    #             check_out=hotel_context["check_out"],
    #             city_name=hotel_context["city_name"],
    #             rooms=hotel_context["rooms"],
    #             room_guests=hotel_context["room_guests"],
    #             guest_nationality="IN",
    #             username=os.getenv("PUBLIC_TTS_API_USERNAME"),
    #             password=os.getenv("PUBLIC_TTS_API_PASSWORD"),
    #         )

    #         state["answer"] = (
    #             f" Here are the best hotel options in "
    #             f"{hotel_context['city_name']}:\n\n"
    #             f"{_format_hotels_summary(api_response)}"
    #         )

    #         # 🧹 CLEAN EXIT
    #         state["hotel_context"] = None
    #         state["hotel_question_index"] = 0
    #         return state

    #     state["answer"] = _get_next_hotel_question(4)
    #     return state
    
    if "answer" not in state or state["answer"] is None:
        next_q = _get_next_hotel_question(
            state.get("hotel_question_index", 0)
        )
        state["answer"] = next_q or "Please continue, I’m processing your hotel request."

    return state
