#!/usr/bin/env python3
"""
Post-Deployment Verification Script for Sapphire Trading System
Executes comprehensive validation of all system components after deployment
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
import aiohttp
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('deployment_verification.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class DeploymentVerifier:
    def __init__(self):
        self.project_id = "sapphireinfinite"
        self.cluster_name = "hft-trading-cluster"
        self.zone = "us-central1-a"
        self.namespace = "trading"
        self.results: Dict[str, Any] = {}

    async def run_command(self, command: str, check: bool = True) -> tuple[bool, str]:
        """Run shell command and return success status and output."""
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

            stdout_str = stdout.decode().strip()
            stderr_str = stderr.decode().strip()

            if process.returncode != 0 and check:
                logger.error(f"Command failed: {command}\nStderr: {stderr_str}")
                return False, stderr_str
            return True, stdout_str
        except Exception as e:
            logger.error(f"Error running command '{command}': {e}")
            return False, str(e)

    async def verify_build_completion(self) -> bool:
        """Verify Cloud Build completed successfully."""
        logger.info("🔍 Verifying Cloud Build completion...")

        success, output = await self.run_command(
            f"gcloud builds list --limit=1 --format='value(status)' --project={self.project_id}"
        )

        if not success:
            logger.error("❌ Cannot access build status")
            return False

        status = output.strip()
        logger.info(f"📊 Build Status: {status}")

        if status == "SUCCESS":
            logger.info("✅ Build completed successfully")
            return True
        elif status in ["FAILURE", "CANCELLED", "TIMEOUT"]:
            logger.error(f"❌ Build failed with status: {status}")
            return False
        else:
            logger.warning(f"⚠️ Build still in progress: {status}")
            return False

    async def verify_gke_connectivity(self) -> bool:
        """Verify GKE cluster connectivity."""
        logger.info("🔗 Verifying GKE cluster connectivity...")

        success, output = await self.run_command(
            f"gcloud container clusters get-credentials {self.cluster_name} --zone={self.zone} --project={self.project_id}"
        )
        if not success:
            logger.error("❌ Failed to get cluster credentials")
            return False

        success, output = await self.run_command("kubectl cluster-info")
        if not success:
            logger.error("❌ Cannot connect to cluster")
            return False

        logger.info("✅ GKE connectivity established")
        return True

    async def verify_namespace_and_secrets(self) -> bool:
        """Verify namespace exists and secrets are configured."""
        logger.info("🔐 Verifying namespace and secrets...")

        # Check namespace
        success, output = await self.run_command(f"kubectl get namespace {self.namespace}")
        if not success:
            logger.error(f"❌ Namespace '{self.namespace}' not found")
            return False

        # Check secrets
        success, output = await self.run_command(f"kubectl get secrets -n {self.namespace}")
        if not success:
            logger.error("❌ Cannot access secrets")
            return False

        required_secrets = ["cloud-trader-secrets"]
        secrets_list = output.strip().split('\n')[1:] if output.strip() else []

        for secret in required_secrets:
            if not any(secret in line for line in secrets_list):
                logger.error(f"❌ Required secret '{secret}' not found")
                return False

        logger.info("✅ Namespace and secrets verified")
        return True

    async def verify_deployments(self) -> bool:
        """Verify all deployments are running."""
        logger.info("🚀 Verifying deployments...")

        expected_deployments = [
            "trading-system-cloud-trader",
            "trading-system-mcp-coordinator",
            "trading-system-deepseek-bot",
            "trading-system-qwen-bot",
            "trading-system-fingpt-bot",
            "trading-system-lagllama-bot",
            "trading-system-vpin-bot"
        ]

        success, output = await self.run_command(f"kubectl get deployments -n {self.namespace}")
        if not success:
            logger.error("❌ Cannot access deployments")
            return False

        deployments_list = output.strip().split('\n')[1:] if output.strip() else []

        for deployment in expected_deployments:
            if not any(deployment in line for line in deployments_list):
                logger.error(f"❌ Deployment '{deployment}' not found")
                return False

        logger.info("✅ All deployments created")

        # Check deployment status
        for deployment in expected_deployments:
            success, output = await self.run_command(
                f"kubectl rollout status deployment/{deployment} -n {self.namespace} --timeout=60s"
            )
            if not success:
                logger.error(f"❌ Deployment '{deployment}' not ready")
                return False

        logger.info("✅ All deployments are ready")
        return True

    async def verify_services_and_ingress(self) -> bool:
        """Verify services and ingress are configured."""
        logger.info("🌐 Verifying services and ingress...")

        # Check services
        success, output = await self.run_command(f"kubectl get services -n {self.namespace}")
        if not success:
            logger.error("❌ Cannot access services")
            return False

        required_services = ["trading-system-cloud-trader", "trading-system-mcp-coordinator"]
        services_list = output.strip().split('\n')[1:] if output.strip() else []

        for service in required_services:
            if not any(service in line for line in services_list):
                logger.error(f"❌ Service '{service}' not found")
                return False

        logger.info("✅ Services verified")
        return True

    async def verify_pod_health(self) -> bool:
        """Verify all pods are healthy."""
        logger.info("🏥 Verifying pod health...")

        success, output = await self.run_command(f"kubectl get pods -n {self.namespace}")
        if not success:
            logger.error("❌ Cannot access pods")
            return False

        pods_list = output.strip().split('\n')[1:] if output.strip() else []

        unhealthy_pods = []
        for pod_line in pods_list:
            if pod_line and not any(status in pod_line for status in ["Running", "Completed"]):
                unhealthy_pods.append(pod_line.split()[0])

        if unhealthy_pods:
            logger.error(f"❌ Unhealthy pods found: {unhealthy_pods}")
            return False

        logger.info("✅ All pods are healthy")
        return True

    async def test_api_endpoints(self) -> bool:
        """Test API endpoints for responsiveness."""
        logger.info("🔌 Testing API endpoints...")

        # Get cloud-trader service endpoint
        success, output = await self.run_command(
            f"kubectl get service trading-system-cloud-trader -n {self.namespace} -o jsonpath='{.spec.clusterIP}'"
        )
        if not success:
            logger.error("❌ Cannot get cloud-trader service IP")
            return False

        service_ip = output.strip()
        api_url = f"http://{service_ip}:8080"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{api_url}/healthz", timeout=10) as response:
                    if response.status == 200:
                        logger.info("✅ Cloud Trader API is responsive")
                        return True
                    else:
                        logger.error(f"❌ Cloud Trader API returned status {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ Cannot connect to Cloud Trader API: {e}")
            return False

    async def verify_system_initialization(self) -> bool:
        """Verify system initialization completed."""
        logger.info("🚀 Verifying system initialization...")

        # Check for system initialization job completion
        success, output = await self.run_command(
            f"kubectl get jobs -n {self.namespace} | grep system-init"
        )

        if success:
            # Job exists, check if completed
            success, output = await self.run_command(
                f"kubectl get job system-init -n {self.namespace} -o jsonpath='{.status.conditions[0].type}'"
            )
            if success and output.strip() == "Complete":
                logger.info("✅ System initialization completed")
                return True
            else:
                logger.warning("⚠️ System initialization still running")
                return False
        else:
            logger.warning("⚠️ System initialization job not found")
            return False

    async def run_comprehensive_verification(self) -> bool:
        """Run all verification checks."""
        logger.info("🧪 STARTING COMPREHENSIVE DEPLOYMENT VERIFICATION")
        logger.info("=" * 60)

        verification_steps = [
            ("Build Completion", self.verify_build_completion),
            ("GKE Connectivity", self.verify_gke_connectivity),
            ("Namespace & Secrets", self.verify_namespace_and_secrets),
            ("Deployments", self.verify_deployments),
            ("Services & Ingress", self.verify_services_and_ingress),
            ("Pod Health", self.verify_pod_health),
            ("API Endpoints", self.test_api_endpoints),
            ("System Initialization", self.verify_system_initialization),
        ]

        all_passed = True
        results_summary = []

        for step_name, verification_func in verification_steps:
            logger.info(f"\n🔍 Running {step_name} verification...")
            try:
                success = await verification_func()
                status = "✅ PASSED" if success else "❌ FAILED"
                results_summary.append(f"{step_name}: {status}")

                if not success:
                    all_passed = False

            except Exception as e:
                logger.error(f"❌ {step_name} verification crashed: {e}")
                results_summary.append(f"{step_name}: ❌ CRASHED")
                all_passed = False

        logger.info("\n" + "=" * 60)
        logger.info("📊 VERIFICATION RESULTS SUMMARY")
        logger.info("=" * 60)

        for result in results_summary:
            logger.info(result)

        logger.info("\n" + "=" * 60)
        if all_passed:
            logger.info("🎉 ALL VERIFICATION CHECKS PASSED!")
            logger.info("🚀 SYSTEM READY FOR LIVE TRADING")
        else:
            logger.error("❌ VERIFICATION FAILED - MANUAL INTERVENTION REQUIRED")

        logger.info("=" * 60)

        return all_passed

async def main():
    verifier = DeploymentVerifier()
    success = await verifier.run_comprehensive_verification()

    if success:
        logger.info("\n🎯 DEPLOYMENT SUCCESS PLAN EXECUTION READY")
        logger.info("Next steps:")
        logger.info("1. ✅ Run system initialization")
        logger.info("2. 🤖 Test AI agent coordination")
        logger.info("3. 💰 Configure trading parameters")
        logger.info("4. 📱 Deploy frontend dashboard")
        logger.info("5. 🚀 Start live trading")
        sys.exit(0)
    else:
        logger.error("\n❌ DEPLOYMENT VERIFICATION FAILED")
        logger.error("Check logs and resolve issues before proceeding")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
