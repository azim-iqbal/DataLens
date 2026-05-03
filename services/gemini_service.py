import json
import os
import re
from typing import Any

from services.dataset_service import is_merit_based_column

SENSITIVE_HINTS = {
    "gender": "Gender is a protected attribute and can directly affect fairness.",
    "sex": "Sex is a protected attribute and can directly affect fairness.",
    "age": "Age can be protected in employment, credit, and public-service decisions.",
    "dob": "Date of birth reveals age, which can be a protected attribute.",
    "birth": "Birth information can reveal age or national origin.",
    "race": "Race is a protected attribute and must be audited carefully.",
    "ethnicity": "Ethnicity is a protected attribute and must be audited carefully.",
    "religion": "Religion is a protected attribute.",
    "disability": "Disability status is a protected attribute.",
    "marital": "Marital status can create unfair treatment in some decision systems.",
    "pregnancy": "Pregnancy status is sensitive and can cause illegal discrimination.",
    "nationality": "Nationality can reveal protected origin information.",
    "citizenship": "Citizenship can act as a sensitive attribute in some contexts.",
}

PROXY_HINTS = {
    "zip": "Location can proxy for race, income, and socioeconomic background.",
    "postal": "Postal code can proxy for race, income, and socioeconomic background.",
    "postcode": "Postcode can proxy for race, income, and socioeconomic background.",
    "address": "Address can reveal neighborhood, income, or ethnic background.",
    "city": "City can proxy for socioeconomic or ethnic background.",
    "state": "State or region can proxy for protected group membership.",
    "name": "Names can reveal gender, ethnicity, religion, or national origin.",
    "surname": "Surnames can reveal ethnicity, religion, or national origin.",
    "university": "University name can proxy for socioeconomic background and historical access.",
    "college": "College name can proxy for socioeconomic background and historical access.",
    "school": "School name can proxy for socioeconomic background and neighborhood.",
    "income": "Income can proxy for socioeconomic background.",
    "employment_gap": "Employment gaps may proxy for caregiving, disability, or other protected patterns.",
}

def _clean_json(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _heuristic_findings(columns: list[str], profile: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    seen = set()

    for col in columns:
        key = str(col).lower().replace(" ", "_")
        finding_type = None
        reason = ""
        is_merit_based = is_merit_based_column(col)

        for hint, hint_reason in SENSITIVE_HINTS.items():
            if hint in key:
                finding_type = "sensitive"
                reason = hint_reason
                break

        if not finding_type and not is_merit_based:
            for hint, hint_reason in PROXY_HINTS.items():
                if hint in key:
                    finding_type = "proxy"
                    reason = hint_reason
                    break

        if finding_type and col not in seen:
            findings.append({
                "column": col,
                "type": finding_type,
                "reason": reason,
                "source": "Heuristic",
                "confidence": "High" if finding_type == "sensitive" else "Medium",
            })
            seen.add(col)

    return findings


def _extract_json_list(text: str) -> list[dict[str, Any]]:
    text = _clean_json(text)
    try:
        parsed = json.loads(text)
    except Exception:
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return []

    if isinstance(parsed, dict):
        parsed = parsed.get("findings", [])

    if not isinstance(parsed, list):
        return []

    normalized = []
    for item in parsed:
        if not isinstance(item, dict) or not item.get("column"):
            continue
        normalized.append({
            "column": str(item.get("column")),
            "type": str(item.get("type", "proxy")).lower(),
            "reason": str(item.get("reason", "Potential fairness-relevant column.")),
            "source": str(item.get("source", "Gemini")),
            "confidence": str(item.get("confidence", "Medium")),
        })

    return normalized


def _normalize_model_name(model_name: str) -> str:
    model_name = (model_name or "").strip()
    if model_name.startswith("models/"):
        return model_name.split("/", 1)[1]
    return model_name


def _candidate_model_names(client: Any) -> list[str]:
    preferred = [
        _normalize_model_name(os.environ.get("GEMINI_MODEL", "")),
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
    ]
    preferred = [name for name in preferred if name]

    discovered: list[str] = []
    try:
        for model in client.models.list():
            name = _normalize_model_name(getattr(model, "name", ""))
            if not name or "flash" not in name:
                continue
            supported_methods = getattr(model, "supported_actions", None) or getattr(
                model, "supported_generation_methods", []
            )
            supported_text = " ".join(str(method).lower() for method in supported_methods)
            if supported_text and "generate" not in supported_text:
                continue
            discovered.append(name)
    except Exception:
        discovered = []

    model_names: list[str] = []
    for name in preferred + discovered:
        if name not in model_names:
            model_names.append(name)
    return model_names


def get_gemini_findings(columns: list[str], samples: Any) -> list[dict[str, Any]]:
    profile = samples if isinstance(samples, dict) else {"samples": samples}
    fallback = _heuristic_findings(columns, profile)
    api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()

    if not api_key:
        return fallback

    prompt = f"""
You are DataLens, a fairness audit reviewer.

Analyze the dataset column profile below. Identify:
1. Sensitive attributes such as gender, age, race, ethnicity, disability, religion, nationality, or similar.
2. Proxy attributes that may correlate with protected groups, such as name, zip code, address, school, university, salary history, or experience.
3. A short plain-English reason for each flagged column.
4. Only flag a column if it is a direct protected attribute or a plausible proxy with weak business justification.
5. Do not flag legitimate merit-based columns such as education, years of experience, skill score, test score, certifications, or salary unless the column is clearly being used as a hidden proxy.

Column profile:
{json.dumps(profile, indent=2, default=str)}

Return ONLY valid JSON in this exact shape:
[
  {{
    "column": "Column Name",
    "type": "sensitive",
    "reason": "Short explanation",
    "source": "Gemini",
    "confidence": "High"
  }}
]
"""

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        model_names = _candidate_model_names(client)
        text = ""
        last_error = None
        for model_name in model_names:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                text = getattr(response, "text", "")
                if text:
                    break
            except Exception as exc:
                last_error = exc
        if not text and last_error:
            raise last_error

        findings = _extract_json_list(text)
        return findings or fallback
    except Exception as exc:
        print("Gemini scan fallback used:", exc)
        return fallback
