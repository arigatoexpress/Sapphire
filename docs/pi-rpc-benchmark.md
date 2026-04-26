# Pi Cluster RPC Benchmark — llama.cpp Distributed Inference

**Date:** 2026-04-14  
**Hardware:** RTX 5070 Ti 16 GB VRAM (Windows) + rari1 + rari2 (Raspberry Pi 4, 4 GB RAM each)

---

## Deployment Status

| Node | Tailscale IP | RPC Port | Status |
|------|-------------|----------|--------|
| rari1 | 100.120.191.1 | 50052 | **ACTIVE** — systemd service, enabled, auto-start |
| rari2 | 100.87.225.89 | 50052 | **ACTIVE** — systemd service, enabled, auto-start |

Both Pi nodes running `rpc-server --host 0.0.0.0 --port 50052` as user `rari`.  
Binary: `/home/rari/llama.cpp/build/bin/rpc-server` (180 KB ARM64, ggml RPC backend)  
Build: llama.cpp `--depth 1` clone, `cmake -DGGML_RPC=ON`, April 2026.

---

## Benchmark Results

**Model:** qwen2.5:32b (19.9 GB) — currently the primary RAM-spill target  
**Setup:** 16 GB VRAM, ~5 GB overflows to system RAM or RPC backends

| Configuration | Load time | Generation speed | Status |
|--------------|-----------|-----------------|--------|
| GPU only (no RPC) | 18.2s | **2.4 tok/s** | ✅ baseline |
| GPU + rari1 RPC (Tailscale) | 600s+ | — | ❌ load timeout |
| GPU + rari1 + rari2 RPC (Tailscale) | — | — | skipped |

---

## Analysis

### What worked
- RPC TCP connections established successfully (rari1 logs show `Accepted client connection`)
- Tensor data began transferring from Windows → rari1 (`bytes_recv=25,297,240` before cut-off)
- Protocol handshake confirmed: llama-server b8795 with `ggml-rpc.dll` can communicate with ARM64 rpc-server
- Both RPC ports reachable from Mac via Tailscale

### Why the load timed out
llama.cpp RPC model loading transfers the full tensor weight for RPC-allocated layers from the GPU host to the remote nodes. For qwen2.5:32b at ~5 GB overflow:

- Tailscale throughput over WiFi: ~10–30 MB/s (encrypted UDP, WiFi hops)
- Transfer time for 5 GB at 10 MB/s: **~500 seconds** → exceeds any reasonable load timeout
- Compare: pure local GPU load (no RPC): **18 seconds**

This is a fundamental WiFi bottleneck, not an RPC protocol issue.

### The direct ethernet link (10.0.0.1 ↔ 10.0.0.2)
The Pis have a direct Ethernet connection to each other (0.26 ms RTT). However:
- The Windows GPU connects via **Tailscale/WiFi**, not the direct Ethernet link
- Direct Ethernet only helps for **Pi-to-Pi** communication (e.g., if one Pi runs llama-server and offloads to the other)
- For **GPU→Pi** offloading, all traffic still traverses WiFi regardless of direct Ethernet

### Comparison: RPC vs current RAM-spill
| Method | Speed |
|--------|-------|
| RAM spill (CPU DRAM) | 2.4–2.7 tok/s |
| Pi RPC over Tailscale | ~0.1 tok/s estimated (5 GB / 500s load, re-transferred each inference) |

**Conclusion: Pi RPC over WiFi is slower than local RAM spill for 32B models.**

---

## When Pi RPC Would Help

Pi RPC would provide real benefit in these scenarios:

### 1. Direct wired GPU→Pi connection
If the Windows GPU were connected to the Pi cluster via wired Ethernet (not WiFi):
- 1 Gbps: 5 GB loads in **5 seconds**, Pi becomes viable backend
- Current network topology doesn't support this without a switch/USB-Ethernet adapter

### 2. Smaller models with balanced layer split  
A 27B model like `qwen3.6:27b` (17.4 GB) fits with slight spill in 16 GB VRAM; the 2026-04-26 Windows benchmark measured about 7 tok/s, so it stays an explicit alias rather than the default `deep` route. Pi RPC adds only latency.
Only models that genuinely spill benefit from RPC, and only when the network is fast.

### 3. Pi-to-Pi coordination  
The direct Ethernet link (10.0.0.1 ↔ 10.0.0.2) is useful for running llama-server on **one Pi** 
and offloading layers to the **other Pi** via the fast local link. This enables ~8B models on Pi cluster.

---

## Recommended Next Steps

| Priority | Action |
|---------|--------|
| Low | Add USB 3.0→Ethernet adapter to Windows GPU machine for direct Pi Ethernet |
| Medium | Benchmark Pi-to-Pi RPC: llama-server on rari1, layers offload to rari2 via 10.0.0.1:50052 |
| Done | Keep RPC servers running — low overhead, will be useful when hardware changes |

---

## Commands

```bash
# Check status
ssh rari@100.120.191.1 'systemctl status llama-rpc'
ssh rari@100.87.225.89 'systemctl status llama-rpc'

# Test connectivity  
nc -zv 100.120.191.1 50052 && echo "rari1 OK"
nc -zv 100.87.225.89 50052 && echo "rari2 OK"

# Pi-to-Pi RPC test (from rari1)
ssh rari@100.120.191.1 'nc -zv 10.0.0.2 50052 && echo "rari2 direct OK"'
```
