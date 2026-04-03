from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol

from app.config import Settings
from app.models import ChatConfig

try:
    from google.cloud import firestore  # type: ignore
except Exception:  # pragma: no cover
    firestore = None


def _merge_sent_ids(existing: Sequence[str], new_ids: Sequence[str], *, limit: int) -> list[str]:
    combined = list(existing) + list(new_ids)
    seen: set[str] = set()
    # Keep last N unique ids (preserve recency).
    out_rev: list[str] = []
    for item_id in reversed(combined):
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        out_rev.append(item_id)
        if len(out_rev) >= limit:
            break
    return list(reversed(out_rev))


class ChatStore(Protocol):
    def get(self, chat_id: int) -> ChatConfig | None:
        ...

    def save(self, chat: ChatConfig) -> None:
        ...

    def list_subscribed(self) -> list[ChatConfig]:
        ...


def _unique_upper(values: list[str]) -> list[str]:
    seen = set()
    cleaned: list[str] = []
    for value in values:
        normalized = value.strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def default_chat_config(chat_id: int, settings: Settings) -> ChatConfig:
    return ChatConfig(
        chat_id=chat_id,
        subscribed=True,
        heartbeat_enabled=True,
        heartbeat_interval_minutes=max(5, settings.heartbeat_interval_minutes),
        assistant_mode="personal",
        focus_project="",
        proactive_checkins_enabled=True,
        assistant_checkin_interval_minutes=120,
        decision_sla_minutes=180,
        aster_assets=_unique_upper(settings.default_aster_assets),
        lighter_assets=_unique_upper(settings.default_lighter_assets),
        extra_keywords=[k.strip().lower() for k in settings.default_macro_keywords if k.strip()],
        operator_directive="",
        preference_tone="concise",
        preference_risk="balanced",
        preference_coding_style="pragmatic",
        sent_item_ids=[],
    )


class InMemoryChatStore:
    def __init__(self) -> None:
        self._items: dict[int, ChatConfig] = {}

    def get(self, chat_id: int) -> ChatConfig | None:
        return self._items.get(chat_id)

    def save(self, chat: ChatConfig) -> None:
        self._items[chat.chat_id] = chat

    def list_subscribed(self) -> list[ChatConfig]:
        return [item for item in self._items.values() if item.subscribed]

    def set_last_digest_sent_at(self, *, chat_id: int, ts: datetime) -> None:
        chat = self._items.get(chat_id)
        if not chat:
            return
        chat.last_digest_sent_at = ts

    def set_last_heartbeat_sent_at(self, *, chat_id: int, ts: datetime) -> None:
        chat = self._items.get(chat_id)
        if not chat:
            return
        chat.last_heartbeat_sent_at = ts

    def set_last_assistant_checkin_at(self, *, chat_id: int, ts: datetime) -> None:
        chat = self._items.get(chat_id)
        if not chat:
            return
        chat.last_assistant_checkin_at = ts

    def set_last_decision_sla_reminder_at(self, *, chat_id: int, ts: datetime) -> None:
        chat = self._items.get(chat_id)
        if not chat:
            return
        chat.last_decision_sla_reminder_at = ts


class FirestoreChatStore:
    def __init__(self, settings: Settings) -> None:
        if firestore is None:
            raise RuntimeError("google-cloud-firestore is not installed")
        self._collection = settings.firestore_collection
        self._db = firestore.Client(project=settings.gcp_project_id)
        self._default_heartbeat_interval_minutes = max(5, settings.heartbeat_interval_minutes)

    def _doc(self, chat_id: int):
        return self._db.collection(self._collection).document(str(chat_id))

    @staticmethod
    def _coerce_ts(value) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            # Normalize to tz-aware UTC (Firestore can return naive timestamps).
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value
        return None

    def get(self, chat_id: int) -> ChatConfig | None:
        snap = self._doc(chat_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        return ChatConfig(
            chat_id=chat_id,
            subscribed=bool(data.get("subscribed", True)),
            heartbeat_enabled=bool(data.get("heartbeat_enabled", True)),
            heartbeat_interval_minutes=max(
                5,
                int(data.get("heartbeat_interval_minutes", self._default_heartbeat_interval_minutes)),
            ),
            assistant_mode=str(data.get("assistant_mode", "personal")).strip().lower() or "personal",
            focus_project=str(data.get("focus_project", "")).strip(),
            proactive_checkins_enabled=bool(data.get("proactive_checkins_enabled", True)),
            assistant_checkin_interval_minutes=max(
                15,
                int(data.get("assistant_checkin_interval_minutes", 120)),
            ),
            decision_sla_minutes=max(30, int(data.get("decision_sla_minutes", 180))),
            aster_assets=[str(x).upper() for x in data.get("aster_assets", [])],
            lighter_assets=[str(x).upper() for x in data.get("lighter_assets", [])],
            extra_keywords=[str(x).lower() for x in data.get("extra_keywords", [])],
            operator_directive=str(data.get("operator_directive", "")).strip(),
            preference_tone=str(data.get("preference_tone", "concise")).strip().lower() or "concise",
            preference_risk=str(data.get("preference_risk", "balanced")).strip().lower() or "balanced",
            preference_coding_style=str(data.get("preference_coding_style", "pragmatic")).strip().lower()
            or "pragmatic",
            sent_item_ids=[str(x) for x in data.get("sent_item_ids", [])],
            last_digest_sent_at=self._coerce_ts(data.get("last_digest_sent_at")),
            last_heartbeat_sent_at=self._coerce_ts(data.get("last_heartbeat_sent_at")),
            last_assistant_checkin_at=self._coerce_ts(data.get("last_assistant_checkin_at")),
            last_decision_sla_reminder_at=self._coerce_ts(data.get("last_decision_sla_reminder_at")),
        )

    def save(self, chat: ChatConfig) -> None:
        payload = asdict(chat)
        payload["updated_at"] = datetime.now(tz=UTC)
        self._doc(chat.chat_id).set(payload, merge=True)

    def list_subscribed(self) -> list[ChatConfig]:
        output: list[ChatConfig] = []
        query = self._db.collection(self._collection).where("subscribed", "==", True)
        for snap in query.stream():
            data = snap.to_dict() or {}
            chat_id = int(data.get("chat_id", int(snap.id)))
            output.append(
                ChatConfig(
                    chat_id=chat_id,
                    subscribed=True,
                    heartbeat_enabled=bool(data.get("heartbeat_enabled", True)),
                    heartbeat_interval_minutes=max(
                        5,
                        int(data.get("heartbeat_interval_minutes", self._default_heartbeat_interval_minutes)),
                    ),
                    assistant_mode=str(data.get("assistant_mode", "personal")).strip().lower() or "personal",
                    focus_project=str(data.get("focus_project", "")).strip(),
                    proactive_checkins_enabled=bool(data.get("proactive_checkins_enabled", True)),
                    assistant_checkin_interval_minutes=max(
                        15,
                        int(data.get("assistant_checkin_interval_minutes", 120)),
                    ),
                    decision_sla_minutes=max(30, int(data.get("decision_sla_minutes", 180))),
                    aster_assets=[str(x).upper() for x in data.get("aster_assets", [])],
                    lighter_assets=[str(x).upper() for x in data.get("lighter_assets", [])],
                    extra_keywords=[str(x).lower() for x in data.get("extra_keywords", [])],
                    operator_directive=str(data.get("operator_directive", "")).strip(),
                    preference_tone=str(data.get("preference_tone", "concise")).strip().lower() or "concise",
                    preference_risk=str(data.get("preference_risk", "balanced")).strip().lower() or "balanced",
                    preference_coding_style=str(data.get("preference_coding_style", "pragmatic")).strip().lower()
                    or "pragmatic",
                    sent_item_ids=[str(x) for x in data.get("sent_item_ids", [])],
                    last_digest_sent_at=self._coerce_ts(data.get("last_digest_sent_at")),
                    last_heartbeat_sent_at=self._coerce_ts(data.get("last_heartbeat_sent_at")),
                    last_assistant_checkin_at=self._coerce_ts(data.get("last_assistant_checkin_at")),
                    last_decision_sla_reminder_at=self._coerce_ts(data.get("last_decision_sla_reminder_at")),
                )
            )
        return output

    def reserve_sent_item_ids(
        self,
        *,
        chat_id: int,
        candidate_ids: Sequence[str],
        limit: int,
    ) -> tuple[int, list[str]]:
        """
        Transactionally append sent item ids and return (newly_added_count, merged_ids).

        This prevents duplicate digests when Cloud Run scales horizontally or when
        Cloud Scheduler retries: multiple instances racing will cause only the
        first transaction to claim the ids, the rest will see 0 new ids and skip
        sending.
        """
        if firestore is None:
            raise RuntimeError("google-cloud-firestore is not installed")

        doc_ref = self._doc(chat_id)

        @firestore.transactional  # type: ignore[attr-defined]
        def _txn(transaction):
            snap = doc_ref.get(transaction=transaction)
            data = snap.to_dict() or {}
            existing = [str(x) for x in data.get("sent_item_ids", [])]
            existing_set = set(existing)

            # Only count ids that aren't already present.
            newly_added = [cid for cid in candidate_ids if cid and cid not in existing_set]
            if not newly_added:
                return 0, existing

            merged = _merge_sent_ids(existing, candidate_ids, limit=limit)
            transaction.set(
                doc_ref,
                {"sent_item_ids": merged, "updated_at": datetime.now(tz=UTC)},
                merge=True,
            )
            return len(newly_added), merged

        transaction = self._db.transaction()
        return _txn(transaction)

    def set_last_digest_sent_at(self, *, chat_id: int, ts: datetime) -> None:
        """Update digest timestamp without clobbering sent-item reservations."""
        self._doc(chat_id).set(
            {"last_digest_sent_at": ts, "updated_at": datetime.now(tz=UTC)},
            merge=True,
        )

    def set_last_heartbeat_sent_at(self, *, chat_id: int, ts: datetime) -> None:
        """Update heartbeat timestamp."""
        self._doc(chat_id).set(
            {"last_heartbeat_sent_at": ts, "updated_at": datetime.now(tz=UTC)},
            merge=True,
        )

    def set_last_assistant_checkin_at(self, *, chat_id: int, ts: datetime) -> None:
        """Update assistant check-in timestamp."""
        self._doc(chat_id).set(
            {"last_assistant_checkin_at": ts, "updated_at": datetime.now(tz=UTC)},
            merge=True,
        )

    def set_last_decision_sla_reminder_at(self, *, chat_id: int, ts: datetime) -> None:
        """Update decision SLA reminder timestamp."""
        self._doc(chat_id).set(
            {"last_decision_sla_reminder_at": ts, "updated_at": datetime.now(tz=UTC)},
            merge=True,
        )


def build_store(settings: Settings) -> ChatStore:
    if settings.use_in_memory_store:
        return InMemoryChatStore()
    return FirestoreChatStore(settings)
