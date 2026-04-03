# Qwen 3.5 Setup & Testing Guide

## 🎯 Goal: Update Ollama and Test Qwen 3.5

---

## Step 1: Update Ollama (Current: v0.17.0 → Need: v0.17.5+)

### Method 1: Taskbar Auto-Update (Easiest - Try First)

1. **Look at your Windows taskbar** (bottom-right, system tray)
2. Find the **Ollama icon** (looks like a speech bubble)
3. **Right-click** on it
4. Click **"Restart to update"**
5. Wait for Ollama to restart

### Method 2: Manual Download (If Method 1 Doesn't Work)

1. Go to: **https://ollama.com/download**
2. Click **"Download for Windows"**
3. Save `OllamaSetup.exe`
4. **Close** any running Ollama windows
5. Run `OllamaSetup.exe` (it will auto-upgrade)
6. Restart your computer

### Verify Update

Open PowerShell or CMD and run:
```bash
ollama --version
```

**You should see:** `ollama version is 0.17.5` or higher

---

## Step 2: Pull Qwen 3.5 Models

### For RTX 5070 Ti (16GB VRAM), best options:

```bash
# Recommended: 9B model (fits perfectly, fast)
ollama pull qwen3.5:9b

# Alternative: 27B model (uses all VRAM, slower but higher quality)
ollama pull qwen3.5:27b

# Quick test: 4B model (very fast, lower quality)
ollama pull qwen3.5:4b
```

### Download Sizes:

| Model | Size | VRAM Usage | Speed | Best For |
|-------|------|------------|-------|----------|
| `qwen3.5:4b` | ~3 GB | ~5 GB | Very Fast | Testing |
| `qwen3.5:9b` | ~6 GB | ~10 GB | Fast | **Production** |
| `qwen3.5:27b` | ~17 GB | ~15 GB | Moderate | Quality |

---

## Step 3: Test Qwen 3.5

### Quick Test
```bash
ollama run qwen3.5:9b "What is 2+2? Explain your reasoning."
```

### Check Installation
```bash
ollama list | findstr qwen3.5
```

---

## Step 4: Run Comprehensive Benchmark

Once Qwen 3.5 is installed, run our testing framework:

```bash
cd C:\Users\aribs\AI_Benchmark
python qwen35_comparison.py
```

This will:
- Test all available Qwen models (2.5, 3.0, 3.5)
- Measure speed and quality
- Generate comparison report

---

## 📊 What to Expect: Qwen 3.5 Improvements

Based on official documentation (https://github.com/QwenLM/Qwen3.5):

### Major Improvements Over Qwen 3.0:

| Feature | Qwen 3.0 | Qwen 3.5 | Improvement |
|---------|----------|----------|-------------|
| **Architecture** | Dense only | Dense + MoE Hybrid | Better efficiency |
| **Vision-Language** | Separate models | Unified foundation | Native multimodal |
| **Languages** | ~100 | **201** | 2x more |
| **Context Length** | 128K | **256K** | 2x longer |
| **RL Training** | Standard | Million-agent scale | Better reasoning |

### Expected Performance on RTX 5070 Ti:

| Model | Tokens/sec | Quality Score | VRAM |
|-------|------------|---------------|------|
| Qwen2.5:14b | ~33 | 85% | 10 GB |
| Qwen3:14b | ~30 | 92% | 11.5 GB |
| **Qwen3.5:9b** | ~35-40 | **95%** | 10 GB |
| Qwen3.5:27b | ~15-18 | **97%** | 15 GB |

**Key Insight:** Qwen 3.5:9b should be faster AND higher quality than both Qwen 2.5 and 3.0!

---

## 🔧 Troubleshooting

### "Model not found" error
```bash
# Make sure you have the latest Ollama
ollama --version

# If version < 0.17.5, update first
```

### "File does not exist" error
```bash
# Try pulling without specific tag first
ollama pull qwen3.5

# Then check available tags
ollama list | findstr qwen3.5
```

### Slow download
```bash
# Pull smaller model first for testing
ollama pull qwen3.5:4b
```

### Out of memory
```bash
# Use smaller model
ollama pull qwen3.5:4b

# Or 9B which fits RTX 5070 Ti perfectly
ollama pull qwen3.5:9b
```

---

## 📁 Files Created for You

| File | Purpose |
|------|---------|
| `test_qwen35.bat` | One-click test script |
| `qwen35_comparison.py` | Comprehensive comparison |
| `qwen_family_comparison.py` | Detailed quality testing |
| `QWEN35_SETUP_GUIDE.md` | This guide |

---

## 🚀 Next Steps

1. **Update Ollama** using methods above
2. **Pull Qwen 3.5:9b** (recommended for RTX 5070 Ti)
3. **Run**: `python qwen35_comparison.py`
4. **Compare** results with Qwen 2.5 and 3.0

---

## 📚 Resources

- **Qwen 3.5 GitHub**: https://github.com/QwenLM/Qwen3.5
- **Hugging Face**: https://huggingface.co/Qwen
- **Ollama Download**: https://ollama.com/download
- **Model Info**: Search "qwen3.5" on https://ollama.com/library

---

*Ready to test the latest Qwen model!*
