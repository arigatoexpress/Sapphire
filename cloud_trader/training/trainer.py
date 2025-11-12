"""Model fine-tuning entrypoints for Vertex AI custom jobs."""
from __future__ import annotations

from typing import Any, Dict

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)

from .configs import TrainingProfile


def _combine_fields(example: Dict[str, Any]) -> str:
    thesis = example.get("thesis") or example.get("analysis") or ""
    reasoning = example.get("reasoning") or example.get("rationale") or ""
    label = example.get("label") or example.get("decision") or "NEUTRAL"
    symbol = example.get("symbol") or "UNKNOWN"
    return (
        f"Instrument: {symbol}\n"
        f"Decision: {label}\n"
        f"Thesis: {thesis}\n"
        f"Reasoning: {reasoning}"
    ).strip()


def train_language_model(dataset, profile: TrainingProfile, *, run_name: str) -> None:
    """Fine-tune an instruction-style language model on trading theses."""

    tokenizer = AutoTokenizer.from_pretrained(profile.base_model, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def tokenize_function(example: Dict[str, Any]) -> Dict[str, Any]:
        text = _combine_fields(example)
        return tokenizer(
            text,
            max_length=profile.max_seq_length,
            truncation=True,
            padding="max_length",
        )

    tokenized_dataset = dataset.map(tokenize_function, batched=False, remove_columns=dataset.column_names)

    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    training_args = TrainingArguments(
        output_dir=profile.output_dir,
        run_name=run_name,
        learning_rate=profile.learning_rate,
        num_train_epochs=profile.num_train_epochs,
        per_device_train_batch_size=profile.per_device_batch_size,
        gradient_accumulation_steps=profile.gradient_accumulation_steps,
        warmup_steps=profile.warmup_steps,
        weight_decay=profile.weight_decay,
        logging_steps=profile.logging_steps,
        save_total_limit=profile.save_total_limit,
        lr_scheduler_type=profile.lr_scheduler_type,
        bf16=profile.bf16,
        seed=profile.seed,
        report_to=["tensorboard"],
    )

    model = AutoModelForCausalLM.from_pretrained(profile.base_model)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
    )

    trainer.train()
    trainer.save_model(profile.output_dir)
    tokenizer.save_pretrained(profile.output_dir)
