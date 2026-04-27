from __future__ import annotations

import json

from lib.autonomy import continuous_intelligence as ci


def test_continuous_intelligence_plan_is_read_only() -> None:
    plan = ci.build_continuous_intelligence_plan(fetch_live=False)

    assert plan["mode"] == "read_only_task_planning"
    assert plan["execution_enabled"] is False
    assert plan["live_trading_enabled"] is False
    assert plan["telegram_sends_enabled"] is False
    assert plan["writes_by_default"] is False
    assert "human_promotion_gate_required" in plan["safety"]["guards"]


def test_continuous_intelligence_plan_has_real_work_lanes() -> None:
    plan = ci.build_continuous_intelligence_plan(fetch_live=False)
    tasks = plan["tasks"]
    lanes = {task["lane"] for task in tasks}

    assert {"strategy_backtest", "confluence_scan", "thesis_research", "promotion_gate"} <= lanes
    assert any(task["target_runtime"] == "windows-gpu" for task in tasks)
    assert any(task["lane"] == "strategy_backtest" and task.get("command") for task in tasks)
    assert any(task["id"] == "eth-privacy-quantum-research-refresh" for task in tasks)
    assert any(task["id"] == "institutional-tokenization-agentic-payments-refresh" for task in tasks)
    assert any(task["id"] == "x402-agent-market-dry-run-plan" for task in tasks)
    assert plan["inputs"]["market_universe"]["liked_symbols"][:3] == ["ETH", "BTC", "ZEC"]
    assert "https://docs.cdp.coinbase.com/x402/docs/welcome" in plan["source_docs"]


def test_continuous_intelligence_task_contracts_are_safe_and_unique() -> None:
    plan = ci.build_continuous_intelligence_plan(fetch_live=False)
    task_ids = [task["id"] for task in plan["tasks"]]
    priorities = [task["priority"] for task in plan["tasks"]]

    assert len(task_ids) == len(set(task_ids))
    assert priorities == sorted(priorities, key=lambda value: ci.PRIORITY_ORDER[value])
    assert {task["safe_mode"] for task in plan["tasks"]} <= ci.SAFE_MODES
    assert all("order submission" not in task["description"].lower() for task in plan["tasks"])
    assert plan["next_dispatch"]
    assert all(task["priority"] == "P1" for task in plan["next_dispatch"])


def test_tokenization_and_x402_tasks_are_explicitly_non_executing() -> None:
    plan = ci.build_continuous_intelligence_plan(fetch_live=False)
    tasks = {task["id"]: task for task in plan["tasks"]}
    tokenization = tasks["institutional-tokenization-agentic-payments-refresh"]
    x402 = tasks["x402-agent-market-dry-run-plan"]

    assert tokenization["target_runtime"] == "windows-gpu"
    assert tokenization["safe_mode"] == "read_only"
    assert {"ETH", "LINK", "ONDO", "COIN"} <= set(tokenization["symbols"])
    assert "https://chain.link/smartdata" in tokenization["source_docs"]
    assert x402["safe_mode"] == "dry_run"
    assert any("X402_ENABLED stays disabled" in gate for gate in x402["acceptance"])


def test_cli_emits_json(capsys) -> None:
    exit_code = ci.cli(["--pretty"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "read_only_task_planning"
    assert payload["live_requested"] is False
