"""Batch prediction using the saved preprocessor and native XGBoost model."""

import math

from .loader import CATEGORICAL, FEATURES


NUMERIC = [
    "experience_years",
    "performance_score",
    "current_workload",
    "previous_project_score",
    "completed_projects",
    "skill_match_ratio",
    "average_skill_proficiency",
    "relevant_skill_years",
    "missing_required_skills_count",
    "role_match",
    "days_until_deadline",
    "required_skills_count",
]


class PredictionInputError(ValueError):
    """Input does not match the exact 16-feature model contract."""


def validate_features(features, categories=None, unknown_category_policy=None):
    if not isinstance(features, dict):
        raise PredictionInputError("Each feature row must be a dictionary")
    if set(features) != set(FEATURES):
        raise PredictionInputError("Feature keys must exactly match artifact metadata")

    for key in NUMERIC:
        value = features[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PredictionInputError(f"{key}: finite numeric value required")
        if not math.isfinite(value):
            raise PredictionInputError(f"{key}: finite numeric value required")

    for key in CATEGORICAL:
        value = features[key]
        if not isinstance(value, str) or not value.strip():
            raise PredictionInputError(f"{key}: nonempty category required")
        if categories is not None and value not in categories[key]:
            policy = (unknown_category_policy or {}).get(key)
            if policy != "ignore":
                raise PredictionInputError(f"{key}: unseen training category")


def predict(model, rows, categories=None):
    import numpy as np
    import pandas as pd

    if not rows:
        return []

    unknown_category_policy = getattr(model, "unknown_category_policy", None)
    for row in rows:
        validate_features(row, categories, unknown_category_policy)

    frame = pd.DataFrame(
        [{key: row[key] for key in FEATURES} for row in rows],
        columns=FEATURES,
    )
    probabilities = np.asarray(model.predict_proba(frame))
    classes = np.asarray(model.predict(frame))
    if probabilities.shape != (len(rows), 2) or classes.shape != (len(rows),):
        raise ValueError("Unexpected model output shape")
    if not np.isfinite(probabilities).all():
        raise ValueError("Invalid probabilities")
    if ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("Invalid probabilities")
    if not np.allclose(probabilities.sum(axis=1), 1):
        raise ValueError("Invalid probability sums")
    if not set(classes).issubset({0, 1}):
        raise ValueError("Invalid class output")

    positive = list(model.classes_).index(1)
    return [
        {
            "predicted_class": int(label),
            "positive_probability": float(probability[positive]),
        }
        for label, probability in zip(classes, probabilities)
    ]