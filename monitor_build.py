#!/usr/bin/env python3
"""Monitor Cloud Build progress and proceed with deployment steps."""

import subprocess
import time
import sys

def run_command(cmd):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()

def get_build_status():
    """Get the current build status."""
    success, output = run_command("gcloud builds describe $(gcloud builds list --limit=1 --format=\"value(id)\" --project=sapphireinfinite) --format=\"value(status)\" --project=sapphireinfinite")
    if success:
        return output
    return "UNKNOWN"

def wait_for_build_completion():
    """Wait for the build to complete."""
    print("🔍 Monitoring Cloud Build progress...")

    while True:
        status = get_build_status()
        print(f"📊 Build Status: {status}")

        if status == "SUCCESS":
            print("✅ Build completed successfully!")
            return True
        elif status == "FAILURE":
            print("❌ Build failed!")
            return False
        elif status == "CANCELLED":
            print("🚫 Build was cancelled!")
            return False
        elif status == "TIMEOUT":
            print("⏰ Build timed out!")
            return False

        print("⏳ Waiting for build to complete...")
        time.sleep(60)  # Check every minute

def check_deployment_status():
    """Check if the deployment was successful."""
    print("🔍 Checking deployment status...")

    # Check if the trading-system namespace exists
    success, output = run_command("kubectl get namespace trading --ignore-not-found")
    if not success or "trading" not in output:
        print("❌ Trading namespace not found!")
        return False

    # Check if deployments are running
    success, output = run_command("kubectl get deployments -n trading --no-headers | wc -l")
    if not success:
        print("❌ Could not get deployments!")
        return False

    deployment_count = int(output.strip())
    print(f"📊 Found {deployment_count} deployments")

    # Check if pods are running
    success, output = run_command("kubectl get pods -n trading --no-headers | grep -c Running")
    if not success:
        print("❌ Could not get pods!")
        return False

    running_pods = int(output.strip())
    print(f"📊 Found {running_pods} running pods")

    if running_pods >= 5:  # Expect at least cloud-trader, mcp-coordinator, and 3 agents
        print("✅ Deployment looks successful!")
        return True
    else:
        print("⚠️ Deployment may not be complete yet")
        return False

def main():
    """Main monitoring function."""
    print("🚀 Starting Sapphire Trading System Deployment Monitor")
    print("=" * 50)

    # Wait for build completion
    build_success = wait_for_build_completion()

    if not build_success:
        print("❌ Build failed. Cannot proceed with deployment.")
        sys.exit(1)

    # Get GKE credentials and check deployment
    print("🔐 Getting GKE credentials...")
    success, output = run_command("gcloud container clusters get-credentials hft-trading-cluster --zone=us-central1-a --project=sapphireinfinite")
    if not success:
        print(f"❌ Failed to get GKE credentials: {output}")
        sys.exit(1)

    # Check deployment status
    deployment_success = check_deployment_status()

    if deployment_success:
        print("🎉 Deployment completed successfully!")
        print("📋 Next steps:")
        print("   1. Verify frontend deployment")
        print("   2. Test telegram notifications")
        print("   3. Start live trading")
    else:
        print("⚠️ Deployment status uncertain. Manual verification needed.")

if __name__ == "__main__":
    main()
