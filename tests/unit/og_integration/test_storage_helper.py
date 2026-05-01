"""Tests for lib.og.storage — subprocess bridge to the Node helper.

We don't have the @0gfoundation/0g-ts-sdk installed in CI, so we mock the
subprocess. The tests verify the Python contract: env vars set correctly,
subprocess output parsed correctly, errors surfaced as OGStorageError.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from lib.og import storage


class _FakeCompleted:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@pytest.fixture
def fake_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Place a stub helper file on disk so the existence check passes."""
    helper = tmp_path / "og_storage.mjs"
    helper.write_text("// stub")
    monkeypatch.setattr(storage, "_HELPER_SCRIPT", helper)
    return helper


@pytest.fixture
def og_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OG_PRIVATE_KEY", "0x" + "11" * 32)


class TestUploadFile:
    def test_returns_root_and_tx(
        self, fake_helper: Path, og_env: None, tmp_path: Path
    ) -> None:
        target = tmp_path / "blob.bin"
        target.write_bytes(b"hi")
        captured: dict[str, Any] = {}

        def fake_run(*args, **kwargs) -> _FakeCompleted:
            captured["args"] = args[0]
            captured["env"] = kwargs.get("env", {})
            return _FakeCompleted(stdout='{"rootHash":"0xabc","txHash":"0xdeadbeef"}\n')

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = storage.upload_file(target, network="testnet")

        assert result.root_hash == "0xabc"
        assert result.tx_hash == "0xdeadbeef"
        # subprocess invoked with absolute path
        assert str(target.resolve()) in captured["args"][3]
        # env carries the network endpoints
        assert captured["env"]["OG_RPC_URL"] == "https://evmrpc-testnet.0g.ai"
        assert captured["env"]["OG_INDEXER_URL"] == "https://indexer-storage-testnet-turbo.0g.ai"

    def test_upload_without_private_key_raises(
        self, fake_helper: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("OG_PRIVATE_KEY", raising=False)
        target = tmp_path / "blob.bin"
        target.write_bytes(b"hi")
        with pytest.raises(storage.OGStorageError, match="OG_PRIVATE_KEY"):
            storage.upload_file(target)

    def test_helper_error_surfaces_as_storage_error(
        self, fake_helper: Path, og_env: None, tmp_path: Path
    ) -> None:
        target = tmp_path / "blob.bin"
        target.write_bytes(b"x")

        def fake_run(*a, **kw) -> _FakeCompleted:
            return _FakeCompleted(stdout='{"error":"indexer down"}\n', returncode=1)

        with patch.object(subprocess, "run", side_effect=fake_run):
            with pytest.raises(storage.OGStorageError, match="indexer down"):
                storage.upload_file(target)

    def test_garbage_output_is_diagnosable(
        self, fake_helper: Path, og_env: None, tmp_path: Path
    ) -> None:
        target = tmp_path / "blob.bin"
        target.write_bytes(b"x")

        def fake_run(*a, **kw) -> _FakeCompleted:
            return _FakeCompleted(stdout="not json", returncode=1)

        with patch.object(subprocess, "run", side_effect=fake_run):
            with pytest.raises(storage.OGStorageError):
                storage.upload_file(target)


class TestUploadBytes:
    def test_string_payload(self, fake_helper: Path, og_env: None) -> None:
        captured: dict[str, Any] = {}

        def fake_run(*args, **kwargs) -> _FakeCompleted:
            captured["args"] = args[0]
            return _FakeCompleted(stdout='{"rootHash":"0x01","txHash":"0x02"}')

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = storage.upload_bytes("hello world")

        assert result.root_hash == "0x01"
        assert result.tx_hash == "0x02"
        # The 4th argv is the JSON payload — verify it carries our data field
        payload = json.loads(captured["args"][3])
        assert payload["data"] == "hello world"

    def test_bytes_payload_decoded_utf8(self, fake_helper: Path, og_env: None) -> None:
        captured: dict[str, Any] = {}

        def fake_run(*args, **kwargs) -> _FakeCompleted:
            captured["args"] = args[0]
            return _FakeCompleted(stdout='{"rootHash":"0x01","txHash":"0x02"}')

        with patch.object(subprocess, "run", side_effect=fake_run):
            storage.upload_bytes("héllo".encode())

        payload = json.loads(captured["args"][3])
        assert payload["data"] == "héllo"


class TestUploadJson:
    def test_canonicalises_keys(self, fake_helper: Path, og_env: None) -> None:
        captured: dict[str, Any] = {}

        def fake_run(*args, **kwargs) -> _FakeCompleted:
            captured["args"] = args[0]
            return _FakeCompleted(stdout='{"rootHash":"0x01","txHash":"0x02"}')

        with patch.object(subprocess, "run", side_effect=fake_run):
            storage.upload_json({"b": 2, "a": 1})

        # Same keys in different order should produce same payload
        payload = json.loads(captured["args"][3])
        assert payload["data"] == '{"a":1,"b":2}'


class TestExplorerUrl:
    def test_explorer_url_uses_network(self) -> None:
        r = storage.UploadResult(root_hash="0xabc", tx_hash="0xdef")
        assert "chainscan.0g.ai" in r.explorer_url("mainnet")
        assert "chainscan-galileo.0g.ai" in r.explorer_url("testnet")
