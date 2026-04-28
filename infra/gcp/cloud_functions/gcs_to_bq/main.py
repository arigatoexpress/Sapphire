"""Cloud Function: GCS-finalize trigger → BigQuery load.

Fires on every new object under gs://sapphire-data-lake/raw/<source>/...
Determines the target BQ table from the path prefix and issues a load job.

Path convention (matches services.pipeline.gcp_sync):
    raw/signals/YYYY-MM-DD/*.ndjson      → sapphire.trading_signals
    raw/predictions/YYYY-MM-DD/*.ndjson  → sapphire.predictions
    raw/threats/YYYY-MM-DD/*.ndjson      → sapphire.threat_intel
    raw/regime/YYYY-MM-DD/*.ndjson       → sapphire.market_regime
    raw/leads/YYYY-MM-DD/*.ndjson        → sapphire.leads
    raw/metrics/YYYY-MM-DD/*.ndjson      → sapphire.inference_metrics
    raw/health/YYYY-MM-DD/*.ndjson       → sapphire.service_health

Non-matching paths and non-NDJSON files are skipped.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import functions_framework
from google.cloud import bigquery

PROJECT = os.environ.get("GCP_PROJECT", "tho-ai-agent")
DATASET = os.environ.get("BQ_DATASET", "sapphire")

SOURCE_TO_TABLE: dict[str, str] = {
    "signals": "trading_signals",
    "predictions": "predictions",
    "threats": "threat_intel",
    "regime": "market_regime",
    "leads": "leads",
    "metrics": "inference_metrics",
    "health": "service_health",
}

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _resolve_table(object_path: str) -> str | None:
    """raw/<source>/... → table name, or None."""
    parts = object_path.split("/")
    if len(parts) < 2 or parts[0] != "raw":
        return None
    return SOURCE_TO_TABLE.get(parts[1])


@functions_framework.cloud_event
def parse_and_load(cloud_event: Any) -> None:
    data = cloud_event.data or {}
    bucket = data.get("bucket")
    name = data.get("name", "")
    size = int(data.get("size", 0))

    log.info("finalize: gs://%s/%s (%d bytes)", bucket, name, size)

    if not name.endswith(".ndjson"):
        log.info("skip (not .ndjson): %s", name)
        return

    if name.endswith("/.keep"):
        return

    table = _resolve_table(name)
    if not table:
        log.warning("no table mapping for %s", name)
        return

    gcs_uri = f"gs://{bucket}/{name}"
    client = bigquery.Client(project=PROJECT)
    table_ref = client.dataset(DATASET).table(table)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ignore_unknown_values=True,
    )
    job = client.load_table_from_uri(gcs_uri, table_ref, job_config=job_config)
    job.result()

    if job.errors:
        log.error("BQ load errors on %s: %s", gcs_uri, job.errors)
        raise RuntimeError(f"BQ load errors: {job.errors}")

    log.info("loaded %d rows: %s -> %s.%s", job.output_rows or 0, gcs_uri, DATASET, table)
