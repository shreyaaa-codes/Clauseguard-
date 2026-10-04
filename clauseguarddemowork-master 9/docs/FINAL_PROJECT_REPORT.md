# FINAL PROJECT REPORT: ClauseGuard
**Status:** COMPLETE (Development Prototype)
**Date:** September 2026

## 1. Abstract
ClauseGuard is an end-to-end privacy analysis system designed to move beyond single-policy reading. It analyzes privacy risk at the portfolio level, enabling users to evaluate how a new digital service increases their overall data exposure compared to services they already use. The system features a NLP extraction pipeline, entity canonicalization, local SQLite risk storage, a mathematical risk scoring engine, and live dashboard visualizers via a Chrome Extension and Flask API.

## 2. Problem Statement
Privacy policies are individually understandable but fail to communicate compounded exposure. Users accept policies in isolation without realizing how multiple services synergistically expose their data footprint.

## 3. Research Questions
* Can privacy clauses be deterministically extracted and categorized?
* Can distinct terminology be canonicalized into a universal privacy entity schema?
* How can marginal risk (the risk of a new service minus overlapping data) be mathematically modeled?

## 4. System Architecture
```
Privacy Policy webpage
       ↓
Chrome Extension (Client)
       ↓
Flask Backend /api/analyze-policy
       ↓
[C1] Extraction (Prefilter + LLM)
       ↓
[C2] Canonicalization
       ↓
[C4] Scoring Engine & [C5] Marginal Risk
       ↓
[C3] SQLite Portfolio Storage (Local DB)
```

## 5. C1 Extraction
Combines a fast local Logistic Regression prefilter (trained to reject non-privacy boilerplate) with a robust LLM extraction agent to structure raw text into discrete clauses with entities, severity, and specificity.

## 6. C2 Canonicalization
Standardizes semantically equivalent entities (e.g., "GPS coordinates" vs "Location data" -> `Location`).

## 7. C3 Portfolio Storage
Uses SQLite (`data/db/portfolio.db`) to persist extracted policies, scores, and relational graphs locally, enforcing privacy-by-design.

## 8. C4 Risk Scoring
Applies a baseline formula: `Clause Risk = (w1 * severity) + (w2 * specificity)`. Service risk and Portfolio risk aggregate additively (SUM).

## 9. C5 Marginal Risk
Calculates candidate risk and precisely tracks overlapping vs. newly introduced entities across the existing portfolio footprint.

## 10. Evaluation Methodology
Evaluated using a 14-example strictly separated evaluation ground truth dataset (`data/evaluation/ground_truth.json`). Tested using an ablation pipeline.

## 11. Evaluation Results
* **Naive Approach:** Precision 0.50, Recall 1.0, F1 0.67
* **Prefilter Approach:** Precision 0.67, Recall 0.86, F1 0.75
* *Note: LogisticRegression uses `random_state=42` for strict reproducibility.*

## 12. Ablation Results
See `data/evaluation/ablation_results.json` for deterministic output. Composite LLM evaluation is disabled in mock mode to preserve scientific integrity.

## 13. Dashboard
A Flask/Vanilla JS dashboard (`src/dashboard.py`). Features a live portfolio summary, an interactive Vis.js node-edge overlap graph, and a Two-Service Marginal Risk Comparator.

## 14. Chrome Extension
A Manifest V3 extension that extracts up to 50,000 characters from the active tab and routes it to the local Flask API for analysis without directly scraping DBs or housing ML logic.

## 15. Robustness Testing
Robustness against messy text (no punctuation, duplicate sentences, long context) was successfully verified. The pipeline successfully extracts, avoids SQL faults, and truncates input safely (`tests/test_robustness.py`).

## 16. Limitations
* Dataset is a 14-example development sandbox, not a proven enterprise benchmark.
* Weights `w1` and `w2` are untuned assumptions due to a lack of independent human-expert-ranked ground truth.
* Marginal risk detects entity overlap but currently does not mathematically discount candidate risk.

## 17. Future Work
* Build a 1,000+ policy expert-annotated corpus.
* Mathematically optimize `w1` and `w2` against expert ground truth.
* Enhance the marginal risk formula to discount overlapping entities logarithmically.

## 18. Conclusion
ClauseGuard matches the explicit implementable requirements of the Full Project Plan, successfully serving as a robust privacy-risk portfolio analysis prototype.
