#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

APP_NAME = "TradingView"
PROCESS_NAME = "TradingView"

SPECIAL_KEYS = {
    "return": 36,
    "enter": 36,
    "tab": 48,
    "space": 49,
    "backspace": 51,
    "delete": 51,
    "esc": 53,
    "escape": 53,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
    "home": 115,
    "end": 119,
    "pageup": 116,
    "pagedown": 121,
    "forwarddelete": 117,
}

MODIFIER_ALIASES = {
    "cmd": "command",
    "command": "command",
    "ctrl": "control",
    "control": "control",
    "opt": "option",
    "option": "option",
    "alt": "option",
    "shift": "shift",
}

MODIFIER_ORDER = ["command", "control", "option", "shift"]

# CoreGraphics constants (Quartz Event Services)
KCG_HID_EVENT_TAP = 0
KCG_EVENT_LEFT_MOUSE_DOWN = 1
KCG_EVENT_LEFT_MOUSE_UP = 2
KCG_EVENT_RIGHT_MOUSE_DOWN = 3
KCG_EVENT_RIGHT_MOUSE_UP = 4
KCG_EVENT_MOUSE_MOVED = 5
KCG_EVENT_LEFT_MOUSE_DRAGGED = 6
KCG_EVENT_RIGHT_MOUSE_DRAGGED = 7
KCG_MOUSE_BUTTON_LEFT = 0
KCG_MOUSE_BUTTON_RIGHT = 1
KCG_MOUSE_BUTTON_CENTER = 2


class OsaScriptError(RuntimeError):
    pass


class CoreGraphicsError(RuntimeError):
    pass


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CoreGraphics:
    def __init__(self) -> None:
        path = ctypes.util.find_library("ApplicationServices")
        if not path:
            raise CoreGraphicsError("ApplicationServices framework not found")
        self.lib = ctypes.CDLL(path)

        self.lib.CGEventCreateMouseEvent.restype = ctypes.c_void_p
        self.lib.CGEventCreateMouseEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            CGPoint,
            ctypes.c_uint32,
        ]
        self.lib.CGEventPost.restype = None
        self.lib.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        self.lib.CFRelease.restype = None
        self.lib.CFRelease.argtypes = [ctypes.c_void_p]
        self.lib.CGEventCreate.restype = ctypes.c_void_p
        self.lib.CGEventCreate.argtypes = [ctypes.c_void_p]
        self.lib.CGEventGetLocation.restype = CGPoint
        self.lib.CGEventGetLocation.argtypes = [ctypes.c_void_p]

    def post_mouse_event(self, event_type: int, x: float, y: float, button: int) -> None:
        ev = self.lib.CGEventCreateMouseEvent(None, event_type, CGPoint(float(x), float(y)), button)
        if not ev:
            raise CoreGraphicsError("Failed to create mouse event")
        try:
            self.lib.CGEventPost(KCG_HID_EVENT_TAP, ev)
        finally:
            self.lib.CFRelease(ev)

    def mouse_location(self) -> tuple[float, float]:
        ev = self.lib.CGEventCreate(None)
        if not ev:
            raise CoreGraphicsError("Failed to read mouse location")
        try:
            p = self.lib.CGEventGetLocation(ev)
            return float(p.x), float(p.y)
        finally:
            self.lib.CFRelease(ev)


_CG: _CoreGraphics | None = None


def cg() -> _CoreGraphics:
    global _CG
    if _CG is None:
        _CG = _CoreGraphics()
    return _CG


def applescript_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def run_osascript(lines: list[str]) -> str:
    cmd = ["osascript"]
    for line in lines:
        cmd.extend(["-e", line])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "osascript failed").strip()
        raise OsaScriptError(err)
    return (proc.stdout or "").strip()


def is_running() -> bool:
    proc = subprocess.run(["pgrep", "-x", PROCESS_NAME], capture_output=True, text=True)
    return proc.returncode == 0


def normalize_modifiers(mods: list[str] | None) -> list[str]:
    if not mods:
        return []
    norm: list[str] = []
    for raw in mods:
        for part in str(raw).split(","):
            part = part.strip().lower()
            if not part:
                continue
            mapped = MODIFIER_ALIASES.get(part)
            if not mapped:
                raise ValueError(f"Unsupported modifier: {raw}")
            if mapped not in norm:
                norm.append(mapped)
    return [m for m in MODIFIER_ORDER if m in norm]


def parse_combo(combo: str) -> tuple[str, list[str]]:
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError("Empty hotkey combo")
    key = parts[-1]
    mods = normalize_modifiers(parts[:-1])
    return key, mods


def using_clause(mods: list[str]) -> str:
    if not mods:
        return ""
    return " using {" + ", ".join(f"{m} down" for m in mods) + "}"


def activate_app(launch: bool = False, delay: float = 0.25) -> None:
    if launch and not is_running():
        subprocess.run(["open", "-a", APP_NAME], check=False)
        time.sleep(0.5)
    run_osascript([f'tell application "{APP_NAME}" to activate'])
    try:
        run_osascript(
            [
                'tell application "System Events"',
                f'  tell process "{PROCESS_NAME}"',
                "    set frontmost to true",
                "  end tell",
                "end tell",
            ]
        )
    except OsaScriptError:
        pass
    if delay > 0:
        time.sleep(delay)


def list_menus() -> list[str]:
    out = run_osascript(
        [
            'tell application "System Events"',
            f'  tell process "{PROCESS_NAME}"',
            "    set namesList to name of menu bar items of menu bar 1",
            '    set AppleScript\'s text item delimiters to linefeed',
            "    return namesList as text",
            "  end tell",
            "end tell",
        ]
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def window_titles() -> list[str]:
    out = run_osascript(
        [
            'tell application "System Events"',
            f'  tell process "{PROCESS_NAME}"',
            "    set winCount to count of windows",
            "    if winCount is 0 then return \"\"",
            "    set namesList to name of windows",
            '    set AppleScript\'s text item delimiters to linefeed',
            "    return namesList as text",
            "  end tell",
            "end tell",
        ]
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def front_window_bounds() -> dict[str, int]:
    out = run_osascript(
        [
            'tell application "System Events"',
            f'  tell process "{PROCESS_NAME}"',
            "    if (count of windows) is 0 then error \"No TradingView window\"",
            "    set p to position of front window",
            "    set s to size of front window",
            "    return ((item 1 of p) as text) & \",\" & ((item 2 of p) as text) & \",\" & ((item 1 of s) as text) & \",\" & ((item 2 of s) as text)",
            "  end tell",
            "end tell",
        ]
    )
    x_str, y_str, w_str, h_str = [part.strip() for part in out.split(",", 3)]
    return {"x": int(float(x_str)), "y": int(float(y_str)), "width": int(float(w_str)), "height": int(float(h_str))}


def app_frontmost() -> bool:
    out = run_osascript(
        [
            'tell application "System Events"',
            f'  tell process "{PROCESS_NAME}"',
            "    return frontmost",
            "  end tell",
            "end tell",
        ]
    ).lower()
    return out == "true"


def send_key(key: str, mods: list[str] | None = None) -> None:
    key = key.strip().lower()
    mods = normalize_modifiers(mods)
    clause = using_clause(mods)
    if key in SPECIAL_KEYS:
        action = f"key code {SPECIAL_KEYS[key]}{clause}"
    elif len(key) == 1:
        action = f"keystroke {applescript_quote(key)}{clause}"
    else:
        raise ValueError(f"Unsupported key: {key}")
    run_osascript(
        [
            'tell application "System Events"',
            f'  tell process "{PROCESS_NAME}"',
            f"    {action}",
            "  end tell",
            "end tell",
        ]
    )


def send_hotkey(combo: str) -> None:
    key, mods = parse_combo(combo)
    send_key(key, mods)


def press_key(key: str, mods: list[str] | None = None, times: int = 1, delay: float = 0.0) -> None:
    if times < 1:
        raise ValueError("times must be >= 1")
    for idx in range(times):
        send_key(key, mods)
        if delay > 0 and idx < times - 1:
            time.sleep(delay)


def type_text(text: str, interval: float = 0.0) -> None:
    if "\n" in text or "\r" in text:
        raise ValueError("Newlines are not supported in type; send `press return` separately.")
    if interval <= 0:
        run_osascript(
            [
                'tell application "System Events"',
                f'  tell process "{PROCESS_NAME}"',
                f"    keystroke {applescript_quote(text)}",
                "  end tell",
                "end tell",
            ]
        )
        return
    run_osascript(
        [
            f"set theText to {applescript_quote(text)}",
            'tell application "System Events"',
            f'  tell process "{PROCESS_NAME}"',
            "    repeat with i from 1 to (length of theText)",
            "      keystroke (character i of theText)",
            f"      delay {interval}",
            "    end repeat",
            "  end tell",
            "end tell",
        ]
    )


def clear_focused_input(strategy: str = "cmd-a-backspace") -> None:
    strategy = strategy.strip().lower()
    if strategy in {"", "none"}:
        return
    if strategy == "cmd-a-backspace":
        send_hotkey("cmd+a")
        send_key("backspace")
        return
    if strategy == "cmd+a-delete":
        send_hotkey("cmd+a")
        send_key("delete")
        return
    raise ValueError(f"Unsupported clear strategy: {strategy}")


def click_menu(path_expr: str) -> None:
    parts = [p.strip() for p in path_expr.split(">") if p.strip()]
    if len(parts) < 2:
        raise ValueError("Menu path must have at least 'Top > Item'")
    top = parts[0]
    items = parts[1:]

    base = f'menu "{top}" of menu bar item "{top}" of menu bar 1'
    if len(items) == 1:
        target = f'menu item "{items[0]}" of {base}'
    else:
        chain = base
        for item in items[:-1]:
            chain = f'menu 1 of menu item "{item}" of {chain}'
        target = f'menu item "{items[-1]}" of {chain}'

    run_osascript(
        [
            'tell application "System Events"',
            f'  tell process "{PROCESS_NAME}"',
            f"    click {target}",
            "  end tell",
            "end tell",
        ]
    )


def mouse_location() -> dict[str, float]:
    x, y = cg().mouse_location()
    return {"x": x, "y": y}


def _resolve_point(
    x: float,
    y: float,
    *,
    relative_window: bool = False,
    normalized_window: bool = False,
) -> tuple[float, float]:
    if relative_window and normalized_window:
        raise ValueError("Use only one of --relative-window or --normalized-window")
    if normalized_window:
        bounds = front_window_bounds()
        return bounds["x"] + (x * bounds["width"]), bounds["y"] + (y * bounds["height"])
    if relative_window:
        bounds = front_window_bounds()
        return bounds["x"] + x, bounds["y"] + y
    return x, y


def move_mouse(
    x: float,
    y: float,
    *,
    relative_window: bool = False,
    normalized_window: bool = False,
) -> tuple[float, float]:
    tx, ty = _resolve_point(x, y, relative_window=relative_window, normalized_window=normalized_window)
    cg().post_mouse_event(KCG_EVENT_MOUSE_MOVED, tx, ty, KCG_MOUSE_BUTTON_LEFT)
    return tx, ty


def mouse_click(
    x: float,
    y: float,
    *,
    button: str = "left",
    clicks: int = 1,
    interval: float = 0.08,
    relative_window: bool = False,
    normalized_window: bool = False,
    move_first: bool = True,
) -> tuple[float, float]:
    if clicks < 1:
        raise ValueError("clicks must be >= 1")
    button = button.strip().lower()
    if button == "left":
        down_ev = KCG_EVENT_LEFT_MOUSE_DOWN
        up_ev = KCG_EVENT_LEFT_MOUSE_UP
        cg_button = KCG_MOUSE_BUTTON_LEFT
    elif button == "right":
        down_ev = KCG_EVENT_RIGHT_MOUSE_DOWN
        up_ev = KCG_EVENT_RIGHT_MOUSE_UP
        cg_button = KCG_MOUSE_BUTTON_RIGHT
    else:
        raise ValueError("button must be 'left' or 'right'")

    tx, ty = _resolve_point(x, y, relative_window=relative_window, normalized_window=normalized_window)
    if move_first:
        cg().post_mouse_event(KCG_EVENT_MOUSE_MOVED, tx, ty, cg_button)
        time.sleep(0.02)
    for i in range(clicks):
        cg().post_mouse_event(down_ev, tx, ty, cg_button)
        cg().post_mouse_event(up_ev, tx, ty, cg_button)
        if i < clicks - 1:
            time.sleep(interval)
    return tx, ty


def mouse_drag(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    button: str = "left",
    relative_window: bool = False,
    normalized_window: bool = False,
    steps: int = 12,
    duration: float = 0.2,
) -> dict[str, tuple[float, float]]:
    if button.strip().lower() != "left":
        raise ValueError("drag currently supports only left button")
    sx, sy = _resolve_point(x1, y1, relative_window=relative_window, normalized_window=normalized_window)
    ex, ey = _resolve_point(x2, y2, relative_window=relative_window, normalized_window=normalized_window)
    cg_api = cg()
    cg_api.post_mouse_event(KCG_EVENT_MOUSE_MOVED, sx, sy, KCG_MOUSE_BUTTON_LEFT)
    time.sleep(0.02)
    cg_api.post_mouse_event(KCG_EVENT_LEFT_MOUSE_DOWN, sx, sy, KCG_MOUSE_BUTTON_LEFT)
    steps = max(1, int(steps))
    pause = max(0.0, float(duration)) / steps if steps else 0.0
    for i in range(1, steps + 1):
        t = i / steps
        x = sx + (ex - sx) * t
        y = sy + (ey - sy) * t
        cg_api.post_mouse_event(KCG_EVENT_LEFT_MOUSE_DRAGGED, x, y, KCG_MOUSE_BUTTON_LEFT)
        if pause > 0:
            time.sleep(pause)
    cg_api.post_mouse_event(KCG_EVENT_LEFT_MOUSE_UP, ex, ey, KCG_MOUSE_BUTTON_LEFT)
    return {"from": (sx, sy), "to": (ex, ey)}


def open_search_and_submit(
    query: str,
    *,
    open_combo: str,
    activate: bool = True,
    launch: bool = False,
    pre_wait: float = 0.2,
    open_wait: float = 0.25,
    type_interval: float = 0.0,
    clear_strategy: str = "cmd-a-backspace",
    confirm: bool = True,
    confirm_key: str = "return",
    escape_first: bool = False,
) -> None:
    if activate:
        activate_app(launch=launch, delay=pre_wait)
    if escape_first:
        send_key("esc")
        if pre_wait > 0:
            time.sleep(min(pre_wait, 0.2))
    send_hotkey(open_combo)
    if open_wait > 0:
        time.sleep(open_wait)
    clear_focused_input(clear_strategy)
    type_text(query, interval=type_interval)
    if confirm:
        send_key(confirm_key)


def watchlist_field_workflow(
    query: str,
    *,
    x: float,
    y: float,
    activate: bool = True,
    launch: bool = False,
    pre_wait: float = 0.2,
    clicks: int = 1,
    button: str = "left",
    relative_window: bool = False,
    normalized_window: bool = False,
    click_wait: float = 0.12,
    clear_strategy: str = "cmd-a-backspace",
    type_interval: float = 0.0,
    confirm: bool = False,
    confirm_key: str = "return",
) -> tuple[float, float]:
    if activate:
        activate_app(launch=launch, delay=pre_wait)
    point = mouse_click(
        x,
        y,
        button=button,
        clicks=clicks,
        relative_window=relative_window,
        normalized_window=normalized_window,
    )
    if click_wait > 0:
        time.sleep(click_wait)
    clear_focused_input(clear_strategy)
    type_text(query, interval=type_interval)
    if confirm:
        send_key(confirm_key)
    return point


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def default_layout_config(layout_name: str = "default") -> dict[str, Any]:
    return {
        "version": 1,
        "layout_name": layout_name,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "shortcuts": {
            "symbol_search": "cmd+k",
            "indicator_search": "/",
        },
        "watchlist": {
            # Named points in the "points" map below.
            "search_field_point": "watchlist_search_field",
            "add_button_point": "watchlist_add_button",
            "remove_menu_item_point": "watchlist_context_remove_item",
            "default_from_row_point": "watchlist_row_1",
            "default_to_row_point": "watchlist_row_2",
            # Row points are arbitrary anchors; you can add more.
            "row_points": [
                "watchlist_row_1",
                "watchlist_row_2",
                "watchlist_row_3",
            ],
            # Defaults for text-entry flows.
            "clear_strategy": "cmd-a-backspace",
            "confirm_key": "return",
            "add_confirm_times": 1,
            "add_confirm_delay": 0.1,
        },
        "points": {},
    }


def _touch_updated_at(config: dict[str, Any]) -> None:
    config["updated_at"] = now_iso()


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a JSON object")
    data.setdefault("version", 1)
    data.setdefault("layout_name", path.stem)
    data.setdefault("shortcuts", {})
    data.setdefault("watchlist", {})
    data.setdefault("points", {})
    return data


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _touch_updated_at(config)
    path.write_text(json.dumps(config, indent=2) + "\n")


def init_config(path: Path, layout_name: str | None = None, force: bool = False) -> dict[str, Any]:
    if path.exists() and not force:
        raise ValueError(f"Config already exists: {path} (use --force to overwrite)")
    cfg = default_layout_config(layout_name or path.stem)
    save_config(path, cfg)
    return cfg


def get_shortcut(config: dict[str, Any], key: str, default: str | None = None) -> str:
    shortcuts = config.setdefault("shortcuts", {})
    value = shortcuts.get(key, default)
    if not value:
        raise ValueError(f"Shortcut '{key}' is not set in config")
    return str(value)


def set_shortcut(config: dict[str, Any], key: str, combo: str) -> None:
    config.setdefault("shortcuts", {})[key] = combo


def normalize_coord_mode(coord_mode: str) -> str:
    mode = coord_mode.strip().lower()
    aliases = {
        "absolute": "absolute",
        "abs": "absolute",
        "relative": "relative_window",
        "relative_window": "relative_window",
        "rel": "relative_window",
        "normalized": "normalized_window",
        "normalized_window": "normalized_window",
        "norm": "normalized_window",
    }
    if mode not in aliases:
        raise ValueError(f"Unsupported coord mode: {coord_mode}")
    return aliases[mode]


def create_point_record(
    *,
    x: float,
    y: float,
    coord_mode: str,
    note: str | None = None,
    capture_window_bounds: bool = True,
) -> dict[str, Any]:
    mode = normalize_coord_mode(coord_mode)
    record: dict[str, Any] = {
        "x": float(x),
        "y": float(y),
        "coord_mode": mode,
        "captured_at": now_iso(),
    }
    if note:
        record["note"] = note
    if capture_window_bounds and mode in {"relative_window", "normalized_window"}:
        record["captured_window_bounds"] = front_window_bounds()
    return record


def capture_mouse_point_record(
    *,
    coord_mode: str = "normalized_window",
    note: str | None = None,
    activate: bool = False,
    launch: bool = False,
) -> dict[str, Any]:
    mode = normalize_coord_mode(coord_mode)
    if activate:
        activate_app(launch=launch, delay=0.15)
    mouse = mouse_location()
    if mode == "absolute":
        return create_point_record(x=mouse["x"], y=mouse["y"], coord_mode=mode, note=note, capture_window_bounds=False)
    bounds = front_window_bounds()
    rx = float(mouse["x"]) - float(bounds["x"])
    ry = float(mouse["y"]) - float(bounds["y"])
    if mode == "relative_window":
        return create_point_record(x=rx, y=ry, coord_mode=mode, note=note, capture_window_bounds=False) | {
            "captured_window_bounds": bounds
        }
    if bounds["width"] <= 0 or bounds["height"] <= 0:
        raise ValueError("Invalid front window bounds for normalized capture")
    nx = rx / float(bounds["width"])
    ny = ry / float(bounds["height"])
    return create_point_record(x=nx, y=ny, coord_mode=mode, note=note, capture_window_bounds=False) | {
        "captured_window_bounds": bounds
    }


def set_point(config: dict[str, Any], name: str, point_record: dict[str, Any]) -> None:
    points = config.setdefault("points", {})
    points[name] = point_record


def get_point(config: dict[str, Any], name: str) -> dict[str, Any]:
    points = config.setdefault("points", {})
    point = points.get(name)
    if not isinstance(point, dict):
        raise ValueError(f"Point '{name}' is not defined in config")
    return point


def point_flags(point: dict[str, Any]) -> dict[str, bool]:
    mode = normalize_coord_mode(str(point.get("coord_mode", "absolute")))
    return {
        "relative_window": mode == "relative_window",
        "normalized_window": mode == "normalized_window",
    }


def point_to_abs(point: dict[str, Any]) -> tuple[float, float]:
    flags = point_flags(point)
    return _resolve_point(
        float(point["x"]),
        float(point["y"]),
        relative_window=flags["relative_window"],
        normalized_window=flags["normalized_window"],
    )


def click_config_point(
    config: dict[str, Any],
    point_name: str,
    *,
    button: str = "left",
    clicks: int = 1,
    interval: float = 0.08,
    move_first: bool = True,
) -> tuple[float, float]:
    point = get_point(config, point_name)
    flags = point_flags(point)
    return mouse_click(
        float(point["x"]),
        float(point["y"]),
        button=button,
        clicks=clicks,
        interval=interval,
        relative_window=flags["relative_window"],
        normalized_window=flags["normalized_window"],
        move_first=move_first,
    )


def drag_between_config_points(
    config: dict[str, Any],
    from_point_name: str,
    to_point_name: str,
    *,
    steps: int = 12,
    duration: float = 0.2,
) -> dict[str, tuple[float, float]]:
    p1 = get_point(config, from_point_name)
    p2 = get_point(config, to_point_name)
    mode1 = normalize_coord_mode(str(p1.get("coord_mode", "absolute")))
    mode2 = normalize_coord_mode(str(p2.get("coord_mode", "absolute")))
    if mode1 != mode2:
        raise ValueError(
            f"Point coord modes must match for drag ({from_point_name}={mode1}, {to_point_name}={mode2})"
        )
    flags = point_flags(p1)
    return mouse_drag(
        float(p1["x"]),
        float(p1["y"]),
        float(p2["x"]),
        float(p2["y"]),
        relative_window=flags["relative_window"],
        normalized_window=flags["normalized_window"],
        steps=steps,
        duration=duration,
    )


def _watchlist_cfg(config: dict[str, Any]) -> dict[str, Any]:
    return config.setdefault("watchlist", {})


def watchlist_config_point_name(config: dict[str, Any], key: str, default: str) -> str:
    watchlist = _watchlist_cfg(config)
    value = watchlist.get(key, default)
    if not value:
        raise ValueError(f"watchlist.{key} is not set in config")
    return str(value)


def watchlist_open_from_config(
    config: dict[str, Any],
    symbol: str,
    *,
    point_name: str | None = None,
    activate: bool = True,
    launch: bool = False,
    pre_wait: float = 0.2,
    click_wait: float = 0.12,
    type_interval: float = 0.0,
    clear_strategy: str | None = None,
    confirm_key: str | None = None,
) -> tuple[float, float]:
    if activate:
        activate_app(launch=launch, delay=pre_wait)
    pname = point_name or watchlist_config_point_name(config, "search_field_point", "watchlist_search_field")
    point = click_config_point(config, pname)
    if click_wait > 0:
        time.sleep(click_wait)
    wl = _watchlist_cfg(config)
    clear_focused_input(clear_strategy or str(wl.get("clear_strategy", "cmd-a-backspace")))
    type_text(symbol, interval=type_interval)
    send_key(str(confirm_key or wl.get("confirm_key", "return")))
    return point


def watchlist_add_from_config(
    config: dict[str, Any],
    symbol: str,
    *,
    add_button_point_name: str | None = None,
    fallback_search_point_name: str | None = None,
    activate: bool = True,
    launch: bool = False,
    pre_wait: float = 0.2,
    click_wait: float = 0.15,
    type_interval: float = 0.0,
    clear_strategy: str | None = None,
    confirm_key: str | None = None,
    confirm_times: int | None = None,
    confirm_delay: float | None = None,
) -> tuple[float, float]:
    if activate:
        activate_app(launch=launch, delay=pre_wait)
    wl = _watchlist_cfg(config)
    pname = add_button_point_name or str(wl.get("add_button_point") or "")
    if not pname:
        pname = fallback_search_point_name or watchlist_config_point_name(config, "search_field_point", "watchlist_search_field")
    point = click_config_point(config, pname)
    if click_wait > 0:
        time.sleep(click_wait)
    clear_focused_input(clear_strategy or str(wl.get("clear_strategy", "cmd-a-backspace")))
    type_text(symbol, interval=type_interval)
    ckey = str(confirm_key or wl.get("confirm_key", "return"))
    count = int(confirm_times if confirm_times is not None else wl.get("add_confirm_times", 1))
    gap = float(confirm_delay if confirm_delay is not None else wl.get("add_confirm_delay", 0.1))
    press_key(ckey, times=max(1, count), delay=max(0.0, gap))
    return point


def watchlist_remove_row_from_config(
    config: dict[str, Any],
    *,
    row_point_name: str | None = None,
    remove_menu_point_name: str | None = None,
    activate: bool = True,
    launch: bool = False,
    pre_wait: float = 0.2,
    context_wait: float = 0.12,
) -> dict[str, Any]:
    if activate:
        activate_app(launch=launch, delay=pre_wait)
    wl = _watchlist_cfg(config)
    row_name = row_point_name or watchlist_config_point_name(config, "default_from_row_point", "watchlist_row_1")
    remove_name = remove_menu_point_name or watchlist_config_point_name(
        config, "remove_menu_item_point", "watchlist_context_remove_item"
    )
    row_point = click_config_point(config, row_name, button="right")
    if context_wait > 0:
        time.sleep(context_wait)
    remove_point = click_config_point(config, remove_name, button="left")
    return {"row_point": row_point, "remove_point": remove_point}


def watchlist_reorder_from_config(
    config: dict[str, Any],
    *,
    from_point_name: str | None = None,
    to_point_name: str | None = None,
    activate: bool = True,
    launch: bool = False,
    pre_wait: float = 0.2,
    steps: int = 12,
    duration: float = 0.25,
) -> dict[str, Any]:
    if activate:
        activate_app(launch=launch, delay=pre_wait)
    wl = _watchlist_cfg(config)
    from_name = from_point_name or watchlist_config_point_name(config, "default_from_row_point", "watchlist_row_1")
    to_name = to_point_name or watchlist_config_point_name(config, "default_to_row_point", "watchlist_row_2")
    result = drag_between_config_points(config, from_name, to_name, steps=steps, duration=duration)
    return {"from_point_name": from_name, "to_point_name": to_name, "drag": result}


def calibrate_watchlist_points(
    config_path: Path,
    *,
    coord_mode: str = "normalized_window",
    delay_per_point: float = 8.0,
    activate: bool = True,
    launch: bool = False,
) -> dict[str, Any]:
    """
    Timed calibration helper.
    It prints a prompt, waits `delay_per_point`, and captures the current mouse position for each point.
    """
    cfg = load_config(config_path)
    sequence: list[tuple[str, str]] = [
        ("watchlist_search_field", "Hover the watchlist search/input field"),
        ("watchlist_add_button", "Hover the watchlist add (+) button"),
        ("watchlist_row_1", "Hover the first watchlist row anchor"),
        ("watchlist_row_2", "Hover the second watchlist row anchor"),
        ("watchlist_row_3", "Hover the third watchlist row anchor"),
        (
            "watchlist_context_remove_item",
            "Right-click a watchlist row, then hover the context-menu Remove item",
        ),
    ]
    if activate:
        activate_app(launch=launch, delay=0.2)
    for idx, (name, prompt) in enumerate(sequence, start=1):
        print(f"[{idx}/{len(sequence)}] {prompt} -> capturing in {delay_per_point:.1f}s...")
        time.sleep(max(0.0, delay_per_point))
        rec = capture_mouse_point_record(coord_mode=coord_mode, note=prompt, activate=False)
        set_point(cfg, name, rec)
        print(f"  captured {name}: {rec['x']:.6f}, {rec['y']:.6f} ({rec['coord_mode']})")
        # Small gap so the operator can move to the next point.
        time.sleep(0.4)
    save_config(config_path, cfg)
    return cfg


def status() -> dict[str, Any]:
    info: dict[str, Any] = {
        "app": APP_NAME,
        "process": PROCESS_NAME,
        "running": is_running(),
    }
    if not info["running"]:
        return info
    try:
        info["frontmost"] = app_frontmost()
    except Exception as e:  # noqa: BLE001
        info["frontmost_error"] = str(e)
    try:
        info["menus"] = list_menus()
    except Exception as e:  # noqa: BLE001
        info["menus_error"] = str(e)
    try:
        info["window_titles"] = window_titles()
    except Exception as e:  # noqa: BLE001
        info["window_titles_error"] = str(e)
    if info.get("frontmost") is True:
        try:
            info["window_bounds"] = front_window_bounds()
        except Exception as e:  # noqa: BLE001
            info["window_bounds_error"] = str(e)
    else:
        info["window_bounds_note"] = "Activate TradingView before requesting bounds"
    try:
        info["mouse_location"] = mouse_location()
    except Exception as e:  # noqa: BLE001
        info["mouse_location_error"] = str(e)
    return info


def _step_bool(step: dict[str, Any], key: str, default: bool = False) -> bool:
    value = step.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _step_float(step: dict[str, Any], key: str, default: float = 0.0) -> float:
    return float(step.get(key, default))


def _step_int(step: dict[str, Any], key: str, default: int = 0) -> int:
    return int(step.get(key, default))


def run_action(step: dict[str, Any]) -> None:
    action = str(step.get("action", "")).strip()
    if not action:
        raise ValueError("Sequence step missing action")

    if action == "activate":
        activate_app(bool(step.get("launch", False)), float(step.get("delay", 0.25)))
        return
    if action == "wait":
        seconds = float(step.get("seconds", 0))
        if seconds < 0:
            raise ValueError("wait.seconds must be >= 0")
        time.sleep(seconds)
        return
    if action == "hotkey":
        send_hotkey(str(step["combo"]))
        return
    if action == "press":
        mods = step.get("mods")
        if isinstance(mods, str):
            mods = [mods]
        press_key(
            str(step["key"]),
            mods,
            times=_step_int(step, "times", 1),
            delay=_step_float(step, "delay", 0.0),
        )
        return
    if action == "type":
        type_text(str(step["text"]), float(step.get("interval", 0.0)))
        return
    if action == "click-menu":
        click_menu(str(step["path"]))
        return
    if action == "move-mouse":
        move_mouse(
            float(step["x"]),
            float(step["y"]),
            relative_window=_step_bool(step, "relative_window", False),
            normalized_window=_step_bool(step, "normalized_window", False),
        )
        return
    if action == "click":
        mouse_click(
            float(step["x"]),
            float(step["y"]),
            button=str(step.get("button", "left")),
            clicks=_step_int(step, "clicks", 1),
            interval=_step_float(step, "interval", 0.08),
            relative_window=_step_bool(step, "relative_window", False),
            normalized_window=_step_bool(step, "normalized_window", False),
            move_first=_step_bool(step, "move_first", True),
        )
        return
    if action == "drag":
        mouse_drag(
            float(step["x1"]),
            float(step["y1"]),
            float(step["x2"]),
            float(step["y2"]),
            relative_window=_step_bool(step, "relative_window", False),
            normalized_window=_step_bool(step, "normalized_window", False),
            steps=_step_int(step, "steps", 12),
            duration=_step_float(step, "duration", 0.2),
        )
        return
    if action == "search":
        open_search_and_submit(
            str(step["query"]),
            open_combo=str(step.get("open_combo", "cmd+k")),
            activate=_step_bool(step, "activate", True),
            launch=_step_bool(step, "launch", False),
            pre_wait=_step_float(step, "pre_wait", 0.2),
            open_wait=_step_float(step, "open_wait", 0.25),
            type_interval=_step_float(step, "type_interval", 0.0),
            clear_strategy=str(step.get("clear_strategy", "cmd-a-backspace")),
            confirm=_step_bool(step, "confirm", True),
            confirm_key=str(step.get("confirm_key", "return")),
            escape_first=_step_bool(step, "escape_first", False),
        )
        return
    if action == "set-symbol":
        open_search_and_submit(
            str(step["symbol"]),
            open_combo=str(step.get("open_combo", "cmd+k")),
            activate=_step_bool(step, "activate", True),
            launch=_step_bool(step, "launch", False),
            pre_wait=_step_float(step, "pre_wait", 0.2),
            open_wait=_step_float(step, "open_wait", 0.25),
            type_interval=_step_float(step, "type_interval", 0.0),
            clear_strategy=str(step.get("clear_strategy", "cmd-a-backspace")),
            confirm=_step_bool(step, "confirm", True),
            confirm_key=str(step.get("confirm_key", "return")),
            escape_first=_step_bool(step, "escape_first", False),
        )
        return
    if action == "add-indicator":
        open_search_and_submit(
            str(step["query"]),
            open_combo=str(step.get("open_combo", "/")),
            activate=_step_bool(step, "activate", True),
            launch=_step_bool(step, "launch", False),
            pre_wait=_step_float(step, "pre_wait", 0.2),
            open_wait=_step_float(step, "open_wait", 0.3),
            type_interval=_step_float(step, "type_interval", 0.0),
            clear_strategy=str(step.get("clear_strategy", "cmd-a-backspace")),
            confirm=_step_bool(step, "confirm", True),
            confirm_key=str(step.get("confirm_key", "return")),
            escape_first=_step_bool(step, "escape_first", False),
        )
        return
    if action == "watchlist-search":
        watchlist_field_workflow(
            str(step["query"]),
            x=float(step["x"]),
            y=float(step["y"]),
            activate=_step_bool(step, "activate", True),
            launch=_step_bool(step, "launch", False),
            pre_wait=_step_float(step, "pre_wait", 0.2),
            clicks=_step_int(step, "clicks", 1),
            button=str(step.get("button", "left")),
            relative_window=_step_bool(step, "relative_window", False),
            normalized_window=_step_bool(step, "normalized_window", False),
            click_wait=_step_float(step, "click_wait", 0.12),
            clear_strategy=str(step.get("clear_strategy", "cmd-a-backspace")),
            type_interval=_step_float(step, "type_interval", 0.0),
            confirm=_step_bool(step, "confirm", False),
            confirm_key=str(step.get("confirm_key", "return")),
        )
        return
    if action == "watchlist-open":
        watchlist_field_workflow(
            str(step["symbol"]),
            x=float(step["x"]),
            y=float(step["y"]),
            activate=_step_bool(step, "activate", True),
            launch=_step_bool(step, "launch", False),
            pre_wait=_step_float(step, "pre_wait", 0.2),
            clicks=_step_int(step, "clicks", 1),
            button=str(step.get("button", "left")),
            relative_window=_step_bool(step, "relative_window", False),
            normalized_window=_step_bool(step, "normalized_window", False),
            click_wait=_step_float(step, "click_wait", 0.12),
            clear_strategy=str(step.get("clear_strategy", "cmd-a-backspace")),
            type_interval=_step_float(step, "type_interval", 0.0),
            confirm=True,
            confirm_key=str(step.get("confirm_key", "return")),
        )
        return
    if action == "config-watchlist-open":
        cfg = load_config(Path(str(step["config"])))
        watchlist_open_from_config(
            cfg,
            str(step["symbol"]),
            point_name=step.get("point_name") and str(step["point_name"]),
            activate=_step_bool(step, "activate", True),
            launch=_step_bool(step, "launch", False),
            pre_wait=_step_float(step, "pre_wait", 0.2),
            click_wait=_step_float(step, "click_wait", 0.12),
            type_interval=_step_float(step, "type_interval", 0.0),
            clear_strategy=step.get("clear_strategy") and str(step.get("clear_strategy")),
            confirm_key=step.get("confirm_key") and str(step.get("confirm_key")),
        )
        return
    if action == "config-watchlist-add":
        cfg = load_config(Path(str(step["config"])))
        watchlist_add_from_config(
            cfg,
            str(step["symbol"]),
            add_button_point_name=step.get("add_button_point_name") and str(step["add_button_point_name"]),
            fallback_search_point_name=step.get("fallback_search_point_name")
            and str(step["fallback_search_point_name"]),
            activate=_step_bool(step, "activate", True),
            launch=_step_bool(step, "launch", False),
            pre_wait=_step_float(step, "pre_wait", 0.2),
            click_wait=_step_float(step, "click_wait", 0.15),
            type_interval=_step_float(step, "type_interval", 0.0),
            clear_strategy=step.get("clear_strategy") and str(step.get("clear_strategy")),
            confirm_key=step.get("confirm_key") and str(step.get("confirm_key")),
            confirm_times=(int(step["confirm_times"]) if "confirm_times" in step else None),
            confirm_delay=(float(step["confirm_delay"]) if "confirm_delay" in step else None),
        )
        return
    if action == "config-watchlist-remove":
        cfg = load_config(Path(str(step["config"])))
        watchlist_remove_row_from_config(
            cfg,
            row_point_name=step.get("row_point_name") and str(step["row_point_name"]),
            remove_menu_point_name=step.get("remove_menu_point_name") and str(step["remove_menu_point_name"]),
            activate=_step_bool(step, "activate", True),
            launch=_step_bool(step, "launch", False),
            pre_wait=_step_float(step, "pre_wait", 0.2),
            context_wait=_step_float(step, "context_wait", 0.12),
        )
        return
    if action == "config-watchlist-reorder":
        cfg = load_config(Path(str(step["config"])))
        watchlist_reorder_from_config(
            cfg,
            from_point_name=step.get("from_point_name") and str(step["from_point_name"]),
            to_point_name=step.get("to_point_name") and str(step["to_point_name"]),
            activate=_step_bool(step, "activate", True),
            launch=_step_bool(step, "launch", False),
            pre_wait=_step_float(step, "pre_wait", 0.2),
            steps=_step_int(step, "steps", 12),
            duration=_step_float(step, "duration", 0.25),
        )
        return

    raise ValueError(f"Unsupported sequence action: {action}")


def run_sequence(path: Path, continue_on_error: bool = False) -> int:
    payload = json.loads(path.read_text())
    steps = payload["steps"] if isinstance(payload, dict) and "steps" in payload else payload
    if not isinstance(steps, list):
        raise ValueError("Sequence JSON must be a list or an object with a 'steps' list")

    failed = 0
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"Sequence step {idx} must be an object")
        action = step.get("action", "<missing>")
        print(f"[{idx}/{len(steps)}] {action}")
        try:
            run_action(step)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR: {e}", file=sys.stderr)
            if not continue_on_error:
                return 1
    return 0 if failed == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Control the local TradingView desktop app on macOS via AppleScript/System Events and CoreGraphics mouse events."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Print JSON status for the TradingView app/process")

    ap = sub.add_parser("activate", help="Activate (focus) the TradingView app")
    ap.add_argument("--launch", action="store_true", help="Launch TradingView if not already running")
    ap.add_argument("--delay", type=float, default=0.25, help="Post-activation delay in seconds")

    sub.add_parser("list-menus", help="List top-level menu bar items")
    sub.add_parser("window-titles", help="List accessible window titles (may be empty)")
    sub.add_parser("window-bounds", help="Print JSON bounds for the front TradingView window")
    sub.add_parser("mouse-location", help="Print JSON current mouse pointer location")

    ci = sub.add_parser("config-init", help="Create a new TradingView layout config JSON")
    ci.add_argument("file", type=Path)
    ci.add_argument("--layout-name", default=None)
    ci.add_argument("--force", action="store_true")

    cs = sub.add_parser("config-show", help="Print a layout config JSON")
    cs.add_argument("file", type=Path)

    css = sub.add_parser("config-set-shortcut", help="Set a shortcut value in config (e.g. symbol_search)")
    css.add_argument("file", type=Path)
    css.add_argument("key")
    css.add_argument("combo")

    csp = sub.add_parser("config-set-point", help="Store a named point in config")
    csp.add_argument("file", type=Path)
    csp.add_argument("name")
    csp.add_argument("x", type=float)
    csp.add_argument("y", type=float)
    csp.add_argument("--coord-mode", default="normalized_window", choices=["absolute", "relative_window", "normalized_window"])
    csp.add_argument("--note", default=None)

    ccp = sub.add_parser(
        "config-capture-point",
        help="Capture current mouse position into config (supports normalized/relative window coords)",
    )
    ccp.add_argument("file", type=Path)
    ccp.add_argument("name")
    ccp.add_argument("--coord-mode", default="normalized_window", choices=["absolute", "relative_window", "normalized_window"])
    ccp.add_argument("--note", default=None)
    ccp.add_argument("--delay", type=float, default=0.0, help="Wait before capture so you can move the cursor")
    ccp.add_argument("--launch", action="store_true")
    ccp.add_argument("--no-activate", action="store_false", dest="activate", default=True)

    cwl = sub.add_parser(
        "calibrate-watchlist",
        help="Timed capture of common watchlist points into config (search/add/rows); requires moving the mouse during prompts",
    )
    cwl.add_argument("file", type=Path)
    cwl.add_argument("--coord-mode", default="normalized_window", choices=["absolute", "relative_window", "normalized_window"])
    cwl.add_argument("--delay-per-point", type=float, default=8.0)
    cwl.add_argument("--launch", action="store_true")
    cwl.add_argument("--no-activate", action="store_false", dest="activate", default=True)

    cwb = sub.add_parser("config-bind-watchlist", help="Update watchlist point bindings in config")
    cwb.add_argument("file", type=Path)
    cwb.add_argument("--search-field-point", default=None)
    cwb.add_argument("--add-button-point", default=None)
    cwb.add_argument("--remove-menu-item-point", default=None)
    cwb.add_argument("--default-from-row-point", default=None)
    cwb.add_argument("--default-to-row-point", default=None)
    cwb.add_argument("--row-points", default=None, help="Comma-separated ordered row point names")

    wc_open = sub.add_parser("watchlist-open-config", help="Open/switch symbol via watchlist search field from config")
    wc_open.add_argument("config", type=Path)
    wc_open.add_argument("symbol")
    wc_open.add_argument("--point-name", default=None, help="Override point name (default watchlist.search_field_point)")
    wc_open.add_argument("--click-wait", type=float, default=0.12)
    wc_open.add_argument("--pre-wait", type=float, default=0.2)
    wc_open.add_argument("--type-interval", type=float, default=0.0)
    wc_open.add_argument("--clear-strategy", default=None)
    wc_open.add_argument("--confirm-key", default=None)
    wc_open.add_argument("--launch", action="store_true")
    wc_open.add_argument("--no-activate", action="store_false", dest="activate", default=True)

    wc_add = sub.add_parser("watchlist-add-config", help="Add symbol to watchlist using configured add/search points")
    wc_add.add_argument("config", type=Path)
    wc_add.add_argument("symbol")
    wc_add.add_argument("--add-button-point-name", default=None)
    wc_add.add_argument("--fallback-search-point-name", default=None)
    wc_add.add_argument("--click-wait", type=float, default=0.15)
    wc_add.add_argument("--pre-wait", type=float, default=0.2)
    wc_add.add_argument("--type-interval", type=float, default=0.0)
    wc_add.add_argument("--clear-strategy", default=None)
    wc_add.add_argument("--confirm-key", default=None)
    wc_add.add_argument("--confirm-times", type=int, default=None)
    wc_add.add_argument("--confirm-delay", type=float, default=None)
    wc_add.add_argument("--launch", action="store_true")
    wc_add.add_argument("--no-activate", action="store_false", dest="activate", default=True)

    wc_rm = sub.add_parser("watchlist-remove-config", help="Remove a watchlist row using config row + context-menu remove points")
    wc_rm.add_argument("config", type=Path)
    wc_rm.add_argument("--row-point-name", default=None)
    wc_rm.add_argument("--remove-menu-point-name", default=None)
    wc_rm.add_argument("--context-wait", type=float, default=0.12)
    wc_rm.add_argument("--pre-wait", type=float, default=0.2)
    wc_rm.add_argument("--launch", action="store_true")
    wc_rm.add_argument("--no-activate", action="store_false", dest="activate", default=True)

    wc_re = sub.add_parser("watchlist-reorder-config", help="Drag between two configured watchlist row points")
    wc_re.add_argument("config", type=Path)
    wc_re.add_argument("--from-point-name", default=None)
    wc_re.add_argument("--to-point-name", default=None)
    wc_re.add_argument("--steps", type=int, default=12)
    wc_re.add_argument("--duration", type=float, default=0.25)
    wc_re.add_argument("--pre-wait", type=float, default=0.2)
    wc_re.add_argument("--launch", action="store_true")
    wc_re.add_argument("--no-activate", action="store_false", dest="activate", default=True)

    hp = sub.add_parser("hotkey", help="Send a hotkey combo like cmd+k or shift+cmd+p")
    hp.add_argument("combo")

    pp = sub.add_parser("press", help="Press a key (special keys or single characters)")
    pp.add_argument("key")
    pp.add_argument(
        "--mods",
        nargs="*",
        default=[],
        help="Modifiers (cmd,ctrl,opt,shift). Accepts space-separated or comma-separated values.",
    )
    pp.add_argument("--times", type=int, default=1, help="Repeat count")
    pp.add_argument("--delay", type=float, default=0.0, help="Delay between repeats")

    tp = sub.add_parser("type", help="Type text into the focused control")
    tp.add_argument("text")
    tp.add_argument("--interval", type=float, default=0.0, help="Delay between typed characters")

    mp = sub.add_parser("click-menu", help='Click a menu path like "View > Layout > Save"')
    mp.add_argument("path")

    def add_point_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("x", type=float)
        sp.add_argument("y", type=float)
        sp.add_argument("--relative-window", action="store_true", help="Treat x,y as offsets from front window origin")
        sp.add_argument("--normalized-window", action="store_true", help="Treat x,y as 0..1 normalized coords inside front window")

    mm = sub.add_parser("move-mouse", help="Move mouse pointer to a point")
    add_point_args(mm)

    mc = sub.add_parser("click", help="Click at a point (supports normalized window coordinates)")
    add_point_args(mc)
    mc.add_argument("--button", choices=["left", "right"], default="left")
    mc.add_argument("--clicks", type=int, default=1)
    mc.add_argument("--interval", type=float, default=0.08, help="Delay between clicks")
    mc.add_argument("--no-move-first", action="store_true", help="Skip explicit mouse move before clicking")

    dg = sub.add_parser("drag", help="Drag from one point to another (left button)")
    dg.add_argument("x1", type=float)
    dg.add_argument("y1", type=float)
    dg.add_argument("x2", type=float)
    dg.add_argument("y2", type=float)
    dg.add_argument("--relative-window", action="store_true")
    dg.add_argument("--normalized-window", action="store_true")
    dg.add_argument("--steps", type=int, default=12)
    dg.add_argument("--duration", type=float, default=0.2)

    sp_search = sub.add_parser("search", help="Open a search dialog/palette via shortcut, type query, optionally confirm")
    sp_search.add_argument("query")
    sp_search.add_argument("--open-combo", default="cmd+k", help="Shortcut that opens the target search UI")
    sp_search.add_argument("--open-wait", type=float, default=0.25)
    sp_search.add_argument("--pre-wait", type=float, default=0.2)
    sp_search.add_argument("--type-interval", type=float, default=0.0)
    sp_search.add_argument("--clear-strategy", default="cmd-a-backspace")
    sp_search.add_argument("--confirm", action="store_true", default=True)
    sp_search.add_argument("--no-confirm", action="store_false", dest="confirm")
    sp_search.add_argument("--confirm-key", default="return")
    sp_search.add_argument("--escape-first", action="store_true")
    sp_search.add_argument("--launch", action="store_true")
    sp_search.add_argument("--no-activate", action="store_false", dest="activate", default=True)

    ss = sub.add_parser("set-symbol", help="Open symbol search (default cmd+k), type symbol, confirm")
    ss.add_argument("symbol")
    ss.add_argument("--open-combo", default="cmd+k")
    ss.add_argument("--open-wait", type=float, default=0.25)
    ss.add_argument("--pre-wait", type=float, default=0.2)
    ss.add_argument("--type-interval", type=float, default=0.0)
    ss.add_argument("--clear-strategy", default="cmd-a-backspace")
    ss.add_argument("--confirm", action="store_true", default=True)
    ss.add_argument("--no-confirm", action="store_false", dest="confirm")
    ss.add_argument("--confirm-key", default="return")
    ss.add_argument("--escape-first", action="store_true")
    ss.add_argument("--launch", action="store_true")
    ss.add_argument("--no-activate", action="store_false", dest="activate", default=True)

    ai = sub.add_parser("add-indicator", help="Open indicators search (default '/'), type query, confirm")
    ai.add_argument("query")
    ai.add_argument("--open-combo", default="/", help="Indicator search shortcut; override if your mapping differs")
    ai.add_argument("--open-wait", type=float, default=0.3)
    ai.add_argument("--pre-wait", type=float, default=0.2)
    ai.add_argument("--type-interval", type=float, default=0.0)
    ai.add_argument("--clear-strategy", default="cmd-a-backspace")
    ai.add_argument("--confirm", action="store_true", default=True)
    ai.add_argument("--no-confirm", action="store_false", dest="confirm")
    ai.add_argument("--confirm-key", default="return")
    ai.add_argument("--escape-first", action="store_true")
    ai.add_argument("--launch", action="store_true")
    ai.add_argument("--no-activate", action="store_false", dest="activate", default=True)

    for name, help_text, confirm_default in [
        ("watchlist-search", "Click the watchlist search/input field, type query, optional confirm", False),
        ("watchlist-open", "Click the watchlist search/input field, type symbol, and confirm", True),
    ]:
        ws = sub.add_parser(name, help=help_text)
        ws.add_argument("query" if name == "watchlist-search" else "symbol")
        add_point_args(ws)
        ws.add_argument("--clicks", type=int, default=1)
        ws.add_argument("--button", choices=["left", "right"], default="left")
        ws.add_argument("--click-wait", type=float, default=0.12)
        ws.add_argument("--type-interval", type=float, default=0.0)
        ws.add_argument("--clear-strategy", default="cmd-a-backspace")
        ws.add_argument("--confirm", action="store_true", default=confirm_default)
        ws.add_argument("--no-confirm", action="store_false", dest="confirm")
        ws.add_argument("--confirm-key", default="return")
        ws.add_argument("--launch", action="store_true")
        ws.add_argument("--no-activate", action="store_false", dest="activate", default=True)
        ws.add_argument("--pre-wait", type=float, default=0.2)

    wp = sub.add_parser("wait", help="Sleep for a number of seconds")
    wp.add_argument("seconds", type=float)

    sp = sub.add_parser("run-sequence", help="Run a JSON sequence of UI actions")
    sp.add_argument("file", type=Path)
    sp.add_argument("--continue-on-error", action="store_true")

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.cmd == "status":
            print(json.dumps(status(), indent=2))
            return 0
        if args.cmd == "activate":
            activate_app(launch=args.launch, delay=args.delay)
            return 0
        if args.cmd == "list-menus":
            for item in list_menus():
                print(item)
            return 0
        if args.cmd == "window-titles":
            for title in window_titles():
                print(title)
            return 0
        if args.cmd == "window-bounds":
            print(json.dumps(front_window_bounds(), indent=2))
            return 0
        if args.cmd == "mouse-location":
            print(json.dumps(mouse_location(), indent=2))
            return 0
        if args.cmd == "config-init":
            cfg = init_config(args.file, layout_name=args.layout_name, force=args.force)
            print(json.dumps(cfg, indent=2))
            return 0
        if args.cmd == "config-show":
            print(json.dumps(load_config(args.file), indent=2))
            return 0
        if args.cmd == "config-set-shortcut":
            cfg = load_config(args.file)
            set_shortcut(cfg, args.key, args.combo)
            save_config(args.file, cfg)
            print(json.dumps(cfg["shortcuts"], indent=2))
            return 0
        if args.cmd == "config-set-point":
            cfg = load_config(args.file)
            rec = create_point_record(x=args.x, y=args.y, coord_mode=args.coord_mode, note=args.note)
            set_point(cfg, args.name, rec)
            save_config(args.file, cfg)
            print(json.dumps({args.name: rec}, indent=2))
            return 0
        if args.cmd == "config-capture-point":
            if args.delay > 0:
                print(
                    f"Capturing point '{args.name}' in {args.delay:.1f}s. Move the mouse to the target.",
                    file=sys.stderr,
                )
                time.sleep(args.delay)
            cfg = load_config(args.file)
            rec = capture_mouse_point_record(
                coord_mode=args.coord_mode,
                note=args.note,
                activate=args.activate,
                launch=args.launch,
            )
            set_point(cfg, args.name, rec)
            save_config(args.file, cfg)
            print(json.dumps({args.name: rec}, indent=2))
            return 0
        if args.cmd == "calibrate-watchlist":
            cfg = calibrate_watchlist_points(
                args.file,
                coord_mode=args.coord_mode,
                delay_per_point=args.delay_per_point,
                activate=args.activate,
                launch=args.launch,
            )
            print(json.dumps(cfg.get("points", {}), indent=2))
            return 0
        if args.cmd == "config-bind-watchlist":
            cfg = load_config(args.file)
            wl = cfg.setdefault("watchlist", {})
            if args.search_field_point:
                wl["search_field_point"] = args.search_field_point
            if args.add_button_point:
                wl["add_button_point"] = args.add_button_point
            if args.remove_menu_item_point:
                wl["remove_menu_item_point"] = args.remove_menu_item_point
            if args.default_from_row_point:
                wl["default_from_row_point"] = args.default_from_row_point
            if args.default_to_row_point:
                wl["default_to_row_point"] = args.default_to_row_point
            if args.row_points is not None:
                wl["row_points"] = [p.strip() for p in args.row_points.split(",") if p.strip()]
            save_config(args.file, cfg)
            print(json.dumps(wl, indent=2))
            return 0
        if args.cmd == "hotkey":
            send_hotkey(args.combo)
            return 0
        if args.cmd == "press":
            press_key(args.key, args.mods, times=args.times, delay=args.delay)
            return 0
        if args.cmd == "type":
            type_text(args.text, args.interval)
            return 0
        if args.cmd == "click-menu":
            click_menu(args.path)
            return 0
        if args.cmd == "move-mouse":
            tx, ty = move_mouse(
                args.x,
                args.y,
                relative_window=args.relative_window,
                normalized_window=args.normalized_window,
            )
            print(json.dumps({"x": tx, "y": ty}, indent=2))
            return 0
        if args.cmd == "click":
            tx, ty = mouse_click(
                args.x,
                args.y,
                button=args.button,
                clicks=args.clicks,
                interval=args.interval,
                relative_window=args.relative_window,
                normalized_window=args.normalized_window,
                move_first=not args.no_move_first,
            )
            print(json.dumps({"x": tx, "y": ty, "button": args.button, "clicks": args.clicks}, indent=2))
            return 0
        if args.cmd == "drag":
            result = mouse_drag(
                args.x1,
                args.y1,
                args.x2,
                args.y2,
                relative_window=args.relative_window,
                normalized_window=args.normalized_window,
                steps=args.steps,
                duration=args.duration,
            )
            print(json.dumps(result, indent=2))
            return 0
        if args.cmd == "search":
            open_search_and_submit(
                args.query,
                open_combo=args.open_combo,
                activate=args.activate,
                launch=args.launch,
                pre_wait=args.pre_wait,
                open_wait=args.open_wait,
                type_interval=args.type_interval,
                clear_strategy=args.clear_strategy,
                confirm=args.confirm,
                confirm_key=args.confirm_key,
                escape_first=args.escape_first,
            )
            return 0
        if args.cmd == "set-symbol":
            open_search_and_submit(
                args.symbol,
                open_combo=args.open_combo,
                activate=args.activate,
                launch=args.launch,
                pre_wait=args.pre_wait,
                open_wait=args.open_wait,
                type_interval=args.type_interval,
                clear_strategy=args.clear_strategy,
                confirm=args.confirm,
                confirm_key=args.confirm_key,
                escape_first=args.escape_first,
            )
            return 0
        if args.cmd == "add-indicator":
            open_search_and_submit(
                args.query,
                open_combo=args.open_combo,
                activate=args.activate,
                launch=args.launch,
                pre_wait=args.pre_wait,
                open_wait=args.open_wait,
                type_interval=args.type_interval,
                clear_strategy=args.clear_strategy,
                confirm=args.confirm,
                confirm_key=args.confirm_key,
                escape_first=args.escape_first,
            )
            return 0
        if args.cmd in {"watchlist-search", "watchlist-open"}:
            query = args.query if args.cmd == "watchlist-search" else args.symbol
            tx, ty = watchlist_field_workflow(
                query,
                x=args.x,
                y=args.y,
                activate=args.activate,
                launch=args.launch,
                pre_wait=args.pre_wait,
                clicks=args.clicks,
                button=args.button,
                relative_window=args.relative_window,
                normalized_window=args.normalized_window,
                click_wait=args.click_wait,
                clear_strategy=args.clear_strategy,
                type_interval=args.type_interval,
                confirm=args.confirm,
                confirm_key=args.confirm_key,
            )
            print(json.dumps({"x": tx, "y": ty, "action": args.cmd}, indent=2))
            return 0
        if args.cmd == "watchlist-open-config":
            cfg = load_config(args.config)
            tx, ty = watchlist_open_from_config(
                cfg,
                args.symbol,
                point_name=args.point_name,
                activate=args.activate,
                launch=args.launch,
                pre_wait=args.pre_wait,
                click_wait=args.click_wait,
                type_interval=args.type_interval,
                clear_strategy=args.clear_strategy,
                confirm_key=args.confirm_key,
            )
            print(json.dumps({"x": tx, "y": ty, "action": "watchlist-open-config"}, indent=2))
            return 0
        if args.cmd == "watchlist-add-config":
            cfg = load_config(args.config)
            tx, ty = watchlist_add_from_config(
                cfg,
                args.symbol,
                add_button_point_name=args.add_button_point_name,
                fallback_search_point_name=args.fallback_search_point_name,
                activate=args.activate,
                launch=args.launch,
                pre_wait=args.pre_wait,
                click_wait=args.click_wait,
                type_interval=args.type_interval,
                clear_strategy=args.clear_strategy,
                confirm_key=args.confirm_key,
                confirm_times=args.confirm_times,
                confirm_delay=args.confirm_delay,
            )
            print(json.dumps({"x": tx, "y": ty, "action": "watchlist-add-config"}, indent=2))
            return 0
        if args.cmd == "watchlist-remove-config":
            cfg = load_config(args.config)
            result = watchlist_remove_row_from_config(
                cfg,
                row_point_name=args.row_point_name,
                remove_menu_point_name=args.remove_menu_point_name,
                activate=args.activate,
                launch=args.launch,
                pre_wait=args.pre_wait,
                context_wait=args.context_wait,
            )
            print(json.dumps({"action": "watchlist-remove-config", **result}, indent=2))
            return 0
        if args.cmd == "watchlist-reorder-config":
            cfg = load_config(args.config)
            result = watchlist_reorder_from_config(
                cfg,
                from_point_name=args.from_point_name,
                to_point_name=args.to_point_name,
                activate=args.activate,
                launch=args.launch,
                pre_wait=args.pre_wait,
                steps=args.steps,
                duration=args.duration,
            )
            print(json.dumps({"action": "watchlist-reorder-config", **result}, indent=2))
            return 0
        if args.cmd == "wait":
            if args.seconds < 0:
                raise ValueError("wait seconds must be >= 0")
            time.sleep(args.seconds)
            return 0
        if args.cmd == "run-sequence":
            return run_sequence(args.file, continue_on_error=args.continue_on_error)
    except OsaScriptError as e:
        msg = str(e)
        if "not allowed assistive access" in msg.lower():
            msg += (
                "\nGrant Accessibility access to Codex/Terminal in System Settings > Privacy & Security > Accessibility."
            )
        print(msg, file=sys.stderr)
        return 2
    except CoreGraphicsError as e:
        print(str(e), file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        print(str(e), file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
