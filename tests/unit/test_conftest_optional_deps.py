import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFTST_SPEC = importlib.util.spec_from_file_location(
    "sapphire_root_conftest_for_test",
    REPO_ROOT / "tests" / "conftest.py",
)
assert _CONFTST_SPEC is not None
assert _CONFTST_SPEC.loader is not None
root_conftest = importlib.util.module_from_spec(_CONFTST_SPEC)
_CONFTST_SPEC.loader.exec_module(root_conftest)


def test_missing_optional_deps_handles_missing_parent_package(monkeypatch):
    def fake_find_spec(module: str):
        assert module == "google.generativeai"
        raise ModuleNotFoundError("No module named 'google'")

    monkeypatch.setattr(root_conftest.importlib.util, "find_spec", fake_find_spec)

    collection_path = root_conftest.REPO_ROOT / "tests/unit/test_chat_intent.py"

    assert root_conftest._missing_optional_test_deps(collection_path) == ["google.generativeai"]


def test_missing_optional_deps_ignores_paths_outside_repo(tmp_path):
    assert root_conftest._missing_optional_test_deps(Path(tmp_path) / "test_example.py") == []
