"""Build the existing exploratory 16-feature model snapshot from Django records."""

import json
import math
from datetime import date

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


class FeatureError(ValueError):
    """Data cannot be mapped without inventing unverified training semantics."""


def parse_terms(value):
    if value is None or not value.strip():
        return set()
    value = value.strip()
    if value.startswith("["):
        try:
            terms = json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            raise FeatureError("Malformed JSON requirements") from exc
        if not isinstance(terms, list) or any(not isinstance(term, str) for term in terms):
            raise FeatureError("Requirements must be a JSON list of names")
    else:
        terms = value.replace("\n", ",").split(",")
    return {
        term.strip().casefold()
        for term in terms
        if term.strip()
    }


def validate_features(features, categories=None, unknown_category_policy=None):
    if not isinstance(features, dict) or set(features) != set(FEATURES):
        raise FeatureError("Feature keys must exactly match artifact metadata")
    if list(features) != FEATURES:
        raise FeatureError("Feature order differs from model metadata")

    for key in NUMERIC:
        value = features[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FeatureError(f"{key}: finite numeric value required")
        if not math.isfinite(value):
            raise FeatureError(f"{key}: finite numeric value required")
        if key != "days_until_deadline" and value < 0:
            raise FeatureError(f"{key}: negative value is invalid")

    for key in (
        "completed_projects",
        "missing_required_skills_count",
        "required_skills_count",
        "days_until_deadline",
    ):
        if int(features[key]) != features[key]:
            raise FeatureError(f"{key}: integer required")

    if not 0 <= features["skill_match_ratio"] <= 1:
        raise FeatureError("Invalid skill ratio")
    if features["role_match"] not in (0, 1):
        raise FeatureError("Invalid role-match flag")

    count = features["required_skills_count"]
    missing = features["missing_required_skills_count"]
    expected_ratio = round((count - missing) / count, 4) if count > 0 else None
    if count <= 0 or missing > count or features["skill_match_ratio"] != expected_ratio:
        raise FeatureError("Inconsistent skill counts/ratio or empty skill requirements")

    for key in CATEGORICAL:
        value = features[key]
        if not isinstance(value, str) or not value.strip():
            raise FeatureError(f"{key}: nonempty category required")
        if categories is not None and value not in categories[key]:
            policy = (unknown_category_policy or {}).get(key)
            if policy != "ignore":
                raise FeatureError(f"{key}: unseen training category")


def extract_features(employee, project, evaluation_date):
    """Build an explicit exploratory snapshot; do not infer missing source fields."""
    if employee.department.company_id != project.company_id:
        raise FeatureError("Employee/project company mismatch")

    profile = getattr(employee, "ai_profile", None)
    if profile is None:
        raise FeatureError("Missing employee AI profile")

    required = set()
    roles = set()
    for requirement in project.requirements.all():
        required |= parse_terms(requirement.required_skills)
        roles |= parse_terms(requirement.required_roles)
    if not required:
        raise FeatureError("Missing explicit required skills")
    if not roles:
        raise FeatureError("Missing explicit required roles")
    if project.deadline is None:
        raise FeatureError("Missing project deadline")
    if not profile.job_title:
        raise FeatureError("Missing job title")

    assignments = {}
    for assignment in employee.skill_assignments.all():
        if assignment.skill.company_id != project.company_id:
            raise FeatureError("Cross-company employee skill")
        key = assignment.skill.name.strip().casefold()
        if key in assignments:
            raise FeatureError("Ambiguous normalized skill names")
        assignments[key] = assignment

    matched = sorted(required & assignments.keys())
    missing = sorted(required - assignments.keys())
    if not matched:
        raise FeatureError("Zero required-skill overlap; no relevant-skill aggregates")

    values = {}
    for field in (
        "experience_years",
        "performance_score",
        "current_workload",
        "previous_project_score",
        "completed_projects",
    ):
        raw = getattr(profile, field)
        if raw is None:
            raise FeatureError(
                f"Missing {field}; training missing-data semantics unverified"
            )
        values[field] = float(raw)

    for name in matched:
        if assignments[name].proficiency is None:
            raise FeatureError("Missing relevant skill proficiency")
        if assignments[name].years_experience is None:
            raise FeatureError("Missing relevant skill years")

    values.update(
        job_title=profile.job_title,
        availability_status=profile.availability_status,
        employment_status=profile.employment_status,
        skill_match_ratio=round(len(matched) / len(required), 4),
        average_skill_proficiency=sum(
            float(assignments[name].proficiency) for name in matched
        ) / len(matched),
        relevant_skill_years=sum(
            float(assignments[name].years_experience) for name in matched
        ) / len(matched),
        missing_required_skills_count=len(missing),
        role_match=int(profile.job_title.strip().casefold() in roles),
        project_priority=project.priority,
        days_until_deadline=(project.deadline - evaluation_date).days,
        required_skills_count=len(required),
    )

    ordered = {key: values[key] for key in FEATURES}
    validate_features(ordered)
    return ordered, {
        "matched_skills": matched,
        "missing_skills": missing,
        "mapping_status": "EXPLORATORY_UNVERIFIED",
    }