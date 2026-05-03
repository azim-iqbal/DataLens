import os

import pandas as pd


def _gemini_sentence(prompt: str, fallback: str) -> str:
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return fallback

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        model_names = [
            (os.environ.get("GEMINI_MODEL") or "").replace("models/", "").strip(),
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.0-flash-001",
        ]
        for model_name in [name for name in model_names if name]:
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                text = (getattr(response, "text", "") or "").strip()
                if text:
                    return text.splitlines()[0].strip()
            except Exception:
                continue
    except Exception:
        return fallback
    return fallback


def _outlier_count(df: pd.DataFrame, column: str) -> int:
    if column not in df.columns or not pd.api.types.is_numeric_dtype(df[column]):
        return 0

    series = pd.to_numeric(df[column], errors="coerce").dropna()
    if len(series) < 2:
        return 0
    std = series.std()
    if not std:
        return 0
    return int(((series - series.mean()).abs() > (3 * std)).sum())


def add_anomaly_notes(profiles: list[dict], df: pd.DataFrame) -> list[dict]:
    for profile in profiles:
        flag = profile.get("data_quality_flag")
        if not flag or str(flag).lower() == "none":
            continue

        column = profile.get("column_name", "")
        beyond_3_std = _outlier_count(df, column)
        fallback = (
            f"{column} has a {flag} data quality concern; review the source data and decide "
            "whether cleaning or business-rule validation is needed."
        )
        prompt = f"""
You are a data documentation expert. Write one plain-English sentence explaining what this anomaly likely means in a business context and what action to take.

Column name: {column}
Description: {profile.get("description")}
Flag type: {flag}
Minimum: {profile.get("min")}
Maximum: {profile.get("max")}
Mean: {profile.get("mean")}
Null percentage: {profile.get("null_pct")}
Values beyond 3 standard deviations: {beyond_3_std}
"""
        profile["anomaly_note"] = _gemini_sentence(prompt, fallback)

    return profiles
