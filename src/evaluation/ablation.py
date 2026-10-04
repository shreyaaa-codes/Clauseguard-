import json
import os
import sys

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from extraction.prefilter import PrivacyPrefilter
from evaluation.metrics import calculate_metrics
from evaluation.dataset import DatasetValidator

def run_ablation_experiment():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    gt_path = os.path.join(base_dir, 'data', 'evaluation', 'ground_truth.json')
    
    # Validate Dataset before running
    validator = DatasetValidator(gt_path)
    stats = validator.validate_all()
    ground_truth = validator.load_dataset()
        
    examples = ground_truth.get("examples", [])
    y_true = [ex["label"] for ex in examples]
    texts = [ex["text"] for ex in examples]
    
    # 1. Naive Baseline
    # Predicts 1 for every sentence
    y_naive = [1] * len(y_true)
    naive_metrics = calculate_metrics(y_true, y_naive)
    
    # 2. Prefilter Only
    prefilter = PrivacyPrefilter()
    if not prefilter.is_trained:
        prefilter.train_with_minimal_fixture()
        
    y_prefilter = []
    for text in texts:
        filtered = prefilter.filter_candidates([text])
        if len(filtered) > 0:
            y_prefilter.append(1)
        else:
            y_prefilter.append(0)
            
    prefilter_metrics = calculate_metrics(y_true, y_prefilter)
    
    # 3. Composite Pipeline
    is_real_llm = "GEMINI_API_KEY" in os.environ
    
    if is_real_llm:
        composite_metrics = None
        composite_note = "Real LLM available but not executed in this offline ablation test."
    else:
        composite_metrics = "N/A"
        composite_note = "Composite evaluation deferred because the available mock extractor is not a valid representation of the production LLM."
        
    # Serialize Results
    results = {
        "dataset_version": ground_truth.get("version", "1.0"),
        "dataset_size": stats["total"],
        "annotation_status": ground_truth.get("dataset_type", "UNKNOWN"),
        "evaluation_mode": "MOCK/DEV" if not is_real_llm else "REAL",
        "training_evaluation_separation": "Verified zero overlap via DatasetValidator.",
        "approaches": {
            "Naive": naive_metrics,
            "Prefilter": prefilter_metrics,
            "Composite": {
                "metrics": composite_metrics,
                "limitations": composite_note
            }
        },
        "limitations": [
            "Dataset is too small (N=14) to represent a true scientific benchmark.",
            "Composite evaluation is explicitly disabled in mock mode to prevent falsifying metrics."
        ]
    }
    
    out_path = os.path.join(base_dir, 'data', 'evaluation', 'ablation_results.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
        
    return results

if __name__ == "__main__":
    res = run_ablation_experiment()
    print("Ablation experiment completed. Results:")
    print(json.dumps(res, indent=2))
