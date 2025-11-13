#!/usr/bin/env python3
"""
Comprehensive Proactive Testing Suite for Sapphire Trading System
Tests hardware, cloud configurations, and identifies issues before deployment
"""

import subprocess
import sys
import json
import os
from datetime import datetime
from typing import Dict, List, Tuple

class CloudTester:
    def __init__(self):
        self.project_id = "sapphireinfinite"
        self.cluster_name = "hft-trading-cluster"
        self.zone = "us-central1-a"
        self.namespace = "trading"
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {},
            "summary": {"passed": 0, "failed": 0, "warnings": 0}
        }

    def run_command(self, cmd: str, description: str = "", check: bool = True) -> Tuple[bool, str]:
        """Run a shell command and return success status and output"""
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            success = result.returncode == 0
            output = result.stdout if success else result.stderr
            if description:
                status = "✅ PASS" if success else "❌ FAIL"
                print(f"{status}: {description}")
                if not success:
                    print(f"   Error: {output}")
            return success, output.strip()
        except subprocess.TimeoutExpired:
            print(f"⏰ TIMEOUT: {description}")
            return False, "Command timed out"
        except Exception as e:
            print(f"💥 ERROR: {description} - {str(e)}")
            return False, str(e)

    def test_gke_cluster_health(self):
        """Test GKE cluster health and basic connectivity"""
        print("\n🔍 Testing GKE Cluster Health...")

        tests = [
            ("Cluster exists", f"gcloud container clusters describe {self.cluster_name} --zone={self.zone} --project={self.project_id} --format='value(status)'"),
            ("Cluster running", f"gcloud container clusters describe {self.cluster_name} --zone={self.zone} --project={self.project_id} --format='value(status)' | grep -q RUNNING"),
            ("Get credentials", f"gcloud container clusters get-credentials {self.cluster_name} --zone={self.zone} --project={self.project_id}"),
            ("Cluster connectivity", "kubectl cluster-info"),
            ("Node count", "kubectl get nodes --no-headers | wc -l"),
            ("Pod capacity", "kubectl get nodes -o jsonpath='{.items[*].status.capacity.pods}' | tr ' ' '+' | bc"),
        ]

        for desc, cmd in tests:
            success, output = self.run_command(cmd, desc)
            self.results["tests"][f"gke_{desc.lower().replace(' ', '_')}"] = {
                "status": "pass" if success else "fail",
                "output": output
            }

    def test_resource_allocations(self):
        """Test resource allocations and limits"""
        print("\n💾 Testing Resource Allocations...")

        tests = [
            ("Node CPU capacity", "kubectl get nodes -o jsonpath='{.items[*].status.capacity.cpu}' | tr ' ' '+' | bc"),
            ("Node memory capacity", "kubectl get nodes -o jsonpath='{.items[*].status.capacity.memory}' | sed 's/Ki//g' | tr ' ' '+' | bc"),
            ("GPU availability", "kubectl get nodes -l cloud.google.com/gke-accelerator | wc -l"),
            ("Storage classes", "kubectl get storageclass --no-headers | wc -l"),
        ]

        for desc, cmd in tests:
            success, output = self.run_command(cmd, desc)
            self.results["tests"][f"resource_{desc.lower().replace(' ', '_')}"] = {
                "status": "pass" if success else "fail",
                "output": output
            }

    def test_network_connectivity(self):
        """Test network connectivity and DNS"""
        print("\n🌐 Testing Network Connectivity...")

        tests = [
            ("DNS resolution", "nslookup google.com"),
            ("External connectivity", "curl -s --connect-timeout 5 google.com > /dev/null && echo 'Connected' || echo 'Failed'"),
            ("Artifact Registry access", f"gcloud artifacts repositories describe cloud-run-source-deploy --location=us-central1 --project={self.project_id}"),
            ("Service account permissions", f"gcloud projects get-iam-policy {self.project_id} --filter='serviceAccount:*' --format='value(bindings.role)' | head -5"),
        ]

        for desc, cmd in tests:
            success, output = self.run_command(cmd, desc)
            self.results["tests"][f"network_{desc.lower().replace(' ', '_')}"] = {
                "status": "pass" if success else "fail",
                "output": output
            }

    def test_helm_charts(self):
        """Test Helm chart validation"""
        print("\n⚓ Testing Helm Charts...")

        # Test if helm is available
        success, output = self.run_command("helm version --short", "Helm availability")
        if not success:
            self.results["tests"]["helm_availability"] = {"status": "fail", "output": "Helm not installed"}
            return

        tests = [
            ("Chart validation", "helm template test ./helm/trading-system --dry-run"),
            ("Dependency check", "helm dependency list ./helm/trading-system"),
            ("Chart linting", "helm lint ./helm/trading-system"),
        ]

        for desc, cmd in tests:
            success, output = self.run_command(cmd, desc)
            self.results["tests"][f"helm_{desc.lower().replace(' ', '_')}"] = {
                "status": "pass" if success else "fail",
                "output": output
            }

    def test_container_images(self):
        """Test container image accessibility"""
        print("\n🐳 Testing Container Images...")

        images = [
            f"us-central1-docker.pkg.dev/{self.project_id}/cloud-run-source-deploy/cloud-trader:latest",
        ]

        for image in images:
            success, output = self.run_command(f"docker pull {image}", f"Pull image {image}")
            self.results["tests"][f"image_{image.split('/')[-1]}"] = {
                "status": "pass" if success else "fail",
                "output": output
            }

    def test_security_configurations(self):
        """Test security configurations"""
        print("\n🔒 Testing Security Configurations...")

        tests = [
            ("RBAC enabled", "kubectl api-versions | grep -q rbac && echo 'RBAC enabled' || echo 'RBAC not found'"),
            ("Network policies", "kubectl get networkpolicies --all-namespaces | wc -l"),
            ("Pod security standards", "kubectl get pods -o jsonpath='{.items[*].spec.securityContext}' | grep -o 'securityContext' | wc -l"),
            ("Service accounts", "kubectl get serviceaccounts --no-headers | wc -l"),
        ]

        for desc, cmd in tests:
            success, output = self.run_command(cmd, desc)
            self.results["tests"][f"security_{desc.lower().replace(' ', '_')}"] = {
                "status": "pass" if success else "fail",
                "output": output
            }

    def generate_report(self):
        """Generate comprehensive test report"""
        print("\n📊 Generating Test Report...")

        # Calculate summary
        for test_name, test_result in self.results["tests"].items():
            if test_result["status"] == "pass":
                self.results["summary"]["passed"] += 1
            elif test_result["status"] == "fail":
                self.results["summary"]["failed"] += 1
            else:
                self.results["summary"]["warnings"] += 1

        # Save detailed report
        with open("proactive_test_report.json", "w") as f:
            json.dump(self.results, f, indent=2)

        # Print summary
        print("\n" + "="*60)
        print("🎯 PROACTIVE TESTING SUMMARY")
        print("="*60)
        print(f"✅ Passed: {self.results['summary']['passed']}")
        print(f"❌ Failed: {self.results['summary']['failed']}")
        print(f"⚠️  Warnings: {self.results['summary']['warnings']}")
        print(f"📅 Timestamp: {self.results['timestamp']}")

        # Show critical failures
        critical_failures = []
        for test_name, test_result in self.results["tests"].items():
            if test_result["status"] == "fail":
                if any(keyword in test_name for keyword in ["cluster", "connectivity", "helm", "image"]):
                    critical_failures.append(test_name)

        if critical_failures:
            print("\n🚨 CRITICAL ISSUES FOUND:")
            for failure in critical_failures:
                print(f"   - {failure}")
            print("\n💡 Recommendation: Address critical issues before deployment")
        else:
            print("\n🎉 All critical systems operational!")

        print(f"\n📄 Detailed report saved to: proactive_test_report.json")

    def run_all_tests(self):
        """Run all proactive tests"""
        print("🚀 Starting Comprehensive Proactive Testing Suite")
        print("="*60)

        self.test_gke_cluster_health()
        self.test_resource_allocations()
        self.test_network_connectivity()
        self.test_helm_charts()
        self.test_container_images()
        self.test_security_configurations()

        self.generate_report()

if __name__ == "__main__":
    tester = CloudTester()
    tester.run_all_tests()
