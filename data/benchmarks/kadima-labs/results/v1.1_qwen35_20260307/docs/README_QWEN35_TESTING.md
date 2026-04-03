# Qwen 3.5 Comprehensive Testing Suite

## System Status

| Component | Current | Required | Status |
|-----------|---------|----------|--------|
| Ollama | 0.17.0 | 0.17.5+ | ⚠️ Update Needed |
| GPU | RTX 5070 Ti (16GB VRAM) | - | ✓ Ready |
| Python | 3.13 | 3.10+ | ✓ Ready |

## Update Instructions

### Method 1: System Tray (Easiest)
1. Right-click the Ollama icon in your system tray
2. Select **"Restart to update"**
3. Wait for restart

### Method 2: Download & Install
1. Download from: https://ollama.com/download
2. Run the installer
3. Follow prompts

### Method 3: PowerShell (Automated)
```powershell
# Run as Administrator
& "C:\Users\aribs\AI_Benchmark\update_ollama_and_test.ps1"
```

## After Update

1. **Verify Update:**
   ```bash
   ollama --version
   # Should show 0.17.5 or later
   ```

2. **Pull Qwen 3.5 Models:**
   ```bash
   ollama pull qwen3.5:9b    # ~10GB, good balance
   ollama pull qwen3.5:27b   # ~16GB, saturates VRAM
   ```

3. **Run Tests:**
   ```bash
   # Quick check
   python check_ollama_update.py
   
   # Comprehensive testing
   python comprehensive_qwen35_test.py
   
   # Or use the batch file
   run_qwen35_tests.bat
   ```

## Testing Framework Overview

### 1. `check_ollama_update.py`
Verifies Ollama version and Qwen 3.5 compatibility.

**Output:** Version status and update instructions

### 2. `comprehensive_qwen35_test.py`
Full testing suite with 5 categories:

| Category | Tests | Metrics |
|----------|-------|---------|
| **Speed** | Short/Medium/Long prompts | Tokens/sec across input sizes |
| **Quality** | Math, Code, Instructions, Creative | Pass/fail scoring |
| **MoE** | Expert routing (coding/math/reasoning) | Latency variance |
| **Long Context** | 32K token handling | Retrieval accuracy |
| **GPU Profile** | Real-time monitoring | VRAM peaks, utilization |

### 3. Generated Visualizations

| File | Description |
|------|-------------|
| `viz_speed_comparison.png` | Side-by-side speed rankings |
| `viz_quality_comparison.png` | Quality score comparison |
| `viz_moe_analysis.png` | Expert switching efficiency |
| `viz_memory_comparison.png` | VRAM usage patterns |
| `viz_comprehensive_dashboard.png` | All-in-one summary |
| `inference_*.png` | Real-time GPU usage timelines |

### 4. Results File
`comprehensive_test_YYYYMMDD_HHMMSS.json` - Raw data for further analysis

## Expected Results (RTX 5070 Ti)

### Qwen 3.5:9b (Dense)
- **Speed:** 45-60 t/s
- **VRAM:** 9-11 GB
- **Quality:** High
- **Best for:** Production use, consistent latency

### Qwen 3.5:27b (MoE)
- **Speed:** 25-35 t/s (varies by expert)
- **VRAM:** 14-16 GB
- **Quality:** Very High
- **Best for:** Complex reasoning, maximum capability

## Model Comparison Matrix

| Model | Size | Type | VRAM | Speed | Quality |
|-------|------|------|------|-------|---------|
| qwen2.5:14b | 14B | Dense | 12GB | 33 t/s | Good |
| qwen3:14b | 14B | Dense | 12GB | 28 t/s | Better |
| qwen3.5:9b | 9B | Dense | 10GB | 50 t/s | Better+ |
| qwen3.5:27b | 27B (MoE) | Sparse | 16GB | 30 t/s | Best |

## Files in This Directory

```
AI_Benchmark/
├── check_ollama_update.py      # Version checker
├── comprehensive_qwen35_test.py # Main testing suite
├── update_ollama_and_test.ps1  # Auto-update script
├── run_qwen35_tests.bat        # Easy launcher
├── qwen35_comparison.py        # 3-gen comparison
├── accurate_benchmark.py       # GPU-isolated benchmarks
├── quality_evaluator.py        # Quality testing
├── improved_visualizations.py  # Chart generation
└── README_QWEN35_TESTING.md    # This file
```

## Troubleshooting

### "Ollama not found"
- Add Ollama to your PATH: `C:\Users\%USERNAME%\AppData\Local\Programs\Ollama`

### "CUDA out of memory"
- Close other GPU applications
- Reduce concurrent models
- Use qwen3.5:9b instead of 27b

### "Timeout during test"
- Increase timeout in comprehensive_qwen35_test.py (line ~160)
- Check Ollama is responding: `ollama run qwen2.5:14b "Hello"`

### Unicode errors
- All scripts now use ASCII-only output
- Run with: `chcp 65001` before execution if needed

## Next Steps

1. Update Ollama to 0.17.5+
2. Pull qwen3.5:9b and qwen3.5:27b
3. Run `python comprehensive_qwen35_test.py`
4. Review visualizations
5. Compare with your existing qwen2.5:14b and qwen3:14b results

---

**Ready to begin?** Run the update, then execute:
```bash
python comprehensive_qwen35_test.py
```

Estimated time: 30-60 minutes for full suite
