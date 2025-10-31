from __future__ import annotations

import argparse
import pathlib
from typing import Iterable, List

import pandas as pd

try:
    from sentence_transformers import SentenceTransformer
except ImportError as exc:  # pragma: no cover - optional dependency
    raise SystemExit(
        "sentence-transformers is required. Install via `pip install sentence-transformers`."
    ) from exc


def load_raw_events() -> pd.DataFrame:
    # Placeholder: replace with actual data fetch (news API, funding, on-chain metrics)
    return pd.DataFrame(
        {
            "symbol": ["BTCUSDT", "ETHUSDT"],
            "event_time": pd.to_datetime(["2025-01-01T00:00:00Z", "2025-01-01T00:05:00Z"]),
            "headline": [
                "BTC funding remains negative as shorts pile in",
                "ETH staking inflows spike ahead of upgrade",
            ],
        }
    )


def embed_texts(model: SentenceTransformer, texts: Iterable[str]) -> List[List[float]]:
    return model.encode(list(texts), normalize_embeddings=True).tolist()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sentiment embeddings for market events")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Hugging Face model ID",
    )
    args = parser.parse_args()

    df = load_raw_events()
    model = SentenceTransformer(args.model)
    df["sentiment_embedding"] = embed_texts(model, df["headline"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.output, index=False)
    print(f"Wrote {len(df)} rows to {args.output}")


if __name__ == "__main__":
    main()

