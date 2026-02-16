# FreedomBot (Archived Prototype)

Imported from `arigatoexpress/FreedomBot` (now archived / superseded by `arigatoexpress/Sapphire`).

Prototype TradingView webhook plumbing (kept for historical reference).

## What's Here
- `flask_sending_webhook.py`: receives TradingView webhook JSON, stores to MySQL, forwards to downstream endpoints.
- `ec2app.py`: receives TradingView webhook JSON and enqueues it to AWS SQS.
- `docker_application.py`: polls SQS and runs placeholder processing.
- `strategy.txt`: example TradingView alert JSON payload template.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r archive/external/freedombot/requirements.txt
```

### Run (direct webhook + DB + forwarding)

```bash
python archive/external/freedombot/flask_sending_webhook.py
```

### Run (webhook to SQS)

```bash
export AWS_REGION=us-east-1
export SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/your-queue
python archive/external/freedombot/ec2app.py
```

## Status
This repository is a prototype and is not production hardened.
