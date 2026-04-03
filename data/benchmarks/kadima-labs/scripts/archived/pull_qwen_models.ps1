# PowerShell script to pull latest Qwen models for RTX 5070 Ti
# Models suitable for 16GB VRAM: 14B, 8B parameters (32B may work with offloading)

$models = @(
    # Qwen3 - Latest generation (released 2025)
    "qwen3:14b",
    "qwen3:8b",
    "qwen3:4b",
    
    # Qwen2.5 Coder - Specialized for code
    "qwen2.5-coder:14b",
    "qwen2.5-coder:32b",
    
    # QwQ - Reasoning model
    "qwq",
    
    # Qwen3 Embedding models (for RAG tasks)
    "qwen3-embedding:4b",
    "qwen3-embedding:8b"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Pulling Latest Qwen Models" -ForegroundColor Cyan
Write-Host "Target Hardware: RTX 5070 Ti (16GB VRAM)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$successful = @()
$failed = @()

foreach ($model in $models) {
    Write-Host "`n[$($successful.Count + $failed.Count + 1)/$($models.Count)] Pulling $model..." -ForegroundColor Yellow
    
    $startTime = Get-Date
    try {
        $process = Start-Process -FilePath "ollama" -ArgumentList "pull", $model -Wait -PassThru -NoNewWindow
        $duration = (Get-Date) - $startTime
        
        if ($process.ExitCode -eq 0) {
            Write-Host "  ✓ Successfully pulled $model in $($duration.ToString('hh\:mm\:ss'))" -ForegroundColor Green
            $successful += $model
        } else {
            Write-Host "  ✗ Failed to pull $model (Exit code: $($process.ExitCode))" -ForegroundColor Red
            $failed += $model
        }
    } catch {
        Write-Host "  ✗ Error pulling $model : $_" -ForegroundColor Red
        $failed += $model
    }
    
    # Brief pause between pulls
    Start-Sleep -Seconds 2
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Pull Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Successful ($($successful.Count)): $($successful -join ', ')" -ForegroundColor Green
if ($failed.Count -gt 0) {
    Write-Host "Failed ($($failed.Count)): $($failed -join ', ')" -ForegroundColor Red
}

# List all installed models
Write-Host "`nCurrently installed models:" -ForegroundColor Cyan
ollama list
