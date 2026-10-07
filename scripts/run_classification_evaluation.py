"""
ClauseGuard - 40-clause classification evaluation (one command).

    python scripts/run_classification_evaluation.py

Steps: dataset validation + leakage/duplicate checks -> predictions from the
EXISTING PrivacyPrefilter -> TP/TN/FP/FN, Precision/Recall/F1 -> confusion
matrix (table + PNG) -> Cohen's kappa -> results table (JSON + Markdown).

Nothing here changes the classifier, analyzer, scoring, Gemini integration or
DB schema. Predictions are never edited; they come straight from the prefilter.
"""
import argparse
import difflib
import json
import os
import re
import sys

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(BASE, "src"))

from evaluation.dataset import DatasetValidator          # existing validator (schema + leakage)
from evaluation.metrics import calculate_metrics, confusion_matrix, cohen_kappa
from extraction.prefilter import PrivacyPrefilter        # existing classifier

EVAL_DIR = os.path.join(BASE, "data", "evaluation")
GT_40 = os.path.join(EVAL_DIR, "ground_truth_40.json")
GT_DEV = os.path.join(EVAL_DIR, "ground_truth.json")
GUIDE = os.path.join(EVAL_DIR, "ANNOTATION_GUIDE.md")
ANNOTATOR_B = os.path.join(EVAL_DIR, "annotator_b_labels.json")
OUT_JSON = os.path.join(EVAL_DIR, "classification_results.json")
OUT_MD = os.path.join(EVAL_DIR, "classification_results.md")
OUT_PNG = os.path.join(EVAL_DIR, "confusion_matrix.png")

EXPECTED_N = 40
NEAR_DUP_THRESHOLD = 0.85   # difflib similarity ratio at/above which two sentences count as near-duplicates


def norm(t):
    return re.sub(r"\s+", " ", t.lower().strip())


def sim(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


# --------------------------------------------------------------------------- #
# 1. Dataset validation
# --------------------------------------------------------------------------- #
class _CapturingPrefilter(PrivacyPrefilter):
    """Identical to PrivacyPrefilter; only records the texts it is trained on,
    so the leakage check uses the REAL fixture rather than a pasted copy."""
    def train(self, texts, labels):
        self.training_texts = list(texts)
        super().train(texts, labels)


def validate_dataset():
    validator = DatasetValidator(GT_40)
    stats = validator.validate_all()          # schema + existing leakage check (raises on failure)
    data = validator.load_dataset()
    ex = data["examples"]
    checks = {"validator": "passed (schema + leakage)", "stats": stats}

    assert len(ex) == EXPECTED_N, f"Expected {EXPECTED_N} clauses, found {len(ex)}"
    ids = [e["id"] for e in ex]
    assert len(set(ids)) == len(ids), "Duplicate IDs found"
    texts = [e["text"] for e in ex]
    assert len({norm(t) for t in texts}) == len(texts), "Exact duplicate texts found"

    # Independent leakage check against the prefilter's actual training fixture.
    pf = _CapturingPrefilter()
    pf.train_with_minimal_fixture()
    train_set = {norm(t) for t in pf.training_texts}
    leaked = [t for t in texts if norm(t) in train_set]
    assert not leaked, f"Leakage against real training fixture: {leaked}"
    checks["training_fixture_size"] = len(pf.training_texts)
    checks["exact_overlap_with_training_fixture"] = 0

    # Near-duplicate check: within the set, vs training fixture, vs 14-example dev set, vs guide examples.
    with open(GT_DEV, encoding="utf-8") as f:
        dev_texts = [e["text"] for e in json.load(f)["examples"]]
    with open(GUIDE, encoding="utf-8") as f:
        guide_texts = re.findall(r'\*\s+"([^"]+)"', f.read())

    def max_cross(pool):
        return max((sim(t, p), t, p) for t in texts for p in pool)

    worst_within = max((sim(texts[i], texts[j]), texts[i], texts[j])
                       for i in range(len(texts)) for j in range(i + 1, len(texts)))
    for label, (s, a, b) in [("within_eval_set", worst_within),
                             ("vs_training_fixture", max_cross(pf.training_texts)),
                             ("vs_14_example_dev_set", max_cross(dev_texts)),
                             ("vs_annotation_guide_examples", max_cross(guide_texts))]:
        assert s < NEAR_DUP_THRESHOLD, f"Near-duplicate ({label}, {s:.2f}): '{a}' ~ '{b}'"
        checks[f"max_similarity_{label}"] = round(s, 3)
    checks["near_duplicate_threshold"] = NEAR_DUP_THRESHOLD
    return data, checks


# --------------------------------------------------------------------------- #
# 2. Predictions from the EXISTING pipeline
# --------------------------------------------------------------------------- #
def predict_prefilter(texts):
    """Primary: PrivacyPrefilter (TF-IDF + LogisticRegression, random_state=42), trained with its own
    built-in fixture - exactly how src/evaluation/ablation.py and src/extract.py use it."""
    pf = PrivacyPrefilter()
    pf.train_with_minimal_fixture()
    return [1 if len(pf.filter_candidates([t])) > 0 else 0 for t in texts]


def predict_analyzer_rule(texts):
    """Secondary: the candidate-selection rule used inside analyzer.extract_clauses():
    keep a sentence if the prefilter keeps it OR analyzer.PRIVACY_WORDS matches.
    extract_clauses() itself cannot be called here because it also invokes the LLM extractor,
    so the one-line rule is re-applied using the real prefilter and the real PRIVACY_WORDS object."""
    from analyzer import PRIVACY_WORDS
    pf = PrivacyPrefilter()
    pf.train_with_minimal_fixture()
    return [1 if (len(pf.filter_candidates([t])) > 0 or PRIVACY_WORDS.search(t)) else 0 for t in texts]


# --------------------------------------------------------------------------- #
# 3. Inter-annotator kappa (only if a genuine second human annotation exists)
# --------------------------------------------------------------------------- #
def inter_annotator(ids, y_a, path):
    if not os.path.exists(path):
        return {"status": "NOT COMPUTED", "reason": "No second human annotation exists yet "
                "(data/evaluation/annotator_b_labels.json not found). Fill data/evaluation/annotator_b_template.json "
                "independently and save it under that name."}
    with open(path, encoding="utf-8") as f:
        b = json.load(f)
    by_id = {e["id"]: e["label"] for e in b.get("examples", [])}
    if set(by_id) != set(ids) or any(v not in (0, 1) for v in by_id.values()):
        return {"status": "NOT COMPUTED", "reason": "annotator_b_labels.json is incomplete: every id needs label 0 or 1."}
    y_b = [by_id[i] for i in ids]
    k = cohen_kappa(y_a, y_b)
    agree = sum(1 for x, y in zip(y_a, y_b) if x == y)
    return {"status": "COMPUTED", "annotator_b": b.get("annotator"), "kappa": k,
            "observed_agreement": agree / len(ids), "disagreements": len(ids) - agree}


# --------------------------------------------------------------------------- #
# 4. Output helpers
# --------------------------------------------------------------------------- #
def f4(x):
    return "undefined" if x is None else f"{x:.4f}"


def interpret_kappa(k):
    """Landis & Koch (1977) bands."""
    if k is None:
        return "undefined"
    if k <= 0.0:
        return "poor (no better than chance)"
    if k <= 0.20:
        return "slight"
    if k <= 0.40:
        return "fair"
    if k <= 0.60:
        return "moderate"
    if k <= 0.80:
        return "substantial"
    return "almost perfect"


def draw_confusion_png(cm, n, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    ax.imshow(cm, cmap="Blues", vmin=0, vmax=max(max(r) for r in cm) or 1)
    names = [["TP", "FN"], ["FP", "TN"]]
    for i in range(2):
        for j in range(2):
            dark = cm[i][j] > (max(max(r) for r in cm) / 2)
            ax.text(j, i, f"{cm[i][j]}\n({names[i][j]})", ha="center", va="center", fontsize=15,
                    color="white" if dark else "black")
    ax.set_xticks([0, 1], ["Predicted\nPositive (1)", "Predicted\nNegative (0)"])
    ax.set_yticks([0, 1], ["Actual\nPositive (1)", "Actual\nNegative (0)"])
    ax.set_title(f"Confusion matrix - privacy-clause prefilter (n = {n})\n(raw counts)", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--annotator-b", default=ANNOTATOR_B, help="completed second-annotator file (optional)")
    ap.add_argument("--no-write", action="store_true", help="print only; do not write result files")
    args = ap.parse_args()

    data, checks = validate_dataset()
    ex = data["examples"]
    ids = [e["id"] for e in ex]
    texts = [e["text"] for e in ex]
    y_true = [e["label"] for e in ex]
    n = len(ex)
    pos, neg = sum(y_true), n - sum(y_true)

    y_pred = predict_prefilter(texts)
    m = calculate_metrics(y_true, y_pred)
    cm = confusion_matrix(y_true, y_pred)

    # ---- internal consistency (fail loudly, never report inconsistent numbers) ----
    assert m["TP"] + m["TN"] + m["FP"] + m["FN"] == n
    assert cm == [[m["TP"], m["FN"]], [m["FP"], m["TN"]]]
    assert m["TP"] + m["FN"] == pos and m["FP"] + m["TN"] == neg
    if m["TP"] + m["FP"]:
        assert m["Precision"] == m["TP"] / (m["TP"] + m["FP"])
    if m["TP"] + m["FN"]:
        assert m["Recall"] == m["TP"] / (m["TP"] + m["FN"])
    if m["Precision"] + m["Recall"]:
        assert abs(m["F1"] - 2 * m["Precision"] * m["Recall"] / (m["Precision"] + m["Recall"])) < 1e-12

    kappa_pred = cohen_kappa(y_true, y_pred)
    iaa = inter_annotator(ids, y_true, args.annotator_b)

    # ---- secondary: analyzer candidate-selection rule ----
    y_an = predict_analyzer_rule(texts)
    m_an = calculate_metrics(y_true, y_an)
    k_an = cohen_kappa(y_true, y_an)

    errors = [{"id": i, "text": t, "actual": a, "predicted": p,
               "error_type": "FN" if a == 1 else "FP",
               "category": e["category"], "difficulty": e["difficulty"]}
              for i, t, a, p, e in zip(ids, texts, y_true, y_pred, ex) if a != p]
    per_clause = [{"id": i, "label": a, "prefilter_pred": p, "analyzer_rule_pred": q}
                  for i, a, p, q in zip(ids, y_true, y_pred, y_an)]

    result = {
        "dataset": {"file": "data/evaluation/ground_truth_40.json", "size": n, "positive": pos, "negative": neg,
                    "annotation_provenance": data.get("annotation_provenance")},
        "validation": checks,
        "y_true": "'label' field of each example in ground_truth_40.json (Annotator A)",
        "y_pred": "PrivacyPrefilter (TF-IDF + LogisticRegression(random_state=42)) trained via "
                  "train_with_minimal_fixture(); predicted per clause with filter_candidates([text])",
        "primary_metrics": m,
        "confusion_matrix": {"layout": "[[TP, FN], [FP, TN]]; rows = actual (1,0), columns = predicted (1,0)", "matrix": cm},
        "cohen_kappa_reference_vs_prediction": {
            "kappa": kappa_pred, "interpretation": interpret_kappa(kappa_pred),
            "meaning": "Agreement between the reference labels and the prefilter's predictions. NOT inter-annotator agreement."},
        "cohen_kappa_inter_annotator": iaa,
        "secondary_analyzer_candidate_rule": {
            "description": "prefilter OR analyzer.PRIVACY_WORDS regex (rule used in analyzer.extract_clauses)",
            "metrics": m_an, "cohen_kappa_reference_vs_prediction": k_an},
        "misclassified_by_primary": errors,
        "per_clause_predictions": per_clause,
    }

    # ---- console + markdown ----
    L = []
    L.append("# ClauseGuard - Classification Evaluation (40 clauses)\n")
    L.append("Positive class = 1 (privacy / data-practice clause); Negative class = 0.\n")
    L.append("## Final classification results table (primary: PrivacyPrefilter)\n")
    L.append("| Metric | Result |\n|--------|--------|")
    rows = [("Dataset Size", n), ("Positive Clauses", pos), ("Negative Clauses", neg),
            ("True Positives", m["TP"]), ("True Negatives", m["TN"]),
            ("False Positives", m["FP"]), ("False Negatives", m["FN"]),
            ("Precision", f4(m["Precision"])), ("Recall", f4(m["Recall"])), ("F1-score", f4(m["F1"])),
            ("Cohen's Kappa (reference labels vs prefilter predictions)", f4(kappa_pred))]
    for k, v in rows:
        L.append(f"| {k} | {v} |")
    if iaa["status"] == "COMPUTED":
        L.append(f"| Cohen's Kappa (inter-annotator, A vs B) | {f4(iaa['kappa'])} |")
    else:
        L.append("| Cohen's Kappa (inter-annotator, A vs B) | NOT COMPUTED - no second human annotator yet |")
    L.append("\n## Confusion matrix (counts)\n")
    L.append("| | Predicted Positive (1) | Predicted Negative (0) |\n|---|---|---|")
    L.append(f"| **Actual Positive (1)** | TP = {cm[0][0]} | FN = {cm[0][1]} |")
    L.append(f"| **Actual Negative (0)** | FP = {cm[1][0]} | TN = {cm[1][1]} |")
    L.append(f"\nCohen's kappa interpretation (Landis & Koch bands) for reference-vs-prediction: **{interpret_kappa(kappa_pred)}**.\n")
    L.append("## Secondary: analyzer candidate-selection rule (prefilter OR PRIVACY_WORDS regex)\n")
    L.append("| TP | TN | FP | FN | Precision | Recall | F1 | Kappa |\n|---|---|---|---|---|---|---|---|")
    L.append(f"| {m_an['TP']} | {m_an['TN']} | {m_an['FP']} | {m_an['FN']} | {f4(m_an['Precision'])} | "
             f"{f4(m_an['Recall'])} | {f4(m_an['F1'])} | {f4(k_an)} |")
    L.append(f"\n## Misclassified by the primary classifier ({len(errors)})\n")
    L.append("| ID | Type | Actual | Pred | Category | Difficulty | Text |\n|---|---|---|---|---|---|---|")
    for e in errors:
        L.append(f"| {e['id']} | {e['error_type']} | {e['actual']} | {e['predicted']} | {e['category']} | {e['difficulty']} | {e['text']} |")
    L.append("\n## Validation checks\n")
    for k, v in checks.items():
        L.append(f"- {k}: {v}")
    md = "\n".join(L) + "\n"

    print(md)
    print("Inter-annotator kappa:", json.dumps(iaa))
    if not args.no_write:
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        with open(OUT_MD, "w", encoding="utf-8") as f:
            f.write(md)
        ok = draw_confusion_png(cm, n, OUT_PNG)
        print(f"\nWrote {os.path.relpath(OUT_JSON, BASE)}, {os.path.relpath(OUT_MD, BASE)}"
              + (f", {os.path.relpath(OUT_PNG, BASE)}" if ok else " (matplotlib not installed: PNG skipped)"))
    return result


if __name__ == "__main__":
    main()
