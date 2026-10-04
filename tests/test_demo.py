import unittest
import os
import sys

# Ensure project root is in path to import run_demo
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from run_demo import run_end_to_end_demo

class TestDemoRunner(unittest.TestCase):
    
    def test_demo_execution(self):
        # Unset API key to ensure mock mode
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
            
        # Get baseline modification time of the real database if it exists
        real_db_path = os.path.join('data', 'db', 'portfolio.db')
        mtime_before = None
        if os.path.exists(real_db_path):
            mtime_before = os.path.getmtime(real_db_path)
            
        # Run demo
        result = run_end_to_end_demo()
        
        # Verify structured result
        self.assertIsInstance(result, dict)
        self.assertEqual(result["existing_service"], "Spotify")
        self.assertEqual(result["candidate_service"], "Google")
        self.assertGreater(result["extracted_clause_count"], 0)
        self.assertIn("Location", result["canonical_entities"])
        self.assertIn("Location", result["overlapping_entities"])
        self.assertIn("Email", result["newly_introduced_entities"])
        
        # Ensure database was not modified
        if mtime_before is not None:
            mtime_after = os.path.getmtime(real_db_path)
            self.assertEqual(mtime_before, mtime_after)
        else:
            # If it didn't exist, it shouldn't have been created
            self.assertFalse(os.path.exists(real_db_path))

if __name__ == '__main__':
    unittest.main()
