from __future__ import annotations

from feast import FeatureStore


def get_feature_store() -> FeatureStore:
    return FeatureStore(repo_path=".")


__all__ = ["get_feature_store"]

