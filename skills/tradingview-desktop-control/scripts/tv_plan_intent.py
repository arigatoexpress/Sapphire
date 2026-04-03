#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any

import tv_resolve_capability as tvr

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = SKILL_ROOT / "output" / "capability-registry.merged.latest.json"
TVCTL_PATH = SKILL_ROOT / "scripts" / "tvctl.py"
TV_WEB_INVENTORY_PATH = SKILL_ROOT / "scripts" / "tv_web_inventory.py"

PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")
QUOTED_RE = re.compile(r"'([^']+)'|\"([^\"]+)\"")
SYMBOLISH_RE = re.compile(r"\b[A-Z][A-Z0-9._:/-]{1,20}\b")
LEADING_VERB_RE = re.compile(
    r"^\s*(please\s+)?(?:(?:open|show|find|get|go\s+to|switch(?:\s+to)?|change|set|add|search(?:\s+for)?)\s+)+",
    re.IGNORECASE,
)
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def load_registry(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("capabilities"), list):
        raise ValueError(f"Invalid registry shape: {path}")
    return data


def index_capabilities(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for cap in registry.get("capabilities", []):
        if isinstance(cap, dict) and cap.get("id"):
            out[str(cap["id"])] = cap
    return out


def extract_quoted_values(text: str) -> list[str]:
    vals: list[str] = []
    for m in QUOTED_RE.finditer(text or ""):
        vals.append(m.group(1) or m.group(2) or "")
    return [v.strip() for v in vals if v and v.strip()]


def extract_symbol_candidates(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in SYMBOLISH_RE.finditer(text or ""):
        val = m.group(0).strip()
        if val.lower() in {"tv", "ui"}:
            continue
        if val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def recipe_parameter_names(recipe: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for p in recipe.get("parameters", []) or []:
        if isinstance(p, dict) and isinstance(p.get("name"), str):
            n = p["name"].strip()
            if n and n not in names:
                names.append(n)

    def walk(v: Any) -> None:
        if isinstance(v, str):
            for m in PLACEHOLDER_RE.finditer(v):
                n = m.group(1)
                if n not in names:
                    names.append(n)
        elif isinstance(v, list):
            for item in v:
                walk(item)
        elif isinstance(v, dict):
            for item in v.values():
                walk(item)

    # Allow placeholders in richer recipe shapes (web actions, verification assertions, etc.)
    walk(recipe)
    return names


def _strip_leading_verb_phrase(text: str) -> str:
    return LEADING_VERB_RE.sub("", (text or "").strip()).strip()


def _strip_noise_for_placeholder(text: str, placeholder: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    p = placeholder.lower()
    if p in {"symbol", "ticker", "asset"}:
        t = re.sub(r"^\s*(chart\s+)?symbol\s+", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+(chart|symbol)\s*$", "", t, flags=re.IGNORECASE)
    if p in {"layout_name", "layout"}:
        t = re.sub(r"^\s*(open|search|select|find|use)\s+", "", t, flags=re.IGNORECASE)
        t = re.sub(r"^\s*(layout(s)?\s+manager\s+)", "", t, flags=re.IGNORECASE)
        t = re.sub(r"^\s*(layout(s)?\s+)", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+layout(s)?\s*$", "", t, flags=re.IGNORECASE)
    if p in {"query", "indicator", "indicator_query"}:
        t = re.sub(r"^\s*(indicator(s)?\s+)", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+indicator(s)?\s*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"^\s*indicator(s)?\s*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"^\s*for\s+", "", t, flags=re.IGNORECASE)
    if p in {"alert_name", "name"}:
        t = re.sub(r"^\s*(alert\s+)?name\s+", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+(alert\s+)?name\s*$", "", t, flags=re.IGNORECASE)
    if p in {"message", "alert_message"}:
        t = re.sub(r"^\s*(alert\s+)?message\s+", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+(alert\s+)?message\s*$", "", t, flags=re.IGNORECASE)
    if p in {"symbol", "ticker", "asset"}:
        t = re.sub(r"^\s*symbol\s*$", "", t, flags=re.IGNORECASE)
    return t.strip()


def infer_parameter_values(intent: str, cap: dict[str, Any], recipe: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    quoted = extract_quoted_values(intent)
    symbols = extract_symbol_candidates(intent)
    tail = _strip_leading_verb_phrase(intent)

    # Prefer explicit quotes for free-form queries.
    q_iter = iter(quoted)
    used_quote = False
    for name in recipe_parameter_names(recipe):
        lname = name.lower()
        val = None
        if lname in {"symbol", "ticker", "asset"}:
            if symbols:
                val = symbols[0]
            elif quoted:
                val = quoted[0]
        elif lname in {"query", "indicator", "indicator_query", "text"} or lname in {"layout_name", "layout"} or lname in {"alert_name", "name"}:
            if quoted:
                val = quoted[0]
                used_quote = True
            else:
                val = _strip_noise_for_placeholder(tail, lname)
        elif lname in {"message", "alert_message"}:
            if quoted:
                val = quoted[0]
                used_quote = True
            else:
                # Message values are too free-form; avoid overfilling unless clearly quoted.
                val = None
        else:
            # Generic fallback: use first quoted string if present.
            try:
                q = next(q_iter)
                val = q
                used_quote = True
            except StopIteration:
                val = None
        if isinstance(val, str):
            val = val.strip()
        if val:
            values[name] = val

    # If we consumed a quote for a query-like field, keep tail-based inference conservative for others.
    if used_quote:
        return values

    # Light heuristic: for "add RSI indicator", query tail collapses to "RSI".
    if "query" in {n.lower() for n in recipe_parameter_names(recipe)} and quoted == []:
        t = _strip_noise_for_placeholder(tail, "query")
        if t and t.lower() not in {"indicators", "indicator"}:
            values.setdefault("query", t)
    return values


def render_template_value(v: Any, values: dict[str, str]) -> Any:
    if isinstance(v, str):
        def repl(m: re.Match[str]) -> str:
            name = m.group(1)
            return str(values.get(name, m.group(0)))

        return PLACEHOLDER_RE.sub(repl, v)
    if isinstance(v, list):
        return [render_template_value(x, values) for x in v]
    if isinstance(v, dict):
        return {k: render_template_value(x, values) for k, x in v.items()}
    return v


def materialize_recipe(recipe: dict[str, Any], values: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    materialized = json.loads(json.dumps(recipe))
    missing: list[str] = []
    placeholders = recipe_parameter_names(recipe)
    for name in placeholders:
        if name not in values or not str(values[name]).strip():
            missing.append(name)

    materialized = render_template_value(materialized, values)
    if "args_template" in materialized:
        materialized["args"] = materialized["args_template"]
    materialized["missing_parameters"] = missing
    materialized["filled_parameters"] = {k: values[k] for k in placeholders if k in values}
    return materialized, missing


def build_command_preview(recipe: dict[str, Any]) -> str | None:
    runner = str(recipe.get("runner") or "")
    if runner == "tvctl.py":
        cmd = ["python3", str(TVCTL_PATH), str(recipe.get("subcommand") or "")]
        for arg in recipe.get("args", []) or []:
            cmd.append(str(arg))
        return shlex.join(cmd)
    if runner == "tv_web_inventory.py":
        cmd = ["python3", str(TV_WEB_INVENTORY_PATH)]
        if recipe.get("url"):
            cmd += ["--url", str(recipe["url"])]
        if recipe.get("capture_label"):
            cmd += ["--capture-label", str(recipe["capture_label"])]
        # The executor writes inline recipe.actions to a temp plan file.
        cmd += ["--actions-file", "<generated-actions.json>", "--output", "<generated-output.json>"]
        return shlex.join(cmd)
    return None


def max_risk_allowed(level: str, max_risk: str) -> bool:
    return RISK_ORDER.get((level or "low").lower(), 0) <= RISK_ORDER.get((max_risk or "high").lower(), 2)


def pick_actionable_match(
    actionable_rows: list[dict[str, Any]],
    cap_index: dict[str, dict[str, Any]],
    *,
    max_risk: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    considered: list[dict[str, Any]] = []
    for row in actionable_rows:
        risk = str(row.get("risk_level") or "low")
        blocked_risk = not max_risk_allowed(risk, max_risk)
        adjusted = float(row.get("score") or 0)
        adjusted += 15.0  # Planner prioritizes executable actions.
        if blocked_risk:
            adjusted -= 30.0
        item = {
            "row": row,
            "cap": cap_index.get(str(row.get("id") or "")),
            "planner_score": round(adjusted, 2),
            "blocked_risk": blocked_risk,
        }
        considered.append(item)
    considered.sort(
        key=lambda x: (
            x["blocked_risk"],
            -float(x["planner_score"]),
            -float((x["row"] or {}).get("score") or 0),
            str((x["row"] or {}).get("label") or "").lower(),
        )
    )
    chosen = next((x for x in considered if not x["blocked_risk"]), None)
    return chosen, considered


def build_plan(
    registry: dict[str, Any],
    intent: str,
    *,
    search_top: int,
    min_score: float,
    prefer_surface_family: str | None,
    max_risk: str,
) -> dict[str, Any]:
    cap_index = index_capabilities(registry)
    all_rows = tvr.resolve_capabilities(
        registry,
        intent,
        top=max(1, search_top),
        min_score=min_score,
        prefer_surface_family=prefer_surface_family,
        only_actionable=False,
    )
    actionable_rows = tvr.resolve_capabilities(
        registry,
        intent,
        top=max(1, search_top),
        min_score=min_score,
        prefer_surface_family=prefer_surface_family,
        only_actionable=True,
    )

    chosen_actionable, actionable_considered = pick_actionable_match(actionable_rows, cap_index, max_risk=max_risk)
    top_match = all_rows[0] if all_rows else None
    strongest_blocked = next((c for c in actionable_considered if bool(c.get("blocked_risk"))), None)

    if strongest_blocked and chosen_actionable:
        blocked_base = float((strongest_blocked.get("row") or {}).get("score") or 0)
        allowed_base = float((chosen_actionable.get("row") or {}).get("score") or 0)
        # Do not silently substitute a weaker but safer action when the intent strongly matches a blocked action.
        if blocked_base >= allowed_base + 20:
            chosen_actionable = strongest_blocked

    out: dict[str, Any] = {
        "intent": intent,
        "registry_generated_at": registry.get("generated_at"),
        "search_top": search_top,
        "max_risk": max_risk,
        "top_match": top_match,
        "alternatives": all_rows[:5],
        "actionable_candidates": [
            {
                "id": c["row"].get("id"),
                "label": c["row"].get("label"),
                "surface_family": c["row"].get("surface_family"),
                "risk_level": c["row"].get("risk_level"),
                "score": c["row"].get("score"),
                "planner_score": c["planner_score"],
                "blocked_risk": c["blocked_risk"],
            }
            for c in actionable_considered[:10]
        ],
    }

    if not chosen_actionable:
        if actionable_considered and all(bool(c.get("blocked_risk")) for c in actionable_considered):
            out["status"] = "blocked_risk"
            out["message"] = "Actionable matches were found, but all exceed the configured max risk."
        else:
            out["status"] = "no_actionable_match"
            out["message"] = "No actionable capability matched the intent within the current risk threshold."
        return out

    row = chosen_actionable["row"]
    cap = chosen_actionable["cap"] or {}
    recipes = list(cap.get("action_recipes") or row.get("action_recipes") or [])
    recipe = recipes[0] if recipes else None
    if not isinstance(recipe, dict):
        out["status"] = "no_recipe"
        out["message"] = "Best actionable capability has no usable recipe payload."
        out["selected_capability"] = row
        return out

    inferred_values = infer_parameter_values(intent, cap, recipe)
    materialized_recipe, missing = materialize_recipe(recipe, inferred_values)
    command_preview = build_command_preview(materialized_recipe)

    status = "ready"
    if bool(chosen_actionable.get("blocked_risk")):
        status = "blocked_risk"
    elif missing:
        status = "needs_input"

    out.update(
        {
            "status": status,
            "selected_capability": {
                "id": row.get("id"),
                "label": row.get("label"),
                "surface_family": row.get("surface_family"),
                "risk_level": row.get("risk_level"),
                "score": row.get("score"),
                "planner_score": chosen_actionable.get("planner_score"),
                "cluster_key_normalized": row.get("cluster_key_normalized"),
                "reasons": row.get("reasons"),
                "tags": cap.get("tags") or row.get("tags"),
                "preconditions": cap.get("preconditions") or [],
            },
            "recipe": materialized_recipe,
            "command_preview": command_preview,
            "missing_parameters": missing,
        }
    )
    if status == "blocked_risk":
        out["message"] = f"Selected action exceeds max risk '{max_risk}'. Increase --max-risk to allow planning this action."
    elif missing:
        out["message"] = f"Need values for: {', '.join(missing)}"
    return out


def format_plan_text(plan: dict[str, Any], registry_path: Path) -> str:
    lines = [f"Intent: {plan.get('intent')}", f"Registry: {registry_path}", f"Status: {plan.get('status')}"]
    msg = plan.get("message")
    if msg:
        lines.append(f"Note: {msg}")

    sel = plan.get("selected_capability")
    if isinstance(sel, dict):
        lines.append("")
        lines.append(
            f"Selected: {sel.get('label')}  [score={sel.get('score')}, planner_score={sel.get('planner_score')}, surface={sel.get('surface_family')}, risk={sel.get('risk_level')}]"
        )
        lines.append(f"id: {sel.get('id')}")
        if sel.get("preconditions"):
            lines.append(f"preconditions: {', '.join(str(x) for x in sel.get('preconditions') or [])}")
        if sel.get("reasons"):
            lines.append(f"resolver_reasons: {', '.join(str(x) for x in sel.get('reasons')[:8])}")

    recipe = plan.get("recipe")
    if isinstance(recipe, dict):
        lines.append("")
        lines.append(f"Recipe: {json.dumps(recipe, ensure_ascii=False)}")
    if plan.get("command_preview"):
        lines.append(f"Command preview: {plan.get('command_preview')}")
    if plan.get("missing_parameters"):
        lines.append(f"Missing parameters: {', '.join(str(x) for x in plan.get('missing_parameters') or [])}")

    alts = plan.get("alternatives") or []
    if isinstance(alts, list) and alts:
        lines.append("")
        lines.append("Top alternatives:")
        for i, row in enumerate(alts[:5], start=1):
            if not isinstance(row, dict):
                continue
            actionable = "yes" if row.get("action_recipes") else "no"
            lines.append(
                f"{i}. {row.get('label')} [score={row.get('score')}, surface={row.get('surface_family')}, risk={row.get('risk_level')}, actionable={actionable}]"
            )
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Plan an executable TradingView action from a natural-language intent")
    p.add_argument("intent", help='Intent text, e.g. \'set chart symbol "AAPL"\'')
    p.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    p.add_argument("--search-top", type=int, default=20, help="Number of resolver candidates to inspect before choosing an action")
    p.add_argument("--min-score", type=float, default=0.0)
    p.add_argument("--prefer-surface-family", choices=["desktop_ui", "web_ui"], default=None)
    p.add_argument("--max-risk", choices=["low", "medium", "high"], default="medium")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    try:
        registry = load_registry(args.registry)
        plan = build_plan(
            registry,
            args.intent,
            search_top=max(1, args.search_top),
            min_score=args.min_score,
            prefer_surface_family=args.prefer_surface_family,
            max_risk=args.max_risk,
        )
    except Exception as e:  # noqa: BLE001
        print(f"{args.registry}: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print(format_plan_text(plan, args.registry))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
