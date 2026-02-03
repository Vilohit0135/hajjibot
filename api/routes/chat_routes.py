from flask import Blueprint, request, jsonify
from datetime import datetime
import google.generativeai as genai
import os
from typing import Optional



## Initialize MongoDB
from pymongo import  errors
from api.db.mongo import init_mongo



## Initialize Chat Graph
from api.core.chat_graph import CHAT_GRAPH, ChatState


chat_bp = Blueprint("chat", __name__, url_prefix="/api")

users_collection, mongo_ready, mongo_error = init_mongo()

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Flight API credentials (set in environment)
def _unquote_env(val: Optional[str]) -> Optional[str]:
    if not val:
        return val
    # strip surrounding single or double quotes
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    return val

PUBLIC_TTS_API_USERNAME = _unquote_env(os.getenv("PUBLIC_TTS_API_USERNAME"))
PUBLIC_TTS_API_PASSWORD = _unquote_env(os.getenv("PUBLIC_TTS_API_PASSWORD"))

@chat_bp.route('/')
def home():
    return jsonify({
        "status": "success",
        "message": "Marhaba Haji API is running",
        "endpoints": {
            "/api/chat": "POST - Send questions about Marhaba Haji services"
        }
    })

@chat_bp.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "Marhaba Haji Chat API"
    })


@chat_bp.route('/chat', methods=['POST'])
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
                {"_id": 0, "history": 1, "visa_context": 1, "flight_context": 1, "hotel_context": 1},
            )
            history = existing_user.get("history", []) if existing_user else []
            visa_context = existing_user.get("visa_context") if existing_user else None
            flight_context = existing_user.get("flight_context") if existing_user else None
            hotel_context = existing_user.get("hotel_context") if existing_user else None
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
            "flight_context": flight_context,
            "flight_question_index": flight_context.get("flight_question_index", 0) if flight_context else 0,
            "hotel_context": hotel_context,
            "hotel_question_index": hotel_context.get("hotel_question_index", 0) if hotel_context else 0,
            "model": model,
            "flight_username": PUBLIC_TTS_API_USERNAME,
            "flight_password": PUBLIC_TTS_API_PASSWORD,
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
        
        updated_flight_context = result_state.get("flight_context")
        # Save flight_context on every message during flight booking (not just at the end)
        if updated_flight_context:
            try:
                users_collection.update_one(
                    {"email": user_email},
                    {"$set": {"flight_context": {
                        "trip_type": updated_flight_context.get("trip_type"),      # ✅ ADD
                        "return_date": updated_flight_context.get("return_date"),  # ✅ ADD
                        "adults": updated_flight_context.get("adults"),
                        "children": updated_flight_context.get("children"),
                        "children_ages": updated_flight_context.get("children_ages"),
                        "departure_date": updated_flight_context.get("departure_date"),
                        "departure_city": updated_flight_context.get("departure_city"),
                        "arrival_city": updated_flight_context.get("arrival_city"),
                        "flight_question_index": result_state.get("flight_question_index", 0),
                        "results": updated_flight_context.get("results", []),
                        "fetched_at": datetime.utcnow(),
                    }}},
                )
            except Exception as db_error:
                return jsonify({
                    "status": "error",
                    "message": f"Database error: {db_error}"
                }), 500
        else:
            users_collection.update_one(
                {"email": user_email},
                {"$unset": {"flight_context": ""}}
            )
        updated_hotel_context = result_state.get("hotel_context")

        if updated_hotel_context:
            try:
                users_collection.update_one(
                    {"email": user_email},
                    {"$set": {"hotel_context": {
                        **updated_hotel_context,
                        "hotel_question_index": result_state.get("hotel_question_index", 0),
                        "fetched_at": datetime.utcnow(),
                    }}},
                )
            except Exception as db_error:
                return jsonify({
                    "status": "error",
                    "message": f"Database error: {db_error}"
                }), 500
        else:
            users_collection.update_one(
                {"email": user_email},
                {"$unset": {"hotel_context": ""}}
            )

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