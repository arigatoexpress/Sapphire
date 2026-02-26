#!/bin/bash
# Setup script for Sapphire OS Self-Improvement Loop
# Run this to configure Cloud Scheduler and initial Firestore structure

echo "=== Setting up Sapphire Self-Improvement Loop ==="

# Create Pub/Sub topic for improvement tasks
echo "Creating Pub/Sub topic..."
gcloud pubsub topics create improvement-tasks --project=sapphire-479610 2>/dev/null || echo "Topic already exists"

# Create Cloud Scheduler job for weekly reviews
echo "Creating weekly Cloud Scheduler job..."
gcloud scheduler jobs create http weekly-self-improvement \
  --project=sapphire-479610 \
  --schedule="0 2 * * 0" \
  --time-zone="UTC" \
  --uri="https://agentic-pm-hub-267358751314.us-central1.run.app/api/self-improvement/weekly-review" \
  --http-method=POST \
  --message-body='{"trigger":"scheduled"}' \
  --headers="Content-Type=application/json" \
  --attempt-deadline=300s \
  --location=us-central1 2>/dev/null || echo "Scheduler job already exists"

# Create Firestore collections (empty docs to initialize)
echo "Initializing Firestore collections..."
python3 << 'EOF'
from google.cloud import firestore
db = firestore.Client(project="sapphire-479610")

# Initialize collections with placeholder docs
collections = ["trading_performance", "improvement_tasks", "weekly_reviews"]
for coll in collections:
    doc_ref = db.collection(coll).document("_init")
    doc_ref.set({"initialized": True, "timestamp": firestore.SERVER_TIMESTAMP})
    print(f"  Initialized: {coll}")

print("Firestore collections ready")
EOF

echo ""
echo "=== Setup Complete ==="
echo "Weekly reviews scheduled for Sundays at 2 AM UTC"
echo "Pub/Sub topic: improvement-tasks"
echo "Firestore collections: trading_performance, improvement_tasks, weekly_reviews"
