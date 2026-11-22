"""Load the saved Agentix preprocessor and native XGBoost model."""

import hashlib
import warnings
from functools import lru_cache
from pathlib import Path

import joblib
import xgboost


ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
FEATURES = [
    "job_title",
    "experience_years",
    "performance_score",
    "availability_status",
    "current_workload",
    "previous_project_score",
    "completed_projects",
    "employment_status",
    "skill_match_ratio",
    "average_skill_proficiency",
    "relevant_skill_years",
    "missing_required_skills_count",
    "role_match",
    "project_priority",
    "days_until_deadline",
    "required_skills_count",
]
CATEGORICAL = [
    "job_title",
    "availability_status",
    "employment_status",
    "project_priority",
]


class SplitArtifactPipeline:
    """Apply the fitted preprocessor before the saved native XGBoost classifier."""

    def __init__(self, preprocessor, classifier, unknown_category_policy):
        import numpy as np

        self.preprocessor = preprocessor
        self.classifier = classifier
        self.steps = [
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
        self.feature_names_in_ = np.asarray(FEATURES, dtype=object)
        self.classes_ = classifier.classes_
        self.unknown_category_policy = unknown_category_policy

    def _transform(self, frame):
        if list(frame.columns) != FEATURES:
            raise ValueError("Feature order differs from model metadata")
        transformed = self.preprocessor.transform(frame)
        if transformed.shape[1] != self.classifier.n_features_in_:
            raise ValueError("Preprocessor output does not match native model feature count")
        return transformed

    def predict(self, frame):
        return self.classifier.predict(self._transform(frame))

    def predict_proba(self, frame):
        return self.classifier.predict_proba(self._transform(frame))


def _extract_categories(preprocessor):
    categories = {}
    unknown_category_policy = {}
    for _, transformer, columns in preprocessor.transformers_:
        for _, step in getattr(transformer, "steps", []):
            if hasattr(step, "categories_"):
                categories.update({
                    column: values.tolist()
                    for column, values in zip(columns, step.categories_)
                })
                unknown_category_policy.update({
                    column: getattr(step, "handle_unknown", "error")
                    for column in columns
                })
    if set(categories) != set(CATEGORICAL):
        raise ValueError("Cannot identify categorical preprocessing")
    return categories, unknown_category_policy


@lru_cache(maxsize=4)
def _load_split_artifacts(preprocessor_path, native_model_path):
    preprocessor_path = Path(preprocessor_path)
    native_model_path = Path(native_model_path)
    for artifact_path in (preprocessor_path, native_model_path):
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Model artifact missing: {artifact_path.name}")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        preprocessor = joblib.load(preprocessor_path)
        classifier = xgboost.XGBClassifier()
        classifier.load_model(native_model_path)

    if list(getattr(preprocessor, "feature_names_in_", [])) != FEATURES:
        raise ValueError("Preprocessor feature order differs from metadata")

    categories, unknown_category_policy = _extract_categories(preprocessor)
    model = SplitArtifactPipeline(
        preprocessor,
        classifier,
        unknown_category_policy,
    )
    if list(model.classes_) != [0, 1]:
        raise ValueError("Expected binary suitability classes 0 and 1")

    preprocessor_hash = hashlib.sha256(preprocessor_path.read_bytes()).hexdigest()
    native_model_hash = hashlib.sha256(native_model_path.read_bytes()).hexdigest()
    info = {
        "artifact": f"{preprocessor_path.name} + {native_model_path.name}",
        "artifacts": {
            "preprocessor": {
                "file": preprocessor_path.name,
                "sha256": preprocessor_hash,
            },
            "native_model": {
                "file": native_model_path.name,
                "sha256": native_model_hash,
            },
        },
        "categories": categories,
        "unknown_category_policy": unknown_category_policy,
        "warnings": [str(w.message) for w in caught],
        "decision": "Saved estimator predict(); not synthetic score >= 65",
    }
    return model, info


def load_model(preprocessor_path=None, native_model_path=None):
    """Load and cache the verified split artifacts."""
    preprocessor_path = (
        Path(preprocessor_path).expanduser().resolve()
        if preprocessor_path is not None
        else (ARTIFACTS_DIR / "agentix_preprocessor.joblib").resolve()
    )
    native_model_path = (
        Path(native_model_path).expanduser().resolve()
        if native_model_path is not None
        else (ARTIFACTS_DIR / "agentix_xgboost_native.json").resolve()
    )
    if not preprocessor_path.is_relative_to(ARTIFACTS_DIR.resolve()):
        raise ValueError("Preprocessor path must remain inside ml_engine/artifacts")
    if not native_model_path.is_relative_to(ARTIFACTS_DIR.resolve()):
        raise ValueError("Native model path must remain inside ml_engine/artifacts")
    return _load_split_artifacts(str(preprocessor_path), str(native_model_path))