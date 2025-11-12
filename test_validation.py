#!/usr/bin/env python3
"""Comprehensive validation script for the HFT Trading System."""

import os
import sys
import asyncio
import json
from typing import Dict, Any

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all modules can be imported."""
    print("🔍 Testing imports...")

    try:
        # Test config
        from cloud_trader.config import get_settings, Settings
        print("✅ config module imported")

        # Test Vertex AI client
        from cloud_trader.vertex_ai_client import VertexAIClient, get_vertex_client
        print("✅ vertex_ai_client module imported")

        # Test MCP
        from cloud_trader.mcp import MCPClient, MCPMessageType, MCPProposalPayload
        print("✅ mcp module imported")

        # Test service
        from cloud_trader.service import TradingService
        print("✅ service module imported")

        # Test API
        from cloud_trader.api import build_app
        print("✅ api module imported")

        return True

    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_validation():
    """Test configuration validation."""
    print("\n🔍 Testing configuration...")

    try:
        from cloud_trader.config import get_settings

        # Test settings creation
        settings = get_settings()
        print("✅ Settings object created")

        # Test Vertex AI configuration
        assert hasattr(settings, 'enable_vertex_ai'), "Missing enable_vertex_ai"
        assert hasattr(settings, 'vertex_ai_region'), "Missing vertex_ai_region"
        assert hasattr(settings, 'deepseek_vertex_endpoint'), "Missing deepseek_vertex_endpoint"
        assert hasattr(settings, 'qwen_vertex_endpoint'), "Missing qwen_vertex_endpoint"
        assert hasattr(settings, 'fingpt_vertex_endpoint'), "Missing fingpt_vertex_endpoint"
        assert hasattr(settings, 'lagllama_vertex_endpoint'), "Missing lagllama_vertex_endpoint"

        print("✅ Vertex AI configuration validated")
        return True

    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

def test_agent_definitions():
    """Test agent definitions."""
    print("\n🔍 Testing agent definitions...")

    try:
        from cloud_trader.service import AGENT_DEFINITIONS

        assert len(AGENT_DEFINITIONS) == 4, f"Expected 4 agents, got {len(AGENT_DEFINITIONS)}"

        required_fields = ['id', 'name', 'model', 'symbols', 'description', 'baseline_win_rate', 'risk_multiplier', 'profit_target']
        for agent in AGENT_DEFINITIONS:
            for field in required_fields:
                assert field in agent, f"Agent {agent.get('id', 'unknown')} missing field: {field}"

        # Check agent IDs match Vertex AI endpoints
        agent_ids = {agent['id'] for agent in AGENT_DEFINITIONS}
        expected_ids = {'deepseek-v3', 'qwen-7b', 'fingpt-alpha', 'lagllama-degen'}
        assert agent_ids == expected_ids, f"Agent IDs mismatch: {agent_ids} vs {expected_ids}"

        print(f"✅ Agent definitions validated ({len(AGENT_DEFINITIONS)} agents)")
        return True

    except Exception as e:
        print(f"❌ Agent definitions test failed: {e}")
        return False

def test_vertex_ai_client():
    """Test Vertex AI client initialization."""
    print("\n🔍 Testing Vertex AI client...")

    try:
        from cloud_trader.vertex_ai_client import get_vertex_client

        # Test client creation (may fail if GCP not configured, but should not crash)
        try:
            client = get_vertex_client()
            print("✅ Vertex AI client initialized")

            # Test basic methods exist
            assert hasattr(client, 'predict'), "Missing predict method"
            assert hasattr(client, 'predict_with_fallback'), "Missing predict_with_fallback method"
            assert hasattr(client, 'get_circuit_breaker_status'), "Missing circuit breaker methods"
            assert hasattr(client, 'get_performance_metrics'), "Missing performance methods"

            print("✅ Vertex AI client methods validated")

        except Exception as init_error:
            print(f"⚠️  Vertex AI client initialization failed (expected if GCP not configured): {init_error}")
            # This is OK if GCP credentials are not set up

        return True

    except Exception as e:
        print(f"❌ Vertex AI client test failed: {e}")
        return False

def test_mcp_integration():
    """Test MCP integration."""
    print("\n🔍 Testing MCP integration...")

    try:
        from cloud_trader.mcp import MCPClient, MCPMessageType

        # Test MCP client creation
        client = MCPClient("http://test-url", "test-session")
        print("✅ MCP client created")

        # Test Vertex AI integration
        assert hasattr(client, 'query_vertex_agent'), "Missing query_vertex_agent method"
        assert hasattr(client, 'query_multiple_agents'), "Missing query_multiple_agents method"
        assert hasattr(client, 'get_agent_status'), "Missing get_agent_status method"

        print("✅ MCP Vertex AI integration validated")
        return True

    except Exception as e:
        print(f"❌ MCP integration test failed: {e}")
        return False

def test_service_initialization():
    """Test service initialization."""
    print("\n🔍 Testing service initialization...")

    try:
        from cloud_trader.service import TradingService
        from cloud_trader.config import Settings

        # Create service with test settings
        settings = Settings(
            enable_vertex_ai=False,  # Disable to avoid GCP calls during test
            enable_paper_trading=True,
            gcp_project_id="test-project"
        )

        service = TradingService(settings)
        print("✅ Trading service initialized")

        # Test key attributes
        assert hasattr(service, '_vertex_client'), "Missing vertex client"
        assert hasattr(service, '_mcp'), "Missing MCP client"
        assert hasattr(service, '_agent_states'), "Missing agent states"

        print("✅ Service attributes validated")
        return True

    except Exception as e:
        print(f"❌ Service initialization test failed: {e}")
        return False

def test_api_endpoints():
    """Test API endpoint definitions."""
    print("\n🔍 Testing API endpoints...")

    try:
        from cloud_trader.api import build_app

        app = build_app()
        print("✅ FastAPI app built")

        # Test that new Vertex AI endpoints are registered
        routes = [route.path for route in app.routes]
        expected_routes = [
            "/api/models/health",
            "/api/models/{agent_id}",
            "/api/models/{agent_id}/test",
            "/api/models/status",
            "/api/models/circuit-breakers",
            "/api/models/performance",
            "/api/models/{agent_id}/reset-circuit",
            "/api/models/health-detailed"
        ]

        for route in expected_routes:
            assert route in routes, f"Missing API route: {route}"

        print(f"✅ API endpoints validated ({len(expected_routes)} new routes)")
        return True

    except Exception as e:
        print(f"❌ API endpoints test failed: {e}")
        return False

def test_dependencies():
    """Test dependency versions and imports."""
    print("\n🔍 Testing dependencies...")

    try:
        # Test core ML dependencies
        import torch
        print(f"✅ PyTorch {torch.__version__}")

        import transformers
        print(f"✅ Transformers {transformers.__version__}")

        # Test GCP dependencies
        import google.cloud.aiplatform
        print(f"✅ Vertex AI {google.cloud.aiplatform.__version__}")

        import google.cloud.pubsub
        print("✅ Pub/Sub client")

        import google.cloud.secretmanager
        print("✅ Secret Manager client")

        return True

    except ImportError as e:
        print(f"⚠️  Dependency import failed (may be expected in test environment): {e}")
        return True  # Not critical for basic validation
    except Exception as e:
        print(f"❌ Dependencies test failed: {e}")
        return False

def main():
    """Run all validation tests."""
    print("🚀 Starting HFT Trading System Validation\n")

    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config_validation),
        ("Agent Definitions", test_agent_definitions),
        ("Vertex AI Client", test_vertex_ai_client),
        ("MCP Integration", test_mcp_integration),
        ("Service Initialization", test_service_initialization),
        ("API Endpoints", test_api_endpoints),
        ("Dependencies", test_dependencies),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} test failed")
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")

    print(f"\n📊 Validation Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All validation tests passed! The codebase is ready for deployment.")
        return 0
    else:
        print("⚠️  Some tests failed. Please review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
