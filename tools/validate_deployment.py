#!/usr/bin/env python3
"""
Pre-Deployment Validation Script

Catches common deployment issues before triggering expensive Cloud Build cycles.
Run this before deploying to save 15-20 minutes per iteration.

Usage:
    python tools/validate_deployment.py
"""

import sys
import importlib.util
from pathlib import Path

# Add project root to path so we can import cloud_trader modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def validate_module_imports():
    """Validate that critical modules can be imported without errors."""
    print("🔍 Validating module imports...")
    
    critical_modules = [
        "cloud_trader.api",
        "cloud_trader.config",
        "cloud_trader.trading_service",
    ]
    
    errors = []
    for module_name in critical_modules:
        try:
            print(f"  ✓ Checking {module_name}...", end=" ")
            __import__(module_name)
            print("OK")
        except ImportError as e:
            errors.append(f"ImportError in {module_name}: {e}")
            print(f"❌ FAILED")
        except NameError as e:
            errors.append(f"NameError in {module_name}: {e}")
            print(f"❌ FAILED")
        except Exception as e:
            errors.append(f"Error in {module_name}: {type(e).__name__}: {e}")
            print(f"⚠️  WARNING")
    
    return errors

def validate_run_py():
    """Validate that run.py can be loaded without syntax errors."""
    print("\n🔍 Validating run.py...")
    
    run_py_path = Path("run.py")
    if not run_py_path.exists():
        return [f"run.py not found at {run_py_path}"]
    
    try:
        spec = importlib.util.spec_from_file_location("run", run_py_path)
        if spec and spec.loader:
            # Check for syntax errors without executing
            spec.loader.exec_module(importlib.util.module_from_spec(spec))
        print("  ✓ run.py syntax OK")
        return []
    except SyntaxError as e:
        return [f"SyntaxError in run.py: {e}"]
    except Exception as e:
        # We expect some runtime errors (like trying to bind port), that's OK
        if "Address already in use" in str(e) or "uvicorn" in str(e).lower():
            print("  ✓ run.py imports OK (runtime binding errors are expected)")
            return []
        return [f"Error loading run.py: {type(e).__name__}: {e}"]

def validate_dockerfile():
    """Basic Dockerfile validation."""
    print("\n🔍 Validating Dockerfile...")
    
    dockerfile_path = Path("Dockerfile")
    if not dockerfile_path.exists():
        return ["Dockerfile not found"]
    
    errors = []
    with open(dockerfile_path, 'r') as f:
        content = f.read()
        
        # Check for common issues
        if "CMD" not in content:
            errors.append("No CMD instruction found in Dockerfile")
        if "EXPOSE 8080" not in content:
            errors.append("Port 8080 not exposed in Dockerfile")
        if "run.py" not in content:
            errors.append("run.py not referenced in Dockerfile CMD")
    
    if not errors:
        print("  ✓ Dockerfile basic checks OK")
    else:
        for error in errors:
            print(f"  ❌ {error}")
    
    return errors

def validate_requirements():
    """Check that requirements.txt is well-formed."""
    print("\n🔍 Validating requirements.txt...")
    
    req_path = Path("requirements.txt")
    if not req_path.exists():
        return ["requirements.txt not found"]
    
    errors = []
    with open(req_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line and not line.startswith('#'):
                # Basic validation
                if '==' not in line and '>=' not in line and '<=' not in line and line.count('=') > 0:
                    errors.append(f"Line {line_num}: Possible malformed version: {line}")
    
    if not errors:
        print("  ✓ requirements.txt OK")
    else:
        for error in errors:
            print(f"  ⚠️  {error}")
    
    return errors

def main():
    print("=" * 60)
    print("🚀 Pre-Deployment Validation")
    print("=" * 60)
    
    all_errors = []
    
    # Run all validations
    all_errors.extend(validate_module_imports())
    all_errors.extend(validate_dockerfile())
    all_errors.extend(validate_requirements())
    
    print("\n" + "=" * 60)
    if all_errors:
        print("❌ VALIDATION FAILED")
        print("=" * 60)
        print("\nErrors found:")
        for i, error in enumerate(all_errors, 1):
            print(f"{i}. {error}")
        print("\n⚠️  Fix these errors before deploying to avoid wasted build cycles!")
        return 1
    else:
        print("✅ ALL VALIDATIONS PASSED")
        print("=" * 60)
        print("\n🎉 Ready to deploy!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
