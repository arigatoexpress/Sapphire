"""Per-chain access layers for Sapphire (read-only by default).

Each chain has its own subpackage that exposes:
  * a typed RPC client (transport layer)
  * a registry of known protocols (addresses + ABI paths)
  * typed contract wrappers (`contracts/`)
  * an intent-level facade (`protocols.py`)

Wave A populates `lib.chains.megaeth` only.
"""
