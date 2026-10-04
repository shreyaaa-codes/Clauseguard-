import unittest
import os
import sys
import json
import sqlite3
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from dashboard import app
from db import init_db

class TestComparator(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        
        self.fd, self.db_path = tempfile.mkstemp()
        init_db(self.db_path)
        
        # Populate with Service A and Service B
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        c = conn.cursor()
        
        # Service A
        c.execute("INSERT INTO services (name, category) VALUES (?, ?)", ("Service A", "General"))
        sa_id = c.lastrowid
        c.execute("INSERT INTO canonical_entities (name) VALUES (?)", ("Location",))
        loc_id = c.lastrowid
        c.execute("INSERT INTO canonical_entities (name) VALUES (?)", ("IP Address",))
        ip_id = c.lastrowid
        
        c.execute("INSERT INTO clauses (service_id, text, severity_score, specificity_score, risk_category) VALUES (?, ?, ?, ?, ?)", (sa_id, "Clause A1", 3.0, 2.0, "Cat"))
        c_a_id = c.lastrowid
        c.execute("INSERT INTO clause_entity_mapping (clause_id, entity_id) VALUES (?, ?)", (c_a_id, loc_id))
        c.execute("INSERT INTO clause_entity_mapping (clause_id, entity_id) VALUES (?, ?)", (c_a_id, ip_id))
        
        # Service B
        c.execute("INSERT INTO services (name, category) VALUES (?, ?)", ("Service B", "General"))
        sb_id = c.lastrowid
        c.execute("INSERT INTO canonical_entities (name) VALUES (?)", ("Email",))
        email_id = c.lastrowid
        
        c.execute("INSERT INTO clauses (service_id, text, severity_score, specificity_score, risk_category) VALUES (?, ?, ?, ?, ?)", (sb_id, "Clause B1", 4.0, 1.0, "Cat"))
        c_b_id = c.lastrowid
        c.execute("INSERT INTO clause_entity_mapping (clause_id, entity_id) VALUES (?, ?)", (c_b_id, ip_id))
        c.execute("INSERT INTO clause_entity_mapping (clause_id, entity_id) VALUES (?, ?)", (c_b_id, email_id))
        
        conn.commit()
        conn.close()

    def tearDown(self):
        os.close(self.fd)
        os.remove(self.db_path)

    def test_compare_real_services(self):
        with patch('dashboard.DB_PATH', self.db_path):
            payload = {
                "candidate_a": "Service B",
                "candidate_b": "Service A"
            }
            response = self.app.post('/api/compare-services', json=payload)
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            ca = data["candidate_a"]
            self.assertEqual(ca["candidate_name"], "Service B")
            
            self.assertIn("IP Address", ca["overlapping_entities"])
            self.assertNotIn("Email", ca["overlapping_entities"])
            self.assertIn("Email", ca["newly_introduced_entities"])

    def test_compare_nonexistent_service(self):
        with patch('dashboard.DB_PATH', self.db_path):
            payload = {
                "candidate_a": "Service X",
                "candidate_b": "Service A"
            }
            response = self.app.post('/api/compare-services', json=payload)
            self.assertEqual(response.status_code, 404)
            data = json.loads(response.data)
            self.assertIn("Service not found", data["error"])

if __name__ == '__main__':
    unittest.main()
