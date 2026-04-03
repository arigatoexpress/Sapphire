#!/usr/bin/env python3
"""
Check if Ollama update is needed for Qwen 3.5 support
"""

import subprocess
import re
import sys


def check_ollama_version():
    """Check current Ollama version"""
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        version_output = result.stdout + result.stderr
        print(f"Ollama version output: {version_output.strip()}")
        
        # Extract version number
        match = re.search(r'(\d+)\.(\d+)\.(\d+)', version_output)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            patch = int(match.group(3))
            
            version_tuple = (major, minor, patch)
            print(f"Detected version: {major}.{minor}.{patch}")
            
            return version_tuple
    except Exception as e:
        print(f"Error checking version: {e}")
        return None
    
    return None


def check_qwen35_support(version_tuple):
    """Check if version supports Qwen 3.5"""
    if not version_tuple:
        return False
    
    major, minor, patch = version_tuple
    
    # Qwen 3.5 requires Ollama 0.17.5+
    if major > 0:
        return True
    if major == 0 and minor > 17:
        return True
    if major == 0 and minor == 17 and patch >= 5:
        return True
    
    return False


def main():
    print("=" * 60)
    print("Ollama Version & Qwen 3.5 Support Checker")
    print("=" * 60)
    print()
    
    version = check_ollama_version()
    
    if version:
        major, minor, patch = version
        print(f"Current version: {major}.{minor}.{patch}")
        
        if check_qwen35_support(version):
            print()
            print("[SUCCESS] Qwen 3.5 is SUPPORTED!")
            print()
            print("You can now pull Qwen 3.5 models:")
            print("  ollama pull qwen3.5:9b")
            print("  ollama pull qwen3.5:27b")
            return 0
        else:
            print()
            print("[WARNING] Update REQUIRED!")
            print()
            print(f"Current: {major}.{minor}.{patch}")
            print("Required: 0.17.5 or later")
            print()
            print("To update Ollama:")
            print("  1. Right-click the Ollama icon in system tray")
            print("  2. Select 'Restart to update'")
            print("  3. Or download from: https://ollama.com/download")
            print()
            print("After updating, run this script again to verify.")
            return 1
    else:
        print("Could not detect Ollama version.")
        print("Make sure Ollama is installed and in your PATH.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
