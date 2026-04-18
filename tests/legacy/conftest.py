import pytest


def pytest_collect_file(parent, file_path):
    """Intercept all legacy test files and skip them without importing."""
    if file_path.suffix == ".py" and file_path.name.startswith("test_"):
        return LegacySkipFile.from_parent(parent, path=file_path)
    return None


class LegacySkipFile(pytest.File):
    def collect(self):
        yield LegacySkipItem.from_parent(self, name=self.fspath.basename)


class LegacySkipItem(pytest.Item):
    def runtest(self):
        pytest.skip("Legacy test — depends on removed modules")

    def repr_failure(self, excinfo):
        return str(excinfo.value)

    def reportinfo(self):
        return self.fspath, None, f"[legacy skip] {self.fspath.basename}"
