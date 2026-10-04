import unittest
import os
import sys
import tempfile
import json
from unittest.mock import patch

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from dashboard import app
from db import init_db
from canonicalize import DatabaseLoader, EntityCanonicalizer

class TestDashboardAPI(unittest.TestCase):
    def setUp(self):
        # Create a temporary database and patch DB_PATH
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp()
        init_db(self.temp_db_path)
        
        # Load some dummy data
        loader = DatabaseLoader(self.temp_db_path)
        canon = EntityCanonicalizer()
        loader.load_extraction({
            "service_name": "TestService",
            "clauses": [
                {
                    "text": "Location shared.",
                    "severity_score": 3.0,
                    "specificity_score": 2.0,
                    "entities": ["Location"]
                }
            ]
        }, canon)
        
        self.app = app.test_client()
        self.app.testing = True

        # Patch the DB_PATH in the dashboard module
        self.patcher = patch('dashboard.DB_PATH', self.temp_db_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        os.close(self.temp_db_fd)
        os.remove(self.temp_db_path)

    def test_get_portfolio(self):
        response = self.app.get('/api/portfolio')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn("portfolio_score", data)
        self.assertEqual(data["portfolio_score"], 5.0)
        self.assertEqual(len(data["services"]), 1)
        self.assertEqual(data["services"][0]["service_name"], "TestService")

    def test_marginal_risk(self):
        candidate = {
            "service_name": "NewService",
            "clauses": [
                {
                    "text": "Location and Email.",
                    "entities": ["Location", "Email"],
                    "severity_score": 2.0,
                    "specificity_score": 2.0,
                    "risk_category": "Test"
                }
            ]
        }
        
        response = self.app.post('/api/marginal-risk', json=candidate)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertEqual(data["baseline_portfolio_risk"], 5.0)
        self.assertEqual(data["candidate_service_risk"], 4.0)
        self.assertEqual(data["marginal_risk_delta"], 3.0)
        self.assertIn("Location", data["overlapping_entities"])
        self.assertIn("Email", data["newly_introduced_entities"])

    def test_marginal_risk_invalid_json(self):
        response = self.app.post('/api/marginal-risk', json={"bad": "data"})
        self.assertEqual(response.status_code, 400)

    def test_missing_db(self):
        with patch('dashboard.DB_PATH', '/does/not/exist.db'):
            res1 = self.app.get('/api/portfolio')
            self.assertEqual(res1.status_code, 404)
            
            res2 = self.app.post('/api/marginal-risk', json={"service_name": "S", "clauses": []})
            self.assertEqual(res2.status_code, 404)
            
            res3 = self.app.get('/api/overlap-graph')
            self.assertEqual(res3.status_code, 404)
            
            res4 = self.app.post('/api/compare-services', json={})
            self.assertEqual(res4.status_code, 404)

    def test_overlap_graph(self):
        response = self.app.get('/api/overlap-graph')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        nodes = data["nodes"]
        # Should contain TestService and Location nodes
        node_ids = [n["id"] for n in nodes]
        self.assertIn("TestService", node_ids)
        self.assertIn("Location", node_ids)
        
    def test_compare_services(self):
        payload = {
            "candidate_a": {
                "service_name": "NewA",
                "clauses": [
                    {"text": "t", "entities": ["Location"], "severity_score": 1.0, "specificity_score": 1.0}
                ]
            },
            "candidate_b": {
                "service_name": "NewB",
                "clauses": [
                    {"text": "t", "entities": ["Email"], "severity_score": 2.0, "specificity_score": 2.0}
                ]
            }
        }
        response = self.app.post('/api/compare-services', json=payload)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("candidate_a", data)
        self.assertIn("candidate_b", data)
        self.assertIn("Location", data["candidate_a"]["overlapping_entities"])
        self.assertIn("Email", data["candidate_b"]["newly_introduced_entities"])
        self.assertEqual(data["candidate_a"]["candidate_service_risk"], 2.0)
        self.assertEqual(data["candidate_b"]["candidate_service_risk"], 4.0)

    def test_compare_services_invalid_json(self):
        response = self.app.post('/api/compare-services', json={"bad": "data"})
        self.assertEqual(response.status_code, 400)

if __name__ == '__main__':
    unittest.main()
