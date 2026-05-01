"""Typed read-only contract wrappers over MegaETH deployments.

Wave A: ``aave_v3`` only.
Wave B step 1: ``kumbaya`` (UniswapV3-fork DEX-spot).

All wrappers compose with the ``MegaETHClient`` from
``plugins.claw_sapphire.tools.internal.megaeth`` (PR #529) — they never
build a transport of their own.

These wrappers are **read-only**. They do not accept private keys,
do not call any state-changing RPC method, and do not import
``eth_account``. Write paths land in Wave C and live in the
gated ``megaeth_executor`` plugin tool.
"""
