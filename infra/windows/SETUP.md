# Windows PC (DESKTOP-HFCK6U9) — GPU Workbench Setup

Tailscale IP: `100.x.x.z` | GPU: RTX 5070 Ti | Hostname: `workbench`

## 1. Expose Ollama to Tailscale Network

By default Ollama only listens on localhost. To make it accessible from the Sapphire mesh:

### Option A: System Environment Variable (Recommended)
```powershell
# Run in PowerShell as Administrator
[System.Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0", "Machine")
# Restart Ollama (or reboot)
```

### Option B: Per-session
```powershell
$env:OLLAMA_HOST = "0.0.0.0"
ollama serve
```

## 2. Pull Nemotron Model

```powershell
ollama pull nvidia/nemotron-mini
ollama pull llama3.3:70b  # If not already present
```

## 3. Windows Firewall — Allow Tailscale

```powershell
# Run as Administrator
New-NetFirewallRule -DisplayName "Ollama Tailscale" -Direction Inbound -Protocol TCP -LocalPort 11434 -RemoteAddress 100.64.0.0/10 -Action Allow
```

This restricts access to Tailscale IPs only (100.64.0.0/10 CGNAT range).

## 4. Verify from Mac

```bash
curl http://100.x.x.z:11434/api/tags
# Should return JSON with model list
```

## 5. Install claw-code (Optional)

```powershell
# Install Rust if needed
winget install Rustlang.Rustup

# Clone and build
cd C:\Users\aribs\Code
git clone https://github.com/instructkr/claw-code.git
cd claw-code\rust
cargo build --release

# Copy config
mkdir C:\Users\aribs\.claw\profiles
# Copy windows-workbench.json from Mac via Tailscale:
# scp mac:~/.claw/profiles/windows-workbench.json C:\Users\aribs\.claw\profiles\
```

## 6. Test Inference from Mac

```bash
# Quick test
curl -X POST http://100.x.x.z:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2:3b", "prompt": "Hello from Sapphire OS", "stream": false}'

# Via Sapphire plugin
python3 ~/Code/Sapphire/plugins/claw-sapphire/src/tools/inference.py "What GPU are you running on?"
```

## Status

- [x] Tailscale connected (7ms ping)
- [ ] Ollama exposed on 0.0.0.0:11434
- [ ] Nemotron model pulled
- [ ] Firewall rule added
- [ ] claw-code built
- [ ] Verified from Mac
