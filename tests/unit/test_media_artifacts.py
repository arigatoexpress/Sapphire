"""Tests for local media artifact manifest/provenance helpers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from lib.media import artifact_record, load_manifest, make_run_id, sha256_file, write_manifest


def test_make_run_id_is_date_kind_slug_stable():
    run_id = make_run_id(
        "Podcast Episode",
        "Austin Market: Week 17",
        when=datetime(2026, 4, 27, 9, 30, tzinfo=UTC),
    )

    assert run_id == "20260427_podcast_episode_austin_market_week_17"


def test_artifact_record_hashes_existing_file(tmp_path):
    output = tmp_path / "episode.wav"
    output.write_bytes(b"fake audio bytes")

    record = artifact_record(
        output,
        root=tmp_path,
        role="output",
        media_kind="audio",
        duration_seconds=12.5,
    )

    assert record["path"] == "episode.wav"
    assert record["role"] == "output"
    assert record["media_kind"] == "audio"
    assert record["mime_type"] == "audio/x-wav"
    assert record["bytes"] == len(b"fake audio bytes")
    assert record["sha256"] == hashlib.sha256(b"fake audio bytes").hexdigest()
    assert record["duration_seconds"] == 12.5


def test_sha256_file_streams_content(tmp_path):
    artifact = tmp_path / "clip.txt"
    artifact.write_text("hello")

    assert sha256_file(artifact) == hashlib.sha256(b"hello").hexdigest()


def test_artifact_record_requires_real_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        artifact_record(tmp_path / "missing.mp4", root=tmp_path, role="output", media_kind="video")


def test_write_manifest_records_inputs_outputs_and_loads(tmp_path):
    source = tmp_path / "transcript.txt"
    rendered = tmp_path / "episode.mp3"
    source.write_text("transcript")
    rendered.write_bytes(b"mp3 bytes")
    manifest_root = tmp_path / "manifests"

    manifest = write_manifest(
        kind="podcast episode",
        slug="Regional Intelligence Pilot",
        media_kind="audio",
        inputs=[source],
        outputs=[rendered],
        root=tmp_path,
        manifest_root=manifest_root,
        dry_run=True,
        approval_status="pending",
        metadata={"operator": "local-test"},
        created_at=datetime(2026, 4, 27, 10, 0, tzinfo=UTC),
    )

    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == "20260427_podcast_episode_regional_intelligence_pilot"
    assert manifest["dry_run"] is True
    assert manifest["approval_status"] == "pending"
    assert manifest["inputs"][0]["path"] == "transcript.txt"
    assert manifest["outputs"][0]["path"] == "episode.mp3"
    assert manifest["metadata"] == {"operator": "local-test"}
    assert (
        manifest["manifest_path"]
        == "manifests/20260427_podcast_episode_regional_intelligence_pilot.json"
    )

    loaded = load_manifest(
        manifest_root / "20260427_podcast_episode_regional_intelligence_pilot.json"
    )
    assert loaded["run_id"] == manifest["run_id"]
    assert "manifest_path" not in loaded


def test_write_manifest_accepts_prebuilt_records(tmp_path):
    rendered = tmp_path / "cover.png"
    rendered.write_bytes(b"png-ish")

    manifest = write_manifest(
        kind="image",
        slug="cover",
        media_kind="image",
        inputs=[
            {
                "path": "prompt.txt",
                "role": "input",
                "media_kind": "text",
                "sha256": "provided",
            }
        ],
        outputs=[rendered],
        root=tmp_path,
        manifest_root=tmp_path / "manifests",
        created_at=datetime(2026, 4, 27, tzinfo=UTC),
    )

    assert manifest["inputs"][0]["sha256"] == "provided"
    assert manifest["outputs"][0]["role"] == "output"
