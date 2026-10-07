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


def confusion_matrix(y_true, y_pred):
    """
    2x2 confusion matrix with the SAME convention as calculate_metrics
    (positive class = 1 = privacy clause). Layout:

                      Predicted 1   Predicted 0
        Actual 1          TP            FN
        Actual 0          FP            TN

    Returns [[TP, FN], [FP, TN]]. Counts come from calculate_metrics so the two
    can never disagree.
    """
    m = calculate_metrics(y_true, y_pred)
    return [[m["TP"], m["FN"]], [m["FP"], m["TN"]]]


def cohen_kappa(rater_a, rater_b):
    """
    Cohen's kappa for two binary label vectors: (po - pe) / (1 - pe).

    This is a generic agreement statistic. What it MEANS depends on the vectors:
    two independent human annotators -> inter-annotator agreement;
    reference labels vs. model predictions -> reference/prediction agreement
    (NOT inter-annotator agreement).

    Returns None when kappa is undefined (empty input, or pe == 1, i.e. both
    raters use a single identical class for every item).
    """
    if len(rater_a) != len(rater_b):
        raise ValueError("Both label vectors must have the same length.")
    n = len(rater_a)
    if n == 0:
        return None
    po = sum(1 for a, b in zip(rater_a, rater_b) if a == b) / n
    pa1 = sum(1 for a in rater_a if a == 1) / n
    pb1 = sum(1 for b in rater_b if b == 1) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    if pe == 1:
        return None
    return (po - pe) / (1 - pe)
