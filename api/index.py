from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import os
from dotenv import load_dotenv
from pymongo import MongoClient, errors
from datetime import datetime
from typing import Optional, TypedDict, Any
from langgraph.graph import StateGraph, END
import requests
import logging

# Load environment variables from .env file (for local development)
load_dotenv()

app = Flask(__name__)
CORS(app)
app.logger.setLevel(logging.INFO)
# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Configure MongoDB
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "marhaba")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "users")
VISA2FLY_TOKEN = os.getenv("VISA2FLY_TOKEN", "JFdxzylwEkvHH")
mongo_client = None
users_collection = None
mongo_ready = False
mongo_error = None
if MONGO_URI:
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        users_collection = mongo_client[MONGO_DB][MONGO_COLLECTION]
        users_collection.create_index("email", unique=True)
        mongo_ready = True
    except Exception as exc:
        mongo_error = exc

# Website context about Marhaba Haji
MARHABA_CONTEXT = """
You are a helpful assistant for Marhaba Haji (marhabahaji.com), a comprehensive Umrah and Hajj travel services provider.

Company Information:
- Marhaba Ventures is a trusted partner for Hajj & Umrah services
- They provide complete Umrah travel services making pilgrimage seamless
- Services include accommodation, guided tours, and comprehensive travel planning
- The company is currently revamping their platform to offer a unique, world-class Umrah and Hajj experience

Services Offered:
1. Umrah Packages - Complete travel packages for Umrah pilgrimage
2. Hajj Packages - Comprehensive Hajj pilgrimage services
3. Hotel Accommodation - Quality hotel bookings in Makkah and Madinah
4. Transportation Services - Ground transportation in Saudi Arabia
5. Ziarath (Ziyarat) - Guided tours to Islamic historical sites
6. Guide Services - Expert guides for pilgrims
7. Visa Processing - Assistance with Saudi visa applications
8. Group Flight Arrangements - Flight bookings for groups
9. Travel Resources - Guides and educational content for pilgrims

Key Features:
- Comprehensive travel services from start to finish
- Focus on making pilgrimage seamless and worry-free
- Guides and resources available for pilgrims
- Professional service with attention to detail

Website Sections:
- Home
- Umrah Packages
- Hajj Packages
- Hotel
- Transport
- Ziarath
- Guide
- Visa
- Group Flight
- Blog
- Contact
- Services
- Cart
- Profile

Instructions:
- Answer questions about Marhaba Haji services professionally and helpfully
- Provide accurate information based on the context above
- If asked about specific prices or detailed package information not provided, suggest contacting Marhaba Haji directly through their website
- Be warm and respectful, understanding the spiritual nature of the services
- If the question is outside the scope of Marhaba Haji services, politely redirect to relevant topics
"""

VISA_COUNTRIES = [
    "Dubai",
    "France",
    "Germany",
    "Finland",
    "Sri Lanka",
    "Canada",
    "United Kingdom",
    "Spain",
    "Switzerland",
    "Egypt",
    "South Africa",
    "Netherlands",
    "Czech Republic",
    "UAE",
    "Austria",
    "Ukraine",
    "USA",
    "Denmark",
    "Greece",
    "Hungary",
    "Sweden",
    "Singapore",
    "Turkey",
    "Australia",
    "Thailand",
    "New Zealand",
    "Italy",
    "Hong Kong",
    "Bangladesh",
    "Slovenia",
    "Saudi Arabia",
    "Belgium",
    "Poland",
    "Slovakia",
    "Iceland",
    "Portugal",
    "Norway",
    "Latvia",
    "Malta",
    "Malaysia",
    "Vietnam",
    "Tom",
    "Jerica",
    "Cambodia",
    "Liechtenstein",
    "Philippines",
]

VISA_COUNTRY_LOOKUP = {country.lower(): country for country in VISA_COUNTRIES}

def _extract_country(text: str) -> Optional[str]:
    lowered = text.lower()
    for name in sorted(VISA_COUNTRY_LOOKUP.keys(), key=len, reverse=True):
        if name in lowered:
            return VISA_COUNTRY_LOOKUP[name]
    return None

def _fetch_visa_data(country: str) -> dict:
    url = f"https://devapi.visa2fly.com/api/b2b/partner/visa/{country}"
    response = requests.get(
        url,
        headers={
            "token": VISA2FLY_TOKEN,
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
        return f"I fetched visa details for {country}, but pricing is not available right now."
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

class ChatState(TypedDict, total=False):
    question: str
    name: str
    history: list
    is_first_message: bool
    visa_context: Optional[dict]
    resolved_country: Optional[str]
    intent: str
    answer: str
    visa_context_updated: bool
    model: Any

def _detect_intent(state: ChatState) -> ChatState:
    model = state["model"]
    question = state["question"]
    resolved_country = _extract_country(question)
    state["resolved_country"] = resolved_country
    if resolved_country:
        state["intent"] = "visa"
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

def _handle_general(state: ChatState) -> ChatState:
    model = state["model"]
    question = state["question"]
    name = state["name"]
    history = state.get("history", [])
    is_first_message = state.get("is_first_message", False)

    history_lines = []
    for item in history:
        role = item.get("role")
        text = item.get("text")
        if role and text:
            history_lines.append(f"{role.title()}: {text}")
    history_block = "\n".join(history_lines)

    conversation_prefix = (
        f"Conversation so far:\n{history_block}\n" if history_block else ""
    )
    greeting_instruction = (
        "Greet the user by name at the start." if is_first_message else "Do not greet again."
    )

    prompt = (
        f"{MARHABA_CONTEXT}\n\n"
        f"User Name: {name}\n"
        f"{conversation_prefix}"
        f"User Question: {question}\n\n"
        "Please provide a helpful and accurate response based on Marhaba Haji's services. "
        "Keep the answer short (2-4 sentences) and warm. "
        f"{greeting_instruction}"
    )

    response = model.generate_content(prompt)
    state["answer"] = response.text
    return state

def _handle_visa(state: ChatState) -> ChatState:
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
        visa_data = _fetch_visa_data(resolved_country)
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

def _build_chat_graph() -> Any:
    graph = StateGraph(ChatState)
    graph.add_node("detect_intent", _detect_intent)
    graph.add_node("handle_general", _handle_general)
    graph.add_node("handle_visa", _handle_visa)

    graph.set_entry_point("detect_intent")
    graph.add_conditional_edges(
        "detect_intent",
        lambda state: state.get("intent", "general"),
        {
            "visa": "handle_visa",
            "general": "handle_general",
        },
    )
    graph.add_edge("handle_general", END)
    graph.add_edge("handle_visa", END)
    return graph.compile()

CHAT_GRAPH = _build_chat_graph()

@app.route('/')
def home():
    return jsonify({
        "status": "success",
        "message": "Marhaba Haji API is running",
        "endpoints": {
            "/api/chat": "POST - Send questions about Marhaba Haji services"
        }
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        # Check if API key is configured
        if not GEMINI_API_KEY:
            return jsonify({
                "status": "error",
                "message": "GEMINI_API_KEY environment variable is not set"
            }), 500
        
        data = request.get_json()
        
        if not data or 'question' not in data or 'name' not in data or 'email' not in data:
            return jsonify({
                "status": "error",
                "message": "Please provide 'question', 'name', and 'email' in the request body"
            }), 400
        
        user_question = data['question']
        user_name = data['name'].strip()
        user_email = data['email'].strip().lower()

        if not user_name or not user_email:
            return jsonify({
                "status": "error",
                "message": "Name and email cannot be empty"
            }), 400

        if not mongo_ready or users_collection is None:
            return jsonify({
                "status": "error",
                "message": f"MongoDB is not configured or unreachable. Check MONGO_URI. {mongo_error}"
            }), 500

        try:
            existing_user = users_collection.find_one(
                {"email": user_email},
                {"_id": 0, "history": 1, "visa_context": 1},
            )
            history = existing_user.get("history", []) if existing_user else []
            visa_context = existing_user.get("visa_context") if existing_user else None
            is_first_message = len(history) == 0

            users_collection.update_one(
                {"email": user_email},
                {
                    "$setOnInsert": {
                        "email": user_email,
                        "created_at": datetime.utcnow(),
                    },
                    "$set": {"name": user_name, "last_seen_at": datetime.utcnow()},
                },
                upsert=True,
            )
        except errors.DuplicateKeyError:
            pass
        except Exception as db_error:
            return jsonify({
                "status": "error",
                "message": f"Database error: {db_error}"
            }), 500
        
        # Initialize Gemini model
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        graph_state: ChatState = {
            "question": user_question,
            "name": user_name,
            "history": history,
            "is_first_message": is_first_message,
            "visa_context": visa_context,
            "model": model,
        }
        result_state = CHAT_GRAPH.invoke(graph_state)
        answer_text = result_state.get("answer", "Sorry, I could not process that request.")
        updated_visa_context = result_state.get("visa_context")
        if result_state.get("visa_context_updated") and updated_visa_context:
            try:
                users_collection.update_one(
                    {"email": user_email},
                    {"$set": {"visa_context": {
                        "country": updated_visa_context.get("country"),
                        "data": updated_visa_context.get("data"),
                        "fetched_at": datetime.utcnow(),
                    }}},
                )
            except Exception as db_error:
                return jsonify({
                    "status": "error",
                    "message": f"Database error: {db_error}"
                }), 500

        try:
            users_collection.update_one(
                {"email": user_email},
                {
                    "$push": {
                        "history": {
                            "$each": [
                                {
                                    "role": "user",
                                    "text": user_question,
                                    "at": datetime.utcnow(),
                                },
                                {
                                    "role": "assistant",
                                    "text": answer_text,
                                    "at": datetime.utcnow(),
                                },
                            ],
                            "$slice": -5,
                        }
                    }
                },
            )
        except Exception as db_error:
            return jsonify({
                "status": "error",
                "message": f"Database error: {db_error}"
            }), 500
        
        return jsonify({
            "status": "success",
            "question": user_question,
            "answer": answer_text
        })
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "Marhaba Haji Chat API"
    })

# For local development
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
