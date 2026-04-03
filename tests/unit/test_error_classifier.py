import importlib.util
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
CLASSIFIER_PATH = ROOT_DIR / "lib/core/src/sapphire_core/error_classifier.py"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_region_unavailable_error_classifies_as_configuration_critical():
    classifier = _load_module(CLASSIFIER_PATH, "alpha_error_classifier_region")
    category, severity = classifier.classify_error(
        "Aster API Error -5019: Service not available in your region."
    )
    assert category == classifier.ErrorCategory.CONFIGURATION
    assert severity == classifier.ErrorSeverity.CRITICAL


def test_unknown_error_defaults_to_system_error():
    classifier = _load_module(CLASSIFIER_PATH, "alpha_error_classifier_default")
    category, severity = classifier.classify_error("something-unmapped-happened")
    assert category == classifier.ErrorCategory.SYSTEM
    assert severity == classifier.ErrorSeverity.ERROR


def test_configuration_critical_errors_require_immediate_notification():
    classifier = _load_module(CLASSIFIER_PATH, "alpha_error_classifier_notify")
    assert (
        classifier.should_notify_immediately(
            classifier.ErrorCategory.CONFIGURATION,
            classifier.ErrorSeverity.CRITICAL,
        )
        is True
    )
