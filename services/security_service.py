import os
import threading
import time
import uuid
from typing import Any

import pandas as pd
from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = (os.environ.get("FILE_ENCRYPTION_KEY") or "").strip()
    if not key:
        raise ValueError("FILE_ENCRYPTION_KEY is not configured")
    return Fernet(key.encode("utf-8"))


def save_encrypted(file_bytes: bytes, upload_dir: str) -> tuple[str, str]:
    session_id = str(uuid.uuid4())
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, f"{session_id}.enc")

    encrypted = _fernet().encrypt(file_bytes)
    with open(path, "wb") as encrypted_file:
        encrypted_file.write(encrypted)

    schedule_deletion(path, seconds=3600)
    return session_id, path


def decrypt_to_memory(path: str) -> bytes:
    with open(path, "rb") as encrypted_file:
        encrypted = encrypted_file.read()
    return _fernet().decrypt(encrypted)


def schedule_deletion(path: str, seconds: int = 3600) -> None:
    def delete_later() -> None:
        time.sleep(seconds)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    thread = threading.Thread(target=delete_later, daemon=True)
    thread.start()


def _json_safe(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def build_safe_payload(df: pd.DataFrame, col: str) -> dict:
    series = df[col]
    non_null = series.dropna()
    sample_size = min(5, len(non_null))
    samples = non_null.sample(n=sample_size, random_state=42).tolist() if sample_size else []

    return {
        "column_name": str(col),
        "dtype": str(series.dtype),
        "sample_values": [_json_safe(value) for value in samples],
        "null_pct": round(float(series.isna().mean() * 100), 1),
        "unique_count": int(non_null.nunique()),
    }
