from itertools import combinations
from typing import Any

import pandas as pd
from scipy.stats import pearsonr


def _relationship_note(col_a: str, col_b: str, correlation: float) -> str:
    direction = "increase together" if correlation > 0 else "move in opposite directions"
    return f"{col_a} and {col_b} tend to {direction}, which may indicate a meaningful business relationship."


def detect_relationships(df: pd.DataFrame) -> list[dict]:
    relationships = []
    numeric_columns = df.select_dtypes(include="number").columns.tolist()

    for col_a, col_b in combinations(numeric_columns, 2):
        pair = df[[col_a, col_b]].dropna()
        if len(pair) < 3 or pair[col_a].nunique() < 2 or pair[col_b].nunique() < 2:
            continue

        try:
            r, p = pearsonr(pair[col_a], pair[col_b])
        except Exception:
            continue

        if pd.isna(r) or pd.isna(p):
            continue

        if abs(float(r)) > 0.7 and float(p) < 0.05:
            rounded = round(float(r), 3)
            relationships.append({
                "col_a": str(col_a),
                "col_b": str(col_b),
                "correlation": rounded,
                "type": "Strong positive" if rounded > 0 else "Strong negative",
                "note": _relationship_note(str(col_a), str(col_b), rounded),
            })

    relationships.extend(_detect_age_birthdate_relationships(df))

    return relationships


def _looks_like_age(column: str) -> bool:
    key = str(column).strip().lower().replace(" ", "_")
    return key == "age" or key.endswith("_age")


def _looks_like_birthdate(column: str) -> bool:
    key = str(column).strip().lower().replace(" ", "_")
    return any(hint in key for hint in ["dob", "date_of_birth", "birth_date", "birthdate"])


def _detect_age_birthdate_relationships(df: pd.DataFrame) -> list[dict]:
    relationships = []
    age_columns = [column for column in df.columns if _looks_like_age(str(column))]
    birthdate_columns = [column for column in df.columns if _looks_like_birthdate(str(column))]

    for age_col in age_columns:
        age_series = pd.to_numeric(df[age_col], errors="coerce")
        for dob_col in birthdate_columns:
            dob_series = pd.to_datetime(df[dob_col], errors="coerce")
            derived_age = pd.Timestamp.utcnow().year - dob_series.dt.year
            pair = pd.DataFrame({"age": age_series, "derived_age": derived_age}).dropna()
            if len(pair) < 3 or pair["age"].nunique() < 2 or pair["derived_age"].nunique() < 2:
                continue
            try:
                r, p = pearsonr(pair["age"], pair["derived_age"])
            except Exception:
                continue
            if pd.isna(r) or pd.isna(p):
                continue
            if abs(float(r)) > 0.7 and float(p) < 0.05:
                relationships.append({
                    "col_a": str(age_col),
                    "col_b": str(dob_col),
                    "correlation": round(float(r), 3),
                    "type": "Age/date redundancy",
                    "note": f"{dob_col} appears to encode the same age signal as {age_col}; keep one authoritative field to avoid redundant sensitive attributes.",
                })
    return relationships


def _normalize(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def detect_redundant_columns(df: pd.DataFrame) -> list[dict]:
    redundant = []

    for col_a, col_b in combinations(df.columns.tolist(), 2):
        pair = df[[col_a, col_b]].dropna()
        if pair.empty:
            continue
        matches = (
            pair[col_a].map(_normalize).reset_index(drop=True)
            == pair[col_b].map(_normalize).reset_index(drop=True)
        ).mean()
        if float(matches) > 0.95:
            redundant.append({
                "col_a": str(col_a),
                "col_b": str(col_b),
                "match_pct": round(float(matches) * 100, 1),
                "note": f"{col_a} and {col_b} appear to contain nearly identical values.",
            })

    return redundant
