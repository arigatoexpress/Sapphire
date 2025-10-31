# Multi-Model LLM Trading System

Advanced autonomous trading system with 4 specialized open-source LLMs, intelligent model routing, and automated deployment.

## 🤖 Available Models

### 1. **DeepSeek-Coder-V2** (16B parameters)
- **Specialization**: Mathematical reasoning and balanced analysis
- **Strengths**: Complex pattern recognition, technical analysis, risk assessment
- **Use Case**: General-purpose trading decisions requiring deep analysis
- **Model**: `deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct`
- **Endpoint**: `https://deepseek-trader-880429861698.us-central1.run.app`

### 2. **Qwen2.5-Coder** (7B parameters)
- **Specialization**: Algorithmic and coding-focused analysis
- **Strengths**: Quantitative strategies, momentum analysis, algorithmic trading
- **Use Case**: High-frequency patterns, technical indicators, algorithmic execution
- **Model**: `Qwen/Qwen2.5-Coder-7B-Instruct`
- **Endpoint**: `https://qwen-trader-880429861698.us-central1.run.app`

### 3. **FinGPT** (7B parameters, LLaMA-based)
- **Specialization**: Financial market expertise
- **Strengths**: Market sentiment, fundamental analysis, institutional-grade insights
- **Use Case**: Complex market analysis, sentiment-driven decisions, fundamental factors
- **Model**: `FinGPT/fingpt-mt_llama2-7b_lora`
- **Endpoint**: `https://fingpt-trader-880429861698.us-central1.run.app`

### 4. **Phi-3** (3.8B parameters)
- **Specialization**: Efficient, fast decision making
- **Strengths**: Quick analysis, edge deployment, low-latency responses
- **Use Case**: Rapid market reactions, simple strategies, high-frequency signals
- **Model**: `microsoft/Phi-3-mini-128k-instruct`
- **Endpoint**: `https://phi3-trader-880429861698.us-central1.run.app`

## 🎯 Intelligent Model Router

### **Smart Model Selection**
The system automatically selects the most appropriate model based on:

```python
# Decision Logic
if has_position and high_volume:
    return FinGPT  # Financial expertise
elif volatility_high:
    return Qwen    # Algorithmic analysis
elif sentiment_clear:
    return Phi3    # Fast execution
else:
    return DeepSeek # Balanced default
```

### **Manual Model Selection**
Override automatic selection with `model_preference`:

```json
{
  "context": {...},
  "bot_id": "momentum_bot",
  "symbol": "BTCUSDT",
  "model_preference": "qwen"
}
```

### **Router Features**
- **Automatic Fallback**: If preferred model fails, uses DeepSeek
- **Health Monitoring**: Tracks model availability and performance
- **Load Balancing**: Distributes requests across healthy models
- **Performance Tracking**: Logs which models perform best

## 🚀 Quick Deployment

### **Deploy All Models**
```bash
cd infra/llm_serving
./deploy-models.sh
```

### **Individual Model Deployment**
```bash
# DeepSeek (already deployed)
gcloud builds submit . --config infra/llm_serving/cloudbuild.yaml

# Qwen
gcloud builds submit . --config infra/llm_serving/cloudbuild-qwen.yaml

# FinGPT
gcloud builds submit . --config infra/llm_serving/cloudbuild-fingpt.yaml

# Phi-3
gcloud builds submit . --config infra/llm_serving/cloudbuild-phi3.yaml

# Router
gcloud builds submit . --config infra/llm_serving/cloudbuild-router.yaml
```

## 📊 Model Comparison

| Model | Parameters | Context | Speed | Specialization | Cost/Month |
|-------|------------|---------|-------|----------------|------------|
| DeepSeek | 16B | 4K | Medium | Balanced Analysis | ~$150 |
| Qwen | 7B | 8K | Fast | Algorithmic | ~$100 |
| FinGPT | 7B | 2K | Medium | Financial | ~$100 |
| Phi-3 | 3.8B | 4K | Fastest | Efficient | ~$80 |

## 🔧 Integration

### **Cloud Trader Configuration**
```bash
# Update LLM endpoint to use router
export LLM_ENDPOINT="https://model-router-880429861698.us-central1.run.app"

# Enable LLM trading
export ENABLE_LLM_TRADING=true
export MIN_LLM_CONFIDENCE=0.7
```

### **API Usage**
```python
import requests

# Use router (automatic model selection)
response = requests.post("https://model-router-880429861698.us-central1.run.app/decide", json={
    "context": {"price": 45000, "volume": 1000000},
    "bot_id": "momentum_bot",
    "symbol": "BTCUSDT",
    "risk_limits": {"max_position_pct": 0.02}
})

# Force specific model
response = requests.post("https://model-router-880429861698.us-central1.run.app/decide", json={
    "context": {...},
    "bot_id": "momentum_bot",
    "symbol": "BTCUSDT",
    "model_preference": "qwen"  # Force Qwen model
})
```

## 📈 Performance Optimization

### **Model Selection Strategy**
- **High Volatility**: Qwen (algorithmic analysis)
- **Large Positions**: FinGPT (financial expertise)
- **Quick Decisions**: Phi-3 (efficient processing)
- **Complex Analysis**: DeepSeek (mathematical reasoning)

### **Concurrent Processing**
- **DeepSeek**: 16 concurrent requests
- **Qwen**: 8 concurrent requests
- **FinGPT**: 12 concurrent requests
- **Phi-3**: 16 concurrent requests

### **Cost Optimization**
- **Phi-3**: Most cost-effective for high-frequency trading
- **Qwen**: Best performance/cost ratio
- **FinGPT**: Premium for complex financial analysis
- **DeepSeek**: Highest capability but more expensive

## 🔍 Monitoring & Analytics

### **Model Performance Tracking**
```bash
# Check model health
curl https://model-router-880429861698.us-central1.run.app/status

# View decision distribution
curl https://cloud-trader-880429861698.us-central1.run.app/metrics | grep trading_llm
```

### **Grafana Dashboards**
- Model selection distribution
- Confidence scores by model
- Response times and latency
- Decision accuracy tracking

## 🛠️ Development & Testing

### **Local Testing**
```bash
# Test individual models
curl -X POST http://localhost:8080/decide \
  -H "Content-Type: application/json" \
  -d '{"context": {"price": 45000}, "bot_id": "test", "symbol": "BTCUSDT"}'
```

### **Model Comparison Testing**
```python
from infra.llm_serving.model_router import ModelRouter

router = ModelRouter()
# Test all models with same input
results = {}
for model in ["deepseek", "qwen", "fingpt", "phi3"]:
    result = router.route_to_model(request, model)
    results[model] = result
```

## 🚨 Troubleshooting

### **Model Not Responding**
```bash
# Check model health
curl https://[model]-trader-880429861698.us-central1.run.app/health

# Check router status
curl https://model-router-880429861698.us-central1.run.app/status
```

### **High Latency**
- Phi-3: Best for speed-critical applications
- Check Redis connectivity
- Monitor Cloud Run instance scaling

### **Low Confidence Scores**
- Adjust `MIN_LLM_CONFIDENCE` threshold
- Review model selection logic
- Check input data quality

## 📚 Advanced Configuration

### **Custom Model Selection**
```python
# Override router logic
class CustomRouter(ModelRouter):
    def select_model(self, request):
        # Your custom logic here
        if request.context.get('volatility') > 0.8:
            return ModelType.QWEN
        return ModelType.DEEPSEEK
```

### **Model Fine-tuning**
- Monitor performance metrics
- Adjust confidence thresholds per model
- Implement A/B testing between models

## 🎯 Next Steps

1. **Deploy Models**: Run `./deploy-models.sh`
2. **Configure Trading**: Update cloud trader LLM settings
3. **Monitor Performance**: Set up Grafana dashboards
4. **Optimize Selection**: Fine-tune model routing logic
5. **Scale**: Add more instances based on load

---

**The multi-model system provides institutional-grade AI trading capabilities with automatic model selection, ensuring optimal performance for every market condition.** 🚀🤖📈
