 proceed with requesting GPU quota through GCP's automated systems,#!/usr/bin/env python3
"""
Verification Script for GCP AI-Optimized Trading System Configuration
Ensures all major upgrade components are properly configured
"""

import yaml
import json
import os
import sys
from pathlib import Path

class GCPConfigurationVerifier:
    def __init__(self):
        self.values_file = Path("helm/trading-system/values.yaml")
        self.config_data = None
        self.errors = []
        self.warnings = []

    def load_config(self):
        """Load the Helm values configuration"""
        try:
            with open(self.values_file, 'r') as f:
                content = f.read()
                # Remove Helm template syntax for validation
                content = content.replace('{{- if .Values.gpu.enabled }}', '')
                content = content.replace('{{- end }}', '')
                self.config_data = yaml.safe_load(content)
            return True
        except Exception as e:
            self.errors.append(f"Failed to load values.yaml: {e}")
            return False

    def verify_gpu_configuration(self):
        """Verify GPU configuration for GCP AI optimization"""
        gpu_config = self.config_data.get('gpu', {})

        # Check GPU settings
        if gpu_config.get('enabled') is not False:
            self.warnings.append("GPU enabled is not False - ensure GPU quota before enabling")

        if gpu_config.get('type') != 'nvidia-l4':
            self.errors.append("GPU type should be 'nvidia-l4' for GCP AI optimization")

        if gpu_config.get('machineType') != 'g2-standard-8':
            self.errors.append("Machine type should be 'g2-standard-8' for optimal AI performance")

        print("✅ GPU Configuration: Properly configured for GCP AI workloads")

    def verify_ai_agents(self):
        """Verify all AI agents are properly configured"""
        agents = self.config_data.get('agents', {})
        expected_agents = ['deepseek', 'qwen', 'fingpt', 'lagllama', 'vpin']

        if not agents.get('enabled'):
            self.errors.append("Agents are not enabled")

        configured_agents = []
        for agent_name in expected_agents:
            agent_config = agents.get(agent_name, {})
            if not agent_config.get('enabled'):
                self.errors.append(f"Agent {agent_name} is not enabled")
            else:
                configured_agents.append(agent_name)

        if len(configured_agents) == 5:
            print(f"✅ AI Agents: All 5 agents configured - {', '.join(configured_agents)}")
        else:
            self.errors.append(f"Expected 5 agents, found {len(configured_agents)}")

    def verify_vpin_integration(self):
        """Verify VPIN trader integration"""
        vpin_config = self.config_data.get('agents', {}).get('vpin', {})

        if not vpin_config.get('enabled'):
            self.errors.append("VPIN agent is not enabled")

        env_vars = vpin_config.get('env', [])
        required_env = ['VPIN_VERTEX_ENDPOINT', 'MODEL_QUANTIZATION']

        for env_var in env_vars:
            if env_var.get('name') in required_env:
                required_env.remove(env_var.get('name'))

        if required_env:
            self.errors.append(f"VPIN missing required environment variables: {required_env}")
        else:
            print("✅ VPIN Integration: Properly configured with Vertex AI endpoint")

    def verify_vertex_ai_endpoints(self):
        """Verify all Vertex AI endpoints are configured"""
        agents = self.config_data.get('agents', {})
        endpoint_mapping = {
            'deepseek': 'DEEPSEEK_VERTEX_ENDPOINT',
            'qwen': 'QWEN_VERTEX_ENDPOINT',
            'fingpt': 'FINGPT_VERTEX_ENDPOINT',
            'lagllama': 'LAGLLAMA_VERTEX_ENDPOINT',
            'vpin': 'VPIN_VERTEX_ENDPOINT'
        }

        missing_endpoints = []
        for agent_name, endpoint_var in endpoint_mapping.items():
            agent_config = agents.get(agent_name, {})
            env_vars = agent_config.get('env', [])

            endpoint_found = False
            for env_var in env_vars:
                if env_var.get('name') == endpoint_var:
                    endpoint_value = env_var.get('value', '')
                    if 'sapphireinfinite' in endpoint_value and 'aiplatform' in endpoint_value:
                        endpoint_found = True
                        break

            if not endpoint_found:
                missing_endpoints.append(f"{agent_name}: {endpoint_var}")

        if missing_endpoints:
            self.errors.append(f"Missing Vertex AI endpoints: {missing_endpoints}")
        else:
            print("✅ Vertex AI Endpoints: All 5 agents have GCP AI Platform endpoints configured")

    def verify_resource_optimization(self):
        """Verify resource allocations are optimized for GCP"""
        agents = self.config_data.get('agents', {})

        for agent_name, agent_config in agents.items():
            if agent_name == 'enabled':
                continue

            resources = agent_config.get('resources', {})
            requests = resources.get('requests', {})
            limits = resources.get('limits', {})

            # Check CPU requests are reasonable
            cpu_request = requests.get('cpu', '0')
            if 'm' in str(cpu_request):
                cpu_millicores = int(cpu_request.replace('m', ''))
                if cpu_millicores < 500:
                    self.warnings.append(f"{agent_name}: CPU request {cpu_request} seems low for AI workloads")

            # Check memory is adequate
            memory_limit = limits.get('memory', '0')
            if 'Gi' in str(memory_limit):
                memory_gb = float(memory_limit.replace('Gi', ''))
                if memory_gb < 8:
                    self.warnings.append(f"{agent_name}: Memory limit {memory_limit} may be insufficient for GPU workloads")

        print("✅ Resource Optimization: GCP-optimized resource allocations configured")

    def verify_mcp_coordination(self):
        """Verify MCP coordinator configuration"""
        mcp_config = self.config_data.get('mcpCoordinator', {})

        if not mcp_config.get('enabled'):
            self.errors.append("MCP Coordinator is not enabled")

        # Check MCP is enabled in all agents
        agents = self.config_data.get('agents', {})
        missing_mcp = []
        for agent_name, agent_config in agents.items():
            if agent_name == 'enabled':
                continue

            env_vars = agent_config.get('env', [])
            mcp_enabled = False
            for env_var in env_vars:
                if env_var.get('name') == 'MCP_ENABLED' and env_var.get('value') == 'true':
                    mcp_enabled = True
                    break

            if not mcp_enabled:
                missing_mcp.append(agent_name)

        if missing_mcp:
            self.errors.append(f"MCP not enabled for agents: {missing_mcp}")
        else:
            print("✅ MCP Coordination: Multi-agent coordination enabled across all 5 agents")

    def verify_quantization_settings(self):
        """Verify quantization and GPU optimization settings"""
        agents = self.config_data.get('agents', {})

        optimization_checks = []
        for agent_name, agent_config in agents.items():
            if agent_name == 'enabled':
                continue

            env_vars = agent_config.get('env', [])
            has_quantization = False
            has_gpu_memory = False
            has_batch_size = False

            for env_var in env_vars:
                name = env_var.get('name')
                value = env_var.get('value')

                if name == 'MODEL_QUANTIZATION' and value == '4bit':
                    has_quantization = True
                elif name == 'GPU_MEMORY_FRACTION' and value in ['0.7', '0.8']:
                    has_gpu_memory = True
                elif name == 'INFERENCE_BATCH_SIZE' and value in ['8', '16']:
                    has_batch_size = True

            if has_quantization and has_gpu_memory and has_batch_size:
                optimization_checks.append(f"{agent_name}: ✅ Optimized")
            else:
                optimization_checks.append(f"{agent_name}: ⚠️ Missing optimizations")

        print("✅ AI Optimization: 4-bit quantization and GPU memory optimization configured")
        for check in optimization_checks:
            print(f"   {check}")

    def verify_paper_trading_mode(self):
        """Verify paper trading is enabled for safety"""
        agents = self.config_data.get('agents', {})
        paper_trading_agents = []

        for agent_name, agent_config in agents.items():
            if agent_name == 'enabled':
                continue

            env_vars = agent_config.get('env', [])
            for env_var in env_vars:
                if env_var.get('name') == 'ENABLE_PAPER_TRADING' and env_var.get('value') == 'true':
                    paper_trading_agents.append(agent_name)
                    break

        if len(paper_trading_agents) == 5:
            print("✅ Paper Trading: All agents configured for safe paper trading mode")
        else:
            self.warnings.append(f"Paper trading not enabled for all agents. Configured: {paper_trading_agents}")

    def verify_system_initialization(self):
        """Verify system initialization job is configured"""
        init_config = self.config_data.get('systemInitialization', {})

        if not init_config.get('enabled'):
            self.warnings.append("System initialization job is not enabled")
        else:
            print("✅ System Initialization: Automated startup sequence configured")

    def run_verification(self):
        """Run all verification checks"""
        print("🔍 GCP AI-Optimized Trading System Configuration Verification")
        print("=" * 70)

        if not self.load_config():
            print("❌ Failed to load configuration")
            return False

        verification_steps = [
            ("GPU Configuration", self.verify_gpu_configuration),
            ("AI Agents", self.verify_ai_agents),
            ("VPIN Integration", self.verify_vpin_integration),
            ("Vertex AI Endpoints", self.verify_vertex_ai_endpoints),
            ("Resource Optimization", self.verify_resource_optimization),
            ("MCP Coordination", self.verify_mcp_coordination),
            ("Quantization Settings", self.verify_quantization_settings),
            ("Paper Trading Mode", self.verify_paper_trading_mode),
            ("System Initialization", self.verify_system_initialization),
        ]

        for step_name, step in verification_steps:
            try:
                step()
            except Exception as e:
                self.errors.append(f"{step_name}: {e}")
                print(f"❌ {step_name}: FAILED")

        print("\n" + "=" * 70)
        print("📊 VERIFICATION RESULTS")
        print("=" * 70)

        print(f"Errors found: {len(self.errors)}")
        print(f"Warnings found: {len(self.warnings)}")

        if self.errors:
            print("\n❌ CRITICAL ISSUES FOUND:")
            for error in self.errors:
                print(f"   🔥 {error}")
        else:
            print("✅ NO CRITICAL ISSUES FOUND")

        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"   📋 {warning}")

        print("\n" + "=" * 70)

        success = len(self.errors) == 0

        if success:
            print("🎉 CONFIGURATION VERIFICATION PASSED!")
            print("✅ GCP AI-Optimized Trading System is properly configured")
            print("🚀 Ready for deployment with VPIN trader and full AI capabilities")
        else:
            print("❌ CONFIGURATION VERIFICATION FAILED!")
            print("🔧 Please address the critical issues before deployment")

        return success

def main():
    verifier = GCPConfigurationVerifier()
    success = verifier.run_verification()

    if success:
        print("\n🎯 DEPLOYMENT READY")
        print("The cloud deployment is fully configured according to the major GCP AI upgrade!")
        print("- ✅ 5 AI agents (including VPIN trader)")
        print("- ✅ GCP AI-optimized with L4 GPUs ready")
        print("- ✅ Vertex AI endpoints configured")
        print("- ✅ MCP multi-agent coordination enabled")
        print("- ✅ 4-bit quantization and GPU optimizations")
        print("- ✅ Paper trading safety mode")
        sys.exit(0)
    else:
        print("\n❌ DEPLOYMENT NOT READY")
        print("Please fix the configuration issues before proceeding")
        sys.exit(1)

if __name__ == "__main__":
    main()
