import importlib.util
import sys
import types
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "sapphirectl.py"

sys.modules.setdefault("google", types.ModuleType("google"))
sys.modules.setdefault("google.cloud", types.ModuleType("google.cloud"))
sys.modules.setdefault("google.cloud.firestore", types.ModuleType("google.cloud.firestore"))

SPEC = importlib.util.spec_from_file_location("sapphirectl_module", SCRIPT_PATH)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


class _Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = dict(data or {})

    def to_dict(self):
        return dict(self._data)


class _DocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self._id = doc_id

    def set(self, data, merge=False):
        current = dict(self._store.get(self._id, {}))
        if merge:
            current.update(data)
            self._store[self._id] = current
        else:
            self._store[self._id] = dict(data)

    def get(self):
        return _Snap(self._id, self._store.get(self._id, {}))


class _CollectionRef:
    def __init__(self, store):
        self._store = store
        self._seq = 0

    def document(self, doc_id=None):
        if doc_id is None:
            self._seq += 1
            doc_id = f"auto-{self._seq}"
        return _DocRef(self._store, doc_id)

    def stream(self):
        return [_Snap(doc_id, data) for doc_id, data in self._store.items()]


class _FakeDB:
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        if name not in self._collections:
            self._collections[name] = {}
        return _CollectionRef(self._collections[name])

    def doc(self, collection, doc_id):
        return dict(self._collections.get(collection, {}).get(doc_id, {}))


def _make_ctl():
    ctl = MOD.SapphireCtl.__new__(MOD.SapphireCtl)
    ctl.project = "test-project"
    ctl.db = _FakeDB()
    return ctl


def test_apply_no_restart_stages_without_runtime_calls(monkeypatch):
    ctl = _make_ctl()

    def _no_run(*_args, **_kwargs):
        raise AssertionError("apply(no_restart=True) must not call _run")

    monkeypatch.setattr(ctl, "_run", _no_run)

    out = ctl.apply(
        profile="luxalgo_sol_5m_active",
        target_host="rari@test",
        run_test=True,
        close_after_test=True,
        test_quantity="0.003",
        notes="stage only",
        overrides={"ALLOW_LIVE_TRADING": "0"},
        requested_by="tester",
        no_restart=True,
    )

    assert out["applied"]["status"] == "staged_no_restart"
    assert out["applied"]["deploy"]["output"] == "skipped_no_restart"
    desired_doc = ctl.db.doc(MOD.DESIRED_COLLECTION, MOD.PLATFORM)
    assert desired_doc["state"] == "staged_no_restart"
    assert desired_doc["last_apply_status"] == "staged_no_restart"


def test_promote_no_restart_sets_stage_and_returns_staged():
    ctl = _make_ctl()
    out = ctl.promote(
        to_stage="live",
        target_host="rari@test",
        requested_by="tester",
        profile_override=None,
        test_quantity_override=None,
        run_test_override=None,
        close_after_test_override=None,
        notes="",
        extra_overrides={},
        no_restart=True,
    )
    assert out["stage"] == "live"
    assert out["result"]["applied"]["status"] == "staged_no_restart"
    desired_doc = ctl.db.doc(MOD.DESIRED_COLLECTION, MOD.PLATFORM)
    assert desired_doc["stage"] == "live"
    assert desired_doc["state"] == "staged_no_restart"


def test_reconcile_already_converged_is_noop():
    ctl = _make_ctl()
    ctl.db.collection(MOD.DESIRED_COLLECTION).document(MOD.PLATFORM).set(
        {"desired_version": "v1", "profile": "luxalgo_sol_5m_active"}
    )
    ctl.db.collection(MOD.APPLIED_COLLECTION).document(MOD.PLATFORM).set(
        {"desired_version": "v1", "status": "applied"}
    )
    out = ctl.reconcile(requested_by="tester", no_restart=True)
    assert out["reconciled"] is False
    assert out["reason"] == "already_converged"


def test_reconcile_passes_no_restart_to_apply(monkeypatch):
    ctl = _make_ctl()
    ctl.db.collection(MOD.DESIRED_COLLECTION).document(MOD.PLATFORM).set(
        {
            "desired_version": "v2",
            "profile": "luxalgo_sol_5m_active",
            "target_host": "rari@test",
            "run_test": True,
            "close_after_test": False,
            "test_quantity": "0.003",
            "notes": "pending",
            "overrides": {"TRADING_ENABLED": "1"},
        }
    )
    ctl.db.collection(MOD.APPLIED_COLLECTION).document(MOD.PLATFORM).set(
        {"desired_version": "v1", "status": "failed"}
    )

    captured = {}

    def _fake_apply(**kwargs):
        captured.update(kwargs)
        return {"desired": {}, "applied": {"status": "staged_no_restart"}}

    monkeypatch.setattr(ctl, "apply", _fake_apply)
    out = ctl.reconcile(requested_by="tester", no_restart=True)
    assert out["reconciled"] is True
    assert captured["no_restart"] is True
    assert captured["desired_version"] == "v2"
    assert captured["update_desired"] is False


def test_rollback_no_restart_uses_historical_profile(monkeypatch):
    ctl = _make_ctl()
    hist = ctl.db.collection(MOD.APPLIED_HISTORY_COLLECTION)
    hist.document("new").set(
        {
            "desired_version": "new-ver",
            "status": "applied",
            "profile": "luxalgo_sol_5m_active",
            "effective_settings": MOD.PROFILE_SETTINGS["luxalgo_sol_5m_active"],
            "applied_at_iso": "2026-03-04T08:00:00+00:00",
        }
    )
    hist.document("old").set(
        {
            "desired_version": "old-ver",
            "status": "applied",
            "profile": "luxalgo_sol_15m_safe",
            "effective_settings": {
                **MOD.PROFILE_SETTINGS["luxalgo_sol_15m_safe"],
                "LIGHTER_ENTRY_COOLDOWN_SECONDS": "777",
            },
            "applied_at_iso": "2026-03-04T07:00:00+00:00",
        }
    )

    captured = {}

    def _fake_apply(**kwargs):
        captured.update(kwargs)
        return {"desired": {}, "applied": {"status": "staged_no_restart"}}

    monkeypatch.setattr(ctl, "apply", _fake_apply)
    out = ctl.rollback(
        steps=1,
        target_host="rari@test",
        requested_by="tester",
        run_test=False,
        close_after_test=False,
        test_quantity="0.002",
        notes="",
        no_restart=True,
    )
    assert out["target_history_record"]["desired_version"] == "old-ver"
    assert captured["profile"] == "luxalgo_sol_15m_safe"
    assert captured["no_restart"] is True
    assert captured["overrides"]["LIGHTER_ENTRY_COOLDOWN_SECONDS"] == "777"
