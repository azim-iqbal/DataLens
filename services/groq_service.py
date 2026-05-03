import json
import os
import re
from typing import Any


def _clean_response(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _parse_json(text: str, fallback: Any) -> Any:
    text = _clean_response(text)
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
        if not match:
            return fallback
        try:
            return json.loads(match.group(1))
        except Exception:
            return fallback


def _client():
    api_key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if not api_key:
        return None

    try:
        from groq import Groq
    except Exception as exc:
        print("Groq package unavailable:", exc)
        return None

    return Groq(api_key=api_key)


def _chat_json(prompt: str, fallback: Any) -> Any:
    client = _client()
    if client is None:
        return fallback

    model_names = [
        os.environ.get("GROQ_MODEL", "").strip(),
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "llama3-8b-8192",
    ]
    model_names = [name for name in model_names if name]

    try:
        last_error = None
        for model_name in model_names:
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
                text = response.choices[0].message.content
                return _parse_json(text, fallback)
            except Exception as exc:
                last_error = exc
        if last_error:
            raise last_error
        return fallback
    except Exception as exc:
        print("Groq fallback:", exc)
        return fallback


def validate_findings_with_claude(columns, samples, gemini_findings):
    fallback = []
    seen = set()
    for finding in gemini_findings or []:
        col = finding.get("column")
        if not col or col in seen:
            continue
        enriched = dict(finding)
        enriched.setdefault("source", "Gemini")
        enriched.setdefault("confidence", "Medium")
        fallback.append(enriched)
        seen.add(col)

    prompt = f"""
You are DataLens's secondary fairness validator. Cross-check Gemini's findings.

Columns:
{json.dumps(columns, indent=2, default=str)}

Profile:
{json.dumps(samples, indent=2, default=str)}

Gemini findings:
{json.dumps(gemini_findings, indent=2, default=str)}

Return ONLY JSON:
[
  {{
    "column": "Column Name",
    "type": "sensitive|proxy",
    "reason": "plain-English explanation",
    "source": "Gemini|Groq|Both",
    "confidence": "High|Medium|Low"
  }}
]
"""
    parsed = _chat_json(prompt, fallback)
    return parsed if isinstance(parsed, list) else fallback


def analyze_counterfactual(flip_rate: float, severity: str, sensitive_column: str = "") -> str:
    if severity == "High":
        fallback = "Changing only the sensitive attribute changed many model decisions. This suggests the decision pattern may depend heavily on protected or proxy information."
    elif severity == "Medium":
        fallback = "Some decisions changed after the sensitive attribute was flipped. This should be reviewed because it may reveal indirect bias."
    else:
        fallback = "Few decisions changed when the sensitive attribute was flipped. This suggests low counterfactual sensitivity in this dataset."

    client = _client()
    if client is None:
        return fallback

    model_names = [
        os.environ.get("GROQ_MODEL", "").strip(),
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "llama3-8b-8192",
    ]
    model_names = [name for name in model_names if name]

    try:
        last_error = None
        for model_name in model_names:
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": f"Explain in 2 simple sentences whether a {flip_rate:.2f}% counterfactual flip rate with {severity} severity for the '{sensitive_column}' attribute indicates bias in an AI decision system."}],
                    temperature=0.3,
                )
                return (response.choices[0].message.content or fallback).strip()
            except Exception as exc:
                last_error = exc
        if last_error:
            raise last_error
        return fallback
    except Exception:
        return fallback


def interpret_eu_clauses(triggered_clauses: list, audit_context: str):
    fallback = {
        c.get("clause", "Clause"): f"This clause is relevant because {c.get('trigger_reason', 'the audit detected a fairness risk')}."
        for c in triggered_clauses
    }

    prompt = f"""
Explain these EU AI Act risk mappings in simple non-legal language.

Clauses:
{json.dumps(triggered_clauses, indent=2, default=str)}

Context:
{audit_context}

Return ONLY JSON:
{{"Article 10(2)(f)": "Explanation"}}
"""
    parsed = _chat_json(prompt, fallback)
    return parsed if isinstance(parsed, dict) else fallback


def generate_report_sections(audit_results: dict):
    fallback = {
        "Executive Summary": "DataLens reviewed the uploaded dataset for sensitive and proxy columns, group outcome gaps, counterfactual sensitivity, and EU AI Act risk indicators.",
        "Bias Findings": "Review the demographic parity, disparate impact, and feature influence sections for the main drivers of unequal outcomes.",
        "Legal Risk Assessment": "This report indicates potential compliance risk and is not a legal determination.",
        "Recommended Actions": "Review flagged columns, retrain with the corrected dataset if appropriate, and document human oversight before deployment.",
    }

    prompt = f"""
Generate a plain-English AI fairness audit report for a non-technical manager.
Avoid saying the system definitely violates law. Say "may indicate risk" where appropriate.

Audit data:
{json.dumps(audit_results, indent=2, default=str)}

Return ONLY JSON:
{{
  "Executive Summary": "...",
  "Bias Findings": "...",
  "Legal Risk Assessment": "...",
  "Recommended Actions": "..."
}}
"""
    parsed = _chat_json(prompt, fallback)
    return parsed if isinstance(parsed, dict) and parsed else fallback
