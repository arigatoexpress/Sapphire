#!/usr/bin/env python3
"""
Command Deck v3.0 Deployment Test Script
Tests all endpoints and integrations
"""

import sys
import requests
from requests.auth import HTTPBasicAuth
import json

class CommandDeckTester:
    def __init__(self, base_url, username=None, password=None):
        self.base_url = base_url.rstrip('/')
        self.auth = HTTPBasicAuth(username, password) if username and password else None
        self.results = []
        
    def test(self, name, method, path, expected_status=200, data=None):
        """Test an endpoint"""
        url = f"{self.base_url}{path}"
        try:
            if method == 'GET':
                resp = requests.get(url, auth=self.auth, timeout=10)
            elif method == 'POST':
                resp = requests.post(url, json=data, auth=self.auth, timeout=10)
            else:
                raise ValueError(f"Unknown method: {method}")
            
            passed = resp.status_code == expected_status
            self.results.append({
                'name': name,
                'passed': passed,
                'status': resp.status_code,
                'expected': expected_status
            })
            
            status = "✓" if passed else "✗"
            print(f"  {status} {name}: HTTP {resp.status_code}")
            
            if passed and resp.headers.get('content-type', '').startswith('application/json'):
                return resp.json()
            return None
            
        except Exception as e:
            self.results.append({
                'name': name,
                'passed': False,
                'error': str(e)
            })
            print(f"  ✗ {name}: {e}")
            return None
    
    def run_all_tests(self):
        """Run complete test suite"""
        print(f"\nTesting Command Deck at {self.base_url}")
        print("=" * 60)
        
        # Public endpoints
        print("\n1. Public Endpoints:")
        health = self.test("Health Check", "GET", "/health")
        if health:
            print(f"     Version: {health.get('version')}")
            print(f"     Service: {health.get('service')}")
        
        self.test("API Health Alias", "GET", "/api/health")
        
        # Protected endpoints
        print("\n2. Dashboard & Status:")
        self.test("Dashboard", "GET", "/api/dashboard")
        self.test("System Status", "GET", "/api/status")
        self.test("Trading Metrics", "GET", "/api/metrics")
        
        print("\n3. PM Integration:")
        self.test("PM Projects", "GET", "/api/pm/projects")
        self.test("PM Tasks", "GET", "/api/pm/tasks")
        self.test("PM Activity", "GET", "/api/pm/activity?limit=5")
        
        print("\n4. Data Endpoints:")
        self.test("Logs", "GET", "/api/logs?limit=5")
        self.test("Metrics History", "GET", "/api/metrics/history?hours=24")
        
        print("\n5. Terminal Commands:")
        self.test("Terminal Help", "POST", "/api/terminal", data={"command": "help"})
        self.test("Terminal Status", "POST", "/api/terminal", data={"command": "status"})
        self.test("Terminal PM", "POST", "/api/terminal", data={"command": "pm"})
        
        # Summary
        print("\n" + "=" * 60)
        passed = sum(1 for r in self.results if r.get('passed'))
        total = len(self.results)
        print(f"Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("✓ All tests passed!")
            return 0
        else:
            print(f"✗ {total - passed} tests failed")
            return 1

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Command Deck deployment")
    parser.add_argument("--url", default="http://localhost:8082", help="Base URL")
    parser.add_argument("--username", default="sapphire", help="Auth username")
    parser.add_argument("--password", default="alpha2024", help="Auth password")
    parser.add_argument("--no-auth", action="store_true", help="Disable auth")
    
    args = parser.parse_args()
    
    auth = None if args.no_auth else (args.username, args.password)
    tester = CommandDeckTester(args.url, *auth if auth else ())
    
    sys.exit(tester.run_all_tests())
