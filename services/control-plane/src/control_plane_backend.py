from __future__ import annotations

import importlib.util
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


_SUPPORTED_BACKENDS = {"sqlite", "postgres"}


def _backend_kind_from_env() -> str:
    raw = str(os.getenv("AGENTIC_CONTROL_PLANE_STORE_BACKEND") or "sqlite").strip().lower()
    return raw or "sqlite"


def _postgres_experimental_enabled() -> bool:
    raw = str(os.getenv("AGENTIC_CONTROL_PLANE_STORE_POSTGRES_EXPERIMENTAL") or "").strip().lower()
    return raw in {"1", "true", "yes", "on", "enabled"}


def _postgres_env_status() -> dict[str, Any]:
    dsn = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_DSN") or "").strip()
    cloudsql_instance = str(os.getenv("AGENTIC_CONTROL_PLANE_CLOUDSQL_INSTANCE") or "").strip()
    cloudsql_project = str(
        os.getenv("AGENTIC_CONTROL_PLANE_CLOUDSQL_PROJECT")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or ""
    ).strip()
    database = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_DB") or "").strip()
    user = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_USER") or "").strip()
    host = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_HOST") or "").strip()
    sslmode = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_SSLMODE") or "").strip().lower() or "default"
    password_present = bool(str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_PASSWORD") or "").strip())
    socket_path = f"/cloudsql/{cloudsql_instance}" if cloudsql_instance else ""
    explicit_parts_configured = bool(database and user and (host or socket_path))
    return {
        "dsn_present": bool(dsn),
        "cloudsql_instance_present": bool(cloudsql_instance),
        "cloudsql_project_present": bool(cloudsql_project),
        "database_present": bool(database),
        "user_present": bool(user),
        "host_present": bool(host),
        "socket_path_present": bool(socket_path),
        "password_present": password_present,
        "sslmode": sslmode,
        "configured_minimally": bool(dsn) or explicit_parts_configured,
    }


def _postgres_driver_name() -> str:
    if importlib.util.find_spec("psycopg") is not None:
        return "psycopg"
    if importlib.util.find_spec("psycopg2") is not None:
        return "psycopg2"
    return ""


def _postgres_driver_available() -> bool:
    return bool(_postgres_driver_name())


def _postgres_connect_config() -> dict[str, Any]:
    dsn = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_DSN") or "").strip()
    database = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_DB") or "").strip()
    user = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_USER") or "").strip()
    password = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_PASSWORD") or "").strip()
    host = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_HOST") or "").strip()
    port = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_PORT") or "").strip()
    sslmode = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_SSLMODE") or "").strip().lower() or "prefer"
    cloudsql_instance = str(os.getenv("AGENTIC_CONTROL_PLANE_CLOUDSQL_INSTANCE") or "").strip()
    socket_dir = f"/cloudsql/{cloudsql_instance}" if cloudsql_instance else ""
    return {
        "dsn": dsn,
        "password": password,
        "database": database,
        "user": user,
        "password_present": bool(password),
        "host": host,
        "port": port,
        "sslmode": sslmode,
        "cloudsql_instance": cloudsql_instance,
        "socket_dir": socket_dir,
    }


def _import_postgres_driver() -> tuple[str, Any]:
    driver_name = _postgres_driver_name()
    if driver_name == "psycopg":
        import psycopg  # type: ignore

        return ("psycopg", psycopg)
    if driver_name == "psycopg2":
        import psycopg2  # type: ignore

        return ("psycopg2", psycopg2)
    raise RuntimeError("No PostgreSQL driver available (install psycopg or psycopg2)")


class _PgCursorCompat:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def _normalize_row(self, row: Any) -> Any:
        if row is None:
            return None
        if isinstance(row, dict):
            return row
        mapping = getattr(row, "_mapping", None)
        if mapping is not None:
            try:
                return dict(mapping)
            except Exception:
                return row
        keys_attr = getattr(row, "keys", None)
        if callable(keys_attr):
            try:
                return {str(key): row[key] for key in row.keys()}
            except Exception:
                return row
        return row

    def fetchone(self) -> Any:
        fetch = getattr(self._cursor, "fetchone", None)
        if not callable(fetch):
            return None
        return self._normalize_row(fetch())

    def fetchall(self) -> list[Any]:
        fetch = getattr(self._cursor, "fetchall", None)
        if not callable(fetch):
            return []
        rows = fetch()
        return [self._normalize_row(row) for row in rows]

    @property
    def rowcount(self) -> int:
        try:
            return int(getattr(self._cursor, "rowcount", -1))
        except Exception:
            return -1

    def close(self) -> None:
        close = getattr(self._cursor, "close", None)
        if callable(close):
            close()


class PostgresConnectionCompat:
    def __init__(self, raw_connection: Any, cursor_factory: Callable[[Any], Any]) -> None:
        self._raw_connection = raw_connection
        self._cursor_factory = cursor_factory

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> _PgCursorCompat:
        cursor = self._cursor_factory(self._raw_connection)
        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, params)
        return _PgCursorCompat(cursor)

    def commit(self) -> None:
        self._raw_connection.commit()

    def rollback(self) -> None:
        rollback = getattr(self._raw_connection, "rollback", None)
        if callable(rollback):
            rollback()

    def close(self) -> None:
        self._raw_connection.close()

    def __enter__(self) -> "PostgresConnectionCompat":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False


def postgres_schema_statements() -> list[str]:
    return [
        """
        CREATE TABLE IF NOT EXISTS agents (
          agent_id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          capabilities_json TEXT NOT NULL,
          labels_json TEXT NOT NULL,
          metadata_json TEXT NOT NULL,
          status TEXT NOT NULL,
          registered_at TEXT NOT NULL,
          last_heartbeat_at TEXT NOT NULL,
          last_heartbeat_unix BIGINT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """.strip(),
        """
        CREATE TABLE IF NOT EXISTS tasks (
          task_id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          required_capabilities_json TEXT NOT NULL,
          status TEXT NOT NULL,
          priority INTEGER NOT NULL,
          created_by TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          lease_owner TEXT,
          lease_expires_unix BIGINT,
          attempts INTEGER NOT NULL,
          max_attempts INTEGER NOT NULL,
          result_json TEXT,
          error_text TEXT
        )
        """.strip(),
        """
        CREATE TABLE IF NOT EXISTS task_events (
          id BIGSERIAL PRIMARY KEY,
          event_id TEXT NOT NULL UNIQUE,
          task_id TEXT,
          agent_id TEXT,
          event_type TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          created_at_unix BIGINT NOT NULL
        )
        """.strip(),
        "CREATE INDEX IF NOT EXISTS idx_agents_last_heartbeat ON agents(last_heartbeat_unix)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(status, priority, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_lease_expiry ON tasks(lease_expires_unix)",
        "CREATE INDEX IF NOT EXISTS idx_events_created ON task_events(created_at_unix DESC)",
    ]


def translate_qmark_sql_to_pyformat(sql: str) -> str:
    # Migration helper for gradual query porting from sqlite `?` placeholders to psycopg `%s`.
    if "?" not in sql:
        return sql
    out: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            out.append(ch)
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append(sql[i + 1])
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue
        if ch == '"' and not in_single:
            out.append(ch)
            in_double = not in_double
            i += 1
            continue
        if ch == "?" and not in_single and not in_double:
            out.append("%s")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _status_payload(*, db_path: Path, requested_backend: str) -> dict[str, Any]:
    postgres = _postgres_env_status()
    postgres_driver = _postgres_driver_name()
    postgres_experimental = _postgres_experimental_enabled()
    postgres_execution_path_canary_ready = bool(
        requested_backend == "postgres"
        and postgres_experimental
        and postgres.get("configured_minimally")
        and bool(postgres_driver)
    )
    active_backend = "postgres" if postgres_execution_path_canary_ready else "sqlite"
    migration_phase = "sqlite_active_postgres_adapter_pending"
    if requested_backend == "postgres" and postgres_experimental:
        migration_phase = "postgres_execution_path_experimental_queries_pending"
    query_adapterized_slices = [
        "task_events.record_event",
        "task_events.list_events",
        "agents.register_agent",
        "agents.heartbeat_agent",
        "agents.list_agents",
        "agents.cleanup_stale_agents",
        "tasks.create_task",
        "tasks.get_task",
        "tasks.update_task",
        "tasks.list_tasks",
        "tasks.lease_tasks",
        "tasks.extend_task_lease",
        "tasks.complete_task",
        "tasks.fail_task",
        "tasks.cancel_task",
        "tasks.watchdog.requeue_expired_leases",
        "tasks.watchdog.fail_exhausted_queued_tasks",
        "tasks.watchdog.fail_stale_leased_tasks",
        "tasks.watchdog.recover_queue_blocked_memberships",
        "tasks.watchdog.recover_single_agent_queue_constraints",
        "tasks.watchdog.auto_cancel_low_signal_tasks",
        "overview.snapshot_reads",
    ]
    sqlite_exists = False
    try:
        sqlite_exists = db_path.exists()
    except OSError:
        sqlite_exists = False

    warnings: list[str] = []
    if requested_backend not in {"sqlite", "postgres"}:
        warnings.append(f"unsupported_requested_backend:{requested_backend}")
    if requested_backend == "postgres":
        if not postgres.get("configured_minimally"):
            warnings.append("postgres_requested_but_not_configured")
        if not postgres_driver:
            warnings.append("postgres_requested_but_driver_missing")
        if not postgres_experimental:
            warnings.append("postgres_requested_but_execution_path_experimental_disabled")
        warnings.append("postgres_requested_but_queries_not_ported")
    if not sqlite_exists:
        warnings.append("sqlite_db_file_not_initialized_yet")

    return {
        "requested_backend": requested_backend,
        "active_backend": active_backend,
        "migration_phase": migration_phase,
        "supported_backends": sorted(_SUPPORTED_BACKENDS),
        "implementation": {
            "sqlite": True,
            "postgres": False,
            "postgres_connection_scaffold": True,
            "postgres_schema_bootstrap_scaffold": True,
            "postgres_sql_placeholder_translation": True,
            "postgres_execution_path_scaffold": True,
            "postgres_row_mapping_compat": True,
            "postgres_schema_bootstrap_invocation": True,
            "postgres_adapter_ready": False,
        },
        "switch_ready": False,
        "sqlite": {
            "db_path": str(db_path),
            "db_file_exists": sqlite_exists,
        },
        "postgres": {
            **postgres,
            "driver_name": postgres_driver,
            "driver_available": bool(postgres_driver),
            "experimental_execution_enabled": postgres_experimental,
            "execution_path_canary_ready": postgres_execution_path_canary_ready,
            "schema_statement_count": len(postgres_schema_statements()),
            "query_adapterized_count": len(query_adapterized_slices),
            "query_adapterized_slices": list(query_adapterized_slices),
            "queries_ported": False,
        },
        "warnings": warnings,
    }


@dataclass
class SqliteControlPlaneBackendAdapter:
    db_path: Path
    requested_backend: str = "sqlite"

    def status(self) -> dict[str, Any]:
        return _status_payload(db_path=self.db_path, requested_backend=self.requested_backend)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        return connection

    def translated_sql(self, sql: str) -> str:
        return sql

    def bootstrap_store_schema(self, conn: sqlite3.Connection) -> bool:
        return False

    @property
    def implemented(self) -> bool:
        return True


@dataclass
class PostgresControlPlaneBackendAdapter:
    db_path: Path
    requested_backend: str = "postgres"

    def status(self) -> dict[str, Any]:
        return _status_payload(db_path=self.db_path, requested_backend=self.requested_backend)

    def _connect_raw(self) -> tuple[Any, Callable[[Any], Any]]:
        driver_name, driver = _import_postgres_driver()
        config = _postgres_connect_config()
        if not (_postgres_env_status().get("configured_minimally")):
            raise RuntimeError(
                "Postgres backend requested but configuration is incomplete "
                "(set AGENTIC_CONTROL_PLANE_POSTGRES_DSN or DB/USER/HOST/CLOUDSQL vars)"
            )

        if driver_name == "psycopg":
            kwargs: dict[str, Any] = {}
            dsn = str(config.get("dsn") or "").strip()
            if dsn:
                kwargs["conninfo"] = dsn
            else:
                dbname = str(config.get("database") or "").strip()
                user = str(config.get("user") or "").strip()
                password = str(config.get("password") or "").strip()
                host = str(config.get("host") or "").strip() or str(config.get("socket_dir") or "").strip()
                port = str(config.get("port") or "").strip()
                if dbname:
                    kwargs["dbname"] = dbname
                if user:
                    kwargs["user"] = user
                if password:
                    kwargs["password"] = password
                if host:
                    kwargs["host"] = host
                if port:
                    kwargs["port"] = int(port)
                # Prefer no sslmode override for Cloud SQL unix sockets; only apply for TCP hosts.
                if host and not str(config.get("socket_dir") or "").strip():
                    kwargs["sslmode"] = str(config.get("sslmode") or "prefer")
            try:
                from psycopg.rows import dict_row  # type: ignore

                kwargs["row_factory"] = dict_row
            except Exception:
                pass
            raw = driver.connect(**kwargs)
            cursor_factory = lambda conn: conn.cursor()
            return raw, cursor_factory

        if driver_name == "psycopg2":
            kwargs = {}
            dsn = str(config.get("dsn") or "").strip()
            if dsn:
                raw = driver.connect(dsn)
            else:
                dbname = str(config.get("database") or "").strip()
                user = str(config.get("user") or "").strip()
                password = str(config.get("password") or "").strip()
                host = str(config.get("host") or "").strip() or str(config.get("socket_dir") or "").strip()
                port = str(config.get("port") or "").strip()
                if dbname:
                    kwargs["dbname"] = dbname
                if user:
                    kwargs["user"] = user
                if password:
                    kwargs["password"] = password
                if host:
                    kwargs["host"] = host
                if port:
                    kwargs["port"] = int(port)
                if host and not str(config.get("socket_dir") or "").strip():
                    kwargs["sslmode"] = str(config.get("sslmode") or "prefer")
                raw = driver.connect(**kwargs)
            try:
                import psycopg2.extras  # type: ignore

                cursor_factory = lambda conn: conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            except Exception:
                cursor_factory = lambda conn: conn.cursor()
            return raw, cursor_factory

        raise RuntimeError("Unsupported PostgreSQL driver")

    def connect(self) -> sqlite3.Connection:
        if not _postgres_experimental_enabled():
            raise NotImplementedError(
                "AGENTIC_CONTROL_PLANE_STORE_BACKEND=postgres execution path is gated. "
                "Set AGENTIC_CONTROL_PLANE_STORE_POSTGRES_EXPERIMENTAL=true for staged testing. "
                "Keep sqlite active for production until parity is complete."
            )
        raw, cursor_factory = self._connect_raw()
        return PostgresConnectionCompat(raw, cursor_factory)  # type: ignore[return-value]

    @property
    def implemented(self) -> bool:
        return _postgres_experimental_enabled()

    def schema_statements(self) -> list[str]:
        return list(postgres_schema_statements())

    def bootstrap_store_schema(self, conn: Any) -> bool:
        for statement in self.schema_statements():
            conn.execute(statement)
        return True

    def translated_sql(self, sql: str) -> str:
        text = sql.strip()
        if text.upper() == "BEGIN IMMEDIATE":
            return "BEGIN"
        return translate_qmark_sql_to_pyformat(sql)


def build_control_plane_backend_adapter(*, db_path: Path):
    requested = _backend_kind_from_env()
    if requested == "sqlite":
        return SqliteControlPlaneBackendAdapter(db_path=db_path, requested_backend=requested)
    if requested == "postgres":
        return PostgresControlPlaneBackendAdapter(db_path=db_path, requested_backend=requested)
    raise ValueError(f"unsupported control plane store backend: {requested}")
