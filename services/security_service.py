"""
security_service.py  —  DataLens
---------------------------------
CHANGES FROM ORIGINAL:
  - Added _anonymize_value() helper that masks PII before sending to AI APIs
  - Added _detect_pii_column() to identify sensitive column types by name
  - Updated build_safe_payload() to anonymize sample_values before returning
  - Everything else (Fernet encryption, file handling, scheduling) is UNCHANGED
"""

import hashlib
import logging
import os
import re
import threading
import time
import uuid
from typing import Any

import pandas as pd
from cryptography.fernet import Fernet

logger = logging.getLogger("datalens.security")

PLACEHOLDER_MARKERS = (
    "generate_with",
    "your_",
    "changeme",
    "replace_me",
    "paste_",
)


# ─── Fernet key management (UNCHANGED) ───────────────────────────────────────

def _looks_like_placeholder(key: str) -> bool:
    lower = key.lower().strip()
    if not lower:
        return True
    return any(marker in lower for marker in PLACEHOLDER_MARKERS)


def _is_valid_fernet_key(key: str) -> bool:
    if _looks_like_placeholder(key):
        return False
    try:
        Fernet(key.encode("utf-8"))
        return True
    except Exception:
        return False


def ensure_file_encryption_key() -> str:
   
    from services.groq_keys import ensure_env_loaded

    ensure_env_loaded()
    key = (os.environ.get("FILE_ENCRYPTION_KEY") or "").strip()
    if _is_valid_fernet_key(key):
        return key

    key = Fernet.generate_key().decode()
    os.environ["FILE_ENCRYPTION_KEY"] = key

    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        env_path = os.path.join(base_dir, ".env")

        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                text = f.read()
            if "FILE_ENCRYPTION_KEY=" in text:
                lines = text.splitlines()
                replaced = False
                for i, line in enumerate(lines):
                    if line.strip().startswith("FILE_ENCRYPTION_KEY="):
                        lines[i] = f"FILE_ENCRYPTION_KEY={key}"
                        replaced = True
                        break
                if not replaced:
                    lines.append(f"FILE_ENCRYPTION_KEY={key}")
                text = "\n".join(lines) + "\n"
            else:
                if not text.endswith("\n") and text:
                    text += "\n"
                text += f"FILE_ENCRYPTION_KEY={key}\n"
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(text)
            logger.warning(
                "FILE_ENCRYPTION_KEY was missing or invalid. Generated and saved to .env."
            )
        else:
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(f"FILE_ENCRYPTION_KEY={key}\n")
            logger.warning(
                "FILE_ENCRYPTION_KEY generated and written to new .env file."
            )
    except Exception as exc:
        logger.warning(
            "FILE_ENCRYPTION_KEY was missing or invalid. Using a temporary "
            "in-memory key for this server session. Failed to persist to "
            ".env: %s",
            exc,
        )

    return key


def _fernet() -> Fernet:
    return Fernet(ensure_file_encryption_key().encode("utf-8"))


# ─── File encryption / decryption / deletion (UNCHANGED) ─────────────────────

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


# ─── NEW: PII detection & anonymization ──────────────────────────────────────

# Regex patterns to detect PII in actual values
_EMAIL_RE    = re.compile(r"^[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}$")
_PHONE_RE    = re.compile(r"^[\+\d][\d\s\-\(\)]{8,}$")
_AADHAAR_RE  = re.compile(r"^\d{4}\s?\d{4}\s?\d{4}$")
_PAN_RE      = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
_URL_RE      = re.compile(r"^https?://")
_IP_RE       = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

# Column name keywords that signal PII — used as a hint so even numeric
# columns with names like "aadhaar_number" are treated carefully
_PII_COLUMN_KEYWORDS = {
    "name", "email", "phone", "mobile", "contact", "address", "street",
    "city", "pincode", "zip", "postal", "aadhaar", "aadhar", "pan",
    "passport", "dob", "birth", "gender", "salary", "income", "ssn",
    "national_id", "voter", "driving", "license", "ip_address", "location",
    "lat", "lon", "latitude", "longitude", "userid", "user_id", "account",
    "card", "ifsc", "upi", "bank",
}


def _detect_pii_column(col_name: str) -> bool:
    """
    Returns True if the column name suggests it likely contains PII.
    Used as an extra layer — anonymize even if the regex doesn't match.
    """
    normalized = re.sub(r"[^a-z0-9]", "_", col_name.lower())
    parts = set(re.split(r"_+", normalized))
    return bool(parts & _PII_COLUMN_KEYWORDS)


def _anonymize_value(value: Any, col_name: str) -> Any:
    
    # Step 1 — nulls are safe
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    str_val = str(value).strip()

    # Step 2 — email
    if _EMAIL_RE.match(str_val):
        return "user@example.com"

    # Step 3 — phone / mobile
    if _PHONE_RE.match(str_val) and len(re.sub(r"\D", "", str_val)) >= 10:
        return "+91-XXXXXXXXXX"

    # Step 4 — Aadhaar
    if _AADHAAR_RE.match(str_val):
        return "XXXX-XXXX-XXXX"

    # Step 5 — PAN
    if _PAN_RE.match(str_val):
        return "ABCDE1234F"

    # Step 6 — URL
    if _URL_RE.match(str_val):
        return "https://example.com"

    # Step 7 — IP address
    if _IP_RE.match(str_val):
        return "0.0.0.0"

    # Steps 8-10 — column name signals PII
    if _detect_pii_column(col_name):
        if isinstance(value, (int, float)):
            # numeric PII (e.g. aadhaar as integer) — zero out
            return 0

        if isinstance(value, str):
            words = str_val.split()
            if len(words) >= 2:
                # Looks like a full name → hash so AI sees "it's a text field"
                token = hashlib.md5(str_val.encode()).hexdigest()[:8].upper()
                return f"PERSON_{token}"
            else:
                return "[REDACTED]"

    # Step 11 — safe value, return as-is
    return value


# ─── UPDATED: build_safe_payload ─────────────────────────────────────────────

def build_safe_payload(df: pd.DataFrame, col: str, masked_columns: list[str] = []) -> dict:
   
    series = df[col]
    non_null = series.dropna()
    sample_size = min(5, len(non_null))
    masked_set = {str(column) for column in masked_columns or []}

    if str(col) in masked_set:
        return {
            "column_name": str(col),
            "dtype": str(series.dtype),
            "sample_values": [],
            "null_pct": round(float(series.isna().mean() * 100), 1),
            "unique_count": int(non_null.nunique()),
            "pii_column": True,
            "masked": True,
        }

    raw_samples = (
        non_null.sample(n=sample_size, random_state=42).tolist()
        if sample_size
        else []
    )

    # ── Anonymize before sending to any AI model ──
    safe_samples = [
        _anonymize_value(_json_safe(v), col)
        for v in raw_samples
    ]

    is_pii = _detect_pii_column(col) or any(
        v != _json_safe(raw_samples[i])
        for i, v in enumerate(safe_samples)
    )

    return {
        "column_name": str(col),
        "dtype": str(series.dtype),
        "sample_values": safe_samples,          # ← anonymized
        "null_pct": round(float(series.isna().mean() * 100), 1),
        "unique_count": int(non_null.nunique()),
        "pii_column": is_pii,                   # ← new hint for AI prompt
    }