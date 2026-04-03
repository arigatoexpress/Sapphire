from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

try:
    import google.auth  # type: ignore
    from googleapiclient.discovery import build  # type: ignore
except Exception:  # pragma: no cover
    google = None  # type: ignore
    build = None  # type: ignore

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


@dataclass(frozen=True)
class GoogleSheetsClientStatus:
    available: bool
    auth_ok: bool
    project_id: str = ""
    error: str = ""


def _service():
    if build is None:
        raise RuntimeError("google-api-python-client is not installed")
    if google is None:
        raise RuntimeError("google-auth is not installed")
    credentials, project_id = google.auth.default(scopes=[SHEETS_SCOPE])  # type: ignore[attr-defined]
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    return service, str(project_id or "")


def sheets_client_status() -> GoogleSheetsClientStatus:
    if build is None or google is None:
        return GoogleSheetsClientStatus(available=False, auth_ok=False, error="google sheets client libs unavailable")
    try:
        _, project_id = _service()
        return GoogleSheetsClientStatus(available=True, auth_ok=True, project_id=project_id)
    except Exception as exc:
        return GoogleSheetsClientStatus(available=True, auth_ok=False, error=str(exc))


def _range_for_tab(tab_name: str) -> str:
    return f"'{tab_name}'!A:ZZ"


def read_sheet_rows(spreadsheet_id: str, tab_name: str) -> List[Dict[str, Any]]:
    service, _ = _service()
    resp = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=_range_for_tab(tab_name))
        .execute()
    )
    values = resp.get("values", [])
    if not values:
        return []
    headers = [str(h).strip() for h in values[0]]
    rows: List[Dict[str, Any]] = []
    for raw in values[1:]:
        if not any(str(cell).strip() for cell in raw):
            continue
        row: Dict[str, Any] = {}
        for i, header in enumerate(headers):
            if not header:
                continue
            row[header] = raw[i] if i < len(raw) else ""
        rows.append(row)
    return rows


def write_sheet_rows(spreadsheet_id: str, tab_name: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    service, _ = _service()
    if rows:
        headers: List[str] = []
        seen = set()
        for row in rows:
            for key in row.keys():
                key_str = str(key)
                if key_str not in seen:
                    seen.add(key_str)
                    headers.append(key_str)
        values: List[List[Any]] = [headers]
        for row in rows:
            values.append([row.get(h, "") for h in headers])
    else:
        values = [[]]

    range_a1 = _range_for_tab(tab_name)
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
        body={},
    ).execute()
    resp = (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
            valueInputOption="RAW",
            body={"values": values},
        )
        .execute()
    )
    return {
        "updated_range": resp.get("updatedRange"),
        "updated_rows": resp.get("updatedRows", 0),
        "updated_columns": resp.get("updatedColumns", 0),
        "updated_cells": resp.get("updatedCells", 0),
        "row_count_written": len(rows),
    }

