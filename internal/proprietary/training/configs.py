"""Configuration helpers for Vertex AI training pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MarketDatasetConfig:
    """Describe how to source the fine-tuning dataset."""

    data_path: Optional[str] = None
    bigquery_table: Optional[str] = None
    symbols: List[str] = field(default_factory=list)
    max_rows: Optional[int] = None


@dataclass
class TrainingProfile:
    """Hyperparameters shared across agent fine-tuning jobs."""

    base_model: str
    output_dir: str = "/gcs/artifacts/output"
    learning_rate: float = 2e-5
    num_train_epochs: float = 1.0
    per_device_batch_size: int = 2
    gradient_accumulation_steps: int = 8
    max_seq_length: int = 2048
    warmup_steps: int = 100
    weight_decay: float = 0.01
    bf16: bool = True
    lr_scheduler_type: str = "cosine"
    logging_steps: int = 50
    save_total_limit: int = 2
    seed: int = 42

    def to_dict(self) -> dict:
        return {
            "base_model": self.base_model,
            "output_dir": self.output_dir,
            "learning_rate": self.learning_rate,
            "num_train_epochs": self.num_train_epochs,
            "per_device_train_batch_size": self.per_device_batch_size,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "max_seq_length": self.max_seq_length,
            "warmup_steps": self.warmup_steps,
            "weight_decay": self.weight_decay,
            "bf16": self.bf16,
            "lr_scheduler_type": self.lr_scheduler_type,
            "logging_steps": self.logging_steps,
            "save_total_limit": self.save_total_limit,
            "seed": self.seed,
        }
