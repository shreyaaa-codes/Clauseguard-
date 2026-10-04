import unittest
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from evaluation.metrics import calculate_metrics

class TestEvaluationMetrics(unittest.TestCase):
    
    def test_perfect_predictions(self):
        y_true = [1, 0, 1, 0]
        y_pred = [1, 0, 1, 0]
        metrics = calculate_metrics(y_true, y_pred)
        
        self.assertEqual(metrics["TP"], 2)
        self.assertEqual(metrics["TN"], 2)
        self.assertEqual(metrics["FP"], 0)
        self.assertEqual(metrics["FN"], 0)
        self.assertEqual(metrics["Precision"], 1.0)
        self.assertEqual(metrics["Recall"], 1.0)
        self.assertEqual(metrics["F1"], 1.0)

    def test_all_positive_predictions(self):
        y_true = [1, 0, 1, 0]
        y_pred = [1, 1, 1, 1]
        metrics = calculate_metrics(y_true, y_pred)
        
        self.assertEqual(metrics["TP"], 2)
        self.assertEqual(metrics["TN"], 0)
        self.assertEqual(metrics["FP"], 2)
        self.assertEqual(metrics["FN"], 0)
        self.assertEqual(metrics["Precision"], 0.5)
        self.assertEqual(metrics["Recall"], 1.0)
        # F1 = 2 * (0.5 * 1.0) / (1.5) = 1.0 / 1.5 = 2/3 = 0.666...
        self.assertAlmostEqual(metrics["F1"], 2.0 / 3.0)

    def test_mixed_case(self):
        y_true = [1, 1, 1, 0, 0, 0]
        y_pred = [1, 1, 0, 1, 0, 0]
        # TP = 2
        # FN = 1
        # FP = 1
        # TN = 2
        metrics = calculate_metrics(y_true, y_pred)
        
        self.assertEqual(metrics["TP"], 2)
        self.assertEqual(metrics["FN"], 1)
        self.assertEqual(metrics["FP"], 1)
        self.assertEqual(metrics["TN"], 2)
        
        # Precision = 2 / (2 + 1) = 2/3
        self.assertAlmostEqual(metrics["Precision"], 2.0 / 3.0)
        # Recall = 2 / (2 + 1) = 2/3
        self.assertAlmostEqual(metrics["Recall"], 2.0 / 3.0)
        # F1 = 2/3
        self.assertAlmostEqual(metrics["F1"], 2.0 / 3.0)

    def test_zero_division_safety(self):
        # Case 1: No positives predicted at all (TP=0, FP=0) -> Precision = 0.0
        y_true = [1, 1]
        y_pred = [0, 0]
        metrics1 = calculate_metrics(y_true, y_pred)
        self.assertEqual(metrics1["Precision"], 0.0)
        self.assertEqual(metrics1["Recall"], 0.0)
        self.assertEqual(metrics1["F1"], 0.0)
        
        # Case 2: No actual positives (TP=0, FN=0) -> Recall = 0.0
        y_true = [0, 0]
        y_pred = [1, 1]
        metrics2 = calculate_metrics(y_true, y_pred)
        self.assertEqual(metrics2["Recall"], 0.0)
        self.assertEqual(metrics2["Precision"], 0.0)
        self.assertEqual(metrics2["F1"], 0.0)

    def test_deterministic_repeated_results(self):
        y_true = [1, 0, 1, 0]
        y_pred = [1, 0, 1, 1]
        metrics1 = calculate_metrics(y_true, y_pred)
        metrics2 = calculate_metrics(y_true, y_pred)
        
        self.assertEqual(metrics1, metrics2)

if __name__ == '__main__':
    unittest.main()
