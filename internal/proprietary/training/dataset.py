"""Dataset utilities for model fine-tuning."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .configs import MarketDatasetConfig

try:  # pragma: no cover - optional dependency for offline environments
    from datasets import Dataset, load_dataset
except ImportError:  # pragma: no cover
    Dataset = None  # type: ignore
    load_dataset = None  # type: ignore


def _ensure_datasets_available() -> None:
    if Dataset is None or load_dataset is None:  # pragma: no cover
        raise ImportError(
            "The 'datasets' library is required for training pipelines. "
            "Install it via `pip install datasets` inside the training image."
        )


def load_market_dataset(config: MarketDatasetConfig) -> "Dataset":
    """Load a fine-tuning dataset from JSON/Parquet files or BigQuery."""

    _ensure_datasets_available()

    dataset: Optional[Dataset] = None

    if config.data_path:
        data_files = config.data_path
        dataset = load_dataset("json", data_files=data_files)["train"]
    elif config.bigquery_table:
        dataset = _load_from_bigquery(config)
    else:
        raise ValueError("Either data_path or bigquery_table must be provided for training data")

    if config.symbols:
        dataset = dataset.filter(lambda example: example.get("symbol") in set(config.symbols))

    if config.max_rows is not None:
        dataset = dataset.select(range(min(config.max_rows, len(dataset))))

    return dataset


def _load_from_bigquery(config: MarketDatasetConfig) -> "Dataset":
    from google.cloud import bigquery  # Lazy import to avoid hard dependency at import time

    client = bigquery.Client()
    table = config.bigquery_table
    query_params = []
    where_clause = ""
    
    if config.symbols:
        where_clause = "WHERE symbol IN UNNEST(@symbols)"
        query_params.append(bigquery.ArrayQueryParameter("symbols", "STRING", config.symbols))

    limit_clause = ""
    if config.max_rows:
        limit_clause = "LIMIT @limit"
        query_params.append(bigquery.ScalarQueryParameter("limit", "INT64", int(config.max_rows)))

    query = f"""
        SELECT
          symbol,
          timestamp,
          thesis,
          reasoning,
          label
        FROM `{table}`
        {where_clause}
        {limit_clause}
    """

    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    frame: pd.DataFrame = client.query(query, job_config=job_config).to_dataframe(create_bqstorage_client=True)
    if frame.empty:
        raise ValueError(f"No rows returned from BigQuery source {table}")
    dataset = Dataset.from_pandas(frame, preserve_index=False)
    return dataset
