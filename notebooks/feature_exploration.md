# Feature Exploration Notebook Outline

Use this skeleton to explore Feast features and embedding outputs.

## 1. Imports & Store

```python
from cloud_trader.data.feature_pipeline import build_feature_repo

store = build_feature_repo("feature_repo")
if store is None:
    raise RuntimeError("Install feast via `pip install feast`.")
```

## 2. Fetch Latest Features

```python
import pandas as pd

entities = [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]
features = [
    "onchain_metrics:price",
    "onchain_metrics:funding",
    "onchain_metrics:volatility",
]
frame = store.get_online_features(features=features, entity_rows=entities).to_df()
frame
```

## 3. Embedding Similarity

```python
from cloud_trader.data.feature_pipeline import embed_news_headlines

headlines = [
    "Bitcoin funding spikes as traders chase breakout",
    "Ethereum activity cools after ETF approval",
]
vectors = embed_news_headlines(headlines)
```

## 4. Cosine Similarity

```python
import numpy as np

norm = np.linalg.norm(vectors, axis=1, keepdims=True)
normalized = vectors / norm
similarity = normalized @ normalized.T
similarity
```

## 5. Save Snapshot

```python
frame.to_parquet("feature_snapshot.parquet")
```

