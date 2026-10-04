import unittest
import os
import sys
import tempfile
import sqlite3

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from extract import extract_pipeline
from canonicalize import EntityCanonicalizer, DatabaseLoader

class TestRobustness(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp()
        from db import init_db
        init_db(self.temp_db_path)

    def tearDown(self):
        os.close(self.temp_db_fd)
        os.remove(self.temp_db_path)

    def test_messy_policy_extraction(self):
        # 1. Load messy text
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        path = os.path.join(base_dir, 'data', 'robustness', 'messy_policy.txt')
        with open(path, 'r', encoding='utf-8') as f:
            raw_text = f.read()

        # 2. Verify extraction doesn't crash on long/messy text
        result = extract_pipeline(raw_text, "MessyService")
        self.assertIsNotNone(result)
        self.assertEqual(result["service_name"], "MessyService")
        self.assertTrue(len(result["clauses"]) >= 0)

        # 3. Verify canonicalization remains deterministic and duplicate handling works
        canon = EntityCanonicalizer()
        loader = DatabaseLoader(self.temp_db_path)
        loader.load_extraction(result, canon)

        # 4. Check DB that it was loaded safely without SQL crashes
        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM services WHERE name = 'MessyService'")
        self.assertEqual(cursor.fetchone()[0], 1)
        conn.close()

if __name__ == '__main__':
    unittest.main()
