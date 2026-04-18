"""Tests for the live publisher clients + the auto_publish orchestrator.

Every HTTP call is monkey-patched — nothing hits the real network.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from lib.content import auto_publish
from lib.content.publishers import (
    LinkedInClient,
    SubstackClient,
    TypefullyClient,
    XClient,
    base,
    load_client,
)

# --- base behaviour ---------------------------------------------------------


def test_dry_run_is_default(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_PUBLISH_LIVE", raising=False)
    c = LinkedInClient()
    assert c.dry_run is True


def test_live_mode_requires_credentials(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PUBLISH_LIVE", "1")
    monkeypatch.delenv("LINKEDIN_ACCESS_TOKEN", raising=False)
    result = LinkedInClient().publish(text="hello")
    assert result.ok is False
    assert "LINKEDIN_ACCESS_TOKEN" in (result.error or "")


def test_dry_run_returns_preview(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_PUBLISH_LIVE", raising=False)
    result = LinkedInClient().publish(text="hello")
    assert result.ok is True
    assert result.dry_run is True
    assert result.request_preview == {"text": "hello"}


def test_client_never_raises(monkeypatch):
    """Exceptions inside _publish become ok=False results."""
    monkeypatch.setenv("SAPPHIRE_PUBLISH_LIVE", "1")
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINKEDIN_AUTHOR_URN", "urn:li:person:abc")

    def boom(self, *a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(LinkedInClient, "_http_json", boom)
    result = LinkedInClient().publish(text="x")
    assert result.ok is False
    assert "boom" in (result.error or "")


# --- LinkedIn ---------------------------------------------------------------


def test_linkedin_post_builds_ugc_body(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PUBLISH_LIVE", "1")
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINKEDIN_AUTHOR_URN", "urn:li:person:abc")

    captured = {}

    def fake(self, url, *, method, headers, body):
        captured.update({"url": url, "method": method, "headers": headers, "body": body})
        return 201, {"id": "urn:li:share:7000"}

    monkeypatch.setattr(LinkedInClient, "_http_json", fake)
    result = LinkedInClient().publish(text="Hello world", visibility="PUBLIC")
    assert result.ok
    assert result.remote_id == "urn:li:share:7000"
    assert captured["body"]["author"] == "urn:li:person:abc"
    assert captured["body"]["specificContent"]["com.linkedin.ugc.ShareContent"][
        "shareCommentary"
    ]["text"] == "Hello world"


def test_linkedin_requires_author_urn(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PUBLISH_LIVE", "1")
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "tok")
    monkeypatch.delenv("LINKEDIN_AUTHOR_URN", raising=False)
    result = LinkedInClient().publish(text="x")
    assert result.ok is False
    assert "LINKEDIN_AUTHOR_URN" in (result.error or "")


# --- X ---------------------------------------------------------------------


def test_x_configured_requires_full_oauth_quartet(monkeypatch):
    for var in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"):
        monkeypatch.delenv(var, raising=False)
    c = XClient()
    assert c.configured() is False

    monkeypatch.setenv("X_API_KEY", "a")
    monkeypatch.setenv("X_API_SECRET", "b")
    monkeypatch.setenv("X_ACCESS_TOKEN", "c")
    monkeypatch.setenv("X_ACCESS_SECRET", "d")
    assert XClient().configured() is True


def test_x_empty_thread_fails(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PUBLISH_LIVE", "1")
    for var in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"):
        monkeypatch.setenv(var, "x")
    result = XClient().publish(tweets=[])
    assert result.ok is False
    assert "empty" in (result.error or "").lower()


# --- Substack ---------------------------------------------------------------


def test_substack_configured_checks_all_three(monkeypatch):
    for var in ("RESEND_API_KEY", "SUBSTACK_POST_EMAIL", "RESEND_FROM_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    assert SubstackClient().configured() is False
    monkeypatch.setenv("RESEND_API_KEY", "rk")
    assert SubstackClient().configured() is False
    monkeypatch.setenv("SUBSTACK_POST_EMAIL", "p@x.com")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "f@kadima.digital")
    assert SubstackClient().configured() is True


def test_substack_sends_via_resend(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PUBLISH_LIVE", "1")
    monkeypatch.setenv("RESEND_API_KEY", "rk")
    monkeypatch.setenv("SUBSTACK_POST_EMAIL", "post@kadima.substack.com")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "press@kadima.digital")

    captured = {}

    def fake(self, url, *, method, headers, body):
        captured["url"] = url
        captured["body"] = body
        captured["auth"] = headers.get("Authorization")
        return 200, {"id": "resend-email-id-9"}

    monkeypatch.setattr(SubstackClient, "_http_json", fake)
    result = SubstackClient().publish(
        title="Weekly Signal", body_html="<p>hi</p>", body_text="hi"
    )
    assert result.ok
    assert result.remote_id == "resend-email-id-9"
    assert captured["body"]["to"] == ["post@kadima.substack.com"]
    assert captured["body"]["subject"] == "Weekly Signal"
    assert captured["auth"] == "Bearer rk"


# --- Typefully -------------------------------------------------------------


def test_typefully_posts_thread(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PUBLISH_LIVE", "1")
    monkeypatch.setenv("TYPEFULLY_API_KEY", "tk")

    captured = {}

    def fake(self, url, *, method, headers, body):
        captured["body"] = body
        captured["auth"] = headers.get("X-API-KEY")
        return 200, {"id": 42, "share_url": "https://typefully.com/x/42"}

    monkeypatch.setattr(TypefullyClient, "_http_json", fake)
    result = TypefullyClient().publish(tweets=["one", "two", "three"])
    assert result.ok
    assert result.url == "https://typefully.com/x/42"
    assert captured["body"]["content"] == "one\n\n\n\ntwo\n\n\n\nthree"
    assert captured["auth"] == "tk"


# --- Registry --------------------------------------------------------------


def test_load_client_registry():
    assert isinstance(load_client("linkedin"), LinkedInClient)
    assert isinstance(load_client("substack"), SubstackClient)
    assert isinstance(load_client("x"), XClient)
    assert isinstance(load_client("typefully"), TypefullyClient)
    assert load_client("bogus") is None


# --- auto_publish orchestrator --------------------------------------------


@pytest.fixture()
def fake_ready(tmp_path: Path, monkeypatch):
    ready = tmp_path / "ready"
    (ready / "linkedin").mkdir(parents=True)
    (ready / "substack").mkdir(parents=True)
    (ready / "x").mkdir(parents=True)
    ledger = tmp_path / "published_ledger.json"

    # three files, same kind, newest should win
    stamp_old = (datetime.now() - timedelta(hours=36)).strftime("%Y%m%d_%H%M")
    stamp_new = datetime.now().strftime("%Y%m%d_%H%M")
    stamp_stale = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d_%H%M")

    (ready / "linkedin" / f"{stamp_new}_weekly_crypto_brief.md").write_text("# New post\nbody")
    (ready / "linkedin" / f"{stamp_old}_weekly_crypto_brief.md").write_text("# Old post\nbody")
    (ready / "linkedin" / f"{stamp_stale}_weekly_crypto_brief.md").write_text("# stale")

    (ready / "substack" / f"{stamp_new}_weekly_crypto_brief.md").write_text(
        "# Substack title\npara"
    )

    (ready / "x" / f"{stamp_new}_market_pulse.jsonl").write_text(
        json.dumps({"index": 0, "text": "tweet one"})
        + "\n"
        + json.dumps({"index": 1, "text": "tweet two"})
        + "\n"
    )

    monkeypatch.setattr(auto_publish, "READY_ROOT", ready)
    monkeypatch.setattr(auto_publish, "LEDGER_PATH", ledger)
    return ready, ledger


def test_discover_picks_newest_and_respects_window(fake_ready):
    ready, ledger = fake_ready
    items = auto_publish.discover()
    # linkedin weekly_crypto_brief (newest), substack weekly_crypto_brief, x market_pulse
    by_platform = {i.platform: i for i in items}
    assert set(by_platform) == {"linkedin", "substack", "x"}
    # newest (not old, not stale)
    assert "20" in by_platform["linkedin"].path.name
    # stale file must be excluded
    assert not any("stale" in i.path.read_text() for i in items)


def test_discover_skips_already_published(fake_ready, monkeypatch):
    ready, ledger_path = fake_ready
    # Pre-populate ledger with the linkedin rendering
    items_before = auto_publish.discover()
    li_item = next(i for i in items_before if i.platform == "linkedin")
    ledger = {auto_publish._ledger_key(li_item): {"published_at": "x"}}
    ledger_path.write_text(json.dumps(ledger))

    items_after = auto_publish.discover()
    assert not any(i.platform == "linkedin" for i in items_after)


def test_dispatch_one_loads_tweets_from_jsonl(fake_ready, monkeypatch):
    items = auto_publish.discover()
    x_item = next(i for i in items if i.platform == "x")

    monkeypatch.delenv("SAPPHIRE_PUBLISH_LIVE", raising=False)  # keep dry-run
    result = auto_publish.dispatch_one(x_item)
    assert result.ok
    assert result.dry_run
    assert result.request_preview["tweets"] == ["tweet one", "tweet two"]


def test_run_end_to_end_dry(fake_ready, monkeypatch):
    monkeypatch.delenv("SAPPHIRE_PUBLISH_LIVE", raising=False)

    # Silence telegram + event bus
    monkeypatch.setattr(auto_publish, "_emit_event", lambda *a, **k: None)
    monkeypatch.setattr(auto_publish, "_telegram_summary", lambda *a, **k: None)

    out = auto_publish.run()
    platforms = {item["item"]["platform"] for item in out["items"]}
    assert platforms == {"linkedin", "substack", "x"}
    assert all(item["result"]["dry_run"] for item in out["items"])


def test_run_writes_ledger_only_for_live_success(fake_ready, monkeypatch):
    ready, ledger_path = fake_ready
    monkeypatch.setattr(auto_publish, "_emit_event", lambda *a, **k: None)
    monkeypatch.setattr(auto_publish, "_telegram_summary", lambda *a, **k: None)

    # Live mode, but _publish is stubbed to return ok=True fake response
    monkeypatch.setenv("SAPPHIRE_PUBLISH_LIVE", "1")
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("LINKEDIN_AUTHOR_URN", "urn:li:person:abc")
    monkeypatch.setenv("RESEND_API_KEY", "rk")
    monkeypatch.setenv("SUBSTACK_POST_EMAIL", "p@s.com")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "f@k.digital")

    def fake_http(self, *a, **k):
        return 200, {"id": "remote-123"}

    monkeypatch.setattr(base.PublisherClient, "_http_json", fake_http)
    auto_publish.run(platforms=["linkedin", "substack"])

    ledger = json.loads(ledger_path.read_text())
    assert len(ledger) == 2
    for entry in ledger.values():
        assert entry["remote_id"] == "remote-123"
    # re-running should find nothing new
    out2 = auto_publish.run(platforms=["linkedin", "substack"])
    assert out2["items"] == []
