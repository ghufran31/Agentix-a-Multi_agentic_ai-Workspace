from orchestrator.ml_engine.feature_extractor import FeatureError, extract_features, validate_features

def build_project_snapshot(project, employees, evaluation_date, model_info):
    rows, errors = [], []
    for employee in employees:
        try:
            features, evidence = extract_features(employee, project, evaluation_date)
            validate_features(features, model_info['categories'], model_info['unknown_category_policy'])
            rows.append({'employee_id': employee.id, 'features': features, **evidence})
        except FeatureError as exc:
            errors.append({'employee_id': employee.id, 'error': str(exc)})
    return {'rows': rows, 'errors': errors, 'complete': len(rows) + len(errors) == len(employees)}
