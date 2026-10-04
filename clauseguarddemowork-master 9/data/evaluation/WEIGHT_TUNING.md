# Weight Tuning & Aggregation Strategy

## Implemented Baseline
The current Phase 1 implementation uses the following formula to compute Clause Risk:
`Clause Risk = (w1 * severity) + (w2 * specificity)`

*   **w1 (severity weight):** 1.0
*   **w2 (specificity weight):** 1.0

The aggregation strategy to compute Service Risk and Portfolio Risk is currently **SUM**, which is mathematically validated in the codebase to guarantee additive property constraints.

## Missing Ground Truth
**Weight tuning is not scientifically performed because independent expert-ranked ground truth is unavailable.** 

We have explicitly refused to mathematically optimize `w1`, `w2`, or the `mean` vs `sum` decision against the synthetic LLM output. Tuning parameters against deterministic mock output or untargeted LLM extraction would constitute over-fitting and fake research. 

## Future Tuning Procedure
Once human domain experts annotate the template at `data/evaluation/expert_portfolio_rankings_template.json`, the following tuning procedure must be executed:
1.  Sweep `w1` and `w2` constraints (e.g., [0.5, 1.0, 2.0]).
2.  Sweep aggregation operators (Mean vs. Sum).
3.  Calculate Mean Absolute Error (MAE) and Rank Correlation (e.g., Spearman's Rho) against the human expert risk scores.
4.  Adopt the configuration that mathematically minimizes deviation from expert judgment.
