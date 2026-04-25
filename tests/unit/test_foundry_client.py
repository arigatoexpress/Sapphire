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
    for name in (
        "PALANTIR_FOUNDRY_URL",
        "FOUNDRY_URL",
        "PALANTIR_FOUNDRY_TOKEN",
        "FOUNDRY_TOKEN",
        "FOUNDRY_API_TOKEN",
        "PALANTIR_FOUNDRY_CLIENT_ID",
        "FOUNDRY_CLIENT_ID",
        "PALANTIR_FOUNDRY_CLIENT_SECRET",
        "FOUNDRY_CLIENT_SECRET",
        "PALANTIR_FOUNDRY_ONTOLOGY",
        "FOUNDRY_ONTOLOGY",
        "PALANTIR_FOUNDRY_UPSERT_ACTION",
        "FOUNDRY_UPSERT_ACTION",
        "PALANTIR_FOUNDRY_WRITE_MODE",
        "FOUNDRY_WRITE_MODE",
        "PALANTIR_FOUNDRY_DATASET_MAP",
        "FOUNDRY_DATASET_MAP",
    ):
        monkeypatch.delenv(name, raising=False)
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
        assert result["ontologies_accessible"] is True

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
        assert call_args[0][0] == "/api/v2/ontologies/ontology/actions/sapphire-upsert/apply"

    def test_upsert_objects_uses_configured_ontology_and_action(self, monkeypatch):
        monkeypatch.setenv("PALANTIR_FOUNDRY_ONTOLOGY", "sapphire-ops")
        monkeypatch.setenv("PALANTIR_FOUNDRY_UPSERT_ACTION", "bulk-upsert-v2")
        client = self._make_client(monkeypatch)
        client._post = mock.Mock(return_value={"editedObjectTypes": ["ServiceHealth"]})

        client.upsert_objects("ServiceHealth", [{"id": "svc-1"}])

        call_args = client._post.call_args
        assert call_args[0][0] == "/api/v2/ontologies/sapphire-ops/actions/bulk-upsert-v2/apply"

    def test_list_actions_uses_configured_ontology(self, monkeypatch):
        monkeypatch.setenv("FOUNDRY_ONTOLOGY", "sapphire-prod")
        client = self._make_client(monkeypatch)
        client._get = mock.Mock(return_value={"data": []})

        client.list_actions()

        client._get.assert_called_once_with("/api/v2/ontologies/sapphire-prod/actionTypes")

    def test_validate_upsert_target_accepts_configured_action(self, monkeypatch):
        monkeypatch.setenv("FOUNDRY_ONTOLOGY", "sapphire-prod")
        monkeypatch.setenv("FOUNDRY_UPSERT_ACTION", "bulk-upsert")
        client = self._make_client(monkeypatch)
        client._get = mock.Mock(side_effect=[
            {"data": [{"apiName": "sapphire-prod", "rid": "ri.ontology.main.ontology.1"}]},
            {"data": [{"apiName": "bulk-upsert", "rid": "ri.action.main.action.1"}]},
        ])

        client.validate_upsert_target()

        assert client._get.call_args_list[0].args[0] == "/api/v2/ontologies"
        assert client._get.call_args_list[1].args[0] == (
            "/api/v2/ontologies/sapphire-prod/actionTypes"
        )

    def test_validate_upsert_target_raises_when_ontology_missing(self, monkeypatch):
        monkeypatch.setenv("FOUNDRY_ONTOLOGY", "missing")
        client = self._make_client(monkeypatch)
        client._get = mock.Mock(return_value={"data": [{"apiName": "default"}]})

        with pytest.raises(FoundryConfigError, match="Configured Foundry ontology"):
            client.validate_upsert_target()

    def test_validate_upsert_target_raises_when_action_missing(self, monkeypatch):
        monkeypatch.setenv("FOUNDRY_ONTOLOGY", "default")
        monkeypatch.setenv("FOUNDRY_UPSERT_ACTION", "sapphire-upsert")
        client = self._make_client(monkeypatch)
        client._get = mock.Mock(side_effect=[
            {"data": [{"apiName": "default"}]},
            {"data": [{"apiName": "other-action"}]},
        ])

        with pytest.raises(FoundryConfigError, match="Configured Foundry upsert action"):
            client.validate_upsert_target()

    def test_search_objects(self, monkeypatch):
        client = self._make_client(monkeypatch)
        client._post = mock.Mock(return_value={"data": []})
        client.search_objects("PaperTrade", {"type": "eq", "field": "symbol", "value": "BTC"})
        client._post.assert_called_once()

    def test_write_mode_and_dataset_map_resolved_from_env(self, monkeypatch):
        monkeypatch.setenv("FOUNDRY_WRITE_MODE", "dataset")
        monkeypatch.setenv(
            "FOUNDRY_DATASET_MAP",
            '{"PaperTrade":"ri.foundry.main.dataset.paper"}',
        )
        client = self._make_client(monkeypatch)

        assert client.write_mode == "dataset"
        assert client.dataset_map == {"PaperTrade": "ri.foundry.main.dataset.paper"}

    def test_invalid_write_mode_raises(self, monkeypatch):
        monkeypatch.setenv("FOUNDRY_WRITE_MODE", "spaceship")

        with pytest.raises(FoundryConfigError, match="Invalid Foundry write mode"):
            self._make_client(monkeypatch)

    def test_invalid_dataset_map_json_raises(self, monkeypatch):
        monkeypatch.setenv("FOUNDRY_DATASET_MAP", "not-json")

        with pytest.raises(FoundryConfigError, match="dataset map"):
            self._make_client(monkeypatch)

    def test_upload_dataset_objects_uses_configured_dataset(self, monkeypatch):
        client = self._make_client(monkeypatch)
        client.dataset_map = {"PaperTrade": "ri.foundry.main.dataset.paper"}
        client.upload_dataset_file = mock.Mock(return_value={})

        result = client.upload_dataset_objects("PaperTrade", [{"id": "1"}])

        client.upload_dataset_file.assert_called_once()
        args, kwargs = client.upload_dataset_file.call_args
        assert args[0] == "ri.foundry.main.dataset.paper"
        assert args[1] == "sapphire_sync/PaperTrade.jsonl"
        assert '{"id": "1"}' in args[2]
        assert kwargs["branch"] == "master"
        assert result["objects_uploaded"] == 1

    def test_upload_dataset_file_encodes_nested_file_path(self, monkeypatch):
        client = self._make_client(monkeypatch)
        seen_urls: list[str] = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_exc_info):
                return False

            def read(self):
                return b'{"path":"sapphire_sync/PaperTrade.jsonl"}'

        def fake_urlopen(req, **_kwargs):
            seen_urls.append(req.full_url)
            return FakeResponse()

        monkeypatch.setattr("lib.foundry.client.urllib.request.urlopen", fake_urlopen)

        client.upload_dataset_file(
            "ri.foundry.main.dataset.paper",
            "sapphire_sync/PaperTrade.jsonl",
            "{}\n",
        )

        assert "files/sapphire_sync%2FPaperTrade.jsonl/upload" in seen_urls[0]

    def test_upload_dataset_objects_raises_when_mapping_missing(self, monkeypatch):
        client = self._make_client(monkeypatch)

        with pytest.raises(FoundryConfigError, match="No Foundry dataset RID"):
            client.upload_dataset_objects("PaperTrade", [{"id": "1"}])

    def test_validate_dataset_target_accepts_configured_resources(self, monkeypatch):
        monkeypatch.setenv("FOUNDRY_ONTOLOGY", "sapphire-prod")
        client = self._make_client(monkeypatch)
        client.dataset_map = {"PaperTrade": "ri.foundry.main.dataset.paper"}
        client._get = mock.Mock(side_effect=[
            {"data": [{"apiName": "sapphire-prod", "rid": "ri.ontology.main.ontology.1"}]},
            {"data": [{"apiName": "PaperTrade", "rid": "ri.ontology.main.object-type.1"}]},
            {"rid": "ri.foundry.main.dataset.paper"},
        ])

        client.validate_dataset_target(["PaperTrade"])

        assert client._get.call_args_list[0].args[0] == "/api/v2/ontologies"
        assert client._get.call_args_list[1].args[0] == (
            "/api/v2/ontologies/sapphire-prod/objectTypes"
        )
        assert client._get.call_args_list[2].args[0] == (
            "/api/v2/datasets/ri.foundry.main.dataset.paper"
        )

    def test_validate_dataset_target_raises_when_object_type_missing(self, monkeypatch):
        client = self._make_client(monkeypatch)
        client.dataset_map = {"PaperTrade": "ri.foundry.main.dataset.paper"}
        client._get = mock.Mock(side_effect=[
            {"data": [{"apiName": "ontology"}]},
            {"data": [{"apiName": "OtherType"}]},
        ])

        with pytest.raises(FoundryConfigError, match="object type"):
            client.validate_dataset_target(["PaperTrade"])


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

    def test_ontology_and_action_resolved_from_secrets_files(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAPPHIRE_SECRETS_DIR", str(tmp_path))
        (tmp_path / "foundry_url").write_text("https://kadima.example.com\n")
        (tmp_path / "foundry_token").write_text("secret-tok\n")
        (tmp_path / "foundry_ontology").write_text("sapphire-prod\n")
        (tmp_path / "foundry_upsert_action").write_text("bulk-upsert\n")
        (tmp_path / "foundry_write_mode").write_text("dataset\n")
        (tmp_path / "foundry_dataset_map").write_text(
            '{"PaperTrade":"ri.foundry.main.dataset.paper"}\n'
        )

        client = FoundryClient.from_env()

        assert client.ontology == "sapphire-prod"
        assert client.upsert_action == "bulk-upsert"
        assert client.write_mode == "dataset"
        assert client.dataset_map == {"PaperTrade": "ri.foundry.main.dataset.paper"}


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(FoundryConfigError, FoundryError)
        assert issubclass(FoundryAuthError, FoundryError)
        assert issubclass(FoundryAPIError, FoundryError)

    def test_api_error_attrs(self):
        err = FoundryAPIError("test", status=404, body='{"error":"not found"}')
        assert err.status == 404
        assert "not found" in err.body
