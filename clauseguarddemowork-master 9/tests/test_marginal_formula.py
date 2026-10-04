import unittest
import os
import sys
import sqlite3
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from marginal import MarginalRiskEngine
from db import init_db

class TestMarginalFormula(unittest.TestCase):
    def setUp(self):
        self.fd, self.db_path = tempfile.mkstemp()
        init_db(self.db_path)
        
        # Populate with Service A (Location, IP Address)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
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
        
        # Add another service (Service X) for multi-service test
        c.execute("INSERT INTO services (name, category) VALUES (?, ?)", ("Service X", "General"))
        sx_id = c.lastrowid
        c.execute("INSERT INTO canonical_entities (name) VALUES (?)", ("Camera",))
        cam_id = c.lastrowid
        c.execute("INSERT INTO clauses (service_id, text, severity_score, specificity_score) VALUES (?, ?, ?, ?)", (sx_id, "Clause X", 2.0, 2.0))
        c_x_id = c.lastrowid
        c.execute("INSERT INTO clause_entity_mapping (clause_id, entity_id) VALUES (?, ?)", (c_x_id, cam_id))
        
        conn.commit()
        conn.close()

        self.engine = MarginalRiskEngine(self.db_path)

    def tearDown(self):
        os.close(self.fd)
        os.remove(self.db_path)

    def test_no_overlap(self):
        candidate = {
            "service_name": "New Service",
            "clauses": [
                {
                    "severity_score": 4.0,
                    "specificity_score": 1.0, # Clause risk = 5.0
                    "entities": ["Microphone"] # Completely new
                }
            ]
        }
        res = self.engine.calculate_marginal_risk(candidate)
        self.assertEqual(res["candidate_service_risk"], 5.0)
        self.assertEqual(res["marginal_risk_delta"], 5.0)
        self.assertEqual(len(res["overlapping_entities"]), 0)

    def test_partial_overlap(self):
        candidate = {
            "service_name": "New Service",
            "clauses": [
                {
                    "severity_score": 4.0,
                    "specificity_score": 1.0, # Clause risk = 5.0
                    "entities": ["IP Address", "Microphone"] # IP is overlap (1/2) -> discount = 0.5 * 0.5 = 0.25. delta = 5.0 * 0.75 = 3.75
                }
            ]
        }
        res = self.engine.calculate_marginal_risk(candidate)
        self.assertEqual(res["candidate_service_risk"], 5.0)
        self.assertEqual(res["marginal_risk_delta"], 3.75)
        self.assertEqual(len(res["overlapping_entities"]), 1)

    def test_full_overlap(self):
        candidate = {
            "service_name": "New Service",
            "clauses": [
                {
                    "severity_score": 4.0,
                    "specificity_score": 1.0, # Clause risk = 5.0
                    "entities": ["IP Address"] # Full overlap -> discount = 0.5 * 1.0 = 0.5. delta = 2.5
                }
            ]
        }
        res = self.engine.calculate_marginal_risk(candidate)
        self.assertEqual(res["candidate_service_risk"], 5.0)
        self.assertEqual(res["marginal_risk_delta"], 2.5)
        self.assertEqual(len(res["overlapping_entities"]), 1)

    def test_same_entity_different_clause_risk(self):
        # Service B has higher risk clause for same entity
        candidate_high = {
            "service_name": "High Risk",
            "clauses": [{"severity_score": 5.0, "specificity_score": 5.0, "entities": ["IP Address"]}] # risk 10.0
        }
        candidate_low = {
            "service_name": "Low Risk",
            "clauses": [{"severity_score": 1.0, "specificity_score": 1.0, "entities": ["IP Address"]}] # risk 2.0
        }
        res_h = self.engine.calculate_marginal_risk(candidate_high)
        res_l = self.engine.calculate_marginal_risk(candidate_low)
        
        self.assertEqual(res_h["candidate_service_risk"], 10.0)
        self.assertEqual(res_h["marginal_risk_delta"], 5.0)
        
        self.assertEqual(res_l["candidate_service_risk"], 2.0)
        self.assertEqual(res_l["marginal_risk_delta"], 1.0)
        
        # Preserves meaningful differences!
        self.assertGreater(res_h["marginal_risk_delta"], res_l["marginal_risk_delta"])

    def test_zero_entities(self):
        candidate = {
            "service_name": "Empty Entities",
            "clauses": [{"severity_score": 2.0, "specificity_score": 2.0, "entities": []}] # risk 4.0
        }
        res = self.engine.calculate_marginal_risk(candidate)
        self.assertEqual(res["candidate_service_risk"], 4.0)
        self.assertEqual(res["marginal_risk_delta"], 4.0)

    def test_multiple_candidate_entities(self):
        candidate = {
            "service_name": "Multi Entities",
            "clauses": [
                {"severity_score": 2.0, "specificity_score": 2.0, "entities": ["Location", "IP Address"]}, # 100% overlap, 4.0 -> 2.0
                {"severity_score": 2.0, "specificity_score": 2.0, "entities": ["New1", "New2"]} # 0% overlap, 4.0 -> 4.0
            ]
        }
        res = self.engine.calculate_marginal_risk(candidate)
        self.assertEqual(res["candidate_service_risk"], 8.0)
        self.assertEqual(res["marginal_risk_delta"], 6.0)

    def test_never_negative(self):
        candidate = {
            "service_name": "Neg Check",
            "clauses": [{"severity_score": 1.0, "specificity_score": 1.0, "entities": ["IP Address"]}] # 100% overlap
        }
        res = self.engine.calculate_marginal_risk(candidate)
        self.assertTrue(res["marginal_risk_delta"] >= 0)

    def test_does_not_exceed_standalone(self):
        candidate = {
            "service_name": "Exceed Check",
            "clauses": [{"severity_score": 2.0, "specificity_score": 2.0, "entities": ["New1", "New2"]}]
        }
        res = self.engine.calculate_marginal_risk(candidate)
        self.assertTrue(res["marginal_risk_delta"] <= res["candidate_service_risk"])

    def test_candidate_excluded_from_baseline(self):
        # Service A is already in the database
        candidate = {
            "service_name": "Service A",
            "clauses": [{"severity_score": 3.0, "specificity_score": 2.0, "entities": ["Location", "IP Address"]}]
        }
        res = self.engine.calculate_marginal_risk(candidate)
        
        # Because Service A is excluded, its entities (Location, IP) are no longer in the baseline! 
        # (Wait, if Service A is the ONLY one with Location/IP, then they are new. But Service X has Camera. So Location/IP are new!)
        self.assertEqual(res["marginal_risk_delta"], 5.0)
        self.assertEqual(len(res["overlapping_entities"]), 0)

if __name__ == '__main__':
    unittest.main()
