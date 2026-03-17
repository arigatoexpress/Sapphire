#!/bin/bash
gcloud run deploy cloud-trader \
  --image gcr.io/sapphire-479610/cloud-trader \
  --platform managed \
  --region northamerica-northeast1 \
  --project sapphire-479610 \
  --allow-unauthenticated \
  --vpc-connector sapphire-conn \
  --vpc-egress all-traffic \
  --memory 4Gi \
  --cpu 2 \
  --timeout 300s
