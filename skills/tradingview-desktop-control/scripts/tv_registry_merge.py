#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = SKILL_ROOT / "output" / "capability-registry.merged.json"

RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
ELLIPSIS_RE = re.compile(r"(…|\.{3})$")
PLAYWRIGHT_WRAPPER_RE = re.compile(r"^'?([a-z][\w\s/#&+.,:-]*)\s+\"(.+?)\"'?:?$", re.IGNORECASE)
PLAYWRIGHT_ROLE_PREFIX_RE = re.compile(r"^(generic|button|toolbar|tablist|tab|region|searchbox|dialog|menu|menuitem):\s*", re.IGNORECASE)

# Canonical alias map for cross-surface clustering.
# Keep this conservative; do not collapse semantically different actions.
CANONICAL_LABEL_ALIASES = {
    "indicators, metrics, and strategies": "indicators",
    "compare or add symbol": "symbol search",
    "symbol search": "symbol search",
    "quick search": "quick search",
    "manage layouts": "layout setup",
    "layout setup": "layout setup",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-") or "item"


def normalize_label(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def strip_trailing_ellipsis(text: str) -> str:
    return ELLIPSIS_RE.sub("", text or "").strip()


def unwrap_playwright_snapshot_label(text: str) -> str:
    """
    Convert snapshot labels like:
      button "Settings":
      'region "Chart #1"':
    into:
      Settings
      Chart #1
    """
    t = (text or "").strip()
    m = PLAYWRIGHT_WRAPPER_RE.match(t)
    if m:
        return m.group(2).strip()
    return t


def strip_playwright_role_prefix(text: str) -> str:
    return PLAYWRIGHT_ROLE_PREFIX_RE.sub("", (text or "").strip()).strip()


def _looks_like_wrapped_snapshot_label(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    return bool(PLAYWRIGHT_WRAPPER_RE.match(t) or PLAYWRIGHT_ROLE_PREFIX_RE.match(t))


def should_replace_display_label(current_label: str, new_label: str) -> bool:
    cur = (current_label or "").strip()
    new = (new_label or "").strip()
    if not new:
        return False
    if not cur:
        return True
    cur_wrapped = _looks_like_wrapped_snapshot_label(cur)
    new_wrapped = _looks_like_wrapped_snapshot_label(new)
    if cur_wrapped and not new_wrapped:
        return True
    if cur_wrapped == new_wrapped:
        # Prefer shorter labels when one is a verbose menu wrapper and the other is cleaner.
        if len(new) + 8 < len(cur):
            return True
    return False


def _desktop_menu_leaf(label: str) -> str:
    parts = [p.strip() for p in label.split(">")]
    return parts[-1] if parts else label


def canonical_cluster_label(label: str, surface: str | None) -> str:
    s = (surface or "").lower()
    t = unwrap_playwright_snapshot_label(label)
    if s in {"web", "web_snapshot", "canvas"}:
        t = strip_playwright_role_prefix(t)
    if s == "desktop_menu":
        t = _desktop_menu_leaf(t)
    t = strip_trailing_ellipsis(t)
    t = normalize_label(t)
    t = CANONICAL_LABEL_ALIASES.get(t, t)
    return t


def canonical_node_label(label: str, surface: str | None) -> str:
    """
    Normalize labels for per-surface node dedupe.
    Preserve desktop menu paths, but unwrap snapshot wrappers and strip ellipses.
    """
    s = (surface or "").lower()
    t = label
    if s in {"web", "web_snapshot", "canvas"}:
        t = unwrap_playwright_snapshot_label(t)
        t = strip_playwright_role_prefix(t)
    t = strip_trailing_ellipsis(t)
    t = normalize_label(t)
    # Apply conservative aliasing to web labels for better dedupe across contexts.
    if s in {"web", "web_snapshot", "canvas"}:
        t = CANONICAL_LABEL_ALIASES.get(t, t)
    return t


def surface_family(surface: str | None) -> str:
    s = (surface or "unknown").strip().lower()
    if s in {"web", "web_snapshot", "canvas"}:
        return "web_ui"
    if s in {"desktop", "desktop_menu", "desktop_shortcut"}:
        return "desktop_ui"
    return s or "unknown"


def max_risk(a: str | None, b: str | None) -> str:
    ra = RISK_ORDER.get((a or "low").lower(), 0)
    rb = RISK_ORDER.get((b or "low").lower(), 0)
    return "low" if max(ra, rb) == 0 else ("medium" if max(ra, rb) == 1 else "high")


def extract_source_capabilities(data: dict[str, Any], path: Path) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"path": str(path)}

    if isinstance(data, dict) and "registry_seed" in data and isinstance(data["registry_seed"], dict):
        reg = data["registry_seed"]
        caps = list(reg.get("capabilities", []) or [])
        meta.update(
            {
                "kind": "desktop_inventory",
                "generated_at": data.get("generated_at") or reg.get("generated_at"),
                "top_menus": ((data.get("desktop") or {}).get("top_menus")),
            }
        )
        return "desktop_inventory", caps, meta

    if isinstance(data, dict) and "captures" in data and isinstance(data.get("capabilities"), list):
        caps = list(data.get("capabilities", []) or [])
        captures = data.get("captures") or []
        meta.update(
            {
                "kind": "web_inventory",
                "generated_at": ((captures[0] if captures else {}) or {}).get("page", {}).get("timestamp"),
                "capture_labels": [c.get("label") for c in captures if isinstance(c, dict)],
                "page_titles": [((c.get("page") or {}).get("title")) for c in captures if isinstance(c, dict)],
            }
        )
        return "web_inventory", caps, meta

    if isinstance(data, dict) and isinstance(data.get("capabilities"), list):
        caps = list(data.get("capabilities", []) or [])
        meta.update(
            {
                "kind": "registry",
                "generated_at": data.get("generated_at"),
                "generator": data.get("generator"),
            }
        )
        return "registry", caps, meta

    raise ValueError(f"Unsupported input shape in {path}")


def _json_fingerprint(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]


def _dedupe_list(values: list[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for v in values:
        key = _json_fingerprint(v)
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def _parse_iso_dt(value: Any) -> dt.datetime | None:
    if not value or not isinstance(value, str):
        return None
    t = value.strip()
    if not t:
        return None
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(t)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _action_recipe_semantic_identity(recipe: Any) -> Any:
    if not isinstance(recipe, dict):
        return recipe
    # Exclude verification + execution policy so semantically identical recipes
    # from newer inventories can replace older variants while preserving behavior.
    return {
        "runner": recipe.get("runner"),
        "subcommand": recipe.get("subcommand"),
        "url": recipe.get("url"),
        "actions": recipe.get("actions"),
        "args": recipe.get("args"),
        "args_template": recipe.get("args_template"),
        "capture_label": recipe.get("capture_label"),
        "baseline_capture_label": recipe.get("baseline_capture_label"),
        "parameters": recipe.get("parameters"),
        "headed": recipe.get("headed"),
        "close_when_done": recipe.get("close_when_done"),
    }


def _recipe_preference_tuple(record: dict[str, Any]) -> tuple[Any, ...]:
    recipe = record.get("recipe")
    if not isinstance(recipe, dict):
        return (0, 0, 0, 0, 0, float("-inf"), -1, 0, _json_fingerprint(record))
    timeouts = recipe.get("timeouts") if isinstance(recipe.get("timeouts"), dict) else {}
    retry_policy = recipe.get("retry_policy") if isinstance(recipe.get("retry_policy"), dict) else {}
    verification = recipe.get("verification") if isinstance(recipe.get("verification"), dict) else {}
    assertions = verification.get("assertions") if isinstance(verification.get("assertions"), list) else []
    source_dt = _parse_iso_dt(record.get("source_generated_at"))
    source_ts = source_dt.timestamp() if source_dt else float("-inf")
    source_order = int(record.get("source_order") or 0)
    actions_count = len(recipe.get("actions") or []) if isinstance(recipe.get("actions"), list) else 0
    return (
        1 if (timeouts or retry_policy) else 0,
        1 if timeouts else 0,
        1 if retry_policy else 0,
        1 if verification else 0,
        len(assertions),
        source_ts,
        source_order,
        actions_count,
        _json_fingerprint(_action_recipe_semantic_identity(recipe)),
    )


def _select_preferred_action_recipes(records: list[dict[str, Any]]) -> list[Any]:
    best_by_identity: dict[str, dict[str, Any]] = {}
    for rec in records:
        recipe = rec.get("recipe")
        if recipe is None:
            continue
        ident_key = _json_fingerprint(_action_recipe_semantic_identity(recipe))
        incumbent = best_by_identity.get(ident_key)
        if incumbent is None or _recipe_preference_tuple(rec) > _recipe_preference_tuple(incumbent):
            best_by_identity[ident_key] = rec
    winners = list(best_by_identity.values())
    winners.sort(
        key=lambda r: (
            _recipe_preference_tuple(r),
            _json_fingerprint(r.get("recipe")),
        ),
        reverse=True,
    )
    return [w.get("recipe") for w in winners if w.get("recipe") is not None]


def merge_capabilities(inputs: list[tuple[Path, str, list[dict[str, Any]], dict[str, Any]]]) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    clusters: dict[str, dict[str, Any]] = {}
    provenance: list[dict[str, Any]] = []

    for input_order, (path, kind, caps, source_meta) in enumerate(inputs):
        provenance.append({"path": str(path), **source_meta, "capability_count": len(caps)})
        for cap in caps:
            if not isinstance(cap, dict):
                continue
            label = str(cap.get("label") or cap.get("id") or "")
            if not label:
                continue
            surface = str(cap.get("surface") or "unknown")
            s_family = surface_family(surface)
            label_norm = canonical_node_label(label, surface)
            cluster_norm = canonical_cluster_label(label, surface)
            if not label_norm:
                # Skip empty snapshot wrappers like "button:" or "generic:" that do not carry a user-facing label.
                continue
            surface_key = f"{s_family}:{label_norm}"
            node = merged.get(surface_key)
            if node is None:
                cid = f"merged.{slugify(s_family)}.{slugify(label)[:96]}"
                node = {
                    "id": cid,
                    "label": label,
                    "label_normalized": label_norm,
                    "cluster_key_normalized": cluster_norm,
                    "surface_family": s_family,
                    "surfaces": [surface],
                    "risk_level": str(cap.get("risk_level") or "low"),
                    "sources": [],
                    "original_ids": [],
                    "tags": [],
                    "preconditions": [],
                    "enabled_states": [],
                    "action_recipes": [],
                    "_action_recipe_records": [],
                    "metadata_samples": [],
                    "observations": 0,
                }
                merged[surface_key] = node
            elif should_replace_display_label(str(node.get("label") or ""), label):
                node["label"] = label
            node["risk_level"] = max_risk(node.get("risk_level"), str(cap.get("risk_level") or "low"))
            node["observations"] = int(node.get("observations") or 0) + 1
            if surface not in node["surfaces"]:
                node["surfaces"].append(surface)
            if cap.get("id") and cap.get("id") not in node["original_ids"]:
                node["original_ids"].append(cap["id"])
            node["sources"].append({
                "input": str(path),
                "kind": kind,
                "source": cap.get("source"),
                "surface": surface,
                "id": cap.get("id"),
            })
            for t in cap.get("tags", []) or []:
                if isinstance(t, str) and t not in node["tags"]:
                    node["tags"].append(t)
            for p in cap.get("preconditions", []) or []:
                if isinstance(p, str) and p not in node["preconditions"]:
                    node["preconditions"].append(p)
            if "enabled" in cap and cap.get("enabled") not in node["enabled_states"]:
                node["enabled_states"].append(cap.get("enabled"))
            if cap.get("action_recipe"):
                node["action_recipes"].append(cap.get("action_recipe"))
                node["_action_recipe_records"].append(
                    {
                        "recipe": cap.get("action_recipe"),
                        "source_order": input_order,
                        "source_generated_at": source_meta.get("generated_at"),
                        "input": str(path),
                        "kind": kind,
                        "cap_source": cap.get("source"),
                    }
                )
            if cap.get("metadata"):
                node["metadata_samples"].append(cap.get("metadata"))

            # Cross-surface cluster by normalized label.
            ckey = cluster_norm
            cluster = clusters.get(ckey)
            if cluster is None:
                cluster = {
                    "cluster_id": f"cluster.{slugify(cluster_norm or label)[:96]}",
                    "label": label,
                    "label_normalized": ckey,
                    "aliases": [],
                    "members": [],
                    "surface_families": [],
                    "surfaces": [],
                    "risk_level": str(cap.get("risk_level") or "low"),
                    "observations": 0,
                }
                clusters[ckey] = cluster
            if label not in cluster["aliases"]:
                cluster["aliases"].append(label)
            # Prefer a cleaner display label when canonicalization simplified a wrapper/menu path.
            if cluster_norm and (cluster.get("label") == label and cluster_norm != normalize_label(label)):
                cluster["label"] = cluster_norm
            cluster["risk_level"] = max_risk(cluster.get("risk_level"), str(cap.get("risk_level") or "low"))
            cluster["observations"] = int(cluster.get("observations") or 0) + 1
            member_id = node["id"]
            if member_id not in cluster["members"]:
                cluster["members"].append(member_id)
            if s_family not in cluster["surface_families"]:
                cluster["surface_families"].append(s_family)
            if surface not in cluster["surfaces"]:
                cluster["surfaces"].append(surface)

    # Cleanup / dedupe nested lists.
    merged_caps: list[dict[str, Any]] = []
    for node in merged.values():
        node["sources"] = _dedupe_list(node.get("sources", []))
        recipe_records = node.pop("_action_recipe_records", [])
        if isinstance(recipe_records, list) and recipe_records:
            node["action_recipes"] = _select_preferred_action_recipes(recipe_records)
        else:
            node["action_recipes"] = _dedupe_list(node.get("action_recipes", []))
        node["metadata_samples"] = _dedupe_list(node.get("metadata_samples", []))[:10]
        if not node.get("enabled_states"):
            node.pop("enabled_states", None)
        if not node.get("action_recipes"):
            node.pop("action_recipes", None)
        if not node.get("metadata_samples"):
            node.pop("metadata_samples", None)
        if not node.get("tags"):
            node.pop("tags", None)
        if not node.get("preconditions"):
            node.pop("preconditions", None)
        merged_caps.append(node)

    merged_caps.sort(key=lambda c: (c.get("surface_family", ""), c.get("label_normalized", ""), c.get("id", "")))
    cluster_list = list(clusters.values())
    for cluster in cluster_list:
        if cluster.get("aliases"):
            cluster["aliases"] = sorted(cluster["aliases"], key=lambda x: (len(str(x)), str(x).lower()))[:20]
    cluster_list.sort(key=lambda c: (-(len(c.get("members", []))), c.get("label_normalized", "")))

    return {
        "schema_version": 1,
        "generator": "tv_registry_merge.py",
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "provenance": provenance,
        "capabilities": merged_caps,
        "clusters": cluster_list,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Merge TradingView desktop/web capability inventories into a canonical registry")
    p.add_argument("inputs", nargs="+", type=Path, help="Inventory/registry JSON files")
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--write-default-output", action="store_true", help=f"Write to {DEFAULT_OUTPUT}")
    p.add_argument("--pretty", action="store_true")
    args = p.parse_args()

    out_path = args.output or (DEFAULT_OUTPUT if args.write_default_output else None)

    loaded: list[tuple[Path, str, list[dict[str, Any]], dict[str, Any]]] = []
    for path in args.inputs:
        try:
            data = load_json(path)
            kind, caps, meta = extract_source_capabilities(data, path)
            loaded.append((path, kind, caps, meta))
        except Exception as e:  # noqa: BLE001
            print(f"{path}: {e}", file=sys.stderr)
            return 1

    merged = merge_capabilities(loaded)

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(merged, indent=2) + "\n")
        summary = {
            "output": str(out_path),
            "input_count": len(loaded),
            "merged_capability_count": len(merged.get("capabilities", [])),
            "cluster_count": len(merged.get("clusters", [])),
            "provenance": [
                {"path": p["path"], "kind": p.get("kind"), "capability_count": p.get("capability_count")}
                for p in merged.get("provenance", [])
            ],
        }
        print(json.dumps(summary, indent=2))
    else:
        print(json.dumps(merged, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
