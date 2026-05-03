import asyncio
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Cookie, File, HTTPException, Response, UploadFile

from services.ai_scan_service import scan_all_columns
from services.anomaly_service import add_anomaly_notes
from services.data_service import profile_dataset
from services.dataset_service import UPLOAD_DIR, ensure_data_dirs
from services.dictionary_cache import get_result, store_result
from services.fairness_flag_service import flag_sensitive_columns
from services.query_service import suggest_queries
from services.readiness_service import ml_readiness_score
from services.relationship_service import detect_redundant_columns, detect_relationships
from services.security_service import decrypt_to_memory, save_encrypted
from routes.export import export_result


router = APIRouter(prefix="/dictionary", tags=["Dictionary"])

HISTORY_COOKIE_NAME = "datalens_history_session"
HISTORY_COOKIE_SECONDS = 3600


def _load_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    buffer = BytesIO(file_bytes)
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(buffer)
    if name.endswith(".csv"):
        return pd.read_csv(buffer)
    raise ValueError("Only CSV or Excel files are allowed")


def _history_db_path() -> str:
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./data/datalens.db")
    if database_url.startswith("sqlite:///"):
        return database_url.replace("sqlite:///", "", 1)
    return os.path.join("data", "datalens.db")


def _ensure_history_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary_history (
            session_id TEXT PRIMARY KEY,
            owner_session_id TEXT,
            filename TEXT,
            timestamp TEXT,
            row_count INTEGER,
            column_count INTEGER,
            readiness_score INTEGER,
            flagged_column_count INTEGER
        )
        """
    )
    columns = connection.execute("PRAGMA table_info(dictionary_history)").fetchall()
    existing_column_names = {row[1] for row in columns}
    if "owner_session_id" not in existing_column_names:
        connection.execute("ALTER TABLE dictionary_history ADD COLUMN owner_session_id TEXT")


def _cookie_is_secure() -> bool:
    return os.environ.get("ENABLE_HTTPS_REDIRECT", "").strip().lower() in {"1", "true", "yes"}


def _history_owner_id(existing_cookie: str | None, response: Response) -> str:
    owner_session_id = (existing_cookie or "").strip() or str(uuid.uuid4())
    response.set_cookie(
        key=HISTORY_COOKIE_NAME,
        value=owner_session_id,
        max_age=HISTORY_COOKIE_SECONDS,
        httponly=True,
        secure=_cookie_is_secure(),
        samesite="lax",
    )
    return owner_session_id


def _save_dictionary_history(result: dict, owner_session_id: str) -> None:
    metadata = result["metadata"]
    readiness = result["readiness"]
    db_path = _history_db_path()
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        _ensure_history_schema(connection)
        cutoff = (datetime.utcnow() - timedelta(seconds=HISTORY_COOKIE_SECONDS)).isoformat()
        connection.execute("DELETE FROM dictionary_history WHERE timestamp < ?", (cutoff,))
        connection.execute(
            """
            INSERT OR REPLACE INTO dictionary_history (
                session_id, owner_session_id, filename, timestamp, row_count, column_count,
                readiness_score, flagged_column_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metadata["session_id"],
                owner_session_id,
                metadata["filename"],
                metadata["timestamp"],
                metadata["row_count"],
                metadata["column_count"],
                readiness["score"],
                metadata["flagged_column_count"],
            ),
        )
        connection.commit()


@router.post("/analyse")
async def analyse_dictionary(
    response: Response,
    file: UploadFile = File(...),
    datalens_history_session: str | None = Cookie(default=None, alias=HISTORY_COOKIE_NAME),
):
    ensure_data_dirs()
    owner_session_id = _history_owner_id(datalens_history_session, response)
    filename = file.filename or ""
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only CSV or Excel files are allowed")

    try:
        encrypted_session_id, encrypted_path = save_encrypted(await file.read(), UPLOAD_DIR)
        file_bytes = decrypt_to_memory(encrypted_path)
        df = _load_dataframe(file_bytes, filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read dataset securely: {exc}")

    if df.empty:
        raise HTTPException(status_code=400, detail="Dataset is empty")

    profiles = profile_dataset(df)
    profiles = await scan_all_columns(df, profiles)
    profiles = add_anomaly_notes(profiles, df)
    relationships = detect_relationships(df)
    redundant_columns = detect_redundant_columns(df)
    query_suggestions, profiles = await asyncio.gather(
        asyncio.to_thread(suggest_queries, profiles),
        asyncio.to_thread(flag_sensitive_columns, profiles, df),
    )
    readiness = ml_readiness_score(df, profiles)

    flagged_column_count = sum(1 for profile in profiles if profile.get("fairness_flag"))
    result = {
        "metadata": {
            "session_id": encrypted_session_id,
            "filename": filename,
            "timestamp": datetime.utcnow().isoformat(),
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "flagged_column_count": int(flagged_column_count),
        },
        "profiles": profiles,
        "relationships": relationships,
        "redundant_columns": redundant_columns,
        "query_suggestions": query_suggestions,
        "readiness": readiness,
        "exports": {
            "pdf": f"/dictionary/export/{encrypted_session_id}/pdf",
            "excel": f"/dictionary/export/{encrypted_session_id}/excel",
            "json": f"/dictionary/export/{encrypted_session_id}/json",
        },
    }

    store_result(encrypted_session_id, result)
    _save_dictionary_history(result, owner_session_id)
    return result


@router.get("/export/{session_id}/{format}")
async def export_dictionary_result(session_id: str, format: str):
    result = get_result(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="Session result not found")
    return export_result(session_id, format, result)


@router.get("/history/list")
async def list_dictionary_history(
    datalens_history_session: str | None = Cookie(default=None, alias=HISTORY_COOKIE_NAME),
):
    if not datalens_history_session:
        return []

    owner_session_id = datalens_history_session.strip()
    if not owner_session_id:
        return []

    db_path = _history_db_path()
    if not os.path.exists(db_path):
        return []

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        _ensure_history_schema(connection)
        cutoff = (datetime.utcnow() - timedelta(seconds=HISTORY_COOKIE_SECONDS)).isoformat()
        connection.execute("DELETE FROM dictionary_history WHERE timestamp < ?", (cutoff,))
        rows = connection.execute(
            """
            SELECT session_id, filename, timestamp, row_count, column_count,
                   readiness_score, flagged_column_count
            FROM dictionary_history
            WHERE owner_session_id = ? AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT 100
            """,
            (owner_session_id, cutoff),
        ).fetchall()
        connection.commit()
    return [dict(row) for row in rows]
