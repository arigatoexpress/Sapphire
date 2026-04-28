#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import tvctl

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = SKILL_ROOT / "config" / "layouts" / "aribs-main.json"
DEFAULT_REGISTRY_OUT = SKILL_ROOT / "references" / "examples" / "capability-registry.seed.json"

SEP = "\x1f"


def _normalize_missing(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip()
    if not v or v == "missing value":
        return None
    return v


def _boolish(value: str | None) -> bool | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v == "true":
        return True
    if v == "false":
        return False
    return None


def _apple_quote(text: str) -> str:
    return tvctl.applescript_quote(text)


def _menu_expr(top_menu: str, parent_chain: list[str]) -> str:
    expr = f"menu {_apple_quote(top_menu)} of menu bar item {_apple_quote(top_menu)} of menu bar 1"
    for name in parent_chain:
        expr = f"menu 1 of menu item {_apple_quote(name)} of {expr}"
    return expr


def list_menu_items(top_menu: str, parent_chain: list[str]) -> list[dict[str, Any]]:
    menu_expr = _menu_expr(top_menu, parent_chain)
    out = tvctl.run_osascript(
        [
            'tell application "System Events"',
            f'  tell process "{tvctl.PROCESS_NAME}"',
            f"    set m to {menu_expr}",
            "    set sep to ASCII character 31",
            '    set outText to ""',
            "    repeat with i from 1 to (count of menu items of m)",
            "      set mi to menu item i of m",
            "      try",
            "        set n to name of mi as text",
            "      on error",
            '        set n to ""',
            "      end try",
            "      try",
            "        set en to enabled of mi as text",
            "      on error",
            '        set en to ""',
            "      end try",
            "      try",
            "        set hs to (exists menu 1 of mi) as text",
            "      on error",
            '        set hs to "false"',
            "      end try",
            "      try",
            '        set c to value of attribute "AXMenuItemCmdChar" of mi as text',
            "      on error",
            '        set c to ""',
            "      end try",
            "      try",
            '        set mods to value of attribute "AXMenuItemCmdModifiers" of mi as text',
            "      on error",
            '        set mods to ""',
            "      end try",
            "      try",
            '        set glyph to value of attribute "AXMenuItemCmdGlyph" of mi as text',
            "      on error",
            '        set glyph to ""',
            "      end try",
            "      try",
            '        set markChar to value of attribute "AXMenuItemMarkChar" of mi as text',
            "      on error",
            '        set markChar to ""',
            "      end try",
            "      set outText to outText & (i as text) & sep & n & sep & en & sep & hs & sep & c & sep & mods & sep & glyph & sep & markChar & linefeed",
            "    end repeat",
            "    return outText",
            "  end tell",
            "end tell",
        ]
    )
    items: list[dict[str, Any]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split(SEP)
        while len(parts) < 8:
            parts.append("")
        idx_s, name_s, en_s, hs_s, char_s, mods_s, glyph_s, mark_s = parts[:8]
        name = _normalize_missing(name_s)
        item = {
            "index": int(idx_s),
            "name": name,
            "separator": name is None,
            "enabled": _boolish(en_s),
            "has_submenu": _boolish(hs_s) or False,
            "shortcut": {
                "cmd_char": _normalize_missing(char_s),
                "cmd_modifiers_raw": _normalize_missing(mods_s),
                "cmd_glyph": _normalize_missing(glyph_s),
                "mark_char": _normalize_missing(mark_s),
            },
        }
        # Drop empty shortcut object for readability.
        if not any(item["shortcut"].values()):
            item.pop("shortcut")
        items.append(item)
    return items


def enumerate_menu_tree(top_menu: str, max_depth: int = 6) -> dict[str, Any]:
    seen_paths: set[tuple[str, ...]] = set()

    def rec(parent_chain: list[str], depth: int) -> list[dict[str, Any]]:
        entries = list_menu_items(top_menu, parent_chain)
        out_items: list[dict[str, Any]] = []
        name_counts: dict[str, int] = {}
        for item in entries:
            name = item.get("name")
            if name:
                name_counts[name] = name_counts.get(name, 0) + 1
            rec_item = dict(item)
            rec_item["path"] = [top_menu] + parent_chain + ([name] if name else [])
            if name:
                dup_n = name_counts[name]
                if dup_n > 1:
                    rec_item["sibling_occurrence"] = dup_n
            can_descend = bool(name) and bool(item.get("has_submenu")) and depth < max_depth
            if can_descend:
                next_path = tuple([top_menu] + parent_chain + [name])
                if next_path not in seen_paths:
                    seen_paths.add(next_path)
                    try:
                        rec_item["children"] = rec(parent_chain + [name], depth + 1)
                    except Exception as e:  # noqa: BLE001
                        rec_item["children_error"] = str(e)
            out_items.append(rec_item)
        return out_items

    return {
        "menu": top_menu,
        "items": rec([], 1),
    }


def menu_path_to_expr(path: list[str]) -> str | None:
    # path includes top menu as first segment and leaf item as last.
    if len(path) < 2:
        return None
    return " > ".join(path)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "item"


def infer_risk(label: str) -> str:
    t = label.lower()
    if any(k in t for k in ["buy", "sell", "trade", "order", "broker", "execute", "cancel order"]):
        return "high"
    if any(k in t for k in ["delete", "remove", "overwrite", "close", "reset", "clear", "logout"]):
        return "medium"
    return "low"


def flatten_menu_leaves(tree: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def rec(items: list[dict[str, Any]]) -> None:
        for item in items:
            children = item.get("children")
            if children:
                rec(children)
            else:
                out.append(item)

    rec(tree.get("items", []))
    return out


def build_capability_candidates(
    desktop_inventory: dict[str, Any], config_data: dict[str, Any] | None
) -> list[dict[str, Any]]:
    caps: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(cap: dict[str, Any]) -> None:
        cid = cap["id"]
        if cid in seen:
            return
        seen.add(cid)
        caps.append(cap)

    # Built-in tvctl capabilities (stable, curated)
    curated = [
        (
            "chart.set_symbol",
            "Set chart symbol",
            ["chart", "search"],
            "low",
            ["chart visible"],
            {
                "runner": "tvctl.py",
                "subcommand": "set-symbol",
                "args_template": ["{{symbol}}"],
                "timeouts": {"command_timeout_seconds": 45},
                "parameters": [
                    {"name": "symbol", "required": True, "description": "Ticker/symbol to open"}
                ],
            },
        ),
        (
            "chart.add_indicator",
            "Add indicator",
            ["chart", "indicator"],
            "low",
            ["chart visible"],
            {
                "runner": "tvctl.py",
                "subcommand": "add-indicator",
                "args_template": ["{{query}}"],
                "timeouts": {"command_timeout_seconds": 60},
                "parameters": [
                    {"name": "query", "required": True, "description": "Indicator search query"}
                ],
            },
        ),
        (
            "watchlist.open_symbol",
            "Open symbol via watchlist",
            ["watchlist"],
            "low",
            ["watchlist calibrated"],
            None,
        ),
        (
            "watchlist.add_symbol",
            "Add symbol to watchlist",
            ["watchlist"],
            "low",
            ["watchlist calibrated"],
            None,
        ),
        (
            "watchlist.remove_row",
            "Remove watchlist row",
            ["watchlist"],
            "medium",
            ["watchlist calibrated"],
            None,
        ),
        (
            "watchlist.reorder_rows",
            "Reorder watchlist rows",
            ["watchlist"],
            "low",
            ["watchlist calibrated"],
            None,
        ),
    ]
    for cid, label, tags, risk, preconds, action_recipe in curated:
        cap = {
            "id": cid,
            "label": label,
            "surface": "desktop",
            "source": "tvctl",
            "risk_level": risk,
            "tags": tags,
            "preconditions": preconds,
        }
        if action_recipe:
            cap["action_recipe"] = action_recipe
        add(cap)

    # Desktop menu leaves -> click-menu capabilities.
    for menu_tree in desktop_inventory.get("menus", []):
        for leaf in flatten_menu_leaves(menu_tree):
            if leaf.get("separator"):
                continue
            if not leaf.get("name"):
                continue
            path = leaf.get("path") or []
            path_expr = menu_path_to_expr(path)
            if not path_expr:
                continue
            label = path_expr
            add(
                {
                    "id": f"desktop.menu.{slugify(path_expr)}",
                    "label": label,
                    "surface": "desktop_menu",
                    "source": "macos-ax-menu",
                    "risk_level": infer_risk(label),
                    "enabled": leaf.get("enabled"),
                    "action_recipe": {
                        "runner": "tvctl.py",
                        "subcommand": "click-menu",
                        "args": [path_expr],
                        "timeouts": {"command_timeout_seconds": 30},
                    },
                    "metadata": {
                        "menu_path": path,
                        "shortcut": leaf.get("shortcut"),
                    },
                }
            )

    # Config-backed actions become fully parameterized capabilities (templates).
    if config_data:
        cfg_path = str(config_data.get("_config_path", "config/layouts/<layout>.json"))
        shortcuts = config_data.get("shortcuts", {}) or {}
        wl = config_data.get("watchlist", {}) or {}
        if shortcuts.get("symbol_search"):
            add(
                {
                    "id": "desktop.shortcut.symbol_search",
                    "label": "Symbol search shortcut",
                    "surface": "desktop_shortcut",
                    "source": "layout-config",
                    "risk_level": "low",
                    "metadata": {"combo": shortcuts.get("symbol_search")},
                }
            )
        if shortcuts.get("indicator_search"):
            add(
                {
                    "id": "desktop.shortcut.indicator_search",
                    "label": "Indicator search shortcut",
                    "surface": "desktop_shortcut",
                    "source": "layout-config",
                    "risk_level": "low",
                    "metadata": {"combo": shortcuts.get("indicator_search")},
                }
            )
        for cid, label, subcommand, risk in [
            (
                "watchlist.open_symbol.config",
                "Open symbol via calibrated watchlist",
                "watchlist-open-config",
                "low",
            ),
            (
                "watchlist.add_symbol.config",
                "Add symbol via calibrated watchlist",
                "watchlist-add-config",
                "low",
            ),
            (
                "watchlist.remove_row.config",
                "Remove watchlist row via calibrated points",
                "watchlist-remove-config",
                "medium",
            ),
            (
                "watchlist.reorder_rows.config",
                "Reorder watchlist rows via calibrated points",
                "watchlist-reorder-config",
                "low",
            ),
        ]:
            args_template: list[Any] = [cfg_path]
            parameters: list[dict[str, Any]] = []
            if subcommand in {"watchlist-open-config", "watchlist-add-config"}:
                args_template.append("{{symbol}}")
                parameters.append(
                    {
                        "name": "symbol",
                        "required": True,
                        "description": "Symbol to open/add in the watchlist",
                    }
                )
            add(
                {
                    "id": cid,
                    "label": label,
                    "surface": "desktop",
                    "source": "layout-config",
                    "risk_level": risk,
                    "preconditions": [
                        "TradingView desktop app running",
                        "watchlist points calibrated",
                    ],
                    "action_recipe": {
                        "runner": "tvctl.py",
                        "subcommand": subcommand,
                        "args_template": args_template,
                        "timeouts": {
                            "command_timeout_seconds": 60
                            if subcommand in {"watchlist-remove-config", "watchlist-reorder-config"}
                            else 45
                        },
                        "parameters": parameters,
                    },
                    "metadata": {
                        "watchlist_bindings": {
                            "search_field_point": wl.get("search_field_point"),
                            "add_button_point": wl.get("add_button_point"),
                            "remove_menu_item_point": wl.get("remove_menu_item_point"),
                            "row_points": wl.get("row_points"),
                        }
                    },
                }
            )

    return caps


def build_registry_seed(inventory: dict[str, Any]) -> dict[str, Any]:
    caps = build_capability_candidates(inventory.get("desktop", {}), inventory.get("config"))
    return {
        "schema_version": 1,
        "generated_at": inventory.get("generated_at"),
        "generator": "tv_inventory.py",
        "workspace": str(SKILL_ROOT),
        "capabilities": caps,
    }


def load_config_if_present(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    if not path.exists():
        return {"_config_path": str(path), "missing": True}
    cfg = tvctl.load_config(path)
    cfg["_config_path"] = str(path)
    return cfg


def export_inventory(
    config_path: Path | None, include_menus: bool, menu_max_depth: int, activate: bool
) -> dict[str, Any]:
    if activate:
        with contextlib.suppress(Exception):
            tvctl.activate_app(launch=False, delay=0.2)

    out: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": tvctl.now_iso(),
        "desktop": {},
        "config": load_config_if_present(config_path),
    }

    try:
        out["desktop"]["status"] = tvctl.status()
    except Exception as e:  # noqa: BLE001
        out["desktop"]["status_error"] = str(e)

    if include_menus:
        menus: list[dict[str, Any]] = []
        menu_errors: list[dict[str, Any]] = []
        try:
            top_menus = [m for m in tvctl.list_menus() if m and m != "Apple"]
            out["desktop"]["top_menus"] = top_menus
            for menu in top_menus:
                try:
                    menus.append(enumerate_menu_tree(menu, max_depth=menu_max_depth))
                except Exception as e:  # noqa: BLE001
                    menu_errors.append({"menu": menu, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            out["desktop"]["menu_discovery_error"] = str(e)
        out["desktop"]["menus"] = menus
        if menu_errors:
            out["desktop"]["menu_errors"] = menu_errors

    out["registry_seed"] = build_registry_seed(out)
    return out


def main() -> int:
    p = argparse.ArgumentParser(
        description="Export TradingView desktop/config inventory and seed capability registry"
    )
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Layout config JSON path")
    p.add_argument("--no-config", action="store_true", help="Skip loading a layout config")
    p.add_argument(
        "--no-menus", action="store_true", help="Skip recursive desktop menu enumeration"
    )
    p.add_argument("--menu-max-depth", type=int, default=5)
    p.add_argument(
        "--no-activate",
        action="store_true",
        help="Do not bring TradingView to front before inspection",
    )
    p.add_argument("--output", type=Path, default=None, help="Write full inventory JSON to a file")
    p.add_argument(
        "--registry-output",
        type=Path,
        default=None,
        help="Write registry seed JSON (defaults to references/examples/capability-registry.seed.json when --write-default-registry is set)",
    )
    p.add_argument(
        "--write-default-registry",
        action="store_true",
        help="Write registry seed to the skill example path",
    )
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output to stdout")
    args = p.parse_args()

    config_path = None if args.no_config else args.config
    try:
        inv = export_inventory(
            config_path=config_path,
            include_menus=not args.no_menus,
            menu_max_depth=max(1, args.menu_max_depth),
            activate=not args.no_activate,
        )
    except Exception as e:  # noqa: BLE001
        print(str(e), file=sys.stderr)
        return 1

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(inv, indent=2) + "\n")

    reg_path: Path | None = args.registry_output
    if args.write_default_registry and reg_path is None:
        reg_path = DEFAULT_REGISTRY_OUT
    if reg_path:
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text(json.dumps(inv["registry_seed"], indent=2) + "\n")

    text = json.dumps(inv, indent=2 if args.pretty or not args.output else None)
    if args.output:
        # Keep stdout shorter if inventory was written to disk.
        summary = {
            "generated_at": inv.get("generated_at"),
            "output": str(args.output),
            "registry_output": str(reg_path) if reg_path else None,
            "desktop_top_menus": inv.get("desktop", {}).get("top_menus"),
            "capability_count": len(inv.get("registry_seed", {}).get("capabilities", [])),
        }
        print(json.dumps(summary, indent=2))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
