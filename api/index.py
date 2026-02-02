from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
import logging

from api.routes.chat_routes import chat_bp



# Load environment variables from .env file (for local development)
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)
app.logger.setLevel(logging.INFO)

@app.route("/")
def root():
    return {"status": "API running on Vercel"}

app.register_blueprint(chat_bp, url_prefix="/api")


# For local development
# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=5000, debug=True)