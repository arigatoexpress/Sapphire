#!/usr/bin/env python3
"""
Check available open source models on Vertex AI for trading applications
"""

import subprocess
import json
from typing import Dict, List, Any

def check_vertex_ai_models():
    """Check what models are available on Vertex AI"""

    # Check available models via gcloud
    try:
        result = subprocess.run([
            'gcloud', 'ai', 'models', 'list',
            '--region=us-central1',
            '--format=json'
        ], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            models = json.loads(result.stdout)
            print(f"✅ Found {len(models)} models in us-central1")
            return models
        else:
            print(f"❌ Error checking models: {result.stderr}")
            return []

    except Exception as e:
        print(f"❌ Exception checking models: {e}")
        return []

def check_model_garden():
    """Check Model Garden for available open source models"""

    models_to_check = [
        "llama3-8b-instruct",
        "llama3-70b-instruct",
        "mistral-large",
        "code-llama-7b-instruct",
        "bert-base-multilingual-cased",
        "t5-small",
        "palm-2-codechat-bison",
        "text-bison",
        "chat-bison"
    ]

    print("\n🔍 CHECKING MODEL GARDEN AVAILABILITY...")
    print("=" * 50)

    available_models = []

    for model in models_to_check:
        try:
            result = subprocess.run([
                'gcloud', 'ai', 'models', 'describe', model,
                '--region=us-central1'
            ], capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                print(f"✅ {model}: AVAILABLE")
                available_models.append(model)
            else:
                print(f"❌ {model}: NOT FOUND")

        except subprocess.TimeoutExpired:
            print(f"⏱️  {model}: TIMEOUT")
        except Exception as e:
            print(f"❓ {model}: ERROR - {e}")

    return available_models

def create_trading_model_configurations(available_models: List[str]):
    """Create optimized configurations for trading based on available models"""

    print(f"\n🎯 CREATING TRADING AGENT CONFIGURATIONS...")
    print("=" * 50)

    # Define trading roles and optimal models
    trading_agents = {
        "momentum_analyzer": {
            "role": "Real-time momentum analysis and trend detection",
            "requirements": "Fast inference, pattern recognition",
            "optimal_models": ["mistral-large", "llama3-8b-instruct", "chat-bison"],
            "temperature": 0.1,
            "max_tokens": 512,
            "latency_target": 200
        },
        "strategy_optimizer": {
            "role": "Complex strategy optimization and risk assessment",
            "requirements": "Advanced reasoning, mathematical analysis",
            "optimal_models": ["llama3-70b-instruct", "mistral-large", "text-bison"],
            "temperature": 0.3,
            "max_tokens": 1024,
            "latency_target": 500
        },
        "sentiment_analyzer": {
            "role": "Financial news and social media sentiment analysis",
            "requirements": "Natural language understanding, context awareness",
            "optimal_models": ["bert-base-multilingual-cased", "mistral-large", "llama3-8b-instruct"],
            "temperature": 0.2,
            "max_tokens": 256,
            "latency_target": 150
        },
        "market_predictor": {
            "role": "Time series forecasting and market prediction",
            "requirements": "Numerical analysis, pattern prediction",
            "optimal_models": ["llama3-70b-instruct", "t5-small", "text-bison"],
            "temperature": 0.4,
            "max_tokens": 768,
            "latency_target": 400
        },
        "volume_analyzer": {
            "role": "Volume microstructure analysis and VPIN calculation",
            "requirements": "High-frequency data processing, mathematical computation",
            "optimal_models": ["llama3-70b-instruct", "code-llama-7b-instruct", "text-bison"],
            "temperature": 0.1,
            "max_tokens": 1024,
            "latency_target": 300
        }
    }

    # Assign best available models to each role
    configurations = {}

    for agent_name, agent_config in trading_agents.items():
        selected_model = None

        # Find the best available model for this role
        for preferred_model in agent_config["optimal_models"]:
            if preferred_model in available_models:
                selected_model = preferred_model
                break

        if selected_model:
            configurations[agent_name] = {
                **agent_config,
                "selected_model": selected_model,
                "vertex_endpoint": f"https://us-central1-aiplatform.googleapis.com/v1/projects/sapphireinfinite/locations/us-central1/endpoints/{agent_name}-endpoint"
            }
            print(f"✅ {agent_name}: {selected_model}")
        else:
            print(f"❌ {agent_name}: No suitable model found")

    return configurations

def generate_updated_values_yaml(configurations: Dict[str, Any]):
    """Generate updated values.yaml with open source models"""

    print(f"\n📝 GENERATING UPDATED CONFIGURATIONS...")
    print("=" * 50)

    # Template for each agent configuration
    agent_template = """
  # {agent_name} - {role}
  {agent_name}:
    enabled: true
    replicaCount: 1
    image:
      repository: cloud-run-source-deploy/cloud-trader
      tag: "latest"
    resources:
      requests:
        cpu: 1000m
        memory: 4Gi
      limits:
        cpu: 3000m
        memory: 12Gi
    # Vertex AI Optimization for {role}
    vertexAI:
      model: "{selected_model}"
      optimization:
        quantization: "int8"
        batchSize: {batch_size}
        temperature: {temperature}
        maxTokens: {max_tokens}
      roleContext: "{agent_name}"
      monitoring:
        latencyThreshold: {latency_target}
        accuracyMetric: "{agent_name}_accuracy"
        driftThreshold: 0.05
    env:
      - name: ENABLE_PAPER_TRADING
        value: "true"
      - name: ENABLED_AGENTS
        value: '["{agent_name}"]'
      - name: ENABLE_VERTEX_AI
        value: "true"
      - name: MCP_ENABLED
        value: "true"
      - name: AGENT_ROLE
        value: "{agent_name}"
      - name: VERTEX_MODEL
        value: "{selected_model}"
      - name: MODEL_TEMPERATURE
        value: "{temperature}"
      - name: MAX_OUTPUT_TOKENS
        value: "{max_tokens}"
      - name: QUANTIZATION_LEVEL
        value: "int8"
      - name: MONITORING_ENABLED
        value: "true" """

    updated_config = "# LLM Agent Services\nagents:\n  enabled: true\n"

    for agent_name, config in configurations.items():
        # Determine batch size based on model type
        batch_size = 16 if "bert" in config["selected_model"] or "mistral" in config["selected_model"] else 4

        agent_config = agent_template.format(
            agent_name=agent_name,
            role=config["role"],
            selected_model=config["selected_model"],
            batch_size=batch_size,
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
            latency_target=config["latency_target"]
        )

        updated_config += agent_config

    # Write to file
    with open('updated_agents_values.yaml', 'w') as f:
        f.write(updated_config)

    print("📄 Updated configuration saved to: updated_agents_values.yaml")
    return updated_config

def main():
    print("🚀 CHECKING VERTEX AI OPEN SOURCE MODELS FOR TRADING")
    print("=" * 60)

    # Check available models
    available_models = check_vertex_ai_models()

    # Check specific models in Model Garden
    garden_models = check_model_garden()

    # Combine available models
    all_available = list(set([model.get('name', model) for model in available_models] + garden_models))

    print(f"\n📊 TOTAL AVAILABLE MODELS: {len(all_available)}")
    print("Available models:", all_available[:10], "..." if len(all_available) > 10 else "")

    # Create trading configurations
    trading_configs = create_trading_model_configurations(all_available)

    # Generate updated YAML
    generate_updated_values_yaml(trading_configs)

    print("\n🎯 SUMMARY:")
    print(f"   ✅ Found {len(trading_configs)} suitable models for trading agents")
    print("   ✅ Generated optimized configurations for each role")
    print("   ✅ Updated values.yaml ready for deployment")
    print("\n🚀 Ready to deploy with open source Vertex AI models!")

if __name__ == "__main__":
    main()
