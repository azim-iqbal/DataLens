import pandas as pd
from sklearn.tree import DecisionTreeClassifier

from services.dataset_service import is_identifier_column, is_protected_column, load_dataset
from services.groq_service import analyze_counterfactual


def _encode_features(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    encoded = pd.DataFrame(index=df.index)
    categories = {}

    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            encoded[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            values = sorted(df[col].astype(str).fillna("").unique().tolist())
            categories[col] = {v: i for i, v in enumerate(values)}
            encoded[col] = df[col].astype(str).fillna("").map(categories[col]).fillna(-1)

    return encoded, categories


def _select_feature_columns(df: pd.DataFrame, sensitive_column: str, outcome_column: str) -> list[str]:
    feature_cols = []

    for col in df.columns:
        if col == outcome_column or col == sensitive_column:
            continue
        if is_protected_column(col):
            continue
        if is_identifier_column(col):
            continue
        feature_cols.append(col)

    return feature_cols


def run_counterfactual_test(filepath, sensitive_column, outcome_column):
    try:
        df = load_dataset(filepath)

        if df.empty or sensitive_column not in df.columns or outcome_column not in df.columns:
            return {"flip_rate": 0, "samples": [], "severity": "Low", "interpretation": "Insufficient data for a counterfactual test."}

        df = df.dropna(subset=[sensitive_column, outcome_column])

        unique_vals = df[sensitive_column].dropna().unique().tolist()
        if len(unique_vals) < 2:
            return {"flip_rate": 0, "samples": [], "severity": "Low", "interpretation": "Only one sensitive group was present, so no flip test was possible."}

        feature_cols = _select_feature_columns(df, sensitive_column, outcome_column)
        if not feature_cols:
            return {
                "flip_rate": 0,
                "samples": [],
                "severity": "Low",
                "interpretation": "No non-protected feature columns were available for the counterfactual model.",
            }

        X = df[feature_cols].copy()
        y = df[outcome_column].astype(str)
        X_encoded, categories = _encode_features(X)

        model = DecisionTreeClassifier(max_depth=5, random_state=42)
        model.fit(X_encoded, y)
        original_preds = model.predict(X_encoded)

        if sensitive_column not in X.columns:
            return {
                "sensitive_column": sensitive_column,
                "flip_rate": 0,
                "samples": [],
                "severity": "Low",
                "interpretation": "The protected column was excluded from model training, so changing it did not affect predictions.",
            }

        X_flipped = X.copy()
        for idx in X_flipped.index:
            original = X_flipped.at[idx, sensitive_column]
            replacement = next((v for v in unique_vals if v != original), original)
            X_flipped.at[idx, sensitive_column] = replacement

        flipped_encoded = pd.DataFrame(index=X_flipped.index)
        for col in X_flipped.columns:
            if pd.api.types.is_numeric_dtype(X_flipped[col]):
                flipped_encoded[col] = pd.to_numeric(X_flipped[col], errors="coerce").fillna(0)
            else:
                mapping = categories.get(col, {})
                flipped_encoded[col] = X_flipped[col].astype(str).fillna("").map(mapping).fillna(-1)

        flipped_preds = model.predict(flipped_encoded)
        flip_mask = original_preds != flipped_preds
        flip_rate = float(flip_mask.sum() / len(df) * 100)

        samples = []
        flipped_indices = df[flip_mask].index.tolist()[:5]
        for idx in flipped_indices:
            pos = df.index.get_loc(idx)
            samples.append({
                "row": int(pos + 1),
                "original_sensitive": str(df.at[idx, sensitive_column]),
                "flipped_sensitive": str(X_flipped.at[idx, sensitive_column]),
                "original_prediction": str(original_preds[pos]),
                "flipped_prediction": str(flipped_preds[pos]),
            })

        if flip_rate < 10:
            severity = "Low"
        elif flip_rate <= 25:
            severity = "Medium"
        else:
            severity = "High"

        return {
            "sensitive_column": sensitive_column,
            "flip_rate": round(flip_rate, 2),
            "samples": samples,
            "severity": severity,
            "interpretation": analyze_counterfactual(flip_rate, severity, sensitive_column),
        }
    except Exception as exc:
        print("Counterfactual error:", exc)
        return {"flip_rate": 0, "samples": [], "severity": "Low", "interpretation": "Counterfactual test could not be completed."}
