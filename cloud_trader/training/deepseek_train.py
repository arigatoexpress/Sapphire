"""Vertex AI custom job entrypoint for DeepSeek Momentum fine-tuning."""
from __future__ import annotations

import argparse
from typing import List

from .configs import MarketDatasetConfig, TrainingProfile
from .dataset import load_market_dataset
from .trainer import train_language_model


def parse_symbols(raw: str) -> List[str]:
    return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()] if raw else []


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune DeepSeek Momentum agent")
    parser.add_argument("--data-path", help="GCS path or local file with JSONL training data")
    parser.add_argument("--bigquery-table", help="Fully-qualified BigQuery table (project.dataset.table)", default=None)
    parser.add_argument("--symbols", help="Comma separated list of symbols to filter", default="")
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--output-dir", default="/gcs/artifacts/deepseek")
    parser.add_argument("--base-model", default="deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct")
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    args = parser.parse_args()

    dataset_config = MarketDatasetConfig(
        data_path=args.data_path,
        bigquery_table=args.bigquery_table,
        symbols=parse_symbols(args.symbols),
        max_rows=args.max_rows,
    )

    profile = TrainingProfile(
        base_model=args.base_model,
        output_dir=args.output_dir,
        learning_rate=args.learning_rate,
        num_train_epochs=args.epochs,
        per_device_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        max_seq_length=args.max_seq_length,
    )

    dataset = load_market_dataset(dataset_config)
    train_language_model(dataset, profile, run_name="deepseek-momentum")


if __name__ == "__main__":
    main()
