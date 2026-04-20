"""Unit tests for lib.foundry.client."""

from __future__ import annotations

from unittest import mock

import pytest

from lib.foundry.client import (
    FoundryAPIError,
    FoundryAuth,
    FoundryAuthError,
    FoundryClient,
    FoundryConfigError,
    FoundryError,
)


@pytest.fixture(autouse=True)
def _isolate_secrets(tmp_path, monkeypatch):
    """Point SAPPHIRE_SECRETS_DIR at an empty tmp dir so tests don't read the
    real ~/.config/sapphire-secrets/ files on the developer machine."""
    monkeypatch.setenv("SAPPHIRE_SECRETS_DIR", str(tmp_path))


# ---------------------------------------------------------------------------
# FoundryAuth
# ---------------------------------------------------------------------------


class TestFoundryAuth:
    def test_from_env_token(self, monkeypatch):
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://foundry.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "tok-abc")
        auth = FoundryAuth.from_env()
        assert auth.base_url == "https://foundry.example.com"
        assert auth.token == "tok-abc"
        assert auth.auth_mode == "token"

    def test_from_env_token_alt_vars(self, monkeypatch):
        monkeypatch.setenv("FOUNDRY_URL", "https://f2.example.com/")
        monkeypatch.setenv("FOUNDRY_TOKEN", "tok-xyz")
        auth = FoundryAuth.from_env()
        assert auth.base_url == "https://f2.example.com"  # trailing slash stripped
        assert auth.token == "tok-xyz"

    def test_from_env_oauth(self, monkeypatch):
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://foundry.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_CLIENT_ID", "cid")
        monkeypatch.setenv("PALANTIR_FOUNDRY_CLIENT_SECRET", "csecret")
        auth = FoundryAuth.from_env()
        assert auth.auth_mode == "oauth"
        assert auth.client_id == "cid"
        assert auth.client_secret == "csecret"

    def test_from_env_no_url_raises(self, monkeypatch):
        monkeypatch.delenv("PALANTIR_FOUNDRY_URL", raising=False)
        monkeypatch.delenv("FOUNDRY_URL", raising=False)
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "tok")
        with pytest.raises(FoundryConfigError, match="No Foundry URL"):
            FoundryAuth.from_env()

    def test_from_env_no_creds_raises(self, monkeypatch):
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        # Clear all credential vars
        for v in ("PALANTIR_FOUNDRY_TOKEN", "FOUNDRY_TOKEN", "FOUNDRY_API_TOKEN",
                   "PALANTIR_FOUNDRY_CLIENT_ID", "FOUNDRY_CLIENT_ID",
                   "PALANTIR_FOUNDRY_CLIENT_SECRET", "FOUNDRY_CLIENT_SECRET"):
            monkeypatch.delenv(v, raising=False)
        with pytest.raises(FoundryConfigError, match="No Foundry credentials"):
            FoundryAuth.from_env()

    def test_bearer_token_returns_static_token(self, monkeypatch):
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "static-tok")
        auth = FoundryAuth.from_env()
        assert auth.bearer_token() == "static-tok"


# ---------------------------------------------------------------------------
# FoundryClient
# ---------------------------------------------------------------------------


class TestFoundryClientHealth:
    def test_health_success(self, monkeypatch):
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "tok")
        client = FoundryClient.from_env()

        # Mock _get to simulate a successful response
        client._get = mock.Mock(return_value={"data": []})
        result = client.health()
        assert result["ok"] is True
        assert result["auth_mode"] == "token"

    def test_health_api_error(self, monkeypatch):
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "tok")
        client = FoundryClient.from_env()

        client._get = mock.Mock(side_effect=FoundryAPIError("fail", status=401))
        result = client.health()
        assert result["ok"] is False
        assert result["status"] == 401


class TestFoundryClientDatasets:
    def _make_client(self, monkeypatch):
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "tok")
        return FoundryClient.from_env()

    def test_get_dataset(self, monkeypatch):
        client = self._make_client(monkeypatch)
        client._get = mock.Mock(return_value={"rid": "ri.foundry..dataset.abc"})
        result = client.get_dataset("ri.foundry..dataset.abc")
        client._get.assert_called_once_with("/api/v2/datasets/ri.foundry..dataset.abc")
        assert result["rid"] == "ri.foundry..dataset.abc"

    def test_list_datasets(self, monkeypatch):
        client = self._make_client(monkeypatch)
        client._get = mock.Mock(return_value={"data": []})
        client.list_datasets(page_size=10)
        client._get.assert_called_once_with("/api/v2/datasets", params={"pageSize": "10"})

    def test_create_dataset(self, monkeypatch):
        client = self._make_client(monkeypatch)
        client._post = mock.Mock(return_value={"rid": "new"})
        client.create_dataset("test-ds", "ri.foundry..folder.root")
        client._post.assert_called_once()

    def test_upsert_objects(self, monkeypatch):
        client = self._make_client(monkeypatch)
        client._post = mock.Mock(return_value={"editedObjectTypes": ["PaperTrade"]})
        objects = [{"id": "1", "symbol": "BTC"}]
        client.upsert_objects("PaperTrade", objects)
        call_args = client._post.call_args
        assert "sapphire-upsert" in call_args[0][0]

    def test_search_objects(self, monkeypatch):
        client = self._make_client(monkeypatch)
        client._post = mock.Mock(return_value={"data": []})
        client.search_objects("PaperTrade", {"type": "eq", "field": "symbol", "value": "BTC"})
        client._post.assert_called_once()


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestSecretsDirFallback:
    def test_url_resolved_from_secrets_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("PALANTIR_FOUNDRY_URL", raising=False)
        monkeypatch.delenv("FOUNDRY_URL", raising=False)
        monkeypatch.setenv("SAPPHIRE_SECRETS_DIR", str(tmp_path))
        (tmp_path / "foundry_url").write_text("https://kadima.example.com\n")
        (tmp_path / "foundry_token").write_text("secret-tok\n")
        auth = FoundryAuth.from_env()
        assert auth.base_url == "https://kadima.example.com"
        assert auth.token == "secret-tok"

    def test_env_takes_precedence_over_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAPPHIRE_SECRETS_DIR", str(tmp_path))
        (tmp_path / "foundry_url").write_text("https://file.example.com")
        (tmp_path / "foundry_token").write_text("file-tok")
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://env.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "env-tok")
        auth = FoundryAuth.from_env()
        assert auth.base_url == "https://env.example.com"
        assert auth.token == "env-tok"

    def test_missing_files_raises_config_error(self, monkeypatch, tmp_path):
        monkeypatch.delenv("PALANTIR_FOUNDRY_URL", raising=False)
        monkeypatch.delenv("FOUNDRY_URL", raising=False)
        monkeypatch.setenv("SAPPHIRE_SECRETS_DIR", str(tmp_path))
        with pytest.raises(FoundryConfigError, match="No Foundry URL"):
            FoundryAuth.from_env()


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(FoundryConfigError, FoundryError)
        assert issubclass(FoundryAuthError, FoundryError)
        assert issubclass(FoundryAPIError, FoundryError)

    def test_api_error_attrs(self):
        err = FoundryAPIError("test", status=404, body='{"error":"not found"}')
        assert err.status == 404
        assert "not found" in err.body
