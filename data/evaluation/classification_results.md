# ClauseGuard - Classification Evaluation (40 clauses)

Positive class = 1 (privacy / data-practice clause); Negative class = 0.

## Final classification results table (primary: PrivacyPrefilter)

| Metric | Result |
|--------|--------|
| Dataset Size | 40 |
| Positive Clauses | 20 |
| Negative Clauses | 20 |
| True Positives | 17 |
| True Negatives | 12 |
| False Positives | 8 |
| False Negatives | 3 |
| Precision | 0.6800 |
| Recall | 0.8500 |
| F1-score | 0.7556 |
| Cohen's Kappa (reference labels vs prefilter predictions) | 0.4500 |
| Cohen's Kappa (inter-annotator, A vs B) | NOT COMPUTED - no second human annotator yet |

## Confusion matrix (counts)

| | Predicted Positive (1) | Predicted Negative (0) |
|---|---|---|
| **Actual Positive (1)** | TP = 17 | FN = 3 |
| **Actual Negative (0)** | FP = 8 | TN = 12 |

Cohen's kappa interpretation (Landis & Koch bands) for reference-vs-prediction: **moderate**.

## Secondary: analyzer candidate-selection rule (prefilter OR PRIVACY_WORDS regex)

| TP | TN | FP | FN | Precision | Recall | F1 | Kappa |
|---|---|---|---|---|---|---|---|
| 19 | 11 | 9 | 1 | 0.6786 | 0.9500 | 0.7917 | 0.5000 |

## Misclassified by the primary classifier (11)

| ID | Type | Actual | Pred | Category | Difficulty | Text |
|---|---|---|---|---|---|---|
| eval40_008 | FP | 0 | 1 | policy_meta | moderate | This Privacy Policy was last updated on 14 March 2024. |
| eval40_010 | FP | 0 | 1 | generic_service_description | easy | Our music service offers over fifty million songs and thousands of curated playlists. |
| eval40_015 | FN | 1 | 0 | device_data_passive | moderate | Details of your device model, operating system version and language settings are sent to our servers each time the app launches. |
| eval40_016 | FP | 0 | 1 | warranty_disclaimer | easy | The service is provided "as is" without warranties of any kind, express or implied. |
| eval40_018 | FP | 0 | 1 | user_obligation | moderate | You are responsible for keeping your password confidential and for all activity under your account. |
| eval40_020 | FP | 0 | 1 | company_information | easy | Our company is headquartered in Dublin, Ireland, and has offices in several European countries. |
| eval40_022 | FP | 0 | 1 | policy_meta | moderate | We may update this policy from time to time, and the revised version takes effect when it is posted. |
| eval40_023 | FN | 1 | 0 | usage_tracking | moderate | Information about how you use the app, such as the features you tap and the time spent on each screen, is recorded. |
| eval40_024 | FP | 0 | 1 | service_feature | easy | Premium members can download tracks and listen to them offline. |
| eval40_028 | FP | 0 | 1 | commercial_terms | moderate | Payment for subscriptions is due at the start of each billing period and is non-refundable. |
| eval40_029 | FN | 1 | 0 | transfer_business | moderate | If our company is acquired, the personal data we hold about you may be transferred to the new owner. |

## Validation checks

- validator: passed (schema + leakage)
- stats: {'total': 40, 'positive': 20, 'negative': 20}
- training_fixture_size: 8
- exact_overlap_with_training_fixture: 0
- max_similarity_within_eval_set: 0.614
- max_similarity_vs_training_fixture: 0.446
- max_similarity_vs_14_example_dev_set: 0.507
- max_similarity_vs_annotation_guide_examples: 0.507
- near_duplicate_threshold: 0.85
