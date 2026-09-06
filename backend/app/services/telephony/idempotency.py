"""Persistent Idempotency Store for Outbound Telephony Operations.

Implements Contract 2:
- Idempotency-Key = outbound_job_id
- Strictly enforces: one outbound_job_id = at most one provider call
- Re-entrant with identical payload: returns existing mapping without re-dialing
- Modified immutable fields: raises IdempotencyConflictError (HTTP 409)
- Persistence: Uses SQLite storage to ensure mapping survives process restart
"""

import asyncio
import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.app.services.telephony.outbound_schemas import (
    OutboundCallRequest,
    OutboundCallStatus,
)

logger = logging.getLogger("telephony.idempotency")


class IdempotencyConflictError(Exception):
    """Raised when an existing outbound_job_id is re-submitted with conflicting fields."""

    def __init__(self, message: str, conflicting_fields: list[str]) -> None:
        super().__init__(message)
        self.conflicting_fields = conflicting_fields


@dataclass
class IdempotencyRecord:
    """Stored record representing an outbound dispatch attempt."""

    outbound_job_id: str
    call_id: str
    gateway_call_id: str
    provider_call_id: str | None
    organization_id: str
    campaign_id: str
    contact_id: str
    agent_id: str
    from_phone_number: str
    to_phone_number: str
    language: str
    status: OutboundCallStatus
    metadata_json: str
    created_at: str
    updated_at: str


class PersistentIdempotencyStore:
    """SQLite-backed persistent idempotency store surviving application restarts."""

    def __init__(self, db_path: str = "data/outbound_idempotency.db") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_file), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbound_idempotency (
                    outbound_job_id TEXT PRIMARY KEY,
                    call_id TEXT NOT NULL,
                    gateway_call_id TEXT NOT NULL,
                    provider_call_id TEXT,
                    organization_id TEXT NOT NULL,
                    campaign_id TEXT NOT NULL,
                    contact_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    from_phone_number TEXT NOT NULL,
                    to_phone_number TEXT NOT NULL,
                    language TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_outbound_call_id ON outbound_idempotency(call_id);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_outbound_gateway_call_id ON outbound_idempotency(gateway_call_id);
                """
            )
            conn.commit()

    async def get_record(self, outbound_job_id: str) -> IdempotencyRecord | None:
        """Retrieve existing record by outbound_job_id."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_get, outbound_job_id)

    def _sync_get(self, outbound_job_id: str) -> IdempotencyRecord | None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM outbound_idempotency WHERE outbound_job_id = ?",
                (outbound_job_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return IdempotencyRecord(
                outbound_job_id=row["outbound_job_id"],
                call_id=row["call_id"],
                gateway_call_id=row["gateway_call_id"],
                provider_call_id=row["provider_call_id"],
                organization_id=row["organization_id"],
                campaign_id=row["campaign_id"],
                contact_id=row["contact_id"],
                agent_id=row["agent_id"],
                from_phone_number=row["from_phone_number"],
                to_phone_number=row["to_phone_number"],
                language=row["language"],
                status=OutboundCallStatus(row["status"]),
                metadata_json=row["metadata_json"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def register_or_get(
        self,
        request: OutboundCallRequest,
        gateway_call_id: str,
    ) -> tuple[IdempotencyRecord, bool]:
        """Atomically register a new outbound job or return existing mapping.

        Returns (record, is_new).
        Raises IdempotencyConflictError if existing record has conflicting immutable fields.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._sync_register_or_get, request, gateway_call_id
        )

    def _sync_register_or_get(
        self,
        request: OutboundCallRequest,
        gateway_call_id: str,
    ) -> tuple[IdempotencyRecord, bool]:
        with self._lock:
            existing = self._sync_get(request.outbound_job_id)
            if existing is not None:
                # Contract 2: Check immutable fields
                conflicts: list[str] = []
                if existing.call_id != request.call_id:
                    conflicts.append("call_id")
                if existing.organization_id != request.organization_id:
                    conflicts.append("organization_id")
                if existing.campaign_id != request.campaign_id:
                    conflicts.append("campaign_id")
                if existing.contact_id != request.contact_id:
                    conflicts.append("contact_id")
                if existing.agent_id != request.agent_id:
                    conflicts.append("agent_id")
                if existing.from_phone_number != request.from_phone_number:
                    conflicts.append("from_phone_number")
                if existing.to_phone_number != request.to_phone_number:
                    conflicts.append("to_phone_number")

                if conflicts:
                    logger.warning(
                        "Idempotency conflict for outbound_job_id=%s. Conflicting fields: %s",
                        request.outbound_job_id,
                        conflicts,
                    )
                    raise IdempotencyConflictError(
                        f"outbound_job_id '{request.outbound_job_id}' was already registered with different immutable fields: {', '.join(conflicts)}",
                        conflicting_fields=conflicts,
                    )

                # Return existing mapping without creating a second customer call
                return existing, False

            # Create new entry
            now_iso = datetime.now(timezone.utc).isoformat()
            meta_str = json.dumps(request.metadata)
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO outbound_idempotency (
                        outbound_job_id, call_id, gateway_call_id, provider_call_id,
                        organization_id, campaign_id, contact_id, agent_id,
                        from_phone_number, to_phone_number, language, status,
                        metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.outbound_job_id,
                        request.call_id,
                        gateway_call_id,
                        None,
                        request.organization_id,
                        request.campaign_id,
                        request.contact_id,
                        request.agent_id,
                        request.from_phone_number,
                        request.to_phone_number,
                        request.language,
                        OutboundCallStatus.DIALING.value,
                        meta_str,
                        now_iso,
                        now_iso,
                    ),
                )
                conn.commit()

            new_record = IdempotencyRecord(
                outbound_job_id=request.outbound_job_id,
                call_id=request.call_id,
                gateway_call_id=gateway_call_id,
                provider_call_id=None,
                organization_id=request.organization_id,
                campaign_id=request.campaign_id,
                contact_id=request.contact_id,
                agent_id=request.agent_id,
                from_phone_number=request.from_phone_number,
                to_phone_number=request.to_phone_number,
                language=request.language,
                status=OutboundCallStatus.DIALING,
                metadata_json=meta_str,
                created_at=now_iso,
                updated_at=now_iso,
            )
            return new_record, True

    async def update_status(
        self,
        outbound_job_id: str,
        status: OutboundCallStatus,
        provider_call_id: str | None = None,
    ) -> None:
        """Update the call status and optional provider_call_id."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._sync_update_status, outbound_job_id, status, provider_call_id
        )

    def _sync_update_status(
        self,
        outbound_job_id: str,
        status: OutboundCallStatus,
        provider_call_id: str | None = None,
    ) -> None:
        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            p_id = str(provider_call_id) if (provider_call_id is not None and isinstance(provider_call_id, str)) else None
            with self._get_connection() as conn:
                if p_id:
                    conn.execute(
                        """
                        UPDATE outbound_idempotency
                        SET status = ?, provider_call_id = ?, updated_at = ?
                        WHERE outbound_job_id = ?
                        """,
                        (status.value, p_id, now_iso, outbound_job_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE outbound_idempotency
                        SET status = ?, updated_at = ?
                        WHERE outbound_job_id = ?
                        """,
                        (status.value, now_iso, outbound_job_id),
                    )
                conn.commit()


_global_idempotency_store: PersistentIdempotencyStore | None = None


def get_idempotency_store(db_path: str = "data/outbound_idempotency.db") -> PersistentIdempotencyStore:
    """Singleton getter for PersistentIdempotencyStore."""
    global _global_idempotency_store
    if _global_idempotency_store is None:
        _global_idempotency_store = PersistentIdempotencyStore(db_path=db_path)
    return _global_idempotency_store
