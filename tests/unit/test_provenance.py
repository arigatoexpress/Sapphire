from __future__ import annotations

import copy
import json

from lib.core.provenance import ProvenanceEnvelope, stamp, verify, write_envelope_sidecar


def test_stamp_empty_payload_verifies() -> None:
    stamped = stamp({}, generator="unit-test")

    assert stamped["provenance"]["schema_version"] == 1
    assert verify(stamped) is True


def test_stamp_big_payload_is_deterministic() -> None:
    payload = {"rows": [{"i": i, "value": f"row-{i}"} for i in range(500)]}
    stamped = stamp(payload, generator="unit-test", ttl_seconds=60)

    assert verify(stamped) is True
    assert stamped["provenance"]["ttl_seconds"] == 60
    assert (
        stamped["provenance"]["payload_hash"]
        == ProvenanceEnvelope.build(payload, generator="unit-test", ttl_seconds=60).payload_hash
    )


def test_payload_mutation_invalidates_stamp() -> None:
    stamped = stamp({"answer": 42}, generator="unit-test")
    mutated = copy.deepcopy(stamped)
    mutated["answer"] = 43

    assert verify(stamped) is True
    assert verify(mutated) is False


def test_envelope_mutation_invalidates_stamp() -> None:
    stamped = stamp({"answer": 42}, generator="unit-test")
    mutated = copy.deepcopy(stamped)
    mutated["provenance"]["generator"] = "other"

    assert verify(mutated) is False


def test_schema_version_one_is_accepted_and_future_version_rejected() -> None:
    stamped = stamp({"answer": 42}, generator="unit-test")
    future = copy.deepcopy(stamped["provenance"])
    future["schema_version"] = 2

    assert verify(stamped) is True
    assert verify(future) is False


def test_sidecar_records_file_hash_and_verifies(tmp_path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps({"ok": True}), encoding="utf-8")

    sidecar = write_envelope_sidecar(artifact, generator="unit-test")
    data = json.loads(sidecar.read_text(encoding="utf-8"))

    assert data["artifact_path"].endswith("artifact.json")
    assert data["artifact_sha256"]
    assert verify(data) is True
