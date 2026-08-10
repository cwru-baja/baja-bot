import os

from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Baja Bot"

# @app.route("/review", methods=["POST"])
# def send_review_messages():
#     if not request.is_json:
#         return jsonify({"error": "Request must be JSON"}), 400


app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

