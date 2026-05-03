from services.groq_service import interpret_eu_clauses


def map_eu_clauses(metrics, flip_rate, primary_findings):
    triggered_clauses = []

    for col, result in metrics.get("disparate_impact_ratio", {}).items():
        if result.get("ratio", 1) < 0.8 and result.get("significant", False):
            triggered_clauses.append({
                "clause": "Article 10(2)(f)",
                "title": "Data Governance",
                "trigger_reason": f"{col} has a disparate impact ratio of {result.get('ratio')}, below the 0.80 review threshold.",
                "severity": "High Risk",
            })
            break

    if flip_rate > 25:
        triggered_clauses.append({
            "clause": "Article 9",
            "title": "Risk Management System",
            "trigger_reason": f"Counterfactual flip rate is {flip_rate:.1f}%, indicating high sensitivity to a protected or proxy attribute.",
            "severity": "High Risk",
        })
    elif flip_rate > 10:
        triggered_clauses.append({
            "clause": "Article 13",
            "title": "Transparency",
            "trigger_reason": f"Counterfactual flip rate is {flip_rate:.1f}%, so the system should explain decision sensitivity clearly.",
            "severity": "Limited Risk",
        })

    if any(
        str(f.get("type", "")).lower() == "proxy" and f.get("correlation_passes", False)
        for f in primary_findings or []
    ):
        triggered_clauses.append({
            "clause": "Article 13",
            "title": "Transparency",
            "trigger_reason": "Proxy variables were detected that may hide protected-group effects.",
            "severity": "Limited Risk",
        })

    influences = metrics.get("feature_influence", {})
    if influences:
        top_feature, top_score = next(iter(influences.items()))
        if top_score > 0.5:
            triggered_clauses.append({
                "clause": "Article 10(2)(g)",
                "title": "Bias Monitoring",
                "trigger_reason": f"{top_feature} strongly influences outcomes with a score of {top_score}.",
                "severity": "Medium Risk",
            })

    deduped = []
    seen = set()
    for clause in triggered_clauses:
        key = (clause["clause"], clause["trigger_reason"])
        if key not in seen:
            deduped.append(clause)
            seen.add(key)

    explanations = interpret_eu_clauses(
        deduped,
        "DataLens audited an uploaded decision dataset for fairness and high-risk AI data governance issues.",
    )

    for clause in deduped:
        clause["explanation"] = explanations.get(
            clause["clause"],
            "This finding may indicate compliance risk and should be reviewed by a human owner.",
        )

    return deduped
