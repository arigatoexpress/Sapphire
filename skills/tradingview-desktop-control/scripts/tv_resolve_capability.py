#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import tv_registry_merge as tvrm

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = SKILL_ROOT / "output" / "capability-registry.merged.latest.json"

STOPWORDS = {
    "the",
    "a",
    "an",
    "to",
    "for",
    "on",
    "of",
    "and",
    "or",
    "in",
    "with",
    "please",
    "open",
    "show",
    "find",
    "get",
    "run",
    "do",
    "my",
}

HIGH_RISK_TERMS = {
    "trade",
    "broker",
    "order",
    "buy",
    "sell",
    "execute",
    "cancel",
    "remove",
    "delete",
}


def tokenize(text: str) -> list[str]:
    toks = [t for t in re.split(r"[^a-zA-Z0-9#]+", (text or "").lower()) if t]
    normed: list[str] = []
    for t in toks:
        if t in STOPWORDS:
            continue
        # Very light stemming to improve singular/plural matching (e.g., indicators -> indicator).
        if len(t) > 4 and t.endswith("ies"):
            t = t[:-3] + "y"
        elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        normed.append(t)
    return normed


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def load_registry(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("capabilities"), list):
        raise ValueError(f"Invalid registry shape: {path}")
    return data


def capability_search_fields(cap: dict[str, Any]) -> dict[str, Any]:
    label = str(cap.get("label") or "")
    label_norm = str(cap.get("label_normalized") or tvrm.normalize_label(label))
    cluster_key = str(cap.get("cluster_key_normalized") or label_norm)
    tags = [str(t) for t in (cap.get("tags") or []) if isinstance(t, str)]
    originals = [str(x) for x in (cap.get("original_ids") or []) if isinstance(x, str)]
    preconds = [str(x) for x in (cap.get("preconditions") or []) if isinstance(x, str)]

    # Mine some extra text from metadata samples (capture labels, menu paths, roles).
    metadata_tokens: list[str] = []
    for m in cap.get("metadata_samples", []) or []:
        if not isinstance(m, dict):
            continue
        for key in ("capture_label", "role", "label", "page_title", "data_name", "data_role"):
            v = m.get(key)
            if isinstance(v, str):
                metadata_tokens.append(v)
        menu_path = m.get("menu_path")
        if isinstance(menu_path, list):
            metadata_tokens.extend(str(x) for x in menu_path if x)

    return {
        "label": label,
        "label_norm": label_norm,
        "cluster_key": cluster_key,
        "tags": tags,
        "originals": originals,
        "preconds": preconds,
        "metadata_text": metadata_tokens,
    }


def score_capability(
    query: str, q_tokens: set[str], cap: dict[str, Any], prefer_surface_family: str | None
) -> tuple[float, list[str]]:
    fields = capability_search_fields(cap)
    fields["label"]
    label_norm = fields["label_norm"]
    cluster_key = fields["cluster_key"]
    score = 0.0
    reasons: list[str] = []

    q_norm = tvrm.normalize_label(query)
    q_cluster = tvrm.canonical_cluster_label(query, None)

    if q_norm == label_norm:
        score += 80
        reasons.append("exact_label")
    if q_cluster and q_cluster == cluster_key:
        score += 95
        reasons.append("exact_cluster_key")
    if q_norm and q_norm in label_norm:
        score += 35
        reasons.append("label_substring")
    if q_cluster and q_cluster in cluster_key:
        score += 45
        reasons.append("cluster_substring")

    label_tokens = set(tokenize(label_norm))
    cluster_tokens = set(tokenize(cluster_key))
    tag_tokens = set(tokenize(" ".join(fields["tags"]))) if fields["tags"] else set()
    metadata_tokens = (
        set(tokenize(" ".join(fields["metadata_text"]))) if fields["metadata_text"] else set()
    )
    orig_tokens = set(tokenize(" ".join(fields["originals"]))) if fields["originals"] else set()

    token_overlap = len(q_tokens & label_tokens)
    if token_overlap:
        score += 12 * token_overlap
        reasons.append(f"label_token_overlap:{token_overlap}")
    cluster_overlap = len(q_tokens & cluster_tokens)
    if cluster_overlap:
        score += 15 * cluster_overlap
        reasons.append(f"cluster_token_overlap:{cluster_overlap}")
    tag_overlap = len(q_tokens & tag_tokens)
    if tag_overlap:
        score += 10 * tag_overlap
        reasons.append(f"tag_overlap:{tag_overlap}")
    meta_overlap = len(q_tokens & metadata_tokens)
    if meta_overlap:
        score += 6 * min(meta_overlap, 4)
        reasons.append(f"metadata_overlap:{meta_overlap}")
    orig_overlap = len(q_tokens & orig_tokens)
    if orig_overlap:
        score += 4 * min(orig_overlap, 4)
        reasons.append(f"original_id_overlap:{orig_overlap}")

    jac = max(jaccard(q_tokens, label_tokens), jaccard(q_tokens, cluster_tokens))
    if jac > 0:
        score += 20 * jac
        reasons.append(f"token_jaccard:{jac:.2f}")

    if cap.get("action_recipes"):
        score += 6
        reasons.append("actionable")

    sf = str(cap.get("surface_family") or "")
    if prefer_surface_family and sf == prefer_surface_family:
        score += 8
        reasons.append(f"surface_pref:{prefer_surface_family}")

    # Risk penalty unless the query explicitly contains risky intent terms.
    q_risky = bool(q_tokens & HIGH_RISK_TERMS)
    risk = str(cap.get("risk_level") or "low").lower()
    if risk == "high" and not q_risky:
        score -= 6
        reasons.append("risk_penalty_high")
    elif risk == "medium" and not q_risky:
        score -= 2
        reasons.append("risk_penalty_medium")

    # Small stability bonus for repeated observations across captures.
    obs = int(cap.get("observations") or 0)
    if obs > 1:
        score += min(8, 2 * math.log2(obs + 1))
        reasons.append(f"observed:{obs}")

    return score, reasons


def resolve_capabilities(
    registry: dict[str, Any],
    query: str,
    *,
    top: int = 10,
    min_score: float = 0.0,
    prefer_surface_family: str | None = None,
    only_actionable: bool = False,
) -> list[dict[str, Any]]:
    q_tokens = set(tokenize(query))
    results: list[dict[str, Any]] = []
    for cap in registry.get("capabilities", []):
        if not isinstance(cap, dict):
            continue
        if only_actionable and not cap.get("action_recipes"):
            continue
        score, reasons = score_capability(query, q_tokens, cap, prefer_surface_family)
        if score < min_score:
            continue
        results.append(
            {
                "score": round(score, 2),
                "reasons": reasons,
                "id": cap.get("id"),
                "label": cap.get("label"),
                "surface_family": cap.get("surface_family"),
                "surfaces": cap.get("surfaces"),
                "risk_level": cap.get("risk_level"),
                "observations": cap.get("observations"),
                "cluster_key_normalized": cap.get("cluster_key_normalized"),
                "action_recipes": cap.get("action_recipes"),
                "tags": cap.get("tags"),
                "metadata_samples": (cap.get("metadata_samples") or [])[:2],
            }
        )

    results.sort(
        key=lambda r: (
            -float(r.get("score") or 0),
            0 if r.get("action_recipes") else 1,
            str(r.get("risk_level") or ""),
            str(r.get("label") or "").lower(),
        )
    )
    return results[: max(1, top)]


def format_text_results(query: str, registry_path: Path, rows: list[dict[str, Any]]) -> str:
    lines = [f"Query: {query}", f"Registry: {registry_path}", f"Matches: {len(rows)}", ""]
    for i, r in enumerate(rows, start=1):
        actionable = "yes" if r.get("action_recipes") else "no"
        lines.append(
            f"{i}. {r.get('label')}  [score={r.get('score')}, surface={r.get('surface_family')}, risk={r.get('risk_level')}, actionable={actionable}]"
        )
        lines.append(f"   id: {r.get('id')}")
        if r.get("cluster_key_normalized"):
            lines.append(f"   cluster_key: {r.get('cluster_key_normalized')}")
        if r.get("action_recipes"):
            lines.append(
                f"   action_recipe: {json.dumps(r.get('action_recipes')[0], ensure_ascii=False)}"
            )
        if r.get("reasons"):
            lines.append(f"   reasons: {', '.join(r.get('reasons')[:8])}")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Resolve a user intent/query to the best TradingView capability candidates"
    )
    p.add_argument("query", help="Intent text, e.g. 'open indicators' or 'settings'")
    p.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--min-score", type=float, default=0.0)
    p.add_argument("--prefer-surface-family", choices=["desktop_ui", "web_ui"], default=None)
    p.add_argument("--only-actionable", action="store_true")
    p.add_argument("--json", action="store_true", help="Print JSON result rows")
    args = p.parse_args()

    try:
        registry = load_registry(args.registry)
    except Exception as e:  # noqa: BLE001
        print(f"{args.registry}: {e}", file=sys.stderr)
        return 1

    rows = resolve_capabilities(
        registry,
        args.query,
        top=max(1, args.top),
        min_score=args.min_score,
        prefer_surface_family=args.prefer_surface_family,
        only_actionable=args.only_actionable,
    )

    if args.json:
        print(
            json.dumps(
                {"query": args.query, "registry": str(args.registry), "results": rows}, indent=2
            )
        )
    else:
        print(format_text_results(args.query, args.registry, rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
