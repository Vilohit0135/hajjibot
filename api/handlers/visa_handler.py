from typing import Dict
from helpers.visa_helpers import (
    _generic_visa_response,
    _is_empty_visa_snippet,
    _fetch_visa_data,
    _format_price_summary,
    _format_price_with_ai,
    _visa_context_snippet,
)
from flask import current_app as app
import os


VISA2FLY_TOKEN = os.getenv("VISA2FLY_TOKEN", "JFdxzylwEkvHH")



def _handle_visa(state: Dict) -> Dict:
    model = state["model"]
    question = state["question"]
    visa_context = state.get("visa_context")
    resolved_country = state.get("resolved_country") or (visa_context or {}).get("country")

    if not resolved_country:
        state["answer"] = (
            "Yes, we provide visa services from Marhaba. "
            "Please let me know the destination country and I will fetch pricing and requirements."
        )
        return state

    if not visa_context or visa_context.get("country") != resolved_country:
        try:
            visa_data = _fetch_visa_data(resolved_country, VISA2FLY_TOKEN)
        except Exception:
            state["answer"] = _generic_visa_response(resolved_country, question)
            return state
        visa_context = {
            "country": resolved_country,
            "data": visa_data,
        }
        state["visa_context"] = visa_context
        state["visa_context_updated"] = True
        try:
            state["answer"] = _format_price_with_ai(model, visa_data, resolved_country, question)
        except Exception:
            state["answer"] = _format_price_summary(visa_data, resolved_country)
        return state

    visa_data = (visa_context or {}).get("data", {})
    visa_snippet = _visa_context_snippet(question, visa_data)
    if _is_empty_visa_snippet(visa_snippet):
        state["answer"] = _generic_visa_response(resolved_country, question)
        return state

    prompt = (
        "You are a visa assistant. Use only the provided visa data to answer the user. "
        "If the data does not contain the answer, say so clearly. "
        "Keep the answer short (2-4 sentences).\n\n"
        f"Visa Country: {visa_context.get('country')}\n"
        f"Visa Data: {visa_snippet}\n\n"
        f"User Question: {question}\n"
    )
    response = model.generate_content(prompt)
    state["answer"] = response.text
    return state
