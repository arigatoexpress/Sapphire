from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _as_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BISSettings:
    environment: str
    require_auth: bool
    app_password: str
    app_username: str
    project_id: str
    backup_dir: str
    autosave_snapshots: bool
    gcs_snapshot_bucket: str
    gcs_snapshot_blob: str
    default_spreadsheet_id: str
    sheets_new_properties_tab: str
    sheets_property_updates_tab: str
    sheets_notes_tab: str
    sheets_input_tab: str
    sheets_computed_tab: str
    sheets_master_view_tab: str
    sheets_reviews_tab: str
    sheets_change_log_tab: str
    sheets_today_tasks_tab: str


@lru_cache(maxsize=1)
def get_settings() -> BISSettings:
    app_password = os.getenv("BIS_APP_PASSWORD", "").strip()
    require_auth = _as_bool(os.getenv("BIS_REQUIRE_AUTH"), default=bool(app_password))
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID") or "local"
    return BISSettings(
        environment=os.getenv("BIS_ENV", "beta").strip() or "beta",
        require_auth=require_auth,
        app_password=app_password,
        app_username=os.getenv("BIS_APP_USERNAME", "blanga").strip() or "blanga",
        project_id=project_id,
        backup_dir=(os.getenv("BIS_BACKUP_DIR", "/tmp/blanga-bis-backups").strip() or "/tmp/blanga-bis-backups"),
        autosave_snapshots=_as_bool(os.getenv("BIS_AUTOSAVE_SNAPSHOTS"), default=True),
        gcs_snapshot_bucket=(os.getenv("BIS_GCS_SNAPSHOT_BUCKET", "").strip()),
        gcs_snapshot_blob=(os.getenv("BIS_GCS_SNAPSHOT_BLOB", "snapshots/master_arena_snapshot.latest.json").strip()
                           or "snapshots/master_arena_snapshot.latest.json"),
        default_spreadsheet_id=(os.getenv("BIS_GOOGLE_SHEETS_SPREADSHEET_ID", "").strip()),
        sheets_new_properties_tab=(os.getenv("BIS_SHEETS_NEW_PROPERTIES_TAB", "properties_new_input").strip() or "properties_new_input"),
        sheets_property_updates_tab=(os.getenv("BIS_SHEETS_PROPERTY_UPDATES_TAB", "property_updates_input").strip() or "property_updates_input"),
        sheets_notes_tab=(os.getenv("BIS_SHEETS_NOTES_TAB", "notes_input").strip() or "notes_input"),
        sheets_input_tab=(os.getenv("BIS_SHEETS_INPUT_TAB", "properties_input").strip() or "properties_input"),
        sheets_computed_tab=(os.getenv("BIS_SHEETS_COMPUTED_TAB", "properties_computed").strip() or "properties_computed"),
        sheets_master_view_tab=(os.getenv("BIS_SHEETS_MASTER_VIEW_TAB", "properties_master_view").strip() or "properties_master_view"),
        sheets_reviews_tab=(os.getenv("BIS_SHEETS_REVIEWS_TAB", "reviews_pending").strip() or "reviews_pending"),
        sheets_change_log_tab=(os.getenv("BIS_SHEETS_CHANGE_LOG_TAB", "change_log_view").strip() or "change_log_view"),
        sheets_today_tasks_tab=(os.getenv("BIS_SHEETS_TODAY_TASKS_TAB", "today_tasks_view").strip() or "today_tasks_view"),
    )
