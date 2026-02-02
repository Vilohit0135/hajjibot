from typing import Dict
from api.helpers.visa_helpers import _extract_country
from flask import current_app as app


def _is_flight_question(text: str) -> bool:
    """Check if the question is asking for flight details/booking"""
    lowered = text.lower()
    flight_keywords = [
        "flight", "book flight", "flights", "airline", "airfare", 
        "flying", "travel", "trip", "booking", "reserve", "departure",
        "arrival", "from", "to", "when", "how much", "price",  "flight", "one way", "round trip", "two-way", "return flight"
    ]
    for keyword in flight_keywords:
        if keyword in lowered:
            return True
    return False



def _detect_intent(state: Dict) -> Dict:
    model = state["model"]
    question = state["question"]
    flight_context = state.get("flight_context")
    flight_question_index = state.get("flight_question_index", 0)
    
    # Check if user is already in flight booking mode
    if flight_context:
        state["intent"] = "flight"
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
