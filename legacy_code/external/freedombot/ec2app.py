"""TradingView webhook receiver that forwards signals to AWS SQS.

This is a prototype. Configure via env vars:
- `AWS_REGION` (default: us-east-1)
- `SQS_QUEUE_URL` (required)
- `PORT` (default: 5000)
"""

from __future__ import annotations

import json
import os

import boto3
from flask import Flask, jsonify, request

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "").strip()

sqs = boto3.client("sqs", region_name=AWS_REGION)

app = Flask(__name__)


@app.route("/webhook", methods=["POST"])
def webhook():
    if not SQS_QUEUE_URL:
        return jsonify({"message": "SQS_QUEUE_URL is not set"}), 500

    payload = request.get_json(silent=True) or {}

    try:
        response = sqs.send_message(QueueUrl=SQS_QUEUE_URL, MessageBody=json.dumps(payload))
    except Exception as exc:
        return jsonify({"message": f"Error sending message to SQS: {exc}"}), 500

    return jsonify({"message": "Signal enqueued", "message_id": response.get("MessageId")}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)

