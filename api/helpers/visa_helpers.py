# helpers/visa_helpers.py

import requests
from typing import Optional, Any
from flask import current_app as app

from api.data.visa_data import VISA_EXPERT_DISCLAIMER
from api.data.visa_data import VISA_COUNTRY_LOOKUP



def _extract_country(text: str) -> Optional[str]:
    lowered = text.lower()
    for name in sorted(VISA_COUNTRY_LOOKUP.keys(), key=len, reverse=True):
        if name in lowered:
            return VISA_COUNTRY_LOOKUP[name]
    return None



def _generic_visa_response(country: Optional[str], question: str) -> str:
    lowered = question.lower()
    base = f"Yes, we provide visa services for {country}." if country else "Yes, we provide visa services."
    parts = [base]

    if any(term in lowered for term in ["document", "requirement", "requirements"]):
        parts.append(
            "Typical requirements include a valid passport, recent photos, a completed application form, "
            "and supporting travel/financial documents."
        )
    elif any(term in lowered for term in ["time", "processing", "duration"]):
        parts.append(
            "Processing times vary by nationality and visa type, and expedited options may be available."
        )
    elif any(term in lowered for term in ["price", "cost", "fee", "fees"]):
        parts.append(
            "Visa fees vary based on visa type, duration, and processing speed."
        )
    else:
        parts.append(
            "Requirements, timelines, and fees vary by nationality and visa type."
        )

    parts.append(VISA_EXPERT_DISCLAIMER)
    return " ".join(parts).strip()



def _is_empty_visa_snippet(snippet: dict) -> bool:
    if not snippet:
        return True
    for value in snippet.values():
        if isinstance(value, dict) and value:
            return False
        if isinstance(value, list) and value:
            return False
        if value not in (None, "", {}, []):
            return False
    return True


def _fetch_visa_data(country: str, token: str) -> dict:
    url = f"https://devapi.visa2fly.com/api/b2b/partner/visa/{country}"
    response = requests.get(
        url,
        headers={
            "token": token,
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    app.logger.info("visa_api status=%s url=%s", response.status_code, url)
    response.raise_for_status()
    payload = response.json()
    app.logger.info("visa_api payload=%s", payload)
    if payload.get("code") != "0":
        raise ValueError(payload.get("message") or "Visa API returned an error")
    return payload.get("data", {})



def _format_price_summary(visa_data: dict, country: str) -> str:
    quotes = visa_data.get("displayQuotes", [])
    if not quotes:
        return _generic_visa_response(country, "price")
    lowest_price = min(
        (quote.get("basePrice") for quote in quotes if isinstance(quote.get("basePrice"), (int, float))),
        default=None,
    )
    currency = quotes[0].get("currency", "") if quotes else ""
    lines = []
    for quote in quotes[:3]:
        currency = quote.get("currency", currency)
        base_price = quote.get("basePrice", "")
        purpose = quote.get("purpose", "")
        entry_type = quote.get("entryType", "")
        stay_period = quote.get("stayPeriod", "")
        lines.append(
            f"{purpose} ({entry_type}, {stay_period}): {currency} {base_price}"
        )
    joined = "; ".join([line for line in lines if line.strip()])
    low_text = f"Prices start as low as {currency} {lowest_price}." if lowest_price is not None else ""
    return (
        f"Yes, we provide visa services for {country}. {low_text} "
        f"Here are current prices: {joined}."
    ).strip()



def _visa_context_snippet(question: str, visa_data: dict) -> dict:
    lowered = question.lower()
    if "document" in lowered or "requirement" in lowered:
        return {"documentRequired": visa_data.get("documentRequired", {})}
    if "faq" in lowered or "question" in lowered:
        return {"faqs": visa_data.get("faqs", {})}
    if "important" in lowered or "info" in lowered:
        return {"importantInfo": visa_data.get("importantInfo", [])}
    if "price" in lowered or "cost" in lowered or "fee" in lowered:
        return {"displayQuotes": visa_data.get("displayQuotes", [])}
    return visa_data


def _format_price_with_ai(model: Any, visa_data: dict, country: str, question: str) -> str:
    quotes = visa_data.get("displayQuotes", [])[:5]
    if not quotes:
        raise ValueError("No pricing data")
    min_price = min(
        (quote.get("basePrice") for quote in quotes if isinstance(quote.get("basePrice"), (int, float))),
        default=None,
    )
    currency = quotes[0].get("currency", "") if quotes else ""
    price_lines = []
    for quote in quotes[:4]:
        purpose = quote.get("purpose", "")
        entry_type = quote.get("entryType", "")
        stay_period = quote.get("stayPeriod", "")
        base_price = quote.get("basePrice", "")
        quote_currency = quote.get("currency", currency)
        price_lines.append(f"{purpose} ({entry_type}, {stay_period}): {quote_currency} {base_price}")
    prompt = (
        "You are a visa assistant. Use only the provided pricing data. "
        "Reply to the user's question, confirm we provide visa services for the country, "
        "then say prices start as low as the minimum basePrice, then list 2-4 prices. "
        "Do not mention categories or documents. Always include numeric prices with currency. "
        "Keep it short (2-3 sentences).\n\n"
        f"Country: {country}\n"
        f"Minimum Price: {currency} {min_price}\n"
        f"Price Lines: {price_lines}\n"
        f"User Question: {question}\n"
    )
    response = model.generate_content(prompt)
    answer = response.text
    if not any(char.isdigit() for char in answer):
        raise ValueError("AI response missing prices")
    if min_price is not None and currency and f"{currency} {min_price}" not in answer:
        raise ValueError("AI response missing minimum price")
    return answer