import asyncio
import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCANNER_PATH = ROOT_DIR / "services/alpha-engine/src/security/virustotal_scanner.py"


def _load_scanner_module():
    spec = importlib.util.spec_from_file_location("vt_scanner_module", SCANNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_bundle_hash_is_deterministic(monkeypatch, tmp_path):
    module = _load_scanner_module()
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "security-audit"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# security-audit\n", encoding="utf-8")
    (skill_dir / "scripts.sh").write_text("echo hello\n", encoding="utf-8")

    monkeypatch.setenv("SAPPHIRE_SKILLS_DIR", str(skills_dir))
    scanner = module.VirusTotalSkillScanner()

    first = scanner._build_deterministic_bundle("security-audit")
    second = scanner._build_deterministic_bundle("security-audit")
    assert first["sha256"] == second["sha256"]
    assert first["file_count"] == second["file_count"]
    assert first["size_bytes"] == second["size_bytes"]


def test_policy_modes_apply_expected_blocks(monkeypatch):
    module = _load_scanner_module()
    scanner = module.VirusTotalSkillScanner()

    scanner.enforcement_mode = "off"
    assert scanner.evaluate_policy("malicious")["allowed"] is True

    scanner.enforcement_mode = "warn"
    assert scanner.evaluate_policy("suspicious")["allowed"] is True

    scanner.enforcement_mode = "block_malicious"
    assert scanner.evaluate_policy("malicious")["allowed"] is False
    assert scanner.evaluate_policy("suspicious")["allowed"] is True

    scanner.enforcement_mode = "block_suspicious"
    assert scanner.evaluate_policy("suspicious")["allowed"] is False
    assert scanner.evaluate_policy("benign")["allowed"] is True


def test_verdict_summary_uses_stats_and_code_insight(monkeypatch):
    module = _load_scanner_module()
    scanner = module.VirusTotalSkillScanner()
    scanner.enforcement_mode = "block_suspicious"

    file_report = {
        "data": {
            "attributes": {
                "last_analysis_stats": {
                    "malicious": 0,
                    "suspicious": 0,
                    "harmless": 12,
                    "undetected": 61,
                }
            }
        }
    }
    analysis_report = {
        "data": {
            "attributes": {
                "status": "completed",
                "ai_summary": {"verdict": "suspicious"},
            }
        }
    }

    summary = scanner._build_verdict_summary(file_report=file_report, analysis_report=analysis_report)
    assert summary["base_verdict"] == "benign"
    assert summary["code_insight_verdict"] == "suspicious"
    assert summary["verdict"] == "suspicious"
    assert summary["policy"]["blocked"] is True


def test_scan_skill_returns_error_when_api_key_missing(monkeypatch, tmp_path):
    module = _load_scanner_module()
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "deploy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# deploy\n", encoding="utf-8")

    monkeypatch.setenv("SAPPHIRE_SKILLS_DIR", str(skills_dir))
    monkeypatch.delenv("VIRUSTOTAL_API_KEY", raising=False)
    scanner = module.VirusTotalSkillScanner()
    scanner.api_key = ""

    result = asyncio.run(scanner.scan_skill("deploy"))
    assert result["ok"] is False
    assert result["error"] == "vt_api_key_missing"


def test_scan_skill_uses_lookup_hit_without_upload(monkeypatch):
    module = _load_scanner_module()
    scanner = module.VirusTotalSkillScanner()
    scanner.api_key = "vt_test_key"
    scanner.enforcement_mode = "warn"

    async def fake_lookup(_sha: str):
        return {
            "ok": True,
            "found": True,
            "status": 200,
            "report": {
                "data": {
                    "attributes": {
                        "last_analysis_stats": {
                            "malicious": 0,
                            "suspicious": 0,
                            "harmless": 8,
                            "undetected": 53,
                        }
                    }
                }
            },
        }

    scanner._build_deterministic_bundle = lambda _skill: {
        "bytes": b"zipdata",
        "sha256": "f" * 64,
        "size_bytes": 7,
        "file_count": 2,
        "meta_embedded": True,
    }
    scanner._lookup_file = fake_lookup

    result = asyncio.run(scanner.scan_skill("security-audit"))
    assert result["ok"] is True
    assert result["vt"]["lookup_hit"] is True
    assert result["vt"]["uploaded"] is False
    assert result["security"]["verdict"] == "benign"
