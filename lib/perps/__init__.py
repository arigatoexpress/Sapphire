"""Sapphire perps surface — multi-chain GMX V2 funding-rate + OI overview.

Read-only. Wave A scope: surface live funding APR and open-interest skew
across MegaETH (chain 4326) and Arbitrum (chain 42161) so the dashboard
panel + future strategy lanes can see cross-chain dislocation in one
place. Write paths land in Wave C and route through dedicated executor
plugins, NOT here.
"""

from __future__ import annotations
