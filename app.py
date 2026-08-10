import os

from flask import Flask, request

from review_message_storage import ReviewMessageStorage

app = Flask(__name__)
review_message_storage = ReviewMessageStorage()
@app.route("/")
def index():
    return "Baja Bot"

@app.route("/review", methods=["POST"])
def send_review_messages():
    secret = request.headers.get('X-Webhook-Header')
    if secret != "SecretWow1234":
        return

    data = request.get_json()

    url = data["data"]["url"]
    reviewers_dicts = data["data"]["properties"]["Reviewers"]["people"]
    reviewers = [person["name"] for person in reviewers_dicts]
    reviewers_str = ", ".join(reviewers)
    gap_num = data["data"]["properties"]["GAP Number"]["formula"]["string"]
    doc_name = data["data"]["properties"]["Name"]["title"][0]["plain_text"]
    extra_data = gap_num + ";" + doc_name
    review_message_storage.add_review_message(
        name=reviewers_str,
        url=url,
        extra_data=extra_data
    )
    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

