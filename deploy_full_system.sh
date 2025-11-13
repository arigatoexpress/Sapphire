#!/bin/bash
set -e

echo "🚀 FULL SYSTEM DEPLOYMENT SCRIPT"
echo "==============================="

# Step 1: Push to GitHub
echo "1. 🔄 Pushing to GitHub..."
git add .
git commit -m "Production-ready AI trading system with $4200 capital allocation" || echo "No changes to commit"
git push origin main

# Step 2: Build and deploy containers
echo "2. 🏗️  Building containers via Cloud Build..."
gcloud builds submit --config cloudbuild.yaml .

# Step 3: Deploy to Kubernetes
echo "3. 🚀 Deploying to GKE..."
kubectl apply -f k8s-configmap-*.yaml
kubectl apply -f k8s-secrets.yaml
kubectl apply -f k8s-deployment-*.yaml
kubectl apply -f k8s-service-*.yaml
kubectl apply -f k8s-hpa-*.yaml

# Step 4: Wait for deployments
echo "4. ⏳ Waiting for deployments..."
kubectl wait --for=condition=available --timeout=300s deployment --all

# Step 5: Deploy frontend
echo "5. 🎨 Deploying frontend..."
cd trading-dashboard
npm install
npm run build
cd ..
firebase deploy --only hosting --project=sapphireinfinite

# Step 6: Verify deployment
echo "6. 🔍 Verifying deployment..."
kubectl get pods
kubectl get services
echo "Frontend: https://sapphiretrade.xyz"

echo "✅ DEPLOYMENT COMPLETE!"
