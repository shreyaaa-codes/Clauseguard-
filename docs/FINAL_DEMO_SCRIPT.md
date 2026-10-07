# ClauseGuard: Final Demo Script

**Duration:** 5-10 minutes

## 0:00 — Problem
**Narrative:** "Privacy policies are individually understandable, but users may not see the compounded exposure created by using multiple digital services. Accepting one policy is fine, but accepting fifty policies leads to an unmanaged data footprint. ClauseGuard models this."

## 0:45 — Architecture
**Narrative:** "ClauseGuard features a Chrome extension to extract text, a local Flask API, a prefilter, and an LLM extraction module. It canonicalizes entities, stores them in SQLite locally to preserve privacy, and scores risk additively."

## 1:30 — Backend demo
**Action:**
```powershell
python run_demo.py
```
**Show:**
* The extraction of clauses.
* Canonicalization of terms into 'Location' and 'IP Address'.
* Secure portfolio mapping.
* Marginal risk calculations cleanly distinguishing overlapping entities vs. newly introduced entities.

## 3:00 — Dashboard
**Action:**
```powershell
python src/dashboard.py
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000)

**Show:**
* The portfolio risk.
* The Live Vis.js Overlap Graph visualizing connections between Services and Canonical Entities.
* The Two-Service Comparator side-by-side marginal risk delta.

## 5:00 — Chrome Extension
**Action:**
* Go to a real privacy policy page (e.g., Spotify).
* Click the ClauseGuard Extension.
* Click 'Analyze Policy'.

**Show:**
* The 50,000-character extraction.
* The API returning canonical entities and the Mock/Dev warning flag.
* Explaining that ClauseGuard parses the active page directly to the local backend without accessing third-party tracking databases.

## 6:30 — Evaluation
**Action:**
* Show `data/evaluation/ablation_results.json`.

**Narrative:** "Our evaluation framework mathematically enforces zero leakage between the 14-example training dataset and testing. We have explicitly disabled composite LLM testing in 'Mock' mode to maintain scientific honesty."

## 7:30 — Contribution
**Narrative:** "ClauseGuard shifts the paradigm from isolated policy reading to portfolio-level privacy exposure analysis. It provides a local, mathematically verifiable foundation for marginal privacy risk analysis. While not yet 'production-ready', the prototype successfully validates the C1-C6 architecture."
