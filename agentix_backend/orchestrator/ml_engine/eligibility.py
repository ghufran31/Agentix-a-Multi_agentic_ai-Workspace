"""Original hard eligibility exclusions for employee matching."""

from .feature_extractor import parse_terms


def eligibility(employee, project):
    profile = getattr(employee, "ai_profile", None)
    if profile is None:
        return None, ["Missing employee AI profile"], {}

    reasons = []
    if profile.employment_status != "active":
        reasons.append(f"Employment status: {profile.employment_status}")
    if profile.availability_status == "unavailable":
        reasons.append("Unavailable")

    required = set()
    for requirement in project.requirements.all():
        required |= parse_terms(requirement.required_skills)

    owned = {
        assignment.skill.name.strip().casefold()
        for assignment in employee.skill_assignments.all()
        if assignment.skill.company_id == project.company_id
    }
    evidence = {
        "matched_skills": sorted(required & owned),
        "missing_skills": sorted(required - owned),
    }
    if not required:
        return None, ["Missing explicit required skills; eligibility cannot be fully evaluated"], evidence
    if not required & owned:
        reasons.append("Zero required-skill overlap")
    return not reasons, reasons, evidence