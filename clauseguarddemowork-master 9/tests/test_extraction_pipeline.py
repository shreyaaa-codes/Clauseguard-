import unittest
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from extraction.llm_extractor import LLMExtractor
from canonicalize import EntityCanonicalizer

class TestExtractionPipeline(unittest.TestCase):
    def setUp(self):
        self.extractor = LLMExtractor("TestService")
        self.canonicalizer = EntityCanonicalizer()

    def test_mock_mode_entity_extraction_positive(self):
        # Realistic policy sentences
        clauses = [
            "We collect your IP address when you use our service.",
            "Your geolocation may be shared with advertisers.",
            "Please enter a valid email address.",
            "We store a unique identifier on your device.",
            "Cookies are used to track page views."
        ]
        res = self.extractor._call_mock_llm(clauses)
        self.assertEqual(res["mode"], "MOCK/DEV")
        
        entities_list = [c["entities"] for c in res["clauses"]]
        self.assertIn("IP Address", entities_list[0])
        self.assertIn("Location", entities_list[1])
        self.assertIn("Email Address", entities_list[2])
        self.assertIn("Identifiers", entities_list[3])
        self.assertIn("Device Information", entities_list[3])
        self.assertIn("Cookies", entities_list[4])
        self.assertIn("Usage Data", entities_list[4])

    def test_mock_mode_entity_extraction_negative(self):
        # Negative cases where entities should not be triggered incorrectly by partial matches
        clauses = [
            "Our offices are located in several countries.", # 'located' != location
            "We skip the introduction.", # 'skip' contains 'ip' but shouldn't match whole word IP
            "Send us a mail via post.", # 'mail' != email
            "Your identity remains a secret." # 'identity' != identifier
        ]
        res = self.extractor._call_mock_llm(clauses)
        entities_list = [c["entities"] for c in res["clauses"]]
        
        self.assertNotIn("Location", entities_list[0])
        self.assertNotIn("IP Address", entities_list[1])
        self.assertNotIn("Email Address", entities_list[2])
        self.assertNotIn("Identifiers", entities_list[3])

    def test_canonicalization_variants(self):
        self.assertEqual(self.canonicalizer.canonicalize("IP Addresses"), "IP Address")
        self.assertEqual(self.canonicalizer.canonicalize("GPS Location"), "Location")
        self.assertEqual(self.canonicalizer.canonicalize("exact location"), "Precise Location")
        self.assertEqual(self.canonicalizer.canonicalize("web beacon"), "Cookies")
        self.assertEqual(self.canonicalizer.canonicalize("mac address"), "Device Information")
        
    def test_unknown_entity_handling(self):
        # Should not blindly title case, should prefix with Unknown:
        self.assertEqual(self.canonicalizer.canonicalize("some random new tech"), "Unknown: some random new tech")

    def test_empty_input_handling(self):
        res = self.extractor.extract([])
        self.assertEqual(res["mode"], "EMPTY")
        self.assertEqual(len(res["clauses"]), 0)

    @patch('urllib.request.urlopen')
    def test_real_llm_mode_success(self, mock_urlopen):
        import io
        import json
        
        mock_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({"clauses": [{"text": "Hello", "entities": ["Location"], "severity_score": 1, "specificity_score": 1, "risk_category": "Test"}]})
                    }]
                }
            }]
        }
        mock_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(mock_response).encode('utf-8')
        
        self.extractor.api_key = "test_key"
        res = self.extractor.extract(["Hello"])
        
        self.assertTrue(res["mode"].startswith("GEMINI"))
        self.assertEqual(len(res["clauses"]), 1)

    @patch('urllib.request.urlopen')
    def test_real_llm_mode_failure(self, mock_urlopen):
        # If API fails, it should raise RuntimeError, not silently return mock
        mock_urlopen.side_effect = Exception("API Down")
        self.extractor.api_key = "test_key"
        
        with self.assertRaises(RuntimeError):
            self.extractor.extract(["Hello"])

if __name__ == '__main__':
    unittest.main()
