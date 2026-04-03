import asyncio
import importlib.util
import sys
import types
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
TWITTER_PATH = ROOT_DIR / "services/alpha/src/media/twitter.py"
SUBSTACK_PATH = ROOT_DIR / "services/alpha/src/media/substack.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _install_tweepy_stub(monkeypatch):
    stub = types.SimpleNamespace()

    class _DummyClient:
        def __init__(self, *args, **kwargs):
            pass

    class _DummyOAuth1:
        def __init__(self, *args, **kwargs):
            pass

    class _DummyApi:
        def __init__(self, *args, **kwargs):
            pass

    stub.Client = _DummyClient
    stub.OAuth1UserHandler = _DummyOAuth1
    stub.API = _DummyApi
    monkeypatch.setitem(sys.modules, "tweepy", stub)


def _install_aiohttp_stub(monkeypatch):
    stub = types.SimpleNamespace()

    class _DummyTimeout:
        def __init__(self, *args, **kwargs):
            pass

    class _DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    stub.ClientTimeout = _DummyTimeout
    stub.ClientSession = _DummySession
    monkeypatch.setitem(sys.modules, "aiohttp", stub)


def _install_loguru_stub(monkeypatch):
    class _Logger:
        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

    stub = types.SimpleNamespace(logger=_Logger())
    monkeypatch.setitem(sys.modules, "loguru", stub)


def test_twitter_client_parses_blob_short_keys(monkeypatch):
    _install_tweepy_stub(monkeypatch)
    _install_loguru_stub(monkeypatch)
    twitter_module = _load_module(TWITTER_PATH, "sapphire_twitter")
    monkeypatch.setenv("SAPPHIRE_TWITTER_API_TOKEN", "Ck ck_value\nSk sk_value\nBear bear_value\naccess token: at_value\naccess token secret: as_value")
    monkeypatch.delenv("SAPPHIRE_TWITTER_API_KEY", raising=False)
    monkeypatch.delenv("SAPPHIRE_TWITTER_API_SECRET", raising=False)
    monkeypatch.delenv("SAPPHIRE_TWITTER_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SAPPHIRE_TWITTER_ACCESS_SECRET", raising=False)
    monkeypatch.delenv("SAPPHIRE_TWITTER_BEARER_TOKEN", raising=False)

    client = twitter_module.TwitterClient()

    assert client.api_key == "ck_value"
    assert client.api_secret == "sk_value"
    assert client.access_token == "at_value"
    assert client.access_secret == "as_value"
    assert client.bearer_token == "bear_value"


def test_twitter_thread_splitter_obeys_limit(monkeypatch):
    _install_tweepy_stub(monkeypatch)
    _install_loguru_stub(monkeypatch)
    twitter_module = _load_module(TWITTER_PATH, "sapphire_twitter_split")
    monkeypatch.setenv("SAPPHIRE_MEDIA_TWITTER_ENABLED", "false")
    client = twitter_module.TwitterClient()

    text = "word " * 200
    parts = client._split_thread(text.strip(), limit=50)

    assert len(parts) > 1
    assert all(len(p) <= 50 for p in parts)


def test_substack_email_mode_ready(monkeypatch):
    _install_aiohttp_stub(monkeypatch)
    _install_loguru_stub(monkeypatch)
    substack_module = _load_module(SUBSTACK_PATH, "sapphire_substack_email")
    monkeypatch.setenv("SAPPHIRE_MEDIA_SUBSTACK_ENABLED", "true")
    monkeypatch.setenv("SAPPHIRE_SUBSTACK_PUBLICATION_EMAIL", "publish@example.com")
    monkeypatch.setenv("SAPPHIRE_SUBSTACK_FROM_EMAIL", "bot@example.com")
    monkeypatch.setenv("SAPPHIRE_SUBSTACK_SMTP_HOST", "smtp.example.com")

    client = substack_module.SubstackClient()
    asyncio.run(client.start())

    assert client.ready is True
    assert client.mode == "email"


def test_substack_webhook_mode_ready(monkeypatch):
    _install_aiohttp_stub(monkeypatch)
    _install_loguru_stub(monkeypatch)
    substack_module = _load_module(SUBSTACK_PATH, "sapphire_substack_webhook")
    monkeypatch.setenv("SAPPHIRE_MEDIA_SUBSTACK_ENABLED", "true")
    monkeypatch.setenv("SAPPHIRE_MEDIA_SUBSTACK_POST_URL", "https://example.com/substack/hook")

    client = substack_module.SubstackClient()
    asyncio.run(client.start())

    assert client.ready is True
    assert client.mode == "webhook"
