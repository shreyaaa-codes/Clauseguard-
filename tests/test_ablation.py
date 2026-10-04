import unittest
import os
import sys
import json

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from evaluation.ablation import run_ablation_experiment

class TestAblationStudy(unittest.TestCase):
    
    def test_ablation_experiment_execution(self):
        # Force mock mode
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
            
        result = run_ablation_experiment()
        
        self.assertIn("dataset_version", result)
        self.assertIn("dataset_size", result)
        self.assertEqual(result["dataset_size"], 14)
        self.assertEqual(result["evaluation_mode"], "MOCK/DEV")
        
        # Check naive
        naive = result["approaches"]["Naive"]
        self.assertEqual(naive["TP"], 7)
        self.assertEqual(naive["FP"], 7)
        self.assertEqual(naive["FN"], 0)
        self.assertEqual(naive["TN"], 0)
        self.assertEqual(naive["Precision"], 0.5)
        self.assertEqual(naive["Recall"], 1.0)
        
        # Check prefilter metrics exist
        prefilter = result["approaches"]["Prefilter"]
        self.assertIn("Precision", prefilter)
        self.assertIn("Recall", prefilter)
        self.assertIn("F1", prefilter)
        
        # Check composite deferral
        self.assertEqual(result["approaches"]["Composite"]["metrics"], "N/A")
        self.assertIn("deferred", result["approaches"]["Composite"]["limitations"].lower())
        
        # Check output file was created
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        out_path = os.path.join(base_dir, 'data', 'evaluation', 'ablation_results.json')
        self.assertTrue(os.path.exists(out_path))

if __name__ == '__main__':
    unittest.main()
