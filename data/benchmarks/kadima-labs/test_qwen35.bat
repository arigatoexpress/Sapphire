@echo off
echo ==========================================
echo Qwen 3.5 Installation & Test Script
echo ==========================================
echo.

echo Step 1: Checking Ollama version...
ollama --version
echo.

echo Step 2: Pulling Qwen 3.5 (9B for RTX 5070 Ti)...
echo This will take several minutes...
ollama pull qwen3.5:9b
echo.

echo Step 3: Testing Qwen 3.5...
ollama run qwen3.5:9b "What is 2+2? Explain your reasoning."
echo.

echo Step 4: Listing installed models...
ollama list | findstr qwen
echo.

echo ==========================================
echo Qwen 3.5 is ready to use!
echo Run: ollama run qwen3.5:9b
echo ==========================================
pause
