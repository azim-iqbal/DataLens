import json
import os
import re


def _clean_json(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _parse_query_list(text: str) -> list[dict]:
    try:
        parsed = json.loads(_clean_json(text))
    except Exception:
        match = re.search(r"\[[\s\S]*\]", text or "")
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return []

    if isinstance(parsed, dict):
        parsed = parsed.get("questions", [])
    if not isinstance(parsed, list):
        return []

    results = []
    for item in parsed[:5]:
        if not isinstance(item, dict):
            continue
        results.append({
            "question": str(item.get("question", "")),
            "pandas_query": str(item.get("pandas_query", "")),
            "sql_query": str(item.get("sql_query", "")),
        })
    return results


def suggest_queries(profiles: list[dict]) -> list[dict]:
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return []

    columns = [
        {
            "display_name": profile.get("display_name") or profile.get("column_name"),
            "description": profile.get("description"),
        }
        for profile in profiles
    ]
    prompt = f"""
You are a data documentation expert. Based only on these column display names and descriptions, suggest 5 analytical questions a business analyst could answer using this data.

Columns:
{json.dumps(columns, indent=2, default=str)}

Return ONLY valid JSON:
[
  {{
    "question": "Plain-English question",
    "pandas_query": "One-line pandas query using df",
    "sql_query": "Standard SQL query using table_name"
  }}
]
"""

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
                parsed = _parse_query_list(getattr(response, "text", ""))
                if parsed:
                    return parsed
            except Exception:
                continue
    except Exception:
        return []
    return []
