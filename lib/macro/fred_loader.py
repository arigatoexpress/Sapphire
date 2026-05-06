"""Cache-first FRED/ALFRED observations loader.

The loader is designed for market-regime features and backtests:

* parsing is pure and fixture-friendly;
* live HTTP requires both ``SAPPHIRE_FRED_LIVE=1`` and a FRED API key;
* ALFRED-style vintages are represented with realtime start/end dates;
* cache files live outside the repo by default.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

FRED_SERIES_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_SERIES_LIMIT = 400
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "sapphire" / "macro" / "fred"
DEFAULT_USER_AGENT = (
    "SapphireFredLoader/0.1 "
    "(+https://github.com/arigatoexpress/Sapphire; contact=ops@sapphirealpha.xyz)"
)

DEFAULT_MARKET_REGIME_SERIES: tuple[str, ...] = (
    "DFF",
    "DGS2",
    "DGS10",
    "T10Y2Y",
    "CPIAUCSL",
    "UNRATE",
    "M2SL",
    "DTWEXBGS",
    "VIXCLS",
    "BAMLH0A0HYM2",
)

FredFetcher = Callable[[str, Mapping[str, str], float], Mapping[str, Any]]


class FredLoaderError(RuntimeError):
    """FRED loader failed in a recoverable way."""


@dataclass(frozen=True)
class FredObservation:
    """One FRED or ALFRED observation."""

    series_id: str
    observation_date: date
    value: float | None
    realtime_start: date
    realtime_end: date

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "observation_date": self.observation_date.isoformat(),
            "value": self.value,
            "realtime_start": self.realtime_start.isoformat(),
            "realtime_end": self.realtime_end.isoformat(),
        }


@dataclass(frozen=True)
class FredSeriesSnapshot:
    """Parsed observations plus the request/provenance metadata needed downstream."""

    series_id: str
    observations: tuple[FredObservation, ...]
    realtime_start: date | None = None
    realtime_end: date | None = None
    observation_start: date | None = None
    observation_end: date | None = None
    units: str = ""
    frequency: str = ""
    title: str = ""
    source_url: str = FRED_SERIES_OBSERVATIONS_URL
    fetched_at: datetime | None = None
    cached: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def latest(self) -> FredObservation | None:
        return latest_observation(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "observations": [row.to_dict() for row in self.observations],
            "realtime_start": self.realtime_start.isoformat() if self.realtime_start else None,
            "realtime_end": self.realtime_end.isoformat() if self.realtime_end else None,
            "observation_start": self.observation_start.isoformat()
            if self.observation_start
            else None,
            "observation_end": self.observation_end.isoformat() if self.observation_end else None,
            "units": self.units,
            "frequency": self.frequency,
            "title": self.title,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at.astimezone(UTC).isoformat() if self.fetched_at else None,
            "cached": self.cached,
            "metadata": dict(self.metadata),
        }


def fred_user_agent() -> str:
    """Return a polite user agent for FRED requests."""

    return os.environ.get("SAPPHIRE_FRED_USER_AGENT", DEFAULT_USER_AGENT).strip() or (
        DEFAULT_USER_AGENT
    )


def fred_cache_dir() -> Path:
    """Return the cache directory for FRED payloads."""

    raw = os.environ.get("SAPPHIRE_FRED_CACHE_DIR")
    if raw:
        return Path(raw).expanduser()
    macro_root = os.environ.get("SAPPHIRE_MACRO_CACHE_DIR")
    if macro_root:
        return Path(macro_root).expanduser() / "fred"
    return DEFAULT_CACHE_DIR


def fred_api_key() -> str | None:
    """Read the FRED key from env or the local secrets file."""

    raw = os.environ.get("FRED_API_KEY")
    if raw and raw.strip():
        return raw.strip()
    path = Path("~/.config/sapphire-secrets/fred_api_key").expanduser()
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def live_reads_enabled() -> bool:
    return os.environ.get("SAPPHIRE_FRED_LIVE") == "1"


def build_fred_observations_url(
    series_id: str,
    *,
    api_key: str,
    limit: int = DEFAULT_SERIES_LIMIT,
    sort_order: str = "asc",
    observation_start: str | date | None = None,
    observation_end: str | date | None = None,
    realtime_start: str | date | None = None,
    realtime_end: str | date | None = None,
    units: str | None = None,
) -> str:
    """Build a FRED observations URL with ALFRED-compatible realtime params."""

    params: dict[str, str] = {
        "series_id": _clean_series_id(series_id),
        "api_key": api_key,
        "file_type": "json",
        "limit": str(int(limit)),
        "sort_order": sort_order,
    }
    optional = {
        "observation_start": observation_start,
        "observation_end": observation_end,
        "realtime_start": realtime_start,
        "realtime_end": realtime_end,
        "units": units,
    }
    for key, value in optional.items():
        if value is not None and str(value).strip():
            params[key] = _date_param(value) if key != "units" else str(value).strip()
    return f"{FRED_SERIES_OBSERVATIONS_URL}?{urllib.parse.urlencode(params)}"


def parse_fred_observations(
    payload: Mapping[str, Any],
    *,
    series_id: str,
    source_url: str = FRED_SERIES_OBSERVATIONS_URL,
    fetched_at: datetime | None = None,
    cached: bool = False,
) -> FredSeriesSnapshot:
    """Parse a FRED observations payload into a typed snapshot."""

    rows = payload.get("observations")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise FredLoaderError("FRED payload missing observations array")

    cleaned_series_id = _clean_series_id(series_id)
    observations: list[FredObservation] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        observations.append(
            FredObservation(
                series_id=cleaned_series_id,
                observation_date=_parse_date(row.get("date"), field_name="date"),
                value=_parse_value(row.get("value")),
                realtime_start=_parse_date(row.get("realtime_start"), field_name="realtime_start"),
                realtime_end=_parse_date(row.get("realtime_end"), field_name="realtime_end"),
            )
        )

    observations.sort(
        key=lambda item: (item.observation_date, item.realtime_start, item.realtime_end)
    )
    metadata_keys = {
        "count",
        "offset",
        "limit",
        "output_type",
        "order_by",
        "sort_order",
        "file_type",
    }
    metadata = {key: payload.get(key) for key in metadata_keys if key in payload}
    return FredSeriesSnapshot(
        series_id=cleaned_series_id,
        observations=tuple(observations),
        realtime_start=_parse_optional_date(payload.get("realtime_start")),
        realtime_end=_parse_optional_date(payload.get("realtime_end")),
        observation_start=_parse_optional_date(payload.get("observation_start")),
        observation_end=_parse_optional_date(payload.get("observation_end")),
        units=str(payload.get("units") or ""),
        frequency=str(payload.get("frequency") or payload.get("frequency_short") or ""),
        title=str(payload.get("title") or ""),
        source_url=source_url,
        fetched_at=fetched_at,
        cached=cached,
        metadata=metadata,
    )


def canonical_observation_id(
    series_id: str,
    observation_date: str | date,
    realtime_start: str | date,
    realtime_end: str | date,
) -> str:
    """Return a stable point-in-time row id for a FRED/ALFRED observation."""

    material = "|".join(
        [
            _clean_series_id(series_id),
            _date_param(observation_date),
            _date_param(realtime_start),
            _date_param(realtime_end),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def latest_observation(snapshot: FredSeriesSnapshot) -> FredObservation | None:
    """Return the most recent non-null observation when available."""

    for row in reversed(snapshot.observations):
        if row.value is not None:
            return row
    return snapshot.observations[-1] if snapshot.observations else None


def fred_observation_rows(
    snapshot: FredSeriesSnapshot,
    *,
    ingested_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Convert a snapshot into append-only JSONL rows for the warehouse path."""

    now = ingested_at or datetime.now(UTC).replace(microsecond=0)
    payload_hash = _snapshot_payload_hash(snapshot)
    rows: list[dict[str, Any]] = []
    for observation in snapshot.observations:
        observation_id = canonical_observation_id(
            observation.series_id,
            observation.observation_date,
            observation.realtime_start,
            observation.realtime_end,
        )
        rows.append(
            {
                "id": observation_id,
                "observation_id": observation_id,
                "series_id": observation.series_id,
                "observation_date": observation.observation_date.isoformat(),
                "value": observation.value,
                "realtime_start": observation.realtime_start.isoformat(),
                "realtime_end": observation.realtime_end.isoformat(),
                "units": snapshot.units,
                "frequency": snapshot.frequency,
                "source_url": snapshot.source_url,
                "payload_hash": payload_hash,
                "ingested_at": now.astimezone(UTC).isoformat(),
            }
        )
    return rows


def macro_feature_row(
    snapshots: Iterable[FredSeriesSnapshot],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a compact latest-value feature row from multiple FRED snapshots."""

    now = generated_at or datetime.now(UTC).replace(microsecond=0)
    series: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        latest = snapshot.latest
        if latest is None:
            series[snapshot.series_id] = {
                "value": None,
                "observation_date": None,
                "realtime_start": snapshot.realtime_start.isoformat()
                if snapshot.realtime_start
                else None,
                "realtime_end": snapshot.realtime_end.isoformat()
                if snapshot.realtime_end
                else None,
                "units": snapshot.units,
            }
            continue
        series[snapshot.series_id] = {
            "value": latest.value,
            "observation_date": latest.observation_date.isoformat(),
            "realtime_start": latest.realtime_start.isoformat(),
            "realtime_end": latest.realtime_end.isoformat(),
            "units": snapshot.units,
        }

    material = json.dumps(series, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": 1,
        "feature_id": hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
        "generated_at": now.astimezone(UTC).isoformat(),
        "source": "fred_alfred",
        "series": series,
    }


def read_fred_observation_jsonl(
    path: str | Path,
    *,
    limit: int = 10_000,
) -> list[dict[str, Any]]:
    """Read bounded FRED observation rows from an append-only JSONL artifact."""

    artifact_path = Path(path).expanduser()
    if not artifact_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in artifact_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, Mapping):
            rows.append(dict(row))
    return rows[-max(1, int(limit)) :]


def macro_feature_row_from_observation_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    generated_at: datetime | None = None,
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build latest-value FRED features from exported observation JSONL rows."""

    now = generated_at or datetime.now(UTC).replace(microsecond=0)
    row_list = [dict(row) for row in rows if isinstance(row, Mapping)]
    latest_by_series: dict[str, dict[str, Any]] = {}
    for row in row_list:
        raw_series_id = str(row.get("series_id") or "").strip()
        if not raw_series_id:
            continue
        series_id = _clean_series_id(raw_series_id)
        observation_date = _parse_optional_date(row.get("observation_date"))
        realtime_start = _parse_optional_date(row.get("realtime_start"))
        realtime_end = _parse_optional_date(row.get("realtime_end"))
        if observation_date is None or realtime_start is None or realtime_end is None:
            continue
        value = row.get("value")
        if value is not None:
            value = _parse_value(value)
        candidate = {
            "value": value,
            "observation_date": observation_date.isoformat(),
            "realtime_start": realtime_start.isoformat(),
            "realtime_end": realtime_end.isoformat(),
            "units": str(row.get("units") or ""),
            "frequency": str(row.get("frequency") or ""),
        }
        current = latest_by_series.get(series_id)
        candidate_key = (value is not None, observation_date, realtime_start, realtime_end)
        current_key = (
            (current or {}).get("value") is not None,
            _parse_optional_date((current or {}).get("observation_date")) or date.min,
            _parse_optional_date((current or {}).get("realtime_start")) or date.min,
            _parse_optional_date((current or {}).get("realtime_end")) or date.min,
        )
        if current is None or candidate_key > current_key:
            latest_by_series[series_id] = candidate

    series = dict(sorted(latest_by_series.items()))
    material = json.dumps(series, sort_keys=True, separators=(",", ":"))
    latest_dates = [
        value["observation_date"]
        for value in series.values()
        if isinstance(value.get("observation_date"), str)
    ]
    feature_row = {
        "schema_version": 1,
        "feature_id": hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
        "generated_at": now.astimezone(UTC).isoformat(),
        "source": "fred_alfred",
        "row_count": len(row_list),
        "series_count": len(series),
        "latest_observation_date": max(latest_dates) if latest_dates else None,
        "series": series,
    }
    if source_path is not None:
        feature_row["source_path"] = str(source_path)
    return feature_row


class FredLoader:
    """Cache-first FRED client with an explicit live-read gate."""

    def __init__(
        self,
        *,
        cache_dir: Path | str | None = None,
        api_key: str | None = None,
        fetcher: FredFetcher | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.cache_dir = Path(cache_dir).expanduser() if cache_dir else fred_cache_dir()
        self.api_key = api_key
        self.fetcher = fetcher or _default_fetcher
        self.timeout_seconds = timeout_seconds

    def pull_series(
        self,
        series_id: str,
        *,
        observation_start: str | date | None = None,
        observation_end: str | date | None = None,
        realtime_start: str | date | None = None,
        realtime_end: str | date | None = None,
        limit: int = DEFAULT_SERIES_LIMIT,
        sort_order: str = "asc",
        units: str | None = None,
        cache_only: bool = False,
    ) -> FredSeriesSnapshot:
        """Load a series from cache, or from live FRED when explicitly enabled."""

        cleaned_series_id = _clean_series_id(series_id)
        cache_path = self.cache_path(
            cleaned_series_id,
            observation_start=observation_start,
            observation_end=observation_end,
            realtime_start=realtime_start,
            realtime_end=realtime_end,
            limit=limit,
            sort_order=sort_order,
            units=units,
        )
        cached_payload = _read_json(cache_path)
        if cached_payload is not None:
            return parse_fred_observations(
                cached_payload,
                series_id=cleaned_series_id,
                source_url=str(cached_payload.get("_source_url") or FRED_SERIES_OBSERVATIONS_URL),
                fetched_at=_parse_optional_datetime(cached_payload.get("_fetched_at")),
                cached=True,
            )

        if cache_only or not live_reads_enabled():
            raise FredLoaderError(
                "FRED cache miss and live reads are disabled; set SAPPHIRE_FRED_LIVE=1 "
                "with FRED_API_KEY for a live pull"
            )

        key = self.api_key or fred_api_key()
        if not key:
            raise FredLoaderError("FRED_API_KEY is required for live FRED reads")

        url = build_fred_observations_url(
            cleaned_series_id,
            api_key=key,
            observation_start=observation_start,
            observation_end=observation_end,
            realtime_start=realtime_start,
            realtime_end=realtime_end,
            limit=limit,
            sort_order=sort_order,
            units=units,
        )
        payload = dict(self.fetcher(url, {"User-Agent": fred_user_agent()}, self.timeout_seconds))
        fetched_at = datetime.now(UTC).replace(microsecond=0)
        payload["_source_url"] = _redact_api_key(url)
        payload["_fetched_at"] = fetched_at.isoformat()
        _write_json(cache_path, payload)
        return parse_fred_observations(
            payload,
            series_id=cleaned_series_id,
            source_url=payload["_source_url"],
            fetched_at=fetched_at,
            cached=False,
        )

    def pull_market_regime_series(
        self,
        *,
        series_ids: Iterable[str] = DEFAULT_MARKET_REGIME_SERIES,
        observation_start: str | date | None = None,
        observation_end: str | date | None = None,
        realtime_start: str | date | None = None,
        realtime_end: str | date | None = None,
        limit: int = DEFAULT_SERIES_LIMIT,
        cache_only: bool = False,
    ) -> tuple[FredSeriesSnapshot, ...]:
        """Load the default macro series used for market-regime feature rows."""

        return tuple(
            self.pull_series(
                series_id,
                observation_start=observation_start,
                observation_end=observation_end,
                realtime_start=realtime_start,
                realtime_end=realtime_end,
                limit=limit,
                cache_only=cache_only,
            )
            for series_id in series_ids
        )

    def cache_path(
        self,
        series_id: str,
        *,
        observation_start: str | date | None = None,
        observation_end: str | date | None = None,
        realtime_start: str | date | None = None,
        realtime_end: str | date | None = None,
        limit: int = DEFAULT_SERIES_LIMIT,
        sort_order: str = "asc",
        units: str | None = None,
    ) -> Path:
        params = {
            "series_id": _clean_series_id(series_id),
            "observation_start": _date_param(observation_start) if observation_start else "",
            "observation_end": _date_param(observation_end) if observation_end else "",
            "realtime_start": _date_param(realtime_start) if realtime_start else "",
            "realtime_end": _date_param(realtime_end) if realtime_end else "",
            "limit": str(limit),
            "sort_order": sort_order,
            "units": units or "",
        }
        material = json.dumps(params, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{params['series_id']}-{digest}.json"


def _default_fetcher(url: str, headers: Mapping[str, str], timeout: float) -> Mapping[str, Any]:
    request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
        return json.loads(response.read().decode("utf-8"))


def _clean_series_id(series_id: str) -> str:
    cleaned = str(series_id or "").strip().upper()
    if not cleaned:
        raise FredLoaderError("series_id is required")
    return cleaned


def _parse_date(value: Any, *, field_name: str) -> date:
    parsed = _parse_optional_date(value)
    if parsed is None:
        raise FredLoaderError(f"FRED observation missing {field_name}")
    return parsed


def _parse_optional_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise FredLoaderError(f"invalid FRED date: {text}") from exc


def _parse_optional_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_value(value: Any) -> float | None:
    text = str(value or "").strip()
    if text in {"", "."}:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise FredLoaderError(f"invalid FRED value: {text}") from exc


def _date_param(value: str | date | None) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise FredLoaderError(f"invalid FRED cache payload: {path}") from exc


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _redact_api_key(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted = [(key, "***" if key == "api_key" else value) for key, value in pairs]
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(redacted)))


def _snapshot_payload_hash(snapshot: FredSeriesSnapshot) -> str:
    payload = {
        "series_id": snapshot.series_id,
        "observations": [row.to_dict() for row in snapshot.observations],
        "realtime_start": snapshot.realtime_start.isoformat() if snapshot.realtime_start else None,
        "realtime_end": snapshot.realtime_end.isoformat() if snapshot.realtime_end else None,
        "observation_start": snapshot.observation_start.isoformat()
        if snapshot.observation_start
        else None,
        "observation_end": snapshot.observation_end.isoformat()
        if snapshot.observation_end
        else None,
        "units": snapshot.units,
        "frequency": snapshot.frequency,
        "source_url": snapshot.source_url,
    }
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
