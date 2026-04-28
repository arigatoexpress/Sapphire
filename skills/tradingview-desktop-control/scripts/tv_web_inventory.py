#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import tv_registry_merge as tvrm

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = SKILL_ROOT / "output" / "tv-web-inventory.json"
PWCLI_DEFAULT = (
    Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    / "skills"
    / "playwright"
    / "scripts"
    / "playwright_cli.sh"
)


ROLE_SELECTOR = ",".join(
    [
        "button",
        "a[href]",
        "input",
        "select",
        "textarea",
        "[role=button]",
        "[role=tab]",
        "[role=menuitem]",
        "[role=option]",
        "[role=checkbox]",
        "[role=switch]",
        "[role=radio]",
        "[role=dialog] [role=button]",
        "[aria-keyshortcuts]",
    ]
)

INTERACTIVE_WEB_ROLES = {
    "button",
    "tab",
    "menuitem",
    "option",
    "checkbox",
    "switch",
    "radio",
    "link",
}
INTERACTIVE_WEB_TAGS = {"button", "a"}

WEB_CLICK_VERIFY_HINTS: dict[str, list[str]] = {
    "indicators": ["Indicators", "Strategies", "Profiles"],
    "settings": ["Symbol", "Scales", "Status line"],
    "create alert": ["Condition", "Notifications", "Create Alert"],
    "layout setup": ["Manage layouts", "Save all charts", "Layouts"],
    "quick search": ["Quick Search", "All sources", "Search"],
    "bar replay": ["Bar Replay", "Go to", "Replay"],
}

WEB_RECIPE_TIMEOUT_PROFILES: dict[str, dict[str, float]] = {
    "generic_click": {"web_exec_timeout_seconds": 60.0, "web_baseline_timeout_seconds": 30.0},
    "dialog_open": {"web_exec_timeout_seconds": 90.0, "web_baseline_timeout_seconds": 45.0},
    "menu_open": {"web_exec_timeout_seconds": 90.0, "web_baseline_timeout_seconds": 45.0},
    "search_dialog": {"web_exec_timeout_seconds": 120.0, "web_baseline_timeout_seconds": 60.0},
    "alert_form": {"web_exec_timeout_seconds": 120.0, "web_baseline_timeout_seconds": 60.0},
    "layout_flow": {"web_exec_timeout_seconds": 150.0, "web_baseline_timeout_seconds": 75.0},
}

WEB_RECIPE_RETRY_PROFILES: dict[str, dict[str, float | int]] = {
    "generic_click": {
        "web_exec_attempts": 2,
        "web_baseline_attempts": 2,
        "backoff_seconds": 0.5,
        "backoff_multiplier": 2.0,
    },
    "dialog_open": {
        "web_exec_attempts": 2,
        "web_baseline_attempts": 2,
        "backoff_seconds": 0.75,
        "backoff_multiplier": 2.0,
    },
    "menu_open": {
        "web_exec_attempts": 2,
        "web_baseline_attempts": 2,
        "backoff_seconds": 0.75,
        "backoff_multiplier": 2.0,
    },
    "search_dialog": {
        "web_exec_attempts": 3,
        "web_baseline_attempts": 2,
        "backoff_seconds": 0.75,
        "backoff_multiplier": 2.0,
    },
    "alert_form": {
        "web_exec_attempts": 3,
        "web_baseline_attempts": 2,
        "backoff_seconds": 0.75,
        "backoff_multiplier": 2.0,
    },
    "layout_flow": {
        "web_exec_attempts": 3,
        "web_baseline_attempts": 2,
        "backoff_seconds": 1.0,
        "backoff_multiplier": 2.0,
    },
}


def run_pw(pwcli: Path, session: str, args: list[str], cwd: Path) -> str:
    cmd = [str(pwcli), "--session", session] + args
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "playwright-cli failed").strip()
        raise RuntimeError(
            f"Playwright CLI failed ({' '.join(shlex.quote(a) for a in args)}): {msg}"
        )
    return (proc.stdout or "").strip()


def _snapshot_timeout_like(message: str) -> bool:
    t = str(message or "")
    return (
        "page._snapshotForAI" in t
        or "Timeout 5000ms exceeded" in t
        or "Snapshot artifact not found" in t
    )


def parse_snapshot_artifact_from_output(output: str, cwd: Path) -> Path | None:
    m = re.search(r"\[Snapshot\]\(([^)]+\.yml)\)", output)
    if not m:
        return None
    rel = m.group(1)
    return (cwd / rel).resolve()


def _extract_result_block(output: str) -> str | None:
    marker = "### Result"
    if marker not in output:
        return None
    tail = output.split(marker, 1)[1].lstrip("\n")
    lines = tail.splitlines()
    block_lines: list[str] = []
    for line in lines:
        if line.startswith("### "):
            break
        if block_lines or line.strip():
            block_lines.append(line)
    raw = "\n".join(block_lines).strip()
    return raw or None


def parse_eval_json_output(output: str) -> Any:
    raw = _extract_result_block(output)
    if raw is None:
        raise RuntimeError(f"Could not parse eval result from output: {output[:500]}")
    # Playwright CLI returns a JSON-quoted string when we JSON.stringify in page context.
    value = json.loads(raw)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def pw_eval_json(pwcli: Path, session: str, cwd: Path, js_expr: str) -> Any:
    out = run_pw(pwcli, session, ["eval", js_expr], cwd)
    return parse_eval_json_output(out)


def parse_snapshot_yaml(snapshot_path: Path, max_refs: int = 4000) -> list[dict[str, Any]]:
    lines = snapshot_path.read_text(errors="replace").splitlines()
    refs: list[dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        if "[ref=e" not in line:
            continue
        m_ref = re.search(r"\[ref=(e\d+)\]", line)
        if not m_ref:
            continue
        ref = m_ref.group(1)

        indent = len(line) - len(line.lstrip(" "))
        level = indent // 2

        payload = line.lstrip()
        if payload.startswith("- "):
            payload = payload[2:]
        # Remove bracket attrs for role/label parsing.
        payload_no_brackets = re.sub(r"\s*\[[^\]]*\]", "", payload).strip()
        m_role = re.match(r'(?P<role>[\w/-]+)(?:\s+"(?P<label>.*?)")?$', payload_no_brackets)
        role = m_role.group("role") if m_role else payload_no_brackets
        label = m_role.group("label") if m_role else None

        attrs_raw: dict[str, str | bool] = {}
        for bracket in re.findall(r"\[([^\]]+)\]", payload):
            if bracket.startswith("ref="):
                continue
            if "=" in bracket:
                k, v = bracket.split("=", 1)
                attrs_raw[k.strip()] = v.strip()
            else:
                attrs_raw[bracket.strip()] = True

        refs.append(
            {
                "ref": ref,
                "line": i,
                "level": level,
                "role": role,
                "label": label,
                "attrs": attrs_raw or None,
                "text": payload_no_brackets,
            }
        )
        if len(refs) >= max_refs:
            break
    return refs


def snapshot_with_refs(
    pwcli: Path, session: str, cwd: Path, *, max_refs: int = 4000
) -> tuple[str, Path, list[dict[str, Any]]]:
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            out = run_pw(pwcli, session, ["snapshot"], cwd)
            snapshot_path = parse_snapshot_artifact_from_output(out, cwd)
            if not snapshot_path or not snapshot_path.exists():
                raise RuntimeError(f"Snapshot artifact not found in output:\n{out}")
            refs = parse_snapshot_yaml(snapshot_path, max_refs=max_refs)
            return out, snapshot_path, refs
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if attempt >= 3 or not _snapshot_timeout_like(str(e)):
                raise
            time.sleep(0.6 * attempt)
    assert last_exc is not None
    raise last_exc


def _text_matches(
    hay: str | None, needle: str, *, match: str = "contains", case_sensitive: bool = False
) -> bool:
    if hay is None:
        return False
    left = hay if case_sensitive else hay.lower()
    right = needle if case_sensitive else needle.lower()
    mode = (match or "contains").strip().lower()
    if mode == "exact":
        return left == right
    if mode == "startswith":
        return left.startswith(right)
    if mode == "contains":
        return right in left
    if mode == "regex":
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.search(needle, hay, flags=flags) is not None
    raise ValueError(f"Unsupported match mode: {match}")


def find_snapshot_ref_by_label(
    refs: list[dict[str, Any]],
    *,
    label: str,
    role: str | None = None,
    match: str = "contains",
    case_sensitive: bool = False,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for ref in refs:
        if role and str(ref.get("role") or "").lower() != role.lower():
            continue
        label_text = str(ref.get("label") or ref.get("text") or "")
        if not label_text:
            continue
        if _text_matches(label_text, label, match=match, case_sensitive=case_sensitive):
            candidates.append(ref)
    if not candidates:
        return None
    # Prefer shallower refs with explicit labels first; then smallest line number for determinism.
    candidates.sort(
        key=lambda r: (
            0 if r.get("label") else 1,
            int(r.get("level") or 9999),
            int(r.get("line") or 999999),
        )
    )
    return candidates[0]


def find_snapshot_ref_by_any_label(
    refs: list[dict[str, Any]],
    labels: list[str],
    *,
    role: str | None = None,
    match: str = "contains",
    case_sensitive: bool = False,
) -> tuple[dict[str, Any], str] | None:
    for label in labels:
        hit = find_snapshot_ref_by_label(
            refs,
            label=label,
            role=role,
            match=match,
            case_sensitive=case_sensitive,
        )
        if hit:
            return hit, label
    return None


def js_page_info() -> str:
    return (
        "JSON.stringify({"
        "href: location.href,"
        "title: document.title,"
        "readyState: document.readyState,"
        "lang: document.documentElement.lang || null,"
        "frames: window.frames.length,"
        "viewport: {w: window.innerWidth, h: window.innerHeight},"
        "timestamp: new Date().toISOString()"
        "})"
    )


def js_dom_controls(limit: int) -> str:
    selector = ROLE_SELECTOR.replace("'", "\\'")
    return (
        "JSON.stringify((function(){"
        f" var nodes = document.querySelectorAll('{selector}');"
        " var out = [];"
        " var seen = Object.create(null);"
        f" var limit = {int(limit)};"
        " for (var i = 0; i < nodes.length && out.length < limit; i++) {"
        "   var el = nodes[i];"
        "   var rect = el.getBoundingClientRect();"
        "   var text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 200);"
        "   var key = [el.tagName, el.getAttribute('role') || '', el.getAttribute('aria-label') || '', text.slice(0,80), Math.round(rect.x), Math.round(rect.y)].join('|');"
        "   if (seen[key]) continue;"
        "   seen[key] = true;"
        "   var classes = [];"
        "   if (el.className && typeof el.className === 'string') {"
        "     classes = el.className.trim() ? el.className.trim().split(/\\s+/).slice(0,8) : [];"
        "   }"
        "   out.push({"
        "     idx: i,"
        "     tag: el.tagName.toLowerCase(),"
        "     role: el.getAttribute('role'),"
        "     text: text,"
        "     aria_label: el.getAttribute('aria-label'),"
        "     aria_keyshortcuts: el.getAttribute('aria-keyshortcuts'),"
        "     title: el.getAttribute('title'),"
        "     placeholder: el.getAttribute('placeholder'),"
        "     name_attr: el.getAttribute('name'),"
        "     data_name: el.getAttribute('data-name'),"
        "     data_role: el.getAttribute('data-role'),"
        "     href: el.getAttribute('href'),"
        "     disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'),"
        "     classes: classes,"
        "     rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }"
        "   });"
        " }"
        " return out;"
        "})())"
    )


def js_data_attributes(limit: int) -> str:
    return (
        "JSON.stringify((function(){"
        " var nodes = document.querySelectorAll('[data-name], [data-role], [aria-label], [title]');"
        " var out = [];"
        f" var limit = {int(limit)};"
        " for (var i = 0; i < nodes.length && out.length < limit; i++) {"
        "   var el = nodes[i];"
        "   var rect = el.getBoundingClientRect();"
        "   var rec = {"
        "     idx: i,"
        "     tag: el.tagName.toLowerCase(),"
        "     data_name: el.getAttribute('data-name'),"
        "     data_role: el.getAttribute('data-role'),"
        "     aria_label: el.getAttribute('aria-label'),"
        "     title: el.getAttribute('title'),"
        "     text: (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 120),"
        "     rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }"
        "   };"
        "   if (rec.data_name || rec.data_role || rec.aria_label || rec.title) out.push(rec);"
        " }"
        " return out;"
        "})())"
    )


def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-") or "item"


def infer_risk(label: str) -> str:
    t = label.lower()
    if any(
        k in t for k in ["buy", "sell", "trade", "order", "broker", "publish strategy", "execute"]
    ):
        return "high"
    if any(k in t for k in ["delete", "remove", "clear", "reset", "close", "logout"]):
        return "medium"
    return "low"


def _clean_recipe_label(label: str) -> str:
    t = str(label or "").strip()
    if not t:
        return ""
    t = tvrm.unwrap_playwright_snapshot_label(t)
    t = tvrm.strip_playwright_role_prefix(t)
    t = tvrm.strip_trailing_ellipsis(t)
    return t.strip()


def _collect_capture_labels(capture: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for ctrl in capture.get("dom_controls", []) or []:
        if not isinstance(ctrl, dict):
            continue
        for key in ("aria_label", "title", "text", "data_name"):
            v = ctrl.get(key)
            if isinstance(v, str) and v.strip():
                labels.append(v.strip())
                break
    for ref in capture.get("snapshot_refs", []) or []:
        if not isinstance(ref, dict):
            continue
        for key in ("label", "text"):
            v = ref.get(key)
            if isinstance(v, str) and v.strip():
                labels.append(v.strip())
                break
    return labels


def _capture_has_any_label(capture: dict[str, Any], labels: list[str]) -> bool:
    if not labels:
        return False
    hay = _collect_capture_labels(capture)
    for needle in labels:
        if any(_text_matches(item, needle, match="contains", case_sensitive=False) for item in hay):
            return True
    return False


def _build_web_verification_assertions(
    *,
    click_action: str,
    capture_label: str,
    hint_labels: list[str] | None = None,
    appear_labels: list[str] | None = None,
) -> list[dict[str, Any]]:
    assertions: list[dict[str, Any]] = [
        {"kind": "plan_action_executed", "action": click_action, "min_count": 1},
        {"kind": "capture_label_equals", "value": capture_label},
    ]
    if hint_labels:
        assertions.append(
            {
                "kind": "snapshot_label_any",
                "values": [str(x) for x in hint_labels if str(x).strip()],
                "match": "contains",
            }
        )
    if appear_labels:
        assertions.append(
            {
                # Baseline-dependent "appears" checks are fragile on slower Pi hosts due extra
                # pre-exec snapshot captures; use presence checks and rely on post-action
                # capture_label + snapshot labels + action execution assertions for confidence.
                "kind": "capture_text_any",
                "values": [str(x) for x in appear_labels if str(x).strip()],
                "match": "contains",
            }
        )
    return assertions


def _with_web_recipe_execution_policy(
    recipe: dict[str, Any], *, profile: str = "generic_click"
) -> dict[str, Any]:
    out = dict(recipe)
    timeout_defaults = dict(
        WEB_RECIPE_TIMEOUT_PROFILES.get(profile, WEB_RECIPE_TIMEOUT_PROFILES["generic_click"])
    )
    retry_defaults = dict(
        WEB_RECIPE_RETRY_PROFILES.get(profile, WEB_RECIPE_RETRY_PROFILES["generic_click"])
    )
    existing_timeouts = out.get("timeouts") if isinstance(out.get("timeouts"), dict) else {}
    existing_retries = out.get("retry_policy") if isinstance(out.get("retry_policy"), dict) else {}
    out["timeouts"] = {**timeout_defaults, **existing_timeouts}
    out["retry_policy"] = {**retry_defaults, **existing_retries}
    return out


def _web_click_recipe(
    *,
    label: str,
    role: str | None,
    page_href: str | None,
    capture_label: str | None,
) -> dict[str, Any] | None:
    click_label = _clean_recipe_label(label)
    if not click_label:
        return None
    if len(click_label) > 160:
        return None
    step: dict[str, Any] = {
        "action": "snapshot-click-label",
        "label": click_label,
        "match": "contains",
        "wait_after": 0.35,
    }
    if role:
        step["role"] = role
    page_url = str(page_href or "https://www.tradingview.com/chart/")
    clabel = f"post-click-{slugify(str(capture_label or 'web'))[:24]}-{slugify(click_label)[:40]}"
    canonical = tvrm.canonical_cluster_label(click_label, "web")
    hint_labels = WEB_CLICK_VERIFY_HINTS.get(canonical)
    assertions = _build_web_verification_assertions(
        click_action="snapshot-click-label",
        capture_label=clabel,
        hint_labels=hint_labels,
    )
    recipe = {
        "runner": "tv_web_inventory.py",
        "subcommand": "capture-after-actions",
        "url": page_url,
        "actions": [step],
        "capture_label": clabel,
        "verification": {
            "type": "web_inventory_capture",
            "post_capture_label": clabel,
            "assertions": assertions,
        },
    }
    return _with_web_recipe_execution_policy(recipe, profile="generic_click")


def _web_action_recipe_for_dom_control(
    ctrl: dict[str, Any], page: dict[str, Any], capture_label: str | None
) -> dict[str, Any] | None:
    raw_label = (
        ctrl.get("aria_label") or ctrl.get("title") or ctrl.get("text") or ctrl.get("data_name")
    )
    if not raw_label:
        return None
    role = str(ctrl.get("role") or "").strip().lower()
    tag = str(ctrl.get("tag") or "").strip().lower()
    role_for_click: str | None = None
    if role in INTERACTIVE_WEB_ROLES:
        role_for_click = role
    elif tag in INTERACTIVE_WEB_TAGS:
        role_for_click = "button" if tag == "button" else "link"
    else:
        return None
    return _web_click_recipe(
        label=str(raw_label),
        role=role_for_click,
        page_href=page.get("href"),
        capture_label=capture_label,
    )


def _web_action_recipe_for_snapshot_ref(
    ref: dict[str, Any], page: dict[str, Any], capture_label: str | None
) -> dict[str, Any] | None:
    raw_label = ref.get("label") or ref.get("role")
    if not raw_label:
        return None
    role = str(ref.get("role") or "").strip().lower()
    if role not in INTERACTIVE_WEB_ROLES:
        return None
    return _web_click_recipe(
        label=str(raw_label),
        role=role,
        page_href=page.get("href"),
        capture_label=capture_label,
    )


def _curated_web_flow_capabilities(capture: dict[str, Any]) -> list[dict[str, Any]]:
    page = capture.get("page") or {}
    page_href = str(page.get("href") or "https://www.tradingview.com/chart/")
    capture_label = str(capture.get("label") or "current-page")
    out: list[dict[str, Any]] = []

    def add(cap: dict[str, Any]) -> None:
        out.append(cap)

    def can_see_any(labels: list[str]) -> bool:
        return _capture_has_any_label(capture, labels)

    def recipe_click_one_of(
        *,
        labels: list[str],
        role: str | None,
        out_capture_label: str,
        verify_snapshot_any: list[str] | None = None,
        verify_capture_text_any: list[str] | None = None,
        verify_capture_text_appears_any: list[str] | None = None,
        escape_first: bool = False,
        policy_profile: str = "dialog_open",
    ) -> dict[str, Any]:
        step: dict[str, Any] = {
            "action": "snapshot-click-one-of",
            "labels": labels,
            "match": "contains",
            "wait_after": 0.4,
        }
        if role:
            step["role"] = role
        actions: list[dict[str, Any]] = []
        if escape_first:
            actions.append({"action": "press", "key": "Escape"})
            actions.append({"action": "wait", "seconds": 0.15})
        actions.append(step)
        recipe = {
            "runner": "tv_web_inventory.py",
            "subcommand": "capture-after-actions",
            "url": page_href,
            "actions": actions,
            "capture_label": out_capture_label,
            "verification": {
                "type": "web_inventory_capture",
                "post_capture_label": out_capture_label,
                "assertions": _build_web_verification_assertions(
                    click_action="snapshot-click-one-of",
                    capture_label=out_capture_label,
                    hint_labels=verify_snapshot_any,
                    appear_labels=verify_capture_text_appears_any,
                ),
            },
        }
        if verify_capture_text_any:
            assertions = (recipe.get("verification") or {}).get("assertions") or []
            assertions.append(
                {
                    "kind": "capture_text_any",
                    "values": [str(x) for x in verify_capture_text_any if str(x).strip()],
                    "match": "contains",
                }
            )
        return _with_web_recipe_execution_policy(recipe, profile=policy_profile)

    def recipe_indicators_search(*, click_result: bool) -> dict[str, Any]:
        actions: list[dict[str, Any]] = [
            {
                "action": "snapshot-click-one-of",
                "labels": ["Indicators, metrics, and strategies", "Indicators"],
                "match": "contains",
                "wait_after": 0.35,
            },
            {"action": "type", "text": "{{query}}"},
            {"action": "wait", "seconds": 0.4},
        ]
        click_action = "type"
        if click_result:
            actions.append(
                {
                    "action": "snapshot-click-label",
                    "label": "{{query}}",
                    "match": "contains",
                    "wait_after": 0.45,
                }
            )
            click_action = "snapshot-click-label"
        out_capture_label = (
            "indicators-dialog-search-and-select" if click_result else "indicators-dialog-search"
        )
        assertions = [
            {"kind": "plan_action_executed", "action": "snapshot-click-one-of", "min_count": 1},
            {"kind": "plan_action_executed", "action": "type", "min_count": 1},
            {"kind": "capture_label_equals", "value": out_capture_label},
            {
                "kind": "snapshot_label_any",
                "values": ["Indicators", "Strategies", "Profiles"],
                "match": "contains",
            },
            {"kind": "capture_text_any", "values": ["Strategies", "Profiles"], "match": "contains"},
        ]
        if click_result:
            assertions.append(
                {"kind": "plan_action_executed", "action": click_action, "min_count": 1}
            )
        else:
            # Query text often appears in the search field or result rows after typing.
            assertions.append(
                {"kind": "capture_text_any", "values": ["{{query}}"], "match": "contains"}
            )
        recipe = {
            "runner": "tv_web_inventory.py",
            "subcommand": "capture-after-actions",
            "url": page_href,
            "actions": actions,
            "capture_label": out_capture_label,
            "verification": {
                "type": "web_inventory_capture",
                "post_capture_label": out_capture_label,
                "assertions": assertions,
            },
            "parameters": [
                {
                    "name": "query",
                    "required": True,
                    "description": "Indicator query or exact indicator label to click",
                }
            ],
        }
        return _with_web_recipe_execution_policy(recipe, profile="search_dialog")

    def recipe_alert_fill_field(
        *,
        field_labels: list[str],
        param_name: str,
        out_capture_label: str,
        click_role: str | None = None,
    ) -> dict[str, Any]:
        assertions = [
            {"kind": "plan_action_executed", "action": "snapshot-click-one-of", "min_count": 2},
            {"kind": "plan_action_executed", "action": "type", "min_count": 1},
            {"kind": "capture_label_equals", "value": out_capture_label},
            {
                "kind": "snapshot_label_any",
                "values": ["Condition", "Notifications", "Create Alert"],
                "match": "contains",
            },
            {"kind": "capture_text_any", "values": [f"{{{{{param_name}}}}}"], "match": "contains"},
            {
                "kind": "capture_text_any",
                "values": ["Condition", "Notifications"],
                "match": "contains",
            },
        ]
        open_step = {
            "action": "snapshot-click-one-of",
            "labels": ["Create Alert", "Alert"],
            "role": "button",
            "match": "contains",
            "wait_after": 0.4,
        }
        field_step: dict[str, Any] = {
            "action": "snapshot-click-one-of",
            "labels": field_labels,
            "match": "contains",
            "wait_after": 0.2,
        }
        if click_role:
            field_step["role"] = click_role
        recipe = {
            "runner": "tv_web_inventory.py",
            "subcommand": "capture-after-actions",
            "url": page_href,
            "actions": [
                open_step,
                field_step,
                {"action": "type", "text": f"{{{{{param_name}}}}}"},
                {"action": "wait", "seconds": 0.35},
            ],
            "capture_label": out_capture_label,
            "verification": {
                "type": "web_inventory_capture",
                "post_capture_label": out_capture_label,
                "assertions": assertions,
            },
            "parameters": [
                {
                    "name": param_name,
                    "required": True,
                    "description": f"Value to type into alert {param_name.replace('_', ' ')} field",
                }
            ],
        }
        return _with_web_recipe_execution_policy(recipe, profile="alert_form")

    def recipe_layout_save_changes() -> dict[str, Any]:
        out_capture_label = "layout-manager-save"
        recipe = {
            "runner": "tv_web_inventory.py",
            "subcommand": "capture-after-actions",
            "url": page_href,
            "actions": [
                {
                    "action": "snapshot-click-one-of",
                    "labels": ["Manage layouts", "Layout setup"],
                    "role": "button",
                    "match": "contains",
                    "wait_after": 0.4,
                },
                {
                    "action": "snapshot-click-one-of",
                    "labels": [
                        "Save all charts for all symbols and intervals on your layout",
                        "Save all charts",
                        "Save",
                    ],
                    "match": "contains",
                    "wait_after": 0.35,
                },
            ],
            "capture_label": out_capture_label,
            "verification": {
                "type": "web_inventory_capture",
                "post_capture_label": out_capture_label,
                "assertions": [
                    {
                        "kind": "plan_action_executed",
                        "action": "snapshot-click-one-of",
                        "min_count": 2,
                    },
                    {"kind": "capture_label_equals", "value": out_capture_label},
                    {
                        "kind": "snapshot_label_any",
                        "values": ["Manage layouts", "Save all charts", "Layout setup"],
                        "match": "contains",
                    },
                ],
            },
        }
        return _with_web_recipe_execution_policy(recipe, profile="layout_flow")

    def recipe_open_layout_manager_panel() -> dict[str, Any]:
        out_capture_label = "layout-manager-menu"
        recipe = {
            "runner": "tv_web_inventory.py",
            "subcommand": "capture-after-actions",
            "url": page_href,
            "actions": [
                {"action": "press", "key": "Escape"},
                {"action": "wait", "seconds": 0.15},
                {
                    "label": "Manage layouts",
                    "action": "snapshot-click-label",
                    "role": "button",
                    "match": "contains",
                    "wait_after": 0.45,
                },
            ],
            "capture_label": out_capture_label,
            "verification": {
                "type": "web_inventory_capture",
                "post_capture_label": out_capture_label,
                "assertions": [
                    {
                        "kind": "plan_action_executed",
                        "action": "snapshot-click-label",
                        "min_count": 1,
                    },
                    {"kind": "capture_label_equals", "value": out_capture_label},
                    {
                        "kind": "snapshot_label_any",
                        "values": ["Save layout", "Create new layout", "Open layout"],
                        "match": "contains",
                    },
                    {
                        "kind": "capture_text_any",
                        "values": ["Save layout", "Create new layout", "Open layout"],
                        "match": "contains",
                    },
                ],
            },
        }
        return _with_web_recipe_execution_policy(recipe, profile="menu_open")

    def recipe_layout_search(*, click_result: bool) -> dict[str, Any]:
        actions: list[dict[str, Any]] = [
            {"action": "press", "key": "Escape"},
            {"action": "wait", "seconds": 0.15},
            {
                "action": "snapshot-click-label",
                "label": "Manage layouts",
                "role": "button",
                "match": "contains",
                "wait_after": 0.35,
            },
            {
                "action": "snapshot-click-one-of",
                "labels": ["Open layout…", "Open layout"],
                "match": "contains",
                "wait_after": 0.4,
            },
            {"action": "type", "text": "{{layout_name}}"},
            {"action": "wait", "seconds": 0.35},
        ]
        assertions = [
            {"kind": "plan_action_executed", "action": "snapshot-click-label", "min_count": 1},
            {"kind": "plan_action_executed", "action": "snapshot-click-one-of", "min_count": 1},
            {"kind": "plan_action_executed", "action": "type", "min_count": 1},
            {
                "kind": "snapshot_label_any",
                "values": ["Open layout", "Create new layout", "Save layout"],
                "match": "contains",
            },
            {
                "kind": "capture_label_equals",
                "value": "layout-manager-search" if not click_result else "layout-manager-select",
            },
            {"kind": "capture_text_any", "values": ["{{layout_name}}"], "match": "contains"},
        ]
        if click_result:
            actions.append(
                {
                    "action": "snapshot-click-label",
                    "label": "{{layout_name}}",
                    "match": "contains",
                    "wait_after": 0.45,
                }
            )
            assertions[0] = {
                "kind": "plan_action_executed",
                "action": "snapshot-click-one-of",
                "min_count": 1,
            }
            assertions.append(
                {"kind": "plan_action_executed", "action": "snapshot-click-label", "min_count": 1}
            )
            # Heuristic: after layout select, exact query text may no longer be visible.
            assertions = [
                a
                for a in assertions
                if not (isinstance(a, dict) and a.get("kind") == "capture_text_any")
            ]
            assertions.append(
                {"kind": "page_href_contains", "value": "/chart/", "match": "contains"}
            )
        recipe = {
            "runner": "tv_web_inventory.py",
            "subcommand": "capture-after-actions",
            "url": page_href,
            "actions": actions,
            "capture_label": "layout-manager-search"
            if not click_result
            else "layout-manager-select",
            "verification": {
                "type": "web_inventory_capture",
                "post_capture_label": "layout-manager-search"
                if not click_result
                else "layout-manager-select",
                "assertions": assertions,
            },
            "parameters": [
                {
                    "name": "layout_name",
                    "required": True,
                    "description": "Layout name/query to search (and optionally click)",
                }
            ],
        }
        return _with_web_recipe_execution_policy(recipe, profile="layout_flow")

    # Dialog openers (multi-step = click + post-capture verification)
    if can_see_any(["Indicators, metrics, and strategies", "Indicators"]):
        add(
            {
                "id": "web.flow.open_indicators_dialog",
                "label": "Open indicators dialog (web)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "low",
                "tags": ["web", "flow", "indicators", "dialog"],
                "preconditions": ["TradingView chart page loaded"],
                "action_recipe": recipe_click_one_of(
                    labels=["Indicators, metrics, and strategies", "Indicators"],
                    role=None,
                    out_capture_label="indicators-dialog",
                    verify_snapshot_any=["Indicators", "Strategies", "Profiles"],
                    verify_capture_text_appears_any=["Strategies", "Profiles"],
                    escape_first=True,
                ),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "open_dialog",
                },
            }
        )
        add(
            {
                "id": "web.flow.search_indicators_dialog",
                "label": "Search indicators dialog (web)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "low",
                "tags": ["web", "flow", "indicators", "search"],
                "preconditions": ["TradingView chart page loaded"],
                "action_recipe": recipe_indicators_search(click_result=False),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "search_dialog",
                },
            }
        )
        add(
            {
                "id": "web.flow.add_indicator_by_search_heuristic",
                "label": "Add indicator via web search (heuristic)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "low",
                "tags": ["web", "flow", "indicators", "search", "heuristic"],
                "preconditions": ["TradingView chart page loaded"],
                "action_recipe": recipe_indicators_search(click_result=True),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "search_and_click",
                    "notes": "Clicks the first snapshot label containing the query after typing; verify results before relying on unattended use.",
                },
            }
        )

    if can_see_any(["Create Alert", "Alert"]):
        add(
            {
                "id": "web.flow.open_create_alert_dialog",
                "label": "Open create alert dialog (web)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "low",
                "tags": ["web", "flow", "alerts", "dialog"],
                "preconditions": ["TradingView chart page loaded"],
                "action_recipe": recipe_click_one_of(
                    labels=["Create Alert", "Alert"],
                    role="button",
                    out_capture_label="create-alert-dialog",
                    verify_snapshot_any=["Condition", "Notifications", "Create Alert"],
                    verify_capture_text_appears_any=["Notifications"],
                    escape_first=True,
                ),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "open_dialog",
                },
            }
        )
        add(
            {
                "id": "web.flow.draft_alert_name_field_heuristic",
                "label": "Draft alert name field (web, heuristic)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "low",
                "tags": ["web", "flow", "alerts", "form", "heuristic"],
                "preconditions": ["TradingView chart page loaded"],
                "action_recipe": recipe_alert_fill_field(
                    field_labels=["Alert name", "Name", "Title"],
                    param_name="alert_name",
                    out_capture_label="create-alert-dialog-name-draft",
                ),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "alert_fill_field",
                    "notes": "Heuristic field targeting by visible label; verify before unattended use.",
                },
            }
        )
        add(
            {
                "id": "web.flow.draft_alert_message_field_heuristic",
                "label": "Draft alert message field (web, heuristic)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "low",
                "tags": ["web", "flow", "alerts", "form", "heuristic"],
                "preconditions": ["TradingView chart page loaded"],
                "action_recipe": recipe_alert_fill_field(
                    field_labels=["Message", "Message (optional)", "Notification message"],
                    param_name="message",
                    out_capture_label="create-alert-dialog-message-draft",
                ),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "alert_fill_field",
                    "notes": "Heuristic field targeting by visible label; verify before unattended use.",
                },
            }
        )

    if can_see_any(["Layout setup", "Manage layouts"]):
        add(
            {
                "id": "web.flow.open_layout_setup_menu",
                "label": "Open layout setup menu (web)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "low",
                "tags": ["web", "flow", "layout", "menu"],
                "preconditions": ["TradingView chart page loaded"],
                "action_recipe": recipe_click_one_of(
                    labels=["Layout setup"],
                    role="button",
                    out_capture_label="layout-setup",
                    verify_snapshot_any=[
                        "Sync in layout",
                        "changes on all charts within the layout",
                        "Crosshair is synced",
                    ],
                    verify_capture_text_any=[
                        "Sync in layout",
                        "changes on all charts within the layout",
                    ],
                    escape_first=True,
                    policy_profile="menu_open",
                ),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "open_menu",
                    "notes": "Opens the layout setup menu (not the deeper Manage layouts panel).",
                },
            }
        )
        add(
            {
                "id": "web.flow.open_layout_manager_menu",
                "label": "Open layout manager menu (web)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "low",
                "tags": ["web", "flow", "layout", "manager", "menu"],
                "preconditions": ["TradingView chart page loaded"],
                "action_recipe": recipe_open_layout_manager_panel(),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "open_menu",
                },
            }
        )
        add(
            {
                "id": "web.flow.save_layout_changes_heuristic",
                "label": "Save layout changes (web, heuristic)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "medium",
                "tags": ["web", "flow", "layout", "save", "heuristic"],
                "preconditions": ["TradingView chart page loaded"],
                "action_recipe": recipe_layout_save_changes(),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "layout_save",
                    "notes": "Heuristic click path that may overwrite current layout state.",
                },
            }
        )
        add(
            {
                "id": "web.flow.search_layout_manager",
                "label": "Search layout manager (web)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "low",
                "tags": ["web", "flow", "layout", "search"],
                "preconditions": ["TradingView chart page loaded"],
                "action_recipe": recipe_layout_search(click_result=False),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "layout_search",
                },
            }
        )
        add(
            {
                "id": "web.flow.select_layout_by_name_heuristic",
                "label": "Select layout by name (web, heuristic)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "medium",
                "tags": ["web", "flow", "layout", "select", "heuristic"],
                "preconditions": ["TradingView chart page loaded"],
                "action_recipe": recipe_layout_search(click_result=True),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "layout_select",
                    "notes": "Heuristic layout selection by visible label after typing the layout name.",
                },
            }
        )

    if can_see_any(["Settings"]):
        add(
            {
                "id": "web.flow.open_chart_settings",
                "label": "Open chart settings (web)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "low",
                "tags": ["web", "flow", "settings", "dialog"],
                "preconditions": ["TradingView chart page loaded"],
                "action_recipe": recipe_click_one_of(
                    labels=["Settings"],
                    role="button",
                    out_capture_label="chart-settings",
                    verify_snapshot_any=["Symbol", "Scales", "Status line"],
                    verify_capture_text_appears_any=["Scales", "Status line"],
                    escape_first=True,
                ),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "open_dialog",
                },
            }
        )

    if can_see_any(["Quick Search"]):
        add(
            {
                "id": "web.flow.open_quick_search",
                "label": "Open quick search (web)",
                "surface": "web",
                "source": "playwright-curated",
                "risk_level": "low",
                "tags": ["web", "flow", "search", "dialog"],
                "preconditions": ["TradingView chart page loaded"],
                # On slower Pi web runs, the "Quick Search" toolbar button can disappear from
                # the pre-click snapshot even though the keyboard shortcut remains reliable.
                "action_recipe": _with_web_recipe_execution_policy(
                    {
                        "runner": "tv_web_inventory.py",
                        "subcommand": "capture-after-actions",
                        "url": page_href,
                        "actions": [
                            {"action": "press", "key": "Escape"},
                            {"action": "wait", "seconds": 0.15},
                            {"action": "press", "key": "Control+K"},
                            {"action": "wait", "seconds": 0.5},
                        ],
                        "capture_label": "quick-search",
                        "verification": {
                            "type": "web_inventory_capture",
                            "post_capture_label": "quick-search",
                            "assertions": [
                                {"kind": "plan_action_executed", "action": "press", "min_count": 2},
                                {"kind": "capture_label_equals", "value": "quick-search"},
                                {
                                    "kind": "snapshot_label_any",
                                    "values": ["Quick Search", "Search tool or function", "Search"],
                                    "match": "contains",
                                },
                                {
                                    "kind": "capture_text_any",
                                    "values": [
                                        "Quick Search",
                                        "Search tool or function",
                                        "Type to search for drawings, functions and settings",
                                        "All sources",
                                        "Search",
                                    ],
                                    "match": "contains",
                                },
                            ],
                        },
                    },
                    profile="dialog_open",
                ),
                "metadata": {
                    "capture_label": capture_label,
                    "page_href": page_href,
                    "flow_kind": "open_dialog",
                },
            }
        )

    return out


def build_web_capability_candidates(
    capture: dict[str, Any], max_caps: int = 300
) -> list[dict[str, Any]]:
    caps: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(cap: dict[str, Any]) -> None:
        cid = cap["id"]
        if cid in seen:
            return
        seen.add(cid)
        caps.append(cap)

    capture_label = capture.get("label")
    page = capture.get("page") or {}
    for curated in _curated_web_flow_capabilities(capture):
        add(curated)
        if len(caps) >= max_caps:
            return caps

    for ctrl in capture.get("dom_controls", []) or []:
        label = (
            ctrl.get("aria_label")
            or ctrl.get("title")
            or ctrl.get("text")
            or ctrl.get("data_name")
            or ctrl.get("role")
        )
        if not label:
            continue
        tag = ctrl.get("tag") or "node"
        role = ctrl.get("role") or tag
        cid = f"web.visible.{slugify(str(label))}.{slugify(str(role))}"
        add(
            {
                "id": cid,
                "label": str(label),
                "surface": "web",
                "source": "playwright-dom",
                "risk_level": infer_risk(str(label)),
                **(
                    {"action_recipe": recipe}
                    if (recipe := _web_action_recipe_for_dom_control(ctrl, page, capture_label))
                    else {}
                ),
                "metadata": {
                    "tag": tag,
                    "role": role,
                    "data_name": ctrl.get("data_name"),
                    "data_role": ctrl.get("data_role"),
                    "aria_keyshortcuts": ctrl.get("aria_keyshortcuts"),
                    "rect": ctrl.get("rect"),
                    "capture_label": capture_label,
                    "page_href": page.get("href"),
                    "page_title": page.get("title"),
                },
            }
        )
        if len(caps) >= max_caps:
            break

    # Add snapshot refs as alternate handles (useful for click automation sessions)
    for ref in capture.get("snapshot_refs", []) or []:
        label = ref.get("label") or ref.get("role")
        if not label:
            continue
        cid = f"web.snapshot.{ref.get('ref')}"
        add(
            {
                "id": cid,
                "label": str(label),
                "surface": "web_snapshot",
                "source": "playwright-snapshot",
                "risk_level": infer_risk(str(label)),
                **(
                    {"action_recipe": recipe}
                    if (recipe := _web_action_recipe_for_snapshot_ref(ref, page, capture_label))
                    else {}
                ),
                "metadata": {
                    "ref": ref.get("ref"),
                    "role": ref.get("role"),
                    "label": ref.get("label"),
                    "attrs": ref.get("attrs"),
                    "capture_label": capture_label,
                    "page_href": page.get("href"),
                    "page_title": page.get("title"),
                },
            }
        )
        if len(caps) >= max_caps:
            break

    return caps


def run_action_plan(pwcli: Path, session: str, cwd: Path, plan_path: Path) -> list[dict[str, Any]]:
    plan = json.loads(plan_path.read_text())
    if not isinstance(plan, list):
        raise ValueError("actions file must be a JSON list")
    executed: list[dict[str, Any]] = []
    for idx, step in enumerate(plan, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"plan step {idx} must be an object")
        action = str(step.get("action", "")).strip()
        if not action:
            raise ValueError(f"plan step {idx} missing action")
        rec: dict[str, Any] = {"index": idx, "action": action}
        if action == "wait":
            seconds = float(step.get("seconds", 0))
            time.sleep(max(0.0, seconds))
            rec["seconds"] = seconds
        elif action == "press":
            key = str(step["key"])
            run_pw(pwcli, session, ["press", key], cwd)
            rec["key"] = key
        elif action == "click":
            ref = str(step["ref"])
            run_pw(pwcli, session, ["click", ref], cwd)
            rec["ref"] = ref
        elif action == "type":
            text = str(step["text"])
            run_pw(pwcli, session, ["type", text], cwd)
            rec["text"] = text
        elif action == "open":
            url = str(step["url"])
            cmd = ["open", url]
            if step.get("headed"):
                cmd.append("--headed")
            run_pw(pwcli, session, cmd, cwd)
            rec["url"] = url
        elif action == "snapshot":
            out, snap_path, refs = snapshot_with_refs(pwcli, session, cwd)
            rec["snapshot_output"] = out
            rec["snapshot_path"] = str(snap_path) if snap_path else None
            rec["ref_count"] = len(refs)
            if step.get("label"):
                rec["label"] = str(step["label"])
        elif action == "snapshot-click-label":
            label = str(step["label"])
            role = str(step["role"]) if step.get("role") else None
            match = str(step.get("match", "contains"))
            case_sensitive = bool(step.get("case_sensitive", False))
            out, snap_path, refs = snapshot_with_refs(pwcli, session, cwd)
            hit = find_snapshot_ref_by_label(
                refs,
                label=label,
                role=role,
                match=match,
                case_sensitive=case_sensitive,
            )
            role_fallback_used = False
            if not hit and role:
                hit = find_snapshot_ref_by_label(
                    refs,
                    label=label,
                    role=None,
                    match=match,
                    case_sensitive=case_sensitive,
                )
                role_fallback_used = hit is not None
            if not hit:
                raise ValueError(
                    f"snapshot-click-label could not find label={label!r}"
                    + (f" role={role!r}" if role else "")
                )
            run_pw(pwcli, session, ["click", str(hit["ref"])], cwd)
            rec["label"] = label
            rec["chosen_ref"] = hit["ref"]
            rec["chosen_role"] = hit.get("role")
            rec["snapshot_path"] = str(snap_path)
            rec["ref_count"] = len(refs)
            rec["match"] = match
            if role:
                rec["role"] = role
            if role_fallback_used:
                rec["role_fallback_used"] = True
            wait_after = float(step.get("wait_after", 0))
            if wait_after > 0:
                time.sleep(wait_after)
                rec["wait_after"] = wait_after
        elif action == "snapshot-click-one-of":
            labels = step.get("labels")
            if not isinstance(labels, list) or not labels:
                raise ValueError("snapshot-click-one-of requires non-empty 'labels' list")
            labels = [str(x) for x in labels]
            role = str(step["role"]) if step.get("role") else None
            match = str(step.get("match", "contains"))
            case_sensitive = bool(step.get("case_sensitive", False))
            out, snap_path, refs = snapshot_with_refs(pwcli, session, cwd)
            hit = find_snapshot_ref_by_any_label(
                refs,
                labels,
                role=role,
                match=match,
                case_sensitive=case_sensitive,
            )
            role_fallback_used = False
            if not hit and role:
                hit = find_snapshot_ref_by_any_label(
                    refs,
                    labels,
                    role=None,
                    match=match,
                    case_sensitive=case_sensitive,
                )
                role_fallback_used = hit is not None
            if not hit:
                raise ValueError(
                    f"snapshot-click-one-of could not find any labels={labels!r}"
                    + (f" role={role!r}" if role else "")
                )
            chosen, matched_label = hit
            run_pw(pwcli, session, ["click", str(chosen["ref"])], cwd)
            rec["labels"] = labels
            rec["matched_label"] = matched_label
            rec["chosen_ref"] = chosen["ref"]
            rec["chosen_role"] = chosen.get("role")
            rec["snapshot_path"] = str(snap_path)
            rec["ref_count"] = len(refs)
            rec["match"] = match
            if role:
                rec["role"] = role
            if role_fallback_used:
                rec["role_fallback_used"] = True
            wait_after = float(step.get("wait_after", 0))
            if wait_after > 0:
                time.sleep(wait_after)
                rec["wait_after"] = wait_after
        elif action == "eval":
            js = str(step["js"])
            out = run_pw(pwcli, session, ["eval", js], cwd)
            rec["result"] = parse_eval_json_output(out)
        else:
            raise ValueError(f"Unsupported plan action: {action}")
        executed.append(rec)
    return executed


def capture_web_inventory(
    pwcli: Path,
    session: str,
    cwd: Path,
    *,
    url: str | None,
    headed: bool,
    dom_limit: int,
    data_limit: int,
    snapshot_ref_limit: int,
    actions_file: Path | None,
    capture_label: str,
    close_when_done: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": 1,
        "generator": "tv_web_inventory.py",
        "session": session,
        "cwd": str(cwd),
        "captures": [],
    }

    if url:
        cmd = ["open", url]
        if headed:
            cmd.append("--headed")
        open_out = run_pw(pwcli, session, cmd, cwd)
        result["open"] = {"url": url, "headed": headed, "output": open_out}

    if actions_file:
        result["plan_execution"] = run_action_plan(pwcli, session, cwd, actions_file)

    snapshot_output, snapshot_path, snapshot_refs = snapshot_with_refs(
        pwcli, session, cwd, max_refs=snapshot_ref_limit
    )

    page_info = pw_eval_json(pwcli, session, cwd, js_page_info())
    dom_controls = pw_eval_json(pwcli, session, cwd, js_dom_controls(dom_limit))
    data_named = pw_eval_json(pwcli, session, cwd, js_data_attributes(data_limit))

    capture = {
        "label": capture_label or "current-page",
        "page": page_info,
        "snapshot": {
            "artifact": str(snapshot_path),
            "output": snapshot_output,
            "ref_count": len(snapshot_refs),
        },
        "snapshot_refs": snapshot_refs,
        "dom_controls": dom_controls,
        "data_attribute_nodes": data_named,
    }
    capture["capability_candidates"] = build_web_capability_candidates(capture)
    result["captures"].append(capture)

    # Flatten top-level capability list for convenience.
    all_caps: list[dict[str, Any]] = []
    for c in result["captures"]:
        all_caps.extend(c.get("capability_candidates", []) or [])
    result["capabilities"] = all_caps

    if close_when_done:
        try:
            run_pw(pwcli, session, ["close"], cwd)
            result["closed"] = True
        except Exception as e:  # noqa: BLE001
            result["close_error"] = str(e)
    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description="Enumerate visible TradingView Web controls/capabilities via Playwright CLI"
    )
    p.add_argument(
        "--pwcli", type=Path, default=PWCLI_DEFAULT, help="Path to playwright_cli.sh wrapper"
    )
    p.add_argument("--session", default="tv-web-inventory")
    p.add_argument(
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="Working directory for .playwright-cli artifacts",
    )
    p.add_argument(
        "--url", default=None, help="Open this URL first (e.g. https://www.tradingview.com/chart/)"
    )
    p.add_argument("--headed", action="store_true", help="Open browser in headed mode")
    p.add_argument(
        "--actions-file",
        type=Path,
        default=None,
        help="Optional JSON action plan to run before final capture",
    )
    p.add_argument(
        "--capture-label", default="current-page", help="Context label stored in the output capture"
    )
    p.add_argument("--dom-limit", type=int, default=800)
    p.add_argument("--data-limit", type=int, default=1500)
    p.add_argument("--snapshot-ref-limit", type=int, default=4000)
    p.add_argument("--output", type=Path, default=None, help="Write JSON output file")
    p.add_argument("--write-default-output", action="store_true", help=f"Write to {DEFAULT_OUTPUT}")
    p.add_argument(
        "--no-close", action="store_true", help="Leave the Playwright session/browser open"
    )
    p.add_argument("--pretty", action="store_true")
    args = p.parse_args()

    pwcli = args.pwcli
    if not pwcli.exists():
        print(f"Playwright wrapper not found: {pwcli}", file=sys.stderr)
        return 2

    out_path = args.output or (DEFAULT_OUTPUT if args.write_default_output else None)
    try:
        data = capture_web_inventory(
            pwcli=pwcli,
            session=args.session,
            cwd=args.cwd,
            url=args.url,
            headed=args.headed,
            dom_limit=max(1, args.dom_limit),
            data_limit=max(1, args.data_limit),
            snapshot_ref_limit=max(1, args.snapshot_ref_limit),
            actions_file=args.actions_file,
            capture_label=str(args.capture_label or "current-page"),
            close_when_done=not args.no_close,
        )
    except Exception as e:  # noqa: BLE001
        print(str(e), file=sys.stderr)
        return 1

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, indent=2) + "\n")
        summary = {
            "output": str(out_path),
            "session": data.get("session"),
            "capture_count": len(data.get("captures", [])),
            "capability_count": len(data.get("capabilities", [])),
            "page": (data.get("captures") or [{}])[0].get("page"),
        }
        print(json.dumps(summary, indent=2))
    else:
        print(json.dumps(data, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
