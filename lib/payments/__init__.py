"""Payment rails for Sapphire APIs.

x402 (Coinbase) — HTTP 402 micropayment middleware for monetizing endpoints.
"""

from .x402_backtest_receipt import (
    artifact_id_for_backtest_receipt,
    build_backtest_receipt,
    reproducibility_hash,
)
from .x402_market_regime import (
    artifact_id_for_report,
    build_market_regime_report,
)
from .x402_middleware import (
    MockVerifier,
    PaymentRequirements,
    PaymentVerificationResult,
    PaymentVerifier,
    X402Middleware,
    build_402_response,
    require_payment,
)
from .x402_product_index import build_product_index
from .x402_products import (
    CatalogValidationError,
    ProductCatalog,
    ProductDefinition,
    ReceiptLedger,
    ReceiptRecord,
    SourceDefinition,
    SourceRegistry,
    load_product_catalog,
    load_source_registry,
    load_validated_catalogs,
    validate_catalog,
)

__all__ = [
    "PaymentRequirements",
    "PaymentVerificationResult",
    "PaymentVerifier",
    "MockVerifier",
    "X402Middleware",
    "build_402_response",
    "require_payment",
    "artifact_id_for_report",
    "build_market_regime_report",
    "artifact_id_for_backtest_receipt",
    "build_backtest_receipt",
    "reproducibility_hash",
    "CatalogValidationError",
    "ProductCatalog",
    "ProductDefinition",
    "ReceiptLedger",
    "ReceiptRecord",
    "SourceDefinition",
    "SourceRegistry",
    "load_product_catalog",
    "load_source_registry",
    "load_validated_catalogs",
    "validate_catalog",
    "build_product_index",
]
