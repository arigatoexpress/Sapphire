"""Task Management System — Agent Tasks, Milestones & Deliverables.

Provides organized tracking of goals, progress, and deliverables across
all Sapphire agents. Each task belongs to a phase, is assigned to an
agent, and can have milestones and deliverables attached.

Features:
1. Task CRUD with status lifecycle (pending → in_progress → completed / blocked)
2. Milestones with target dates and completion tracking
3. Deliverables linked to tasks with verification metadata
4. Automated progress reports per agent and per phase
5. Thread-safe in-memory store with optional JSON persistence
"""

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from loguru import logger

# ── Task status lifecycle ──────────────────────────────────────────

VALID_STATUSES = {"pending", "in_progress", "completed", "blocked", "cancelled"}
VALID_PRIORITIES = {"low", "medium", "high", "critical"}
VALID_AGENTS = {"SAPPHIRE", "EMERALD", "OBSIDIAN", "UNASSIGNED"}


class TaskManager:
    """Manages tasks, milestones, and deliverables for Sapphire agents.

    All public methods return Dict[str, Any] with an 'ok' field.
    Thread-safe with internal locking.
    """

    MAX_TASKS = 2000
    MAX_MILESTONES_PER_TASK = 20
    MAX_DELIVERABLES_PER_TASK = 20
    MAX_TITLE_LENGTH = 200
    MAX_DESCRIPTION_LENGTH = 2000
    MAX_NOTES_LENGTH = 1000

    def __init__(self, store_path: str = ""):
        self._lock = threading.Lock()
        self._store_path = store_path or os.getenv(
            "SAPPHIRE_TASK_STORE_PATH", ""
        )
        self._tasks: dict[str, dict[str, Any]] = {}
        self._task_counter = 0
        self._milestones: dict[str, dict[str, Any]] = {}  # milestone_id → milestone
        self._milestone_counter = 0
        self._deliverables: dict[str, dict[str, Any]] = {}  # deliverable_id → deliverable
        self._deliverable_counter = 0

        # Load persisted state if available
        if self._store_path:
            self._load_store()

    # ── Task CRUD ─────────────────────────────────────────────────

    def create_task(
        self,
        title: str,
        phase: str = "",
        agent: str = "UNASSIGNED",
        priority: str = "medium",
        description: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new task.

        Args:
            title: Task title (required, max 200 chars).
            phase: Phase identifier (e.g. "phase_5", "production").
            agent: Assigned agent (SAPPHIRE, EMERALD, OBSIDIAN, UNASSIGNED).
            priority: Task priority (low, medium, high, critical).
            description: Detailed description (max 2000 chars).
            tags: Optional list of tags for categorization.

        Returns:
            Created task dict or error.
        """
        with self._lock:
            title_clean = str(title or "").strip()[:self.MAX_TITLE_LENGTH]
            if not title_clean:
                return {"ok": False, "error": "Title is required."}

            agent_clean = str(agent or "UNASSIGNED").strip().upper()
            if agent_clean not in VALID_AGENTS:
                agent_clean = "UNASSIGNED"

            priority_clean = str(priority or "medium").strip().lower()
            if priority_clean not in VALID_PRIORITIES:
                priority_clean = "medium"

            phase_clean = str(phase or "").strip().lower()[:50]
            description_clean = str(description or "").strip()[:self.MAX_DESCRIPTION_LENGTH]
            tags_clean = [str(t).strip().lower()[:30] for t in (tags or []) if str(t).strip()][:10]

            self._task_counter += 1
            task_id = f"TASK-{self._task_counter:05d}"

            task = {
                "task_id": task_id,
                "title": title_clean,
                "phase": phase_clean,
                "agent": agent_clean,
                "priority": priority_clean,
                "status": "pending",
                "description": description_clean,
                "tags": tags_clean,
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
                "completed_at": None,
                "milestones": [],
                "deliverables": [],
                "notes": [],
            }

            self._tasks[task_id] = task
            self._enforce_limits()
            self._persist()

            logger.info(f"Task created: {task_id} — {title_clean} (agent={agent_clean})")
            return {"ok": True, "task": task}

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Retrieve a task by ID."""
        with self._lock:
            task_id_clean = str(task_id or "").strip().upper()
            task = self._tasks.get(task_id_clean)
            if not task:
                return {"ok": False, "error": f"Task not found: {task_id_clean}"}
            # Attach milestones and deliverables
            enriched = dict(task)
            enriched["milestones"] = [
                self._milestones[mid]
                for mid in task.get("milestones", [])
                if mid in self._milestones
            ]
            enriched["deliverables"] = [
                self._deliverables[did]
                for did in task.get("deliverables", [])
                if did in self._deliverables
            ]
            return {"ok": True, "task": enriched}

    def update_task(
        self,
        task_id: str,
        status: str = "",
        priority: str = "",
        agent: str = "",
        title: str = "",
        description: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update a task's fields.

        Only provided (non-empty) fields are updated.
        """
        with self._lock:
            task_id_clean = str(task_id or "").strip().upper()
            task = self._tasks.get(task_id_clean)
            if not task:
                return {"ok": False, "error": f"Task not found: {task_id_clean}"}

            if status:
                status_clean = str(status).strip().lower()
                if status_clean not in VALID_STATUSES:
                    return {"ok": False, "error": f"Invalid status: {status_clean}"}
                task["status"] = status_clean
                if status_clean == "completed":
                    task["completed_at"] = int(time.time())

            if priority:
                priority_clean = str(priority).strip().lower()
                if priority_clean in VALID_PRIORITIES:
                    task["priority"] = priority_clean

            if agent:
                agent_clean = str(agent).strip().upper()
                if agent_clean in VALID_AGENTS:
                    task["agent"] = agent_clean

            if title:
                task["title"] = str(title).strip()[:self.MAX_TITLE_LENGTH]

            if description:
                task["description"] = str(description).strip()[:self.MAX_DESCRIPTION_LENGTH]

            if tags is not None:
                task["tags"] = [str(t).strip().lower()[:30] for t in tags if str(t).strip()][:10]

            task["updated_at"] = int(time.time())
            self._persist()

            logger.info(f"Task updated: {task_id_clean} status={task['status']}")
            return {"ok": True, "task": task}

    def delete_task(self, task_id: str) -> dict[str, Any]:
        """Delete a task and its linked milestones/deliverables."""
        with self._lock:
            task_id_clean = str(task_id or "").strip().upper()
            task = self._tasks.pop(task_id_clean, None)
            if not task:
                return {"ok": False, "error": f"Task not found: {task_id_clean}"}

            # Clean up linked milestones and deliverables
            for mid in task.get("milestones", []):
                self._milestones.pop(mid, None)
            for did in task.get("deliverables", []):
                self._deliverables.pop(did, None)

            self._persist()
            logger.info(f"Task deleted: {task_id_clean}")
            return {"ok": True, "deleted_task_id": task_id_clean}

    def list_tasks(
        self,
        phase: str = "",
        agent: str = "",
        status: str = "",
        priority: str = "",
        tag: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        """List tasks with optional filters.

        Args:
            phase: Filter by phase.
            agent: Filter by assigned agent.
            status: Filter by status.
            priority: Filter by priority.
            tag: Filter by tag.
            limit: Max results (default 50).

        Returns:
            Filtered task list.
        """
        with self._lock:
            tasks = list(self._tasks.values())

            if phase:
                phase_clean = str(phase).strip().lower()
                tasks = [t for t in tasks if t["phase"] == phase_clean]

            if agent:
                agent_clean = str(agent).strip().upper()
                tasks = [t for t in tasks if t["agent"] == agent_clean]

            if status:
                status_clean = str(status).strip().lower()
                tasks = [t for t in tasks if t["status"] == status_clean]

            if priority:
                priority_clean = str(priority).strip().lower()
                tasks = [t for t in tasks if t["priority"] == priority_clean]

            if tag:
                tag_clean = str(tag).strip().lower()
                tasks = [t for t in tasks if tag_clean in t.get("tags", [])]

            # Sort by priority weight then created_at
            priority_weight = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            tasks.sort(key=lambda t: (priority_weight.get(t["priority"], 2), t["created_at"]))

            limited = tasks[:max(1, min(limit, 200))]
            return {
                "ok": True,
                "tasks": limited,
                "total": len(tasks),
                "showing": len(limited),
            }

    # ── Milestones ────────────────────────────────────────────────

    def add_milestone(
        self,
        task_id: str,
        title: str,
        target_date: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """Add a milestone to a task.

        Args:
            task_id: Parent task ID.
            title: Milestone title.
            target_date: Target completion date (YYYY-MM-DD).
            description: Milestone description.

        Returns:
            Created milestone or error.
        """
        with self._lock:
            task_id_clean = str(task_id or "").strip().upper()
            task = self._tasks.get(task_id_clean)
            if not task:
                return {"ok": False, "error": f"Task not found: {task_id_clean}"}

            if len(task.get("milestones", [])) >= self.MAX_MILESTONES_PER_TASK:
                return {"ok": False, "error": "Maximum milestones reached for this task."}

            title_clean = str(title or "").strip()[:self.MAX_TITLE_LENGTH]
            if not title_clean:
                return {"ok": False, "error": "Milestone title is required."}

            self._milestone_counter += 1
            milestone_id = f"MS-{self._milestone_counter:05d}"

            milestone = {
                "milestone_id": milestone_id,
                "task_id": task_id_clean,
                "title": title_clean,
                "target_date": str(target_date or "").strip()[:10],
                "description": str(description or "").strip()[:self.MAX_DESCRIPTION_LENGTH],
                "completed": False,
                "completed_at": None,
                "created_at": int(time.time()),
            }

            self._milestones[milestone_id] = milestone
            task["milestones"].append(milestone_id)
            task["updated_at"] = int(time.time())
            self._persist()

            logger.info(f"Milestone added: {milestone_id} → {task_id_clean}")
            return {"ok": True, "milestone": milestone}

    def complete_milestone(self, milestone_id: str) -> dict[str, Any]:
        """Mark a milestone as completed."""
        with self._lock:
            mid_clean = str(milestone_id or "").strip().upper()
            milestone = self._milestones.get(mid_clean)
            if not milestone:
                return {"ok": False, "error": f"Milestone not found: {mid_clean}"}

            milestone["completed"] = True
            milestone["completed_at"] = int(time.time())

            # Update parent task timestamp
            task = self._tasks.get(milestone["task_id"])
            if task:
                task["updated_at"] = int(time.time())

            self._persist()
            logger.info(f"Milestone completed: {mid_clean}")
            return {"ok": True, "milestone": milestone}

    # ── Deliverables ──────────────────────────────────────────────

    def add_deliverable(
        self,
        task_id: str,
        title: str,
        deliverable_type: str = "code",
        description: str = "",
        reference: str = "",
    ) -> dict[str, Any]:
        """Add a deliverable to a task.

        Args:
            task_id: Parent task ID.
            title: Deliverable title.
            deliverable_type: Type (code, test, doc, config, deploy).
            description: Deliverable description.
            reference: Reference link (PR URL, file path, etc).

        Returns:
            Created deliverable or error.
        """
        with self._lock:
            task_id_clean = str(task_id or "").strip().upper()
            task = self._tasks.get(task_id_clean)
            if not task:
                return {"ok": False, "error": f"Task not found: {task_id_clean}"}

            if len(task.get("deliverables", [])) >= self.MAX_DELIVERABLES_PER_TASK:
                return {"ok": False, "error": "Maximum deliverables reached for this task."}

            title_clean = str(title or "").strip()[:self.MAX_TITLE_LENGTH]
            if not title_clean:
                return {"ok": False, "error": "Deliverable title is required."}

            valid_types = {"code", "test", "doc", "config", "deploy", "other"}
            type_clean = str(deliverable_type or "code").strip().lower()
            if type_clean not in valid_types:
                type_clean = "other"

            self._deliverable_counter += 1
            deliverable_id = f"DLV-{self._deliverable_counter:05d}"

            deliverable = {
                "deliverable_id": deliverable_id,
                "task_id": task_id_clean,
                "title": title_clean,
                "type": type_clean,
                "description": str(description or "").strip()[:self.MAX_DESCRIPTION_LENGTH],
                "reference": str(reference or "").strip()[:500],
                "verified": False,
                "verified_at": None,
                "created_at": int(time.time()),
            }

            self._deliverables[deliverable_id] = deliverable
            task["deliverables"].append(deliverable_id)
            task["updated_at"] = int(time.time())
            self._persist()

            logger.info(f"Deliverable added: {deliverable_id} → {task_id_clean}")
            return {"ok": True, "deliverable": deliverable}

    def verify_deliverable(self, deliverable_id: str) -> dict[str, Any]:
        """Mark a deliverable as verified."""
        with self._lock:
            did_clean = str(deliverable_id or "").strip().upper()
            deliverable = self._deliverables.get(did_clean)
            if not deliverable:
                return {"ok": False, "error": f"Deliverable not found: {did_clean}"}

            deliverable["verified"] = True
            deliverable["verified_at"] = int(time.time())

            # Update parent task timestamp
            task = self._tasks.get(deliverable["task_id"])
            if task:
                task["updated_at"] = int(time.time())

            self._persist()
            logger.info(f"Deliverable verified: {did_clean}")
            return {"ok": True, "deliverable": deliverable}

    # ── Notes ─────────────────────────────────────────────────────

    def add_note(
        self, task_id: str, text: str, author: str = "SYSTEM"
    ) -> dict[str, Any]:
        """Add a note/comment to a task.

        Args:
            task_id: Task to add note to.
            text: Note content (max 1000 chars).
            author: Note author (agent name or SYSTEM).

        Returns:
            Note metadata or error.
        """
        with self._lock:
            task_id_clean = str(task_id or "").strip().upper()
            task = self._tasks.get(task_id_clean)
            if not task:
                return {"ok": False, "error": f"Task not found: {task_id_clean}"}

            text_clean = str(text or "").strip()[:self.MAX_NOTES_LENGTH]
            if not text_clean:
                return {"ok": False, "error": "Note text is required."}

            author_clean = str(author or "SYSTEM").strip().upper()[:32]
            note = {
                "text": text_clean,
                "author": author_clean,
                "created_at": int(time.time()),
            }

            if "notes" not in task:
                task["notes"] = []
            task["notes"].append(note)

            # Cap notes at 50 per task
            if len(task["notes"]) > 50:
                task["notes"] = task["notes"][-50:]

            task["updated_at"] = int(time.time())
            self._persist()

            logger.info(f"Note added to {task_id_clean} by {author_clean}")
            return {"ok": True, "note": note, "total_notes": len(task["notes"])}

    # ── Progress Reports ──────────────────────────────────────────

    def progress_report(
        self, phase: str = "", agent: str = ""
    ) -> dict[str, Any]:
        """Generate a progress report.

        Args:
            phase: Filter by phase (optional).
            agent: Filter by agent (optional).

        Returns:
            Comprehensive progress report dict.
        """
        with self._lock:
            tasks = list(self._tasks.values())

            if phase:
                phase_clean = str(phase).strip().lower()
                tasks = [t for t in tasks if t["phase"] == phase_clean]

            if agent:
                agent_clean = str(agent).strip().upper()
                tasks = [t for t in tasks if t["agent"] == agent_clean]

            total = len(tasks)
            if total == 0:
                return {
                    "ok": True,
                    "total": 0,
                    "by_status": {},
                    "by_agent": {},
                    "by_priority": {},
                    "completion_rate": 0.0,
                    "milestones_summary": {"total": 0, "completed": 0},
                    "deliverables_summary": {"total": 0, "verified": 0},
                    "recent_activity": [],
                }

            # Status breakdown
            by_status: dict[str, int] = {}
            for t in tasks:
                s = t["status"]
                by_status[s] = by_status.get(s, 0) + 1

            # Agent breakdown
            by_agent: dict[str, dict[str, int]] = {}
            for t in tasks:
                a = t["agent"]
                if a not in by_agent:
                    by_agent[a] = {"total": 0, "completed": 0, "in_progress": 0}
                by_agent[a]["total"] += 1
                if t["status"] == "completed":
                    by_agent[a]["completed"] += 1
                elif t["status"] == "in_progress":
                    by_agent[a]["in_progress"] += 1

            # Priority breakdown
            by_priority: dict[str, int] = {}
            for t in tasks:
                p = t["priority"]
                by_priority[p] = by_priority.get(p, 0) + 1

            # Milestones summary
            all_milestone_ids = []
            for t in tasks:
                all_milestone_ids.extend(t.get("milestones", []))
            ms_total = len(all_milestone_ids)
            ms_completed = sum(
                1 for mid in all_milestone_ids
                if self._milestones.get(mid, {}).get("completed", False)
            )

            # Deliverables summary
            all_deliverable_ids = []
            for t in tasks:
                all_deliverable_ids.extend(t.get("deliverables", []))
            dlv_total = len(all_deliverable_ids)
            dlv_verified = sum(
                1 for did in all_deliverable_ids
                if self._deliverables.get(did, {}).get("verified", False)
            )

            # Completion rate
            completed = by_status.get("completed", 0)
            completion_rate = round(completed / total, 4) if total > 0 else 0.0

            # Recent activity (last 10 updated tasks)
            sorted_tasks = sorted(tasks, key=lambda t: t["updated_at"], reverse=True)
            recent = [
                {
                    "task_id": t["task_id"],
                    "title": t["title"],
                    "status": t["status"],
                    "agent": t["agent"],
                    "updated_at": t["updated_at"],
                }
                for t in sorted_tasks[:10]
            ]

            return {
                "ok": True,
                "total": total,
                "by_status": by_status,
                "by_agent": by_agent,
                "by_priority": by_priority,
                "completion_rate": completion_rate,
                "milestones_summary": {"total": ms_total, "completed": ms_completed},
                "deliverables_summary": {"total": dlv_total, "verified": dlv_verified},
                "recent_activity": recent,
                "filter_phase": phase or "all",
                "filter_agent": agent or "all",
            }

    def agent_report(self, agent: str) -> dict[str, Any]:
        """Generate a report for a specific agent's tasks.

        Args:
            agent: Agent name (SAPPHIRE, EMERALD, OBSIDIAN).

        Returns:
            Agent-specific report with task details.
        """
        with self._lock:
            agent_clean = str(agent or "").strip().upper()
            if agent_clean not in VALID_AGENTS or agent_clean == "UNASSIGNED":
                return {"ok": False, "error": f"Invalid agent: {agent_clean}"}

            tasks = [t for t in self._tasks.values() if t["agent"] == agent_clean]
            total = len(tasks)

            if total == 0:
                return {
                    "ok": True,
                    "agent": agent_clean,
                    "total": 0,
                    "tasks": [],
                    "completion_rate": 0.0,
                }

            completed = sum(1 for t in tasks if t["status"] == "completed")
            in_progress = sum(1 for t in tasks if t["status"] == "in_progress")
            blocked = sum(1 for t in tasks if t["status"] == "blocked")

            # Sort by priority then status
            status_weight = {"blocked": 0, "in_progress": 1, "pending": 2, "completed": 3, "cancelled": 4}
            priority_weight = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            tasks.sort(
                key=lambda t: (
                    status_weight.get(t["status"], 2),
                    priority_weight.get(t["priority"], 2),
                )
            )

            task_summaries = [
                {
                    "task_id": t["task_id"],
                    "title": t["title"],
                    "status": t["status"],
                    "priority": t["priority"],
                    "phase": t["phase"],
                    "milestones_done": sum(
                        1 for mid in t.get("milestones", [])
                        if self._milestones.get(mid, {}).get("completed", False)
                    ),
                    "milestones_total": len(t.get("milestones", [])),
                    "deliverables_done": sum(
                        1 for did in t.get("deliverables", [])
                        if self._deliverables.get(did, {}).get("verified", False)
                    ),
                    "deliverables_total": len(t.get("deliverables", [])),
                }
                for t in tasks
            ]

            return {
                "ok": True,
                "agent": agent_clean,
                "total": total,
                "completed": completed,
                "in_progress": in_progress,
                "blocked": blocked,
                "completion_rate": round(completed / total, 4) if total > 0 else 0.0,
                "tasks": task_summaries,
            }

    def summary(self) -> dict[str, Any]:
        """Quick overall summary of the task system."""
        with self._lock:
            total = len(self._tasks)
            if total == 0:
                return {
                    "ok": True,
                    "total_tasks": 0,
                    "total_milestones": 0,
                    "total_deliverables": 0,
                    "agents": {},
                    "phases": {},
                }

            by_agent: dict[str, int] = {}
            by_phase: dict[str, int] = {}
            by_status: dict[str, int] = {}
            for t in self._tasks.values():
                by_agent[t["agent"]] = by_agent.get(t["agent"], 0) + 1
                if t["phase"]:
                    by_phase[t["phase"]] = by_phase.get(t["phase"], 0) + 1
                by_status[t["status"]] = by_status.get(t["status"], 0) + 1

            return {
                "ok": True,
                "total_tasks": total,
                "total_milestones": len(self._milestones),
                "total_deliverables": len(self._deliverables),
                "by_status": by_status,
                "agents": by_agent,
                "phases": by_phase,
            }

    # ── Batch Operations ──────────────────────────────────────────

    def bulk_create_from_phase(
        self, phase: str, items: list[dict[str, str]]
    ) -> dict[str, Any]:
        """Create multiple tasks for a phase at once.

        Args:
            phase: Phase identifier.
            items: List of dicts with 'title', optional 'agent', 'priority',
                   'description', 'tags'.

        Returns:
            Batch creation result.
        """
        if not items or not isinstance(items, list):
            return {"ok": False, "error": "Items list is required."}

        created = []
        errors = []
        for i, item in enumerate(items[:50]):  # Cap at 50
            if not isinstance(item, dict):
                errors.append({"index": i, "error": "Item must be a dict."})
                continue

            result = self.create_task(
                title=str(item.get("title", "")),
                phase=phase,
                agent=str(item.get("agent", "UNASSIGNED")),
                priority=str(item.get("priority", "medium")),
                description=str(item.get("description", "")),
                tags=item.get("tags"),
            )
            if result.get("ok"):
                created.append(result["task"])
            else:
                errors.append({"index": i, "error": result.get("error", "unknown")})

        return {
            "ok": len(created) > 0,
            "created": len(created),
            "errors": len(errors),
            "error_details": errors,
            "task_ids": [t["task_id"] for t in created],
        }

    # ── Internal Helpers ──────────────────────────────────────────

    def _enforce_limits(self):
        """Remove oldest completed tasks if over limit."""
        if len(self._tasks) <= self.MAX_TASKS:
            return
        # Remove oldest completed tasks first
        completed = [
            (tid, t) for tid, t in self._tasks.items()
            if t["status"] in ("completed", "cancelled")
        ]
        completed.sort(key=lambda x: x[1].get("completed_at") or x[1]["created_at"])
        while len(self._tasks) > self.MAX_TASKS and completed:
            tid, _ = completed.pop(0)
            task = self._tasks.pop(tid, None)
            if task:
                for mid in task.get("milestones", []):
                    self._milestones.pop(mid, None)
                for did in task.get("deliverables", []):
                    self._deliverables.pop(did, None)

    def _persist(self):
        """Persist state to JSON file if store_path is configured."""
        if not self._store_path:
            return
        try:
            data = {
                "tasks": self._tasks,
                "milestones": self._milestones,
                "deliverables": self._deliverables,
                "task_counter": self._task_counter,
                "milestone_counter": self._milestone_counter,
                "deliverable_counter": self._deliverable_counter,
                "saved_at": int(time.time()),
            }
            path = Path(self._store_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, default=str))
        except Exception as exc:
            logger.warning(f"Task store persist failed: {exc}")

    def _load_store(self):
        """Load state from JSON file."""
        if not self._store_path:
            return
        try:
            path = Path(self._store_path)
            if not path.exists():
                return
            data = json.loads(path.read_text())
            self._tasks = data.get("tasks", {})
            self._milestones = data.get("milestones", {})
            self._deliverables = data.get("deliverables", {})
            self._task_counter = data.get("task_counter", 0)
            self._milestone_counter = data.get("milestone_counter", 0)
            self._deliverable_counter = data.get("deliverable_counter", 0)
            logger.info(
                f"Task store loaded: {len(self._tasks)} tasks, "
                f"{len(self._milestones)} milestones, "
                f"{len(self._deliverables)} deliverables"
            )
        except Exception as exc:
            logger.warning(f"Task store load failed: {exc}")


# ── Roadmap Parser ────────────────────────────────────────────────────

# Maps phase header keywords → agent assignment.
# Order matters: more specific patterns are tried first, then generic ones.
# Uses word-boundary regex to avoid substring false positives (e.g. "ci" in "social").
_PHASE_AGENT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bsocial\b"), "SAPPHIRE"),
    (re.compile(r"\bmedia\b"), "SAPPHIRE"),
    (re.compile(r"\bprediction\b"), "SAPPHIRE"),
    (re.compile(r"\btrading\b"), "SAPPHIRE"),
    (re.compile(r"\bsecurity\b"), "EMERALD"),
    (re.compile(r"\bforum\b"), "EMERALD"),
    (re.compile(r"\bswarm\b"), "EMERALD"),
    (re.compile(r"\breputation\b"), "EMERALD"),
    (re.compile(r"\bvirtuals\b"), "EMERALD"),
    (re.compile(r"\btest(?:ing|s)?\b"), "EMERALD"),
    (re.compile(r"\bhardening\b"), "OBSIDIAN"),
    (re.compile(r"\binfrastructure\b"), "OBSIDIAN"),
    (re.compile(r"\bdeploy\b"), "OBSIDIAN"),
    (re.compile(r"\bci(?:/cd)?\b"), "OBSIDIAN"),
    (re.compile(r"\bopenclaw\b"), "OBSIDIAN"),
    (re.compile(r"\bagent\b"), "OBSIDIAN"),
]


class RoadmapParser:
    """Parses ROADMAP.md and generates tasks for incomplete items.

    Scans for ``- [ ]`` checkboxes, groups them by phase header, assigns
    agents based on keyword matching, and creates tasks in the
    ``TaskManager`` (skipping duplicates by title).

    Usage::

        parser = RoadmapParser("/path/to/ROADMAP.md")
        result = parser.generate_tasks(task_manager)
        # result: {"ok": True, "created": 5, "skipped": 2, "items_found": 7}
    """

    def __init__(self, roadmap_path: str = ""):
        self.roadmap_path = roadmap_path or os.getenv(
            "SAPPHIRE_ROADMAP_PATH",
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "ROADMAP.md"),
        )

    def parse_incomplete_items(self) -> list[dict[str, str]]:
        """Scan ROADMAP.md for unchecked ``- [ ]`` items.

        Returns a list of dicts with 'title', 'phase', 'agent'.
        """
        path = Path(self.roadmap_path).resolve()
        if not path.exists():
            logger.warning(f"Roadmap file not found: {path}")
            return []

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Failed to read roadmap: {exc}")
            return []

        items: list[dict[str, str]] = []
        current_phase = "unknown"

        for line in content.splitlines():
            line_stripped = line.strip()

            # Detect phase headers (## Phase N: Title)
            phase_match = re.match(r"^#{1,3}\s+(?:Phase\s+\d+[:\s]*)?(.+)", line_stripped)
            if phase_match:
                current_phase = phase_match.group(1).strip().rstrip("✅🔮⚡🔒📖🐝📋📢🤖🌐 ")
                continue

            # Detect incomplete checkbox items
            if re.match(r"^-\s*\[\s*\]\s+", line_stripped):
                title = re.sub(r"^-\s*\[\s*\]\s+", "", line_stripped).strip()
                if not title:
                    continue
                agent = self._infer_agent(current_phase, title)
                items.append({
                    "title": title[:200],
                    "phase": self._normalize_phase(current_phase),
                    "agent": agent,
                })

        return items

    def generate_tasks(self, task_manager: "TaskManager") -> dict[str, Any]:
        """Create tasks for all unchecked roadmap items.

        Skips items whose title already exists as an active task (pending /
        in_progress / blocked).  Returns summary of actions taken.
        """
        items = self.parse_incomplete_items()
        if not items:
            return {"ok": True, "created": 0, "skipped": 0, "items_found": 0}

        # Gather existing titles to avoid duplicates
        existing_titles: set = set()
        try:
            with task_manager._lock:
                for task in task_manager._tasks.values():
                    if task["status"] in ("pending", "in_progress", "blocked"):
                        existing_titles.add(task["title"].strip().lower())
        except Exception:
            pass

        created = 0
        skipped = 0
        for item in items:
            if item["title"].strip().lower() in existing_titles:
                skipped += 1
                continue

            result = task_manager.create_task(
                title=item["title"],
                phase=item["phase"],
                agent=item["agent"],
                priority="medium",
                description=f"Auto-generated from ROADMAP.md ({item['phase']})",
                tags=["roadmap", "auto_generated"],
            )
            if result.get("ok"):
                created += 1
            else:
                skipped += 1

        logger.info(f"RoadmapParser: {created} tasks created, {skipped} skipped, {len(items)} items found")
        return {
            "ok": True,
            "created": created,
            "skipped": skipped,
            "items_found": len(items),
        }

    # ── Internal helpers ─────────────────────────────────────────

    @staticmethod
    def _infer_agent(phase: str, title: str) -> str:
        """Pick agent based on phase keywords and item text."""
        combined = f"{phase} {title}".lower()
        for pattern, agent in _PHASE_AGENT_PATTERNS:
            if pattern.search(combined):
                return agent
        return "OBSIDIAN"  # default to OBSIDIAN

    @staticmethod
    def _normalize_phase(raw: str) -> str:
        """Normalize a phase header into a slug."""
        slug = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
        return slug[:60] if slug else "unknown"
