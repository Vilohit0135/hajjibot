from flask import Flask
from flask_cors import CORS
import os
from dotenv import load_dotenv
from typing import Optional
import logging

from routes.chat_routes import chat_bp



# Load environment variables from .env file (for local development)
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)
app.logger.setLevel(logging.INFO)

app.register_blueprint(chat_bp)
# For local development
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)