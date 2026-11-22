"""Read-only eligible-candidate ranking using the verified saved estimator."""

from .eligibility import eligibility
from .feature_extractor import FeatureError, extract_features, validate_features
from .loader import FEATURES, load_model
from .predictor import PredictionInputError, predict


def rank_candidates(results):
    ranked = sorted(
        (
            row
            for row in results
            if row.get("positive_probability") is not None
            and row.get("eligible") is True
        ),
        key=lambda row: (
            -row["positive_probability"],
            row["employee_id"],
        ),
    )
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank
    return ranked


def rank_project_candidates(
    project,
    employees,
    evaluation_date,
    *,
    model=None,
    model_info=None,
):
    """Rank same-company candidates without any create/update/delete operation."""
    if model is None or model_info is None:
        model, model_info = load_model()

    rows = []
    evaluable = []
    for employee in employees:
        row = {
            "employee_id": employee.pk,
            "project_id": project.pk,
            "eligible": None,
            "rejection_reasons": [],
            "feature_errors": [],
            "features": {key: None for key in FEATURES},
            "matched_skills": [],
            "missing_skills": [],
            "mapping_status": "EXPLORATORY_UNVERIFIED",
            "predicted_class": None,
            "positive_probability": None,
            "rank": None,
        }
        try:
            row["eligible"], row["rejection_reasons"], evidence = eligibility(
                employee,
                project,
            )
            row.update(evidence)
        except Exception as exc:
            row["eligible"] = None
            row["feature_errors"].append(str(exc))

        try:
            features, evidence = extract_features(
                employee,
                project,
                evaluation_date,
            )
            row["features"] = features
            row.update(evidence)
            validate_features(
                features,
                model_info["categories"],
                model_info["unknown_category_policy"],
            )
        except (FeatureError, PredictionInputError) as exc:
            row["feature_errors"].append(str(exc))

        rows.append(row)
        if row["eligible"] is True and not row["feature_errors"]:
            evaluable.append(row)

    predictions = predict(
        model,
        [row["features"] for row in evaluable],
        model_info["categories"],
    )
    repeated = predict(
        model,
        [row["features"] for row in evaluable],
        model_info["categories"],
    )
    if predictions != repeated:
        raise ValueError("Repeated predictions differ")
    for row, prediction in zip(evaluable, predictions):
        row.update(prediction)

    return rank_candidates(rows), rows