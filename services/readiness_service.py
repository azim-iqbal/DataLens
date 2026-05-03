import pandas as pd


def _add_deduction(deductions: list[dict], reason: str, points: int) -> None:
    if points > 0:
        deductions.append({"reason": reason, "points": int(points)})


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def ml_readiness_score(df: pd.DataFrame, profiles: list[dict]) -> dict:
    deductions: list[dict] = []

    avg_null_rate = sum(float(profile.get("null_pct") or 0) for profile in profiles) / max(len(profiles), 1)
    if avg_null_rate > 10:
        _add_deduction(deductions, "Average null rate is above 10%.", min(20, round(avg_null_rate / 100 * 20)))

    elevated_null_columns = [
        profile for profile in profiles
        if float(profile.get("null_pct") or 0) >= 5
    ]
    _add_deduction(
        deductions,
        "One or more columns have elevated null rates that may skew analysis.",
        min(10, len(elevated_null_columns) * 2),
    )

    high_cardinality = [
        profile
        for profile in profiles
        if not str(profile.get("dtype", "")).startswith(("int", "float"))
        and int(profile.get("unique_count") or 0) > 100
    ]
    _add_deduction(
        deductions,
        "High-cardinality categorical columns may need encoding or grouping.",
        min(15, len(high_cardinality) * 5),
    )

    flagged_count = sum(1 for profile in profiles if profile.get("fairness_flag"))
    _add_deduction(
        deductions,
        "Sensitive or proxy columns require fairness review before modeling.",
        min(20, flagged_count * 10),
    )

    duplicate_rate = float(df.duplicated().mean() * 100) if len(df) else 0.0
    if duplicate_rate > 5:
        _add_deduction(deductions, "Duplicate rows exceed 5%.", min(10, round(duplicate_rate / 100 * 10)))

    if len(df) < 500:
        _add_deduction(deductions, "Dataset has fewer than 500 rows.", 15)
    elif len(df) < 1000:
        _add_deduction(deductions, "Dataset has fewer than 1000 rows.", 7)

    outlier_columns = 0
    for column in df.select_dtypes(include="number").columns:
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if len(series) < 2:
            continue
        std = series.std()
        if not std:
            continue
        outlier_rate = float(((series - series.mean()).abs() > (3 * std)).mean() * 100)
        if outlier_rate > 5:
            outlier_columns += 1
    _add_deduction(
        deductions,
        "Numeric columns contain more than 5% extreme outliers.",
        min(10, outlier_columns * 5),
    )

    score = max(0, 100 - sum(item["points"] for item in deductions))
    grade = _grade(score)
    if score >= 80:
        summary = "This dataset looks broadly ready for analysis, with limited issues to review before modeling."
    elif score >= 60:
        summary = "This dataset is usable but needs cleaning, documentation, or fairness review before modeling."
    else:
        summary = "This dataset needs substantial preparation before it is reliable for machine learning."

    return {
        "score": int(score),
        "grade": grade,
        "deductions": deductions,
        "summary": summary,
    }
