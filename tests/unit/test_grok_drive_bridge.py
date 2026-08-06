from __future__ import annotations

from lib.grok.drive_bridge import build_drive_pack, load_folder_registry


def test_folder_registry():
    reg = load_folder_registry()
    assert reg.get("grok_bridge", {}).get("folder_id")
    assert "01-exports" in (reg.get("lanes") or {})


def test_build_pack():
    man = build_drive_pack(max_exports=5)
    assert man["copied_count"] >= 3
    assert man.get("grok_bridge_url")
