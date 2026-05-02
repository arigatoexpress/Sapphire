"""Typed read-only contract wrappers over Arbitrum One deployments.

Wave 1: ``aave_v3`` only. Future protocols (GMX V2, Camelot V3, etc.)
extend this same package.

All wrappers compose with the chain's ``ArbitrumClient`` (or any object
satisfying the ``_call(method, params)`` Protocol) — they never build
a transport of their own.

These wrappers are **read-only**. They do not accept private keys,
do not call any state-changing RPC method, and do not import
``eth_account``.
"""
