from typing import Dict
from api.helpers.visa_helpers import _extract_country
from flask import current_app as app


def _is_flight_question(text: str) -> bool:
    """Check if the question is asking for flight details/booking"""
    lowered = text.lower()
    flight_keywords = [
        "flight", "book flight", "flight booking",
        "one way flight", "round trip flight",
        "return flight", "airfare",
        "departure flight", "arrival flight"
    ]

    for keyword in flight_keywords:
        if keyword in lowered:
            return True
    return False



def _detect_intent(state: Dict) -> Dict:
    model = state["model"]
    question = state["question"]
    flight_context = state.get("flight_context")
    hotel_context = state.get("hotel_context")
    app.logger.info("intent_classifier initial_state=%s", state)

    # Check if user is already in flight booking mode
    if flight_context:
        state["intent"] = "flight"
        return state
    
    # Check if user is already in hotel booking mode
    if hotel_context:
        state["intent"] = "hotel"
        return state
    
    resolved_country = _extract_country(question)
    state["resolved_country"] = resolved_country
    if resolved_country:
        state["intent"] = "visa"
        return state
    
    # Check for flight questions
    if _is_flight_question(question):
        state["intent"] = "flight"
        return state
    
    hotel_keywords = ["hotel", "hotels", "accommodation", "stay", "room booking"]

    if any(k in question.lower() for k in hotel_keywords):
        state["intent"] = "hotel"
        state["hotel_context"] = {"active": True}
        return state
    
    prompt = (
        "Classify the user intent into one of: visa, general. "
        "Respond with only the label.\n\n"
        f"User Question: {question}\n"
    )
    response = model.generate_content(prompt)
    label = response.text.strip().lower()
    state["intent"] = "visa" if "visa" in label else "general"
    app.logger.info("intent_classifier final_state=%s", state)
    
    return state
