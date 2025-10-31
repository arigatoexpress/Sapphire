# PnL Trace Notebook Outline

This markdown file documents the steps for analysing Redis stream data in a
Jupyter notebook. Copy the snippets below into a `.ipynb` and execute to build a
rich analysis environment.

## 1. Setup

```python
import json
import pandas as pd
import requests

STREAM_API = "http://localhost:8000/streams/positions?limit=500"
```

## 2. Load Stream Data

```python
response = requests.get(STREAM_API, timeout=10)
data = response.json()
df = pd.DataFrame(data["entries"])
df["timestamp"] = pd.to_datetime(df["timestamp"])
df.head()
```

## 3. Expand Position Payload

```python
positions = df["positions"].apply(json.loads).apply(pd.Series)
combined = pd.concat([df.drop(columns=["positions"]), positions], axis=1)
combined.plot(x="timestamp", y=["balance", "total_exposure"])
```

## 4. Sharpe / Sortino Estimates

```python
combined["returns"] = combined["balance"].pct_change().fillna(0)
sharpe = (combined["returns"].mean() / combined["returns"].std()) * (365 ** 0.5)
sortino = (
    combined["returns"].mean() /
    combined.loc[combined["returns"] < 0, "returns"].std()
) * (365 ** 0.5)
sharpe, sortino
```

## 5. Export

```python
combined.to_parquet("pnl_trace.parquet")
```

