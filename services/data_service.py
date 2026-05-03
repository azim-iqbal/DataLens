from typing import Any

import pandas as pd


def _json_safe(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _top_values(series: pd.Series) -> list[Any]:
    counts = series.dropna().value_counts().head(5)
    return [_json_safe(value) for value in counts.index.tolist()]


def _sample_values(series: pd.Series) -> list[Any]:
    non_null = series.dropna()
    sample_size = min(5, len(non_null))
    if sample_size == 0:
        return []
    return [_json_safe(value) for value in non_null.sample(n=sample_size, random_state=42).tolist()]


def profile_dataset(df: pd.DataFrame) -> list[dict]:
    profiles = []

    for column in df.columns:
        series = df[column]
        non_null = series.dropna()
        is_numeric = pd.api.types.is_numeric_dtype(series)

        profile = {
            "column_name": str(column),
            "dtype": str(series.dtype),
            "null_count": int(series.isna().sum()),
            "null_pct": round(float(series.isna().mean() * 100), 1),
            "unique_count": int(non_null.nunique()),
            "min": _json_safe(non_null.min()) if is_numeric and not non_null.empty else None,
            "max": _json_safe(non_null.max()) if is_numeric and not non_null.empty else None,
            "mean": _json_safe(non_null.mean()) if is_numeric and not non_null.empty else None,
            "median": _json_safe(non_null.median()) if is_numeric and not non_null.empty else None,
            "std": _json_safe(non_null.std()) if is_numeric and len(non_null) > 1 else None,
            "top_values": _top_values(series),
            "sample_values": _sample_values(series),
            "description": None,
            "display_name": None,
            "confidence": None,
            "anomaly_note": None,
            "fairness_flag": None,
            "query_suggestions": [],
        }
        profiles.append(profile)

    return profiles
