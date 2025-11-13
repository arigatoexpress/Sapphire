#!/usr/bin/env python3
"""Comprehensive testing and debugging script for Sapphire Trading System."""

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Any, Tuple

class ComprehensiveTester:
    """Comprehensive testing suite for the Sapphire Trading System."""

    def __init__(self):
        self.results = {}
        self.errors = []
        self.warnings = []

    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    async def run_command(self, cmd: str, check: bool = True, timeout: int = 30) -> Tuple[bool, str]:
        """Run a shell command asynchronously."""
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            success = process.returncode == 0 if check else True
            output = stdout.decode().strip() if stdout else stderr.decode().strip()
            return success, output
        except asyncio.TimeoutError:
            return False, f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, str(e)

    async def test_gke_cluster(self) -> Dict[str, Any]:
        """Test GKE cluster health and configuration."""
        self.log("🔍 Testing GKE cluster configuration...")
        results = {}

        # 1. Check cluster exists and is running
        success, output = await self.run_command(
            "gcloud container clusters list --filter='name:hft-trading-cluster' --format='value(status)' --project=sapphireinfinite"
        )
        results["cluster_exists"] = {"status": "pass" if success and output == "RUNNING" else "fail", "output": output}

        # 2. Get cluster credentials
        success, output = await self.run_command(
            "gcloud container clusters get-credentials hft-trading-cluster --zone=us-central1-a --project=sapphireinfinite"
        )
        results["cluster_credentials"] = {"status": "pass" if success else "fail", "output": output}

        # 3. Test kubectl connectivity
        success, output = await self.run_command("kubectl cluster-info")
        results["kubectl_connectivity"] = {"status": "pass" if success and "is running at" in output else "fail", "output": output}

        # 4. Check node count and resources
        success, output = await self.run_command("kubectl get nodes --no-headers | wc -l")
        node_count = int(output.strip()) if success else 0
        results["node_count"] = {"status": "pass" if success and node_count >= 3 else "fail", "count": node_count}

        # 5. Check GPU availability (look for any nodes with GPU capacity)
        success, output = await self.run_command("kubectl get nodes -o json | jq '.items[] | select(.status.allocatable.\"nvidia.com/gpu\" != null) | .metadata.name' | wc -l", check=False)
        gpu_node_count = int(output.strip()) if success and output.strip() else 0
        results["gpu_availability"] = {"status": "pass" if gpu_node_count >= 3 else "warn" if gpu_node_count > 0 else "info", "gpu_nodes": gpu_node_count, "note": "No dedicated GPU nodes found - agents will use CPU-only mode"}

        # 6. Check CPU and memory resources
        success, output = await self.run_command("kubectl get nodes -o json | jq -r '.items[].status.allocatable.cpu' | sed 's/m$//' | awk '{sum += $1} END {print sum/1000}'")
        cpu_count = float(output.strip()) if success and output.strip() else 0
        results["cpu_capacity"] = {"status": "pass" if cpu_count >= 12 else "fail", "cores": round(cpu_count, 2)}

        return results

    async def test_helm_charts(self) -> Dict[str, Any]:
        """Test Helm chart validation and deployment."""
        self.log("🔍 Testing Helm charts...")
        results = {}

        # 1. Check Helm installation
        success, output = await self.run_command("helm version --short", check=False)
        if not success:
            results["helm_installed"] = {"status": "skip", "version": "Helm not installed locally"}
            results["chart_lint"] = {"status": "skip", "output": "Helm not available"}
            results["dependency_build"] = {"status": "skip", "output": "Helm not available"}
            results["dry_run"] = {"status": "skip", "output": "Helm not available"}
            return results

        results["helm_installed"] = {"status": "pass" if "v3" in output else "fail", "version": output}

        # 2. Validate chart syntax
        success, output = await self.run_command("helm lint ./helm/trading-system")
        results["chart_lint"] = {"status": "pass" if success else "fail", "output": output}

        # 3. Check dependency build
        success, output = await self.run_command("helm dependency build ./helm/trading-system")
        results["dependency_build"] = {"status": "pass" if success else "fail", "output": output}

        # 4. Dry-run deployment
        success, output = await self.run_command(
            "helm upgrade --install trading-system ./helm/trading-system --namespace trading --create-namespace --dry-run --debug",
            timeout=60
        )
        results["dry_run"] = {"status": "pass" if success else "fail", "output": output[:500] if output else ""}  # Truncate long output

        return results

    async def test_container_images(self) -> Dict[str, Any]:
        """Test container image availability and security."""
        self.log("🔍 Testing container images...")
        results = {}

        # 1. Check if image exists in registry
        success, output = await self.run_command(
            "gcloud artifacts docker images list us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy --format='value(package)' --limit=5 --project=sapphireinfinite"
        )
        results["image_exists"] = {"status": "pass" if success and "cloud-trader" in output else "fail", "output": output}

        # 2. Check image size (should be reasonable for AI workloads)
        success, output = await self.run_command(
            "gcloud artifacts docker images describe us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy/cloud-trader:latest --format='value(size)' --project=sapphireinfinite",
            check=False
        )
        if success and output:
            size_gb = int(output) / (1024**3)  # Convert bytes to GB
            results["image_size"] = {"status": "pass" if size_gb < 10 else "warn", "size_gb": round(size_gb, 2)}
        else:
            results["image_size"] = {"status": "unknown", "size_gb": 0}

        # 3. Test image pull (this might take time)
        docker_success, _ = await self.run_command("docker --version", check=False)
        if docker_success:
            success, output = await self.run_command(
                "docker pull us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy/cloud-trader:latest",
                timeout=120
            )
            results["image_pull"] = {"status": "pass" if success else "fail", "output": output}
        else:
            results["image_pull"] = {"status": "skip", "output": "Docker not available locally"}

        return results

    async def test_networking(self) -> Dict[str, Any]:
        """Test network connectivity and DNS."""
        self.log("🔍 Testing network connectivity...")
        results = {}

        # 1. Test external connectivity
        success, output = await self.run_command("curl -s --max-time 10 google.com")
        results["external_connectivity"] = {"status": "pass" if success else "fail", "output": output}

        # 2. Test DNS resolution (only if kubectl is connected)
        kubectl_success, _ = await self.run_command("kubectl cluster-info", check=False)
        if kubectl_success:
            success, output = await self.run_command("kubectl run -it --rm --restart=Never busybox --image=busybox -- nslookup kubernetes.default", check=False)
            results["dns_resolution"] = {"status": "pass" if success and "Address" in output else "fail", "output": output}
        else:
            results["dns_resolution"] = {"status": "skip", "output": "kubectl not connected to cluster"}

        # 3. Test Artifact Registry access
        success, output = await self.run_command(
            "gcloud artifacts repositories describe cloud-run-source-deploy --location=us-central1 --project=sapphireinfinite"
        )
        results["artifact_registry"] = {"status": "pass" if success else "fail", "output": output}

        # 4. Test Vertex AI endpoint accessibility (if available)
        success, output = await self.run_command(
            "curl -s --max-time 5 https://us-central1-aiplatform.googleapis.com/v1/projects/sapphireinfinite/locations/us-central1/endpoints",
            check=False
        )
        results["vertex_ai_api"] = {"status": "pass" if success else "warn", "output": output[:200] if output else ""}

        return results

    async def test_security(self) -> Dict[str, Any]:
        """Test security configurations."""
        self.log("🔍 Testing security configurations...")
        results = {}

        # 1. Check RBAC
        success, output = await self.run_command("kubectl get clusterrolebindings --no-headers | wc -l")
        rbac_count = int(output.strip()) if success else 0
        results["rbac_enabled"] = {"status": "pass" if rbac_count > 0 else "fail", "count": rbac_count}

        # 2. Check network policies
        success, output = await self.run_command("kubectl api-resources | grep -c networkpolicies")
        has_network_policies = int(output.strip()) if success else 0
        results["network_policies"] = {"status": "pass" if has_network_policies > 0 else "warn", "available": has_network_policies > 0}

        # 3. Check service accounts
        success, output = await self.run_command("kubectl get serviceaccounts -n trading --no-headers | wc -l")
        sa_count = int(output.strip()) if success else 0
        results["service_accounts"] = {"status": "pass" if sa_count > 0 else "fail", "count": sa_count}

        # 4. Check secrets
        success, output = await self.run_command("kubectl get secrets -n trading --no-headers | grep -c cloud-trader")
        secret_count = int(output.strip()) if success else 0
        results["secrets_configured"] = {"status": "pass" if secret_count > 0 else "warn", "count": secret_count}

        return results

    async def test_deployment_readiness(self) -> Dict[str, Any]:
        """Test deployment readiness and resource allocation."""
        self.log("🔍 Testing deployment readiness...")
        results = {}

        # 1. Check namespace exists
        success, output = await self.run_command("kubectl get namespace trading --ignore-not-found")
        results["namespace_exists"] = {"status": "pass" if success and "trading" in output else "fail", "output": output}

        # 2. Check deployments (if any exist from previous runs)
        success, output = await self.run_command("kubectl get deployments -n trading --no-headers 2>/dev/null | wc -l", check=False)
        deployment_count = int(output.strip()) if success and output.strip() else 0
        results["existing_deployments"] = {"status": "info", "count": deployment_count}

        # 3. Check storage classes
        success, output = await self.run_command("kubectl get storageclass --no-headers | wc -l")
        storage_count = int(output.strip()) if success else 0
        results["storage_classes"] = {"status": "pass" if storage_count > 0 else "fail", "count": storage_count}

        # 4. Check GPU node availability
        success, output = await self.run_command("kubectl get nodes -l accelerator=nvidia-tesla-l4 --no-headers | wc -l")
        gpu_nodes = int(output.strip()) if success else 0
        results["gpu_nodes"] = {"status": "pass" if gpu_nodes > 0 else "warn", "count": gpu_nodes}

        return results

    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all comprehensive tests."""
        self.log("🚀 Starting Comprehensive Testing Suite")
        self.log("=" * 50)

        all_results = {}

        # Run all test suites
        test_suites = [
            ("GKE Cluster", self.test_gke_cluster),
            ("Helm Charts", self.test_helm_charts),
            ("Container Images", self.test_container_images),
            ("Networking", self.test_networking),
            ("Security", self.test_security),
            ("Deployment Readiness", self.test_deployment_readiness),
        ]

        for test_name, test_func in test_suites:
            try:
                self.log(f"Running {test_name} tests...")
                results = await test_func()
                all_results[test_name.lower().replace(" ", "_")] = results

                # Count results
                passed = sum(1 for r in results.values() if r.get("status") == "pass")
                failed = sum(1 for r in results.values() if r.get("status") == "fail")
                warnings = sum(1 for r in results.values() if r.get("status") == "warn")

                self.log(f"✅ {test_name}: {passed} passed, {warnings} warnings, {failed} failed")

                if failed > 0:
                    self.errors.append(f"{test_name}: {failed} failed tests")
                if warnings > 0:
                    self.warnings.append(f"{test_name}: {warnings} warnings")

            except Exception as e:
                self.log(f"❌ {test_name} test suite failed: {e}", "ERROR")
                all_results[test_name.lower().replace(" ", "_")] = {"error": str(e)}
                self.errors.append(f"{test_name}: Test suite crashed")

        return all_results

    def generate_report(self, results: Dict[str, Any]) -> str:
        """Generate a comprehensive test report."""
        report_lines = []
        report_lines.append("📊 COMPREHENSIVE TEST REPORT")
        report_lines.append("=" * 50)
        report_lines.append(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")

        # Summary statistics
        total_tests = 0
        total_passed = 0
        total_failed = 0
        total_warnings = 0

        for suite_name, suite_results in results.items():
            if isinstance(suite_results, dict) and "error" not in suite_results:
                for test_name, test_result in suite_results.items():
                    total_tests += 1
                    status = test_result.get("status", "unknown")
                    if status == "pass":
                        total_passed += 1
                    elif status == "fail":
                        total_failed += 1
                    elif status == "warn":
                        total_warnings += 1

        report_lines.append("SUMMARY:")
        report_lines.append(f"  Total Tests: {total_tests}")
        report_lines.append(f"  ✅ Passed: {total_passed}")
        report_lines.append(f"  ⚠️  Warnings: {total_warnings}")
        report_lines.append(f"  ❌ Failed: {total_failed}")
        report_lines.append("")

        # Detailed results
        report_lines.append("DETAILED RESULTS:")
        for suite_name, suite_results in results.items():
            report_lines.append(f"\n{suite_name.upper().replace('_', ' ')}:")
            if isinstance(suite_results, dict) and "error" in suite_results:
                report_lines.append(f"  ❌ CRASHED: {suite_results['error']}")
            else:
                for test_name, test_result in suite_results.items():
                    status = test_result.get("status", "unknown")
                    emoji = {"pass": "✅", "fail": "❌", "warn": "⚠️", "info": "ℹ️", "unknown": "?"}.get(status, "?")
                    report_lines.append(f"  {emoji} {test_name}: {test_result.get('output', '')}")

        # Issues and recommendations
        if self.errors or self.warnings:
            report_lines.append("\nISSUES FOUND:")
            for error in self.errors:
                report_lines.append(f"  ❌ {error}")
            for warning in self.warnings:
                report_lines.append(f"  ⚠️  {warning}")

        # Overall assessment
        report_lines.append("\nOVERALL ASSESSMENT:")
        if total_failed == 0 and total_warnings <= 2:
            report_lines.append("🎉 SYSTEM IS READY FOR DEPLOYMENT!")
        elif total_failed == 0:
            report_lines.append("⚠️  SYSTEM IS MOSTLY READY - ADDRESS WARNINGS BEFORE PRODUCTION")
        else:
            report_lines.append("❌ CRITICAL ISSUES FOUND - DEPLOYMENT NOT RECOMMENDED")

        return "\n".join(report_lines)

async def main():
    """Main test execution function."""
    tester = ComprehensiveTester()

    try:
        results = await tester.run_all_tests()
        report = tester.generate_report(results)

        print("\n" + report)

        # Save detailed results to file
        with open("comprehensive_test_results.json", "w") as f:
            json.dump(results, f, indent=2, default=str)

        with open("comprehensive_test_report.txt", "w") as f:
            f.write(report)

        print("\n📄 Detailed results saved to: comprehensive_test_results.json")
        print("📄 Report saved to: comprehensive_test_report.txt")

        # Exit with appropriate code
        if tester.errors:
            sys.exit(1)
        elif tester.warnings:
            sys.exit(2)  # Warnings but no errors
        else:
            sys.exit(0)  # All good

    except Exception as e:
        print(f"❌ Test suite crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
