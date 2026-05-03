import pandas as pd
from scipy.stats import chi2_contingency, pointbiserialr

from services.dataset_service import build_outcome_binary, encode_series_for_correlation, is_continuous_numeric, is_identifier_column, load_dataset


MIN_GROUP_FLOOR = 5


def _coerce_favorable(series: pd.Series, favorable_value):
    if pd.api.types.is_numeric_dtype(series):
        try:
            if "." in str(favorable_value):
                return float(favorable_value)
            return int(favorable_value)
        except Exception:
            return favorable_value
    return str(favorable_value)


def _positive_mask(series: pd.Series, favorable_value) -> pd.Series:
    return build_outcome_binary(series, favorable_value).astype(bool)


def _encode_for_correlation(df: pd.DataFrame, outcome_column: str, favorable_value) -> pd.DataFrame:
    encoded = pd.DataFrame(index=df.index)
    encoded["__outcome__"] = _positive_mask(df[outcome_column], favorable_value).astype(int)

    for col in df.columns:
        if col == outcome_column:
            continue
        if is_identifier_column(col):
            continue
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            encoded[col] = pd.to_numeric(series, errors="coerce")
        else:
            codes, _ = pd.factorize(series.astype(str), sort=True)
            encoded[col] = codes

    return encoded

def _min_group_size(total_rows: int) -> int:
    return max(MIN_GROUP_FLOOR, int(total_rows * 0.02))


def calculate_fairness_metrics(filepath, sensitive_columns, outcome_column, favorable_value):
    df = load_dataset(filepath)

    if df.empty or outcome_column not in df.columns:
        return {
            "demographic_parity": {},
            "disparate_impact_ratio": {},
            "continuous_associations": {},
            "feature_influence": {},
            "significance_tests": {},
            "plain_language": [],
            "overall_status": "Passes 80% Rule",
        }

    sensitive_columns = [
        c for c in sensitive_columns
        if c in df.columns and c != outcome_column and not is_identifier_column(c)
    ]
    df = df.dropna(subset=sensitive_columns + [outcome_column])

    if df.empty or not sensitive_columns:
        return {
            "demographic_parity": {},
            "disparate_impact_ratio": {},
            "continuous_associations": {},
            "feature_influence": {},
            "significance_tests": {},
            "plain_language": ["No statistically relevant protected columns were flagged for audit."],
            "overall_status": "Passes 80% Rule",
        }

    positive = _positive_mask(df[outcome_column], favorable_value)
    demographic_parity = {}
    disparate_impact_ratio = {}
    continuous_associations = {}
    plain_language = []
    significance_tests = {}
    failing_columns = []

    for col in sensitive_columns:
        group_rows = []
        rates = {}
        valid_rates = {}
        skipped_groups = []

        if is_continuous_numeric(df[col]):
            pair = pd.DataFrame({
                "x": encode_series_for_correlation(df[col]),
                "y": positive.astype(int),
            }).dropna()
            if len(pair) >= 3 and pair["x"].nunique() >= 2 and pair["y"].nunique() >= 2:
                r, p = pointbiserialr(pair["x"], pair["y"])
                continuous_associations[col] = {
                    "r": round(float(r), 4),
                    "p_value": round(float(p), 4),
                    "significant": bool(abs(float(r)) >= 0.10 and float(p) <= 0.05),
                    "sample_size": int(len(pair)),
                }
                significance_tests[col] = {
                    "test": "point-biserial",
                    "p_value": round(float(p), 4),
                    "significant": bool(float(p) <= 0.05),
                    "sample_size": int(len(pair)),
                }
            plain_language.append(
                f"{col} is continuous, so DataLens used point-biserial correlation instead of disparate impact ratio."
            )
            continue

        min_group_size = _min_group_size(len(df))

        for group_value, group_df in df.groupby(col, dropna=False):
            mask = group_df.index
            favorable_count = int(positive.loc[mask].sum())
            total = int(len(group_df))
            rate = favorable_count / total if total else 0
            rates[str(group_value)] = rate
            if total >= min_group_size:
                valid_rates[str(group_value)] = rate
            else:
                skipped_groups.append(str(group_value))
            group_rows.append({
                "group": str(group_value),
                "total": total,
                "favorable": favorable_count,
                "rate": round(rate, 4),
                "percent": round(rate * 100, 1),
            })

        demographic_parity[col] = group_rows
        contingency = pd.crosstab(df[col], positive.astype(int))
        if contingency.shape[0] >= 2 and contingency.shape[1] >= 2:
            chi2, p_value, _, _ = chi2_contingency(contingency)
            significance_tests[col] = {
                "test": "chi-square",
                "p_value": round(float(p_value), 4),
                "significant": bool(float(p_value) <= 0.05),
                "sample_size": int(len(df)),
            }

        if len(valid_rates) >= 2:
            max_group = max(valid_rates, key=valid_rates.get)
            min_group = min(valid_rates, key=valid_rates.get)
            max_rate = valid_rates[max_group]
            min_rate = valid_rates[min_group]
            ratio = min_rate / max_rate if max_rate else 0
            gap = max_rate - min_rate

            disparate_impact_ratio[col] = {
                "ratio": round(ratio, 4),
                "percent": round(ratio * 100, 1),
                "passes_80_rule": ratio >= 0.8,
                "significant": bool(significance_tests.get(col, {}).get("significant", False)),
                "lowest_group": str(min_group),
                "highest_group": str(max_group),
                "lowest_rate": round(min_rate, 4),
                "highest_rate": round(max_rate, 4),
                "gap": round(gap, 4),
                "gap_points": round(gap * 100, 1),
                "min_group_size": min_group_size,
                "skipped_groups": skipped_groups,
            }

            if ratio < 0.8 and significance_tests.get(col, {}).get("significant", False):
                failing_columns.append(col)

            plain_language.append(
                f"For {col}, {min_group} had a {min_rate * 100:.1f}% favorable outcome rate versus {max_group} at {max_rate * 100:.1f}%, a {gap * 100:.1f} point gap."
            )
        elif skipped_groups:
            plain_language.append(
                f"DataLens skipped disparate impact ratio for underpowered groups in {col}. Groups with fewer than {min_group_size} rows were excluded from the 80% rule calculation."
            )

    feature_influence = {}
    encoded = _encode_for_correlation(df, outcome_column, favorable_value)
    if len(encoded.columns) > 1:
        corr = encoded.corr(numeric_only=True)["__outcome__"].drop("__outcome__", errors="ignore")
        corr = corr.dropna().abs().sort_values(ascending=False)
        feature_influence = {
            str(k): round(float(v), 4)
            for k, v in corr.head(10).to_dict().items()
        }

    overall_status = "Fails 80% Rule" if failing_columns else "Passes 80% Rule"

    return {
        "demographic_parity": demographic_parity,
        "disparate_impact_ratio": disparate_impact_ratio,
        "continuous_associations": continuous_associations,
        "feature_influence": feature_influence,
        "significance_tests": significance_tests,
        "plain_language": plain_language,
        "overall_status": overall_status,
    }
