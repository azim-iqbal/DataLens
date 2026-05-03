import pandas as pd


def apply_reweighing_and_resample(df, sensitive_column, outcome_column, favorable_outcome):
    if sensitive_column not in df.columns or outcome_column not in df.columns or df.empty:
        return df.copy()

    working = df.dropna(subset=[sensitive_column, outcome_column]).copy()
    if working.empty:
        return df.copy()

    favorable_mask = working[outcome_column].astype(str).str.strip().str.lower() == str(favorable_outcome).strip().lower()
    p_fav = favorable_mask.mean()
    p_unfav = 1 - p_fav

    weights = []
    for _, row in working.iterrows():
        s_val = row[sensitive_column]
        outcome_is_fav = str(row[outcome_column]).strip().lower() == str(favorable_outcome).strip().lower()
        p_s = (working[sensitive_column] == s_val).mean()
        p_s_and_o = ((working[sensitive_column] == s_val) & (favorable_mask == outcome_is_fav)).mean()
        expected_prob = p_s * (p_fav if outcome_is_fav else p_unfav)
        weights.append(expected_prob / p_s_and_o if p_s_and_o else 1.0)

    working["_datalens_weight"] = weights
    fixed = working.sample(
        n=len(working),
        replace=True,
        weights="_datalens_weight",
        random_state=42,
    ).drop(columns=["_datalens_weight"])

    return fixed.reset_index(drop=True)


def apply_multi_column_fix(df: pd.DataFrame, sensitive_columns, outcome_column, favorable_outcome) -> pd.DataFrame:
    fixed = df.copy()
    for col in sensitive_columns:
        if col in fixed.columns:
            fixed = apply_reweighing_and_resample(fixed, col, outcome_column, favorable_outcome)
    return fixed
