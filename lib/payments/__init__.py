"""Payment rails for Sapphire APIs.

x402 (Coinbase) — HTTP 402 micropayment middleware for monetizing endpoints.
"""

from .x402_middleware import (
    MockVerifier,
    PaymentRequirements,
    PaymentVerificationResult,
    PaymentVerifier,
    X402Middleware,
    build_402_response,
    require_payment,
)
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
]
