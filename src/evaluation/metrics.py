def calculate_metrics(y_true, y_pred):
    """
    Deterministic standard formulas for evaluating binary classification.
    y_true: list of int (0 or 1)
    y_pred: list of int (0 or 1)
    
    Positive class = 1 (Privacy clause)
    Negative class = 0 (Non-privacy clause)
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length.")
        
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)
    
    # Zero-division safety
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        "TP": tp,
        "TN": tn,
        "FP": fp,
        "FN": fn,
        "Precision": precision,
        "Recall": recall,
        "F1": f1
    }

def define_baselines():
    """
    Defines what the baselines mean for Phase 2 ablation based on the current implementation.
    Does NOT execute the ablation.
    """
    return {
        "naive_baseline": "Predict 1 (privacy clause) for every sentence. High recall, terrible precision.",
        "composite_approach": "The current C1 pipeline: TF-IDF + Logistic Regression prefilter -> LLM extraction."
    }
