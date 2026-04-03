"""Tests for Phase 5 Task Management System."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine"))

import pytest
from src.collaboration.task_manager import TaskManager


@pytest.fixture
def mgr():
    """Fresh TaskManager with no persistence."""
    return TaskManager()


@pytest.fixture
def mgr_persistent():
    """TaskManager with JSON file persistence."""
    tmp = tempfile.mktemp(suffix=".json")
    yield TaskManager(store_path=tmp)
    if os.path.exists(tmp):
        os.unlink(tmp)


# ── Task CRUD ─────────────────────────────────────────────────────


def test_create_task(mgr):
    result = mgr.create_task(title="Wire AgentGate into main.py")
    assert result["ok"] is True
    task = result["task"]
    assert task["task_id"] == "TASK-00001"
    assert task["title"] == "Wire AgentGate into main.py"
    assert task["status"] == "pending"
    assert task["priority"] == "medium"
    assert task["agent"] == "UNASSIGNED"
    assert task["created_at"] > 0
    assert task["completed_at"] is None


def test_create_task_with_all_fields(mgr):
    result = mgr.create_task(
        title="Build forum expansion",
        phase="phase_3",
        agent="EMERALD",
        priority="high",
        description="Implement rich forum features.",
        tags=["forum", "collaboration"],
    )
    assert result["ok"] is True
    task = result["task"]
    assert task["phase"] == "phase_3"
    assert task["agent"] == "EMERALD"
    assert task["priority"] == "high"
    assert task["description"] == "Implement rich forum features."
    assert "forum" in task["tags"]
    assert "collaboration" in task["tags"]


def test_create_task_empty_title(mgr):
    result = mgr.create_task(title="")
    assert result["ok"] is False
    assert "Title" in result["error"]


def test_create_task_normalizes_agent(mgr):
    result = mgr.create_task(title="Test task", agent="unknown_agent")
    assert result["ok"] is True
    assert result["task"]["agent"] == "UNASSIGNED"


def test_create_task_normalizes_priority(mgr):
    result = mgr.create_task(title="Test task", priority="ultra")
    assert result["ok"] is True
    assert result["task"]["priority"] == "medium"


def test_create_task_truncates_title(mgr):
    long_title = "A" * 300
    result = mgr.create_task(title=long_title)
    assert result["ok"] is True
    assert len(result["task"]["title"]) == 200


def test_create_task_increments_ids(mgr):
    r1 = mgr.create_task(title="Task 1")
    r2 = mgr.create_task(title="Task 2")
    r3 = mgr.create_task(title="Task 3")
    assert r1["task"]["task_id"] == "TASK-00001"
    assert r2["task"]["task_id"] == "TASK-00002"
    assert r3["task"]["task_id"] == "TASK-00003"


def test_get_task(mgr):
    created = mgr.create_task(title="Get me")
    task_id = created["task"]["task_id"]
    result = mgr.get_task(task_id)
    assert result["ok"] is True
    assert result["task"]["title"] == "Get me"


def test_get_task_not_found(mgr):
    result = mgr.get_task("TASK-99999")
    assert result["ok"] is False
    assert "not found" in result["error"].lower()


def test_update_task_status(mgr):
    created = mgr.create_task(title="Update me")
    task_id = created["task"]["task_id"]
    result = mgr.update_task(task_id, status="in_progress")
    assert result["ok"] is True
    assert result["task"]["status"] == "in_progress"


def test_update_task_to_completed(mgr):
    created = mgr.create_task(title="Complete me")
    task_id = created["task"]["task_id"]
    result = mgr.update_task(task_id, status="completed")
    assert result["ok"] is True
    assert result["task"]["status"] == "completed"
    assert result["task"]["completed_at"] is not None


def test_update_task_invalid_status(mgr):
    created = mgr.create_task(title="Bad status")
    task_id = created["task"]["task_id"]
    result = mgr.update_task(task_id, status="invalid_status")
    assert result["ok"] is False
    assert "Invalid status" in result["error"]


def test_update_task_not_found(mgr):
    result = mgr.update_task("TASK-99999", status="completed")
    assert result["ok"] is False
    assert "not found" in result["error"].lower()


def test_update_task_multiple_fields(mgr):
    created = mgr.create_task(title="Multi update")
    task_id = created["task"]["task_id"]
    result = mgr.update_task(
        task_id,
        priority="critical",
        agent="OBSIDIAN",
        title="Updated title",
    )
    assert result["ok"] is True
    assert result["task"]["priority"] == "critical"
    assert result["task"]["agent"] == "OBSIDIAN"
    assert result["task"]["title"] == "Updated title"


def test_delete_task(mgr):
    created = mgr.create_task(title="Delete me")
    task_id = created["task"]["task_id"]
    result = mgr.delete_task(task_id)
    assert result["ok"] is True
    assert result["deleted_task_id"] == task_id
    # Verify deleted
    get_result = mgr.get_task(task_id)
    assert get_result["ok"] is False


def test_delete_task_not_found(mgr):
    result = mgr.delete_task("TASK-99999")
    assert result["ok"] is False


def test_delete_task_cleans_milestones(mgr):
    created = mgr.create_task(title="With milestones")
    task_id = created["task"]["task_id"]
    ms = mgr.add_milestone(task_id, title="MS 1")
    ms_id = ms["milestone"]["milestone_id"]
    mgr.delete_task(task_id)
    # Milestone should be cleaned up
    result = mgr.complete_milestone(ms_id)
    assert result["ok"] is False


def test_delete_task_cleans_deliverables(mgr):
    created = mgr.create_task(title="With deliverables")
    task_id = created["task"]["task_id"]
    dlv = mgr.add_deliverable(task_id, title="DLV 1")
    dlv_id = dlv["deliverable"]["deliverable_id"]
    mgr.delete_task(task_id)
    # Deliverable should be cleaned up
    result = mgr.verify_deliverable(dlv_id)
    assert result["ok"] is False


# ── List Tasks ────────────────────────────────────────────────────


def test_list_tasks_empty(mgr):
    result = mgr.list_tasks()
    assert result["ok"] is True
    assert result["total"] == 0
    assert result["tasks"] == []


def test_list_tasks_all(mgr):
    for i in range(5):
        mgr.create_task(title=f"Task {i}")
    result = mgr.list_tasks()
    assert result["ok"] is True
    assert result["total"] == 5
    assert result["showing"] == 5


def test_list_tasks_filter_by_phase(mgr):
    mgr.create_task(title="Phase 3 task", phase="phase_3")
    mgr.create_task(title="Phase 5 task", phase="phase_5")
    mgr.create_task(title="Phase 5 task 2", phase="phase_5")
    result = mgr.list_tasks(phase="phase_5")
    assert result["total"] == 2


def test_list_tasks_filter_by_agent(mgr):
    mgr.create_task(title="Sapphire task", agent="SAPPHIRE")
    mgr.create_task(title="Emerald task", agent="EMERALD")
    result = mgr.list_tasks(agent="SAPPHIRE")
    assert result["total"] == 1
    assert result["tasks"][0]["agent"] == "SAPPHIRE"


def test_list_tasks_filter_by_status(mgr):
    r1 = mgr.create_task(title="Pending")
    r2 = mgr.create_task(title="Done")
    mgr.update_task(r2["task"]["task_id"], status="completed")
    result = mgr.list_tasks(status="completed")
    assert result["total"] == 1
    assert result["tasks"][0]["title"] == "Done"


def test_list_tasks_filter_by_priority(mgr):
    mgr.create_task(title="Low prio", priority="low")
    mgr.create_task(title="Critical", priority="critical")
    result = mgr.list_tasks(priority="critical")
    assert result["total"] == 1


def test_list_tasks_filter_by_tag(mgr):
    mgr.create_task(title="Tagged", tags=["security", "urgent"])
    mgr.create_task(title="Not tagged", tags=["forum"])
    result = mgr.list_tasks(tag="security")
    assert result["total"] == 1
    assert result["tasks"][0]["title"] == "Tagged"


def test_list_tasks_sorted_by_priority(mgr):
    mgr.create_task(title="Low", priority="low")
    mgr.create_task(title="Critical", priority="critical")
    mgr.create_task(title="High", priority="high")
    result = mgr.list_tasks()
    assert result["tasks"][0]["priority"] == "critical"
    assert result["tasks"][1]["priority"] == "high"
    assert result["tasks"][2]["priority"] == "low"


def test_list_tasks_limit(mgr):
    for i in range(10):
        mgr.create_task(title=f"Task {i}")
    result = mgr.list_tasks(limit=3)
    assert result["showing"] == 3
    assert result["total"] == 10


# ── Milestones ────────────────────────────────────────────────────


def test_add_milestone(mgr):
    created = mgr.create_task(title="With milestone")
    task_id = created["task"]["task_id"]
    result = mgr.add_milestone(task_id, title="Alpha release")
    assert result["ok"] is True
    ms = result["milestone"]
    assert ms["milestone_id"] == "MS-00001"
    assert ms["title"] == "Alpha release"
    assert ms["task_id"] == task_id
    assert ms["completed"] is False


def test_add_milestone_with_target_date(mgr):
    created = mgr.create_task(title="Dated milestone")
    task_id = created["task"]["task_id"]
    result = mgr.add_milestone(task_id, title="Due date", target_date="2026-03-01")
    assert result["ok"] is True
    assert result["milestone"]["target_date"] == "2026-03-01"


def test_add_milestone_task_not_found(mgr):
    result = mgr.add_milestone("TASK-99999", title="Orphan")
    assert result["ok"] is False


def test_add_milestone_empty_title(mgr):
    created = mgr.create_task(title="No title ms")
    result = mgr.add_milestone(created["task"]["task_id"], title="")
    assert result["ok"] is False
    assert "title" in result["error"].lower()


def test_add_milestone_max_limit(mgr):
    created = mgr.create_task(title="Many milestones")
    task_id = created["task"]["task_id"]
    for i in range(20):
        r = mgr.add_milestone(task_id, title=f"MS {i}")
        assert r["ok"] is True
    # 21st should fail
    result = mgr.add_milestone(task_id, title="Too many")
    assert result["ok"] is False
    assert "Maximum" in result["error"]


def test_complete_milestone(mgr):
    created = mgr.create_task(title="Complete ms")
    task_id = created["task"]["task_id"]
    ms = mgr.add_milestone(task_id, title="Done ms")
    result = mgr.complete_milestone(ms["milestone"]["milestone_id"])
    assert result["ok"] is True
    assert result["milestone"]["completed"] is True
    assert result["milestone"]["completed_at"] is not None


def test_complete_milestone_not_found(mgr):
    result = mgr.complete_milestone("MS-99999")
    assert result["ok"] is False


def test_get_task_includes_milestones(mgr):
    created = mgr.create_task(title="With ms detail")
    task_id = created["task"]["task_id"]
    mgr.add_milestone(task_id, title="First MS")
    mgr.add_milestone(task_id, title="Second MS")
    result = mgr.get_task(task_id)
    assert result["ok"] is True
    assert len(result["task"]["milestones"]) == 2
    assert result["task"]["milestones"][0]["title"] == "First MS"


# ── Deliverables ──────────────────────────────────────────────────


def test_add_deliverable(mgr):
    created = mgr.create_task(title="With deliverable")
    task_id = created["task"]["task_id"]
    result = mgr.add_deliverable(task_id, title="PR #31", deliverable_type="code")
    assert result["ok"] is True
    dlv = result["deliverable"]
    assert dlv["deliverable_id"] == "DLV-00001"
    assert dlv["title"] == "PR #31"
    assert dlv["type"] == "code"
    assert dlv["verified"] is False


def test_add_deliverable_types(mgr):
    created = mgr.create_task(title="Types test")
    task_id = created["task"]["task_id"]
    for dtype in ["code", "test", "doc", "config", "deploy"]:
        r = mgr.add_deliverable(task_id, title=f"{dtype} delivery", deliverable_type=dtype)
        assert r["ok"] is True
        assert r["deliverable"]["type"] == dtype


def test_add_deliverable_unknown_type_defaults(mgr):
    created = mgr.create_task(title="Unknown type")
    task_id = created["task"]["task_id"]
    result = mgr.add_deliverable(task_id, title="Mystery", deliverable_type="unknown")
    assert result["ok"] is True
    assert result["deliverable"]["type"] == "other"


def test_add_deliverable_with_reference(mgr):
    created = mgr.create_task(title="Referenced")
    task_id = created["task"]["task_id"]
    result = mgr.add_deliverable(
        task_id,
        title="PR Link",
        reference="https://github.com/arigatoexpress/Sapphire/pull/31",
    )
    assert result["ok"] is True
    assert "pull/31" in result["deliverable"]["reference"]


def test_add_deliverable_task_not_found(mgr):
    result = mgr.add_deliverable("TASK-99999", title="Orphan")
    assert result["ok"] is False


def test_add_deliverable_empty_title(mgr):
    created = mgr.create_task(title="No title dlv")
    result = mgr.add_deliverable(created["task"]["task_id"], title="")
    assert result["ok"] is False


def test_add_deliverable_max_limit(mgr):
    created = mgr.create_task(title="Many deliverables")
    task_id = created["task"]["task_id"]
    for i in range(20):
        r = mgr.add_deliverable(task_id, title=f"DLV {i}")
        assert r["ok"] is True
    result = mgr.add_deliverable(task_id, title="Too many")
    assert result["ok"] is False
    assert "Maximum" in result["error"]


def test_verify_deliverable(mgr):
    created = mgr.create_task(title="Verify dlv")
    task_id = created["task"]["task_id"]
    dlv = mgr.add_deliverable(task_id, title="Verified DLV")
    result = mgr.verify_deliverable(dlv["deliverable"]["deliverable_id"])
    assert result["ok"] is True
    assert result["deliverable"]["verified"] is True
    assert result["deliverable"]["verified_at"] is not None


def test_verify_deliverable_not_found(mgr):
    result = mgr.verify_deliverable("DLV-99999")
    assert result["ok"] is False


def test_get_task_includes_deliverables(mgr):
    created = mgr.create_task(title="With dlv detail")
    task_id = created["task"]["task_id"]
    mgr.add_deliverable(task_id, title="First DLV")
    mgr.add_deliverable(task_id, title="Second DLV")
    result = mgr.get_task(task_id)
    assert result["ok"] is True
    assert len(result["task"]["deliverables"]) == 2
    assert result["task"]["deliverables"][0]["title"] == "First DLV"


# ── Notes ─────────────────────────────────────────────────────────


def test_add_note(mgr):
    created = mgr.create_task(title="With notes")
    task_id = created["task"]["task_id"]
    result = mgr.add_note(task_id, text="This is a note.", author="EMERALD")
    assert result["ok"] is True
    assert result["note"]["text"] == "This is a note."
    assert result["note"]["author"] == "EMERALD"
    assert result["total_notes"] == 1


def test_add_note_empty_text(mgr):
    created = mgr.create_task(title="Empty note")
    result = mgr.add_note(created["task"]["task_id"], text="")
    assert result["ok"] is False
    assert "text" in result["error"].lower()


def test_add_note_task_not_found(mgr):
    result = mgr.add_note("TASK-99999", text="Lost note")
    assert result["ok"] is False


def test_add_note_default_author(mgr):
    created = mgr.create_task(title="Default author")
    result = mgr.add_note(created["task"]["task_id"], text="System note")
    assert result["note"]["author"] == "SYSTEM"


def test_notes_capped_at_50(mgr):
    created = mgr.create_task(title="Many notes")
    task_id = created["task"]["task_id"]
    for i in range(60):
        mgr.add_note(task_id, text=f"Note {i}")
    task = mgr.get_task(task_id)["task"]
    assert len(task["notes"]) == 50


# ── Progress Reports ──────────────────────────────────────────────


def test_progress_report_empty(mgr):
    result = mgr.progress_report()
    assert result["ok"] is True
    assert result["total"] == 0
    assert result["completion_rate"] == 0.0


def test_progress_report_with_data(mgr):
    mgr.create_task(title="T1", agent="SAPPHIRE", phase="phase_5")
    mgr.create_task(title="T2", agent="EMERALD", phase="phase_5")
    r3 = mgr.create_task(title="T3", agent="SAPPHIRE", phase="phase_5")
    mgr.update_task(r3["task"]["task_id"], status="completed")
    result = mgr.progress_report()
    assert result["ok"] is True
    assert result["total"] == 3
    assert result["by_status"]["completed"] == 1
    assert result["by_status"]["pending"] == 2
    assert result["by_agent"]["SAPPHIRE"]["total"] == 2
    assert result["by_agent"]["SAPPHIRE"]["completed"] == 1
    assert result["completion_rate"] == round(1 / 3, 4)
    assert len(result["recent_activity"]) == 3


def test_progress_report_filter_by_phase(mgr):
    mgr.create_task(title="Phase 3", phase="phase_3")
    mgr.create_task(title="Phase 5", phase="phase_5")
    result = mgr.progress_report(phase="phase_5")
    assert result["total"] == 1
    assert result["filter_phase"] == "phase_5"


def test_progress_report_filter_by_agent(mgr):
    mgr.create_task(title="Sapphire", agent="SAPPHIRE")
    mgr.create_task(title="Emerald", agent="EMERALD")
    result = mgr.progress_report(agent="EMERALD")
    assert result["total"] == 1
    assert result["filter_agent"] == "EMERALD"


def test_progress_report_milestones_summary(mgr):
    t = mgr.create_task(title="MS report")
    tid = t["task"]["task_id"]
    ms1 = mgr.add_milestone(tid, title="MS 1")
    ms2 = mgr.add_milestone(tid, title="MS 2")
    mgr.complete_milestone(ms1["milestone"]["milestone_id"])
    result = mgr.progress_report()
    assert result["milestones_summary"]["total"] == 2
    assert result["milestones_summary"]["completed"] == 1


def test_progress_report_deliverables_summary(mgr):
    t = mgr.create_task(title="DLV report")
    tid = t["task"]["task_id"]
    d1 = mgr.add_deliverable(tid, title="DLV 1")
    mgr.add_deliverable(tid, title="DLV 2")
    mgr.verify_deliverable(d1["deliverable"]["deliverable_id"])
    result = mgr.progress_report()
    assert result["deliverables_summary"]["total"] == 2
    assert result["deliverables_summary"]["verified"] == 1


# ── Agent Report ──────────────────────────────────────────────────


def test_agent_report(mgr):
    mgr.create_task(title="S1", agent="SAPPHIRE")
    r2 = mgr.create_task(title="S2", agent="SAPPHIRE")
    mgr.update_task(r2["task"]["task_id"], status="completed")
    mgr.create_task(title="E1", agent="EMERALD")
    result = mgr.agent_report("SAPPHIRE")
    assert result["ok"] is True
    assert result["agent"] == "SAPPHIRE"
    assert result["total"] == 2
    assert result["completed"] == 1
    assert result["completion_rate"] == 0.5
    assert len(result["tasks"]) == 2


def test_agent_report_invalid_agent(mgr):
    result = mgr.agent_report("INVALID")
    assert result["ok"] is False
    assert "Invalid agent" in result["error"]


def test_agent_report_unassigned_rejected(mgr):
    result = mgr.agent_report("UNASSIGNED")
    assert result["ok"] is False


def test_agent_report_empty(mgr):
    result = mgr.agent_report("EMERALD")
    assert result["ok"] is True
    assert result["total"] == 0


def test_agent_report_includes_milestone_counts(mgr):
    t = mgr.create_task(title="Agent MS", agent="OBSIDIAN")
    tid = t["task"]["task_id"]
    ms1 = mgr.add_milestone(tid, title="MS 1")
    mgr.add_milestone(tid, title="MS 2")
    mgr.complete_milestone(ms1["milestone"]["milestone_id"])
    result = mgr.agent_report("OBSIDIAN")
    assert result["tasks"][0]["milestones_total"] == 2
    assert result["tasks"][0]["milestones_done"] == 1


# ── Summary ───────────────────────────────────────────────────────


def test_summary_empty(mgr):
    result = mgr.summary()
    assert result["ok"] is True
    assert result["total_tasks"] == 0
    assert result["total_milestones"] == 0
    assert result["total_deliverables"] == 0


def test_summary_with_data(mgr):
    t = mgr.create_task(title="S task", agent="SAPPHIRE", phase="phase_5")
    tid = t["task"]["task_id"]
    mgr.add_milestone(tid, title="MS")
    mgr.add_deliverable(tid, title="DLV")
    result = mgr.summary()
    assert result["total_tasks"] == 1
    assert result["total_milestones"] == 1
    assert result["total_deliverables"] == 1
    assert result["agents"]["SAPPHIRE"] == 1
    assert result["phases"]["phase_5"] == 1


# ── Bulk Create ───────────────────────────────────────────────────


def test_bulk_create(mgr):
    items = [
        {"title": "Task A", "agent": "SAPPHIRE", "priority": "high"},
        {"title": "Task B", "agent": "EMERALD"},
        {"title": "Task C", "priority": "critical"},
    ]
    result = mgr.bulk_create_from_phase("phase_5", items)
    assert result["ok"] is True
    assert result["created"] == 3
    assert result["errors"] == 0
    assert len(result["task_ids"]) == 3


def test_bulk_create_with_errors(mgr):
    items = [
        {"title": "Good task"},
        {"title": ""},  # Empty title → error
        {"title": "Another good"},
    ]
    result = mgr.bulk_create_from_phase("phase_5", items)
    assert result["ok"] is True
    assert result["created"] == 2
    assert result["errors"] == 1


def test_bulk_create_empty_items(mgr):
    result = mgr.bulk_create_from_phase("phase_5", [])
    assert result["ok"] is False


def test_bulk_create_caps_at_50(mgr):
    items = [{"title": f"Task {i}"} for i in range(60)]
    result = mgr.bulk_create_from_phase("phase_5", items)
    assert result["created"] == 50


# ── Persistence ───────────────────────────────────────────────────


def test_persistence_save_and_load(mgr_persistent):
    mgr_persistent.create_task(title="Persisted task", phase="phase_5")
    t = mgr_persistent.create_task(title="Another task")
    tid = t["task"]["task_id"]
    mgr_persistent.add_milestone(tid, title="Persisted MS")
    mgr_persistent.add_deliverable(tid, title="Persisted DLV")

    # Load into a new manager from same file
    mgr2 = TaskManager(store_path=mgr_persistent._store_path)
    assert len(mgr2._tasks) == 2
    assert len(mgr2._milestones) == 1
    assert len(mgr2._deliverables) == 1


def test_persistence_counter_survives_reload(mgr_persistent):
    mgr_persistent.create_task(title="T1")
    mgr_persistent.create_task(title="T2")
    mgr_persistent.create_task(title="T3")

    mgr2 = TaskManager(store_path=mgr_persistent._store_path)
    r = mgr2.create_task(title="T4")
    assert r["task"]["task_id"] == "TASK-00004"


def test_no_persistence_when_no_path():
    mgr = TaskManager(store_path="")
    mgr.create_task(title="Ephemeral")
    # Should not crash when persisting
    assert len(mgr._tasks) == 1


# ── Edge Cases ────────────────────────────────────────────────────


def test_task_id_case_insensitive(mgr):
    created = mgr.create_task(title="Case test")
    task_id = created["task"]["task_id"].lower()
    result = mgr.get_task(task_id)
    assert result["ok"] is True


def test_tags_normalized_to_lowercase(mgr):
    result = mgr.create_task(title="Tag case", tags=["SECURITY", "Forum", "phase5"])
    assert all(t.islower() for t in result["task"]["tags"])


def test_tags_limited_to_10(mgr):
    tags = [f"tag{i}" for i in range(20)]
    result = mgr.create_task(title="Many tags", tags=tags)
    assert len(result["task"]["tags"]) == 10


def test_description_truncated(mgr):
    long_desc = "B" * 3000
    result = mgr.create_task(title="Long desc", description=long_desc)
    assert len(result["task"]["description"]) == 2000


def test_update_tags(mgr):
    created = mgr.create_task(title="Update tags", tags=["old"])
    task_id = created["task"]["task_id"]
    result = mgr.update_task(task_id, tags=["new", "updated"])
    assert result["ok"] is True
    assert "new" in result["task"]["tags"]
    assert "old" not in result["task"]["tags"]


def test_enforce_limits(mgr):
    mgr.MAX_TASKS = 5
    for i in range(6):
        r = mgr.create_task(title=f"Task {i}")
        if i < 3:
            mgr.update_task(r["task"]["task_id"], status="completed")
    # Should have trimmed oldest completed
    assert len(mgr._tasks) <= 5


def test_update_task_description(mgr):
    created = mgr.create_task(title="Desc update")
    task_id = created["task"]["task_id"]
    result = mgr.update_task(task_id, description="New description here")
    assert result["task"]["description"] == "New description here"


# ── Tags in update ────────────────────────────────────────────────


def test_update_task_tags_to_empty(mgr):
    created = mgr.create_task(title="Tags to empty", tags=["one", "two"])
    task_id = created["task"]["task_id"]
    result = mgr.update_task(task_id, tags=[])
    assert result["ok"] is True
    assert result["task"]["tags"] == []
