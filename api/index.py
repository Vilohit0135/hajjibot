from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import os
from dotenv import load_dotenv
from pymongo import MongoClient, errors
from datetime import datetime

# Load environment variables from .env file (for local development)
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Configure MongoDB
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "marhaba")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "users")
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
                {"_id": 0, "history": 1},
            )
            history = existing_user.get("history", []) if existing_user else []
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
        
        # Create the prompt with context
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
            f"User Name: {user_name}\n"
            f"{conversation_prefix}"
            f"User Question: {user_question}\n\n"
            "Please provide a helpful and accurate response based on Marhaba Haji's services. "
            "Keep the answer short (2-4 sentences) and warm. "
            f"{greeting_instruction}"
        )
        
        # Generate response
        response = model.generate_content(prompt)
        answer_text = response.text

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
