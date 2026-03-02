#!/usr/bin/env python3
"""Test Sapphire Commander functionality"""

import sys
import requests

def test_imports():
    """Test that required modules can be imported"""
    print("Testing imports...")
    
    try:
        import rumps
        print("✓ rumps imported")
    except ImportError as e:
        print(f"✗ rumps failed: {e}")
        return False
        
    try:
        import requests
        print("✓ requests imported")
    except ImportError as e:
        print(f"✗ requests failed: {e}")
        return False
    
    return True

def test_api_endpoints():
    """Test API connectivity"""
    print("\nTesting API connectivity...")
    
    base_url = "https://sapphirealpha.xyz"
    
    # Health endpoint
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
        print(f"✓ Health endpoint: {resp.status_code}")
        data = resp.json()
        print(f"  Service: {data.get('service')}")
        print(f"  Version: {data.get('version')}")
    except Exception as e:
        print(f"✗ Health failed: {e}")
        return False
    
    # Status endpoint
    try:
        resp = requests.get(f"{base_url}/api/status", timeout=5)
        print(f"✓ Status endpoint: {resp.status_code}")
        data = resp.json()
        by_cat = data.get('by_category', {})
        total = sum(len(svcs) for svcs in by_cat.values())
        healthy = sum(
            1 for cat in by_cat.values() 
            for svc in cat if svc.get('healthy')
        )
        print(f"  Services: {healthy}/{total} healthy")
    except Exception as e:
        print(f"✗ Status failed: {e}")
        return False
    
    # Projects endpoint
    try:
        resp = requests.get(f"{base_url}/api/projects", timeout=5)
        print(f"✓ Projects endpoint: {resp.status_code}")
        data = resp.json()
        print(f"  Projects: {data.get('count')}")
        for p in data.get('projects', [])[:3]:
            print(f"    - {p.get('name')} ({p.get('status')})")
    except Exception as e:
        print(f"✗ Projects failed: {e}")
        return False
    
    # Trading metrics
    try:
        resp = requests.get(f"{base_url}/api/trading/metrics", timeout=5)
        print(f"✓ Trading metrics: {resp.status_code}")
        data = resp.json()
        print(f"  Active signals: {data.get('active_signals')}")
    except Exception as e:
        print(f"✗ Trading metrics failed: {e}")
        # Non-critical
    
    # Prices endpoint
    try:
        resp = requests.get(f"{base_url}/api/market/prices", timeout=5)
        print(f"✓ Prices endpoint: {resp.status_code}")
        data = resp.json()
        btc = data.get('BTC', {}).get('price', 0)
        eth = data.get('ETH', {}).get('price', 0)
        sol = data.get('SOL', {}).get('price', 0)
        print(f"  BTC: ${btc:,.0f}")
        print(f"  ETH: ${eth:,.0f}")
        print(f"  SOL: ${sol:,.0f}")
    except Exception as e:
        print(f"✗ Prices failed: {e}")
        return False
    
    # Terminal endpoint
    try:
        resp = requests.post(
            f"{base_url}/api/terminal",
            json={"command": "help"},
            timeout=5
        )
        print(f"✓ Terminal endpoint: {resp.status_code}")
        data = resp.json()
        print(f"  Type: {data.get('type')}")
    except Exception as e:
        print(f"✗ Terminal failed: {e}")
        return False
    
    return True

def test_menu_structure():
    """Test that menu structure is valid"""
    print("\nTesting menu structure...")
    
    # Import the main app module
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("app", "sapphire_commander.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        print("✓ App module loads successfully")
        
        # Check CONFIG
        config = module.CONFIG
        required_keys = ['sapphire_url', 'gateway_url', 'pm_hub_url', 'rari1_ip', 'rari2_ip']
        for key in required_keys:
            if key in config:
                print(f"  ✓ CONFIG.{key} = {config[key]}")
            else:
                print(f"  ✗ CONFIG.{key} missing")
                return False
        
        return True
    except Exception as e:
        print(f"✗ Menu structure test failed: {e}")
        return False

def main():
    print("=" * 60)
    print("Sapphire Commander - Test Suite")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("API Endpoints", test_api_endpoints()))
    results.append(("Menu Structure", test_menu_structure()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n✓ All tests passed! App is ready to run.")
        print("\nTo start the app:")
        print("  python3 sapphire_commander.py")
        return 0
    else:
        print("\n✗ Some tests failed. Please fix issues before running.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
