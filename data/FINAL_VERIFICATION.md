# ClauseGuard Final Verification Matrix

| Component | Status | Evidence |
| :--- | :--- | :--- |
| C1 Extraction | PASS | Verified via automated test suite and Chrome Extension API |
| C2 Canonicalization | PASS | Verified deterministic mapping via test_canonicalize.py |
| C3 Database | PASS | Verified idempotent portfolio.db architecture |
| C4 Scoring | PASS | Verified mathematically via invariants test suite |
| C5 Marginal Risk | PASS | Verified overlap vs. novel entity deltas |
| C6 Demo | PASS | Verified end-to-end run_demo.py execution |
| Evaluation | PASS | Verified zero-leakage pipeline and reproducibility |
| Weight tuning | BASELINE / NOT SCIENTIFICALLY TUNED | Blocked by missing expert annotations. Kept at w1=1.0, w2=1.0 |
| Live dashboard | PASS | Verified interactive Flask/Tailwind web app |
| Overlap graph | PASS | Verified live Vis.js graph mapping Services to Entities |
| Two-service comparator | PASS | Verified side-by-side marginal candidate calculation |
| Robustness | PASS | Verified test_robustness.py handles long, messy policy |
| Chrome extension | PASS | Verified API integration and text-scraping limit |
| Final regression | PASS | 87/87 test suite execution successful |

### Final Verification Checks
* **Final test count**: 87/87 PASS.
* **Database verification**: `data/db/portfolio.db` is confirmed untouched and maintains schema/integrity.
* **Dashboard verification**: Web UI fetches portfolio and marginal risk dynamically with zero hardcoded JSON.
* **Extension verification**: Validated endpoint behavior, character truncations, and CORS integration.
* **Security check**: Extension asks for minimum permissions (`activeTab`, `scripting`, `localhost:5000`). No API keys or `.env` checked into git.
* **Known limitations**: No human-rated ground truth for weights; 14-example evaluation sandbox; marginal risk remains strictly additive despite overlap detection.
