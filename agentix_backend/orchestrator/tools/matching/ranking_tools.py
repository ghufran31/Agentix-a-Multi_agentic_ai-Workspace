from orchestrator.ml_engine.loader import load_model
from orchestrator.ml_engine.predictor import predict

def execute_ranking(rows):
    model, info = load_model()
    outputs = predict(model, [row['features'] for row in rows], info['categories'])
    combined = [{**row, **prediction} for row, prediction in zip(rows, outputs)]
    combined.sort(key=lambda row: (-row['positive_probability'], row['employee_id']))
    for rank, row in enumerate(combined, 1):
        row['rank'] = rank
    return {'results': combined, 'model_info': info}
