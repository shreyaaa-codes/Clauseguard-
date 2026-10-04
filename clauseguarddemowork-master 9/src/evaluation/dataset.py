import json
import os
import sys

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from extraction.prefilter import PrivacyPrefilter

class DatasetValidator:
    def __init__(self, ground_truth_path):
        self.ground_truth_path = ground_truth_path

    def load_dataset(self):
        with open(self.ground_truth_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def validate_schema(self, data):
        if "examples" not in data:
            raise ValueError("Missing 'examples' array in dataset.")
            
        examples = data["examples"]
        if len(examples) == 0:
            raise ValueError("Dataset is empty.")
            
        pos_count = 0
        neg_count = 0
        
        for i, ex in enumerate(examples):
            if "id" not in ex: raise ValueError(f"Missing 'id' at index {i}")
            if "text" not in ex: raise ValueError(f"Missing 'text' at index {i}")
            if "label" not in ex: raise ValueError(f"Missing 'label' at index {i}")
            if "source" not in ex: raise ValueError(f"Missing 'source' at index {i}")
            
            if ex["label"] == 1:
                pos_count += 1
            elif ex["label"] == 0:
                neg_count += 1
            else:
                raise ValueError(f"Invalid label {ex['label']} at index {i}")
                
        if pos_count == 0 or neg_count == 0:
            raise ValueError("Dataset must contain both positive and negative examples.")
            
        return {
            "total": len(examples),
            "positive": pos_count,
            "negative": neg_count
        }

    def check_leakage(self, data):
        """
        Ensures none of the evaluation texts exist in the prefilter's training fixture.
        """
        # We temporarily grab the dummy texts by patching or extracting them
        # Since train_with_minimal_fixture is hardcoded, we will just read them
        # by initializing a prefilter, training it, and grabbing its vectorizer's feature names? No,
        # we can just inspect the class source or recreate the array for the check.
        # Let's extract the array used in train_with_minimal_fixture.
        
        training_texts = [
            "We share your location data with marketing partners.",
            "You can opt out of data sharing in your account settings.",
            "We collect cookies to improve site performance.",
            "Click here to reset your password.",
            "The app requires an internet connection to stream music.",
            "Welcome to the user manual.",
            "Your IP address is logged for security purposes.",
            "Contact customer support if the app crashes."
        ]
        
        training_set = set(t.lower().strip() for t in training_texts)
        
        for ex in data["examples"]:
            text_norm = ex["text"].lower().strip()
            if text_norm in training_set:
                raise RuntimeError(f"DATA LEAKAGE DETECTED: Evaluation sentence '{ex['text']}' exists in training set.")
                
        return True

    def validate_all(self):
        data = self.load_dataset()
        stats = self.validate_schema(data)
        self.check_leakage(data)
        return stats

if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    gt_path = os.path.join(base_dir, 'data', 'evaluation', 'ground_truth.json')
    validator = DatasetValidator(gt_path)
    try:
        stats = validator.validate_all()
        print("Dataset is valid and leakage-free.")
        print(f"Stats: {stats}")
    except Exception as e:
        print(f"Validation failed: {e}")
        sys.exit(1)
