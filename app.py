import os

from flask import Flask

from review_message_storage import ReviewMessageStorage

app = Flask(__name__)
review_message_storage = ReviewMessageStorage()
@app.route("/")
def index():
    return "Baja Bot"

@app.route("/review", methods=["POST"])
async def send_review_messages(data: dict):
    url = data["data"]["url"]
    reviewers_dict = data["data"]["properties"]["Reviewers"]["people"]
    reviewers = [person["name"] for person in reviewers_dict.values()]
    reviewers_str = ", ".join(reviewers)
    gap_num = data["data"]["properties"]["GAP Number"]["formula"]["string"]
    review_message_storage.add_review_message(
        name=reviewers_str,
        url=url,
        extra_data=gap_num
    )
    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

