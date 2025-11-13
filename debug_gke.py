#!/usr/bin/env python3
"""Debug GKE cluster resource queries."""

import asyncio
import subprocess

async def run_command(cmd):
    """Run a shell command."""
    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        success = process.returncode == 0
        output = stdout.decode().strip() if stdout else stderr.decode().strip()
        return success, output
    except Exception as e:
        return False, str(e)

async def debug_gke():
    """Debug GKE resource queries."""
    print("🔍 Debugging GKE cluster resources...")

    # Get cluster credentials first
    print("Getting cluster credentials...")
    success, output = await run_command("gcloud container clusters get-credentials hft-trading-cluster --zone=us-central1-a --project=sapphireinfinite")
    print(f"Credentials: {'✅' if success else '❌'} - {output[:100]}...")

    # Check GPU nodes
    print("\nChecking GPU nodes...")
    success, output = await run_command("kubectl get nodes -l accelerator=nvidia-tesla-l4 --no-headers | wc -l")
    print(f"GPU nodes command: {'✅' if success else '❌'} - output: '{output}'")

    # Check all nodes
    print("\nChecking all nodes...")
    success, output = await run_command("kubectl get nodes --no-headers")
    print(f"Nodes list: {'✅' if success else '❌'}")
    print("Nodes:")
    print(output)

    # Check node details
    print("\nChecking node details...")
    success, output = await run_command("kubectl get nodes -o json | jq '.items[0].status.allocatable' 2>/dev/null || echo 'jq failed'")
    print(f"Node allocatables: {'✅' if success else '❌'}")
    print("Allocatable resources:")
    print(output)

    # Check CPU capacity
    print("\nChecking CPU capacity...")
    success, output = await run_command("kubectl get nodes -o json | jq '[.items[].status.allocatable.cpu | select(. != null) | tonumber] | add // 0' 2>/dev/null || echo 'jq failed'")
    print(f"CPU capacity command: {'✅' if success else '❌'} - output: '{output}'")

if __name__ == "__main__":
    asyncio.run(debug_gke())
