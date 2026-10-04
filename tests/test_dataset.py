import unittest
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from evaluation.dataset import DatasetValidator

class TestDatasetValidator(unittest.TestCase):
    
    def setUp(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.gt_path = os.path.join(base_dir, 'data', 'evaluation', 'ground_truth.json')
        self.validator = DatasetValidator(self.gt_path)

    def test_real_dataset_is_valid(self):
        # This will fail if the real dataset has leakage or bad schema
        stats = self.validator.validate_all()
        self.assertEqual(stats["total"], 14)
        self.assertGreater(stats["positive"], 0)
        self.assertGreater(stats["negative"], 0)

    def test_leakage_detection(self):
        # Create a mock dataset that overlaps with training data
        leaky_data = {
            "examples": [
                {
                    "id": "leak_001",
                    "text": "Click here to reset your password.", # This is in training set
                    "label": 0,
                    "source": "test"
                }
            ]
        }
        with self.assertRaises(RuntimeError) as context:
            self.validator.check_leakage(leaky_data)
        self.assertIn("DATA LEAKAGE DETECTED", str(context.exception))
        
    def test_schema_validation_failures(self):
        bad_data_1 = {"version": "1.0"} # Missing examples
        with self.assertRaises(ValueError):
            self.validator.validate_schema(bad_data_1)
            
        bad_data_2 = {"examples": []} # Empty examples
        with self.assertRaises(ValueError):
            self.validator.validate_schema(bad_data_2)
            
        bad_data_3 = {"examples": [{"id": "1", "text": "t", "label": 1, "source": "s"}]} # Missing negative class
        with self.assertRaises(ValueError):
            self.validator.validate_schema(bad_data_3)

if __name__ == '__main__':
    unittest.main()
