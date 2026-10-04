import unittest
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from extract import extract_pipeline
from canonicalize import EntityCanonicalizer, DatabaseLoader
from dashboard import app
from db import init_db
from marginal import MarginalRiskEngine

class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_extract_pipeline_empty_and_whitespace(self):
        # Should handle empty gracefully
        res1 = extract_pipeline("", "TestService")
        self.assertEqual(res1["mode"], "EMPTY")
        self.assertEqual(len(res1["clauses"]), 0)

        # Should handle whitespace gracefully
        res2 = extract_pipeline("   \n \t  ", "TestService")
        self.assertEqual(res2["mode"], "EMPTY")
        self.assertEqual(len(res2["clauses"]), 0)
        
    def test_extract_pipeline_very_long_text(self):
        # Long text but without periods (one long chunk)
        long_chunk = "word " * 20000
        res = extract_pipeline(long_chunk, "TestService")
        # The split('.') might result in one giant string.
        # It shouldn't crash.
        self.assertIn("mode", res)
        
    def test_canonicalize_empty(self):
        c = EntityCanonicalizer()
        self.assertIsNone(c.canonicalize(""))
        self.assertIsNone(c.canonicalize("   "))
        
    def test_prefilter_fallback(self):
        from extraction.prefilter import PrivacyPrefilter
        pf = PrivacyPrefilter()
        # If clauses are empty
        self.assertEqual(pf.filter_candidates([]), [])
        
        # If input has no privacy vocabulary
        res = pf.filter_candidates(["The sky is blue.", "Hello world."])
        self.assertIsInstance(res, list)
        
    def test_dashboard_api_edge_cases(self):
        # missing fields
        r1 = self.app.post('/api/analyze-policy', json={"url": "test"})
        self.assertEqual(r1.status_code, 400)
        
        # non-existent service comparator
        r2 = self.app.post('/api/compare-services', json={"candidate_a": "Doesnotexist", "candidate_b": "Neither"})
        self.assertEqual(r2.status_code, 404)

        # overlap-graph without db (mocking a bad DB path)
        with patch('dashboard.DB_PATH', '/invalid/path.db'):
            r3 = self.app.get('/api/overlap-graph')
            self.assertEqual(r3.status_code, 404)

    def test_data_consistency_integration(self):
        # Full data consistency cycle as requested in Phase 5
        fd, path = tempfile.mkstemp()
        init_db(path)
        
        with patch('dashboard.DB_PATH', path):
            loader = DatabaseLoader(path)
            canon = EntityCanonicalizer()
            
            # 1. Insert Service A
            service_a = {
                "service_name": "Service A",
                "clauses": [
                    {
                        "text": "A clause", 
                        "entities": ["Location", "IP Address", "Email Address"],
                        "severity_score": 1.0,
                        "specificity_score": 1.0,
                        "risk_category": "Test"
                    }
                ]
            }
            loader.load_extraction(service_a, canon)
            
            # 2. Insert Service B
            service_b = {
                "service_name": "Service B",
                "clauses": [
                    {
                        "text": "B clause", 
                        "entities": ["IP Address", "Device Information"],
                        "severity_score": 2.0,
                        "specificity_score": 2.0,
                        "risk_category": "Test"
                    }
                ]
            }
            loader.load_extraction(service_b, canon)
            
            # 3. Verify Portfolio contains A and B
            port_resp = self.app.get('/api/portfolio')
            port_data = port_resp.get_json()
            services = port_data["services"]
            self.assertEqual(len(services), 2)
            s_names = [s["service_name"] for s in services]
            self.assertIn("Service A", s_names)
            self.assertIn("Service B", s_names)
            
            # 4. Verify Overlap logic using Comparator
            comp_resp = self.app.post('/api/compare-services', json={"candidate_a": "Service A", "candidate_b": "Service B"})
            comp_data = comp_resp.get_json()
            
            # Evaluating B vs A
            res_b = comp_data["candidate_b"]
            
            # Overlap: IP Address
            self.assertIn("IP Address", res_b["overlapping_entities"])
            self.assertNotIn("Location", res_b["overlapping_entities"])
            self.assertNotIn("Email Address", res_b["overlapping_entities"])
            
            # B-only: Device Information
            self.assertIn("Device Information", res_b["newly_introduced_entities"])
            self.assertNotIn("Location", res_b["newly_introduced_entities"])
            
            # 5. Marginal Risk
            # Candidate B Risk: 4.0 (one clause 2+2)
            # Overlap: 1 out of 2 (IP Address overlaps, Device Info doesn't)
            # Ratio = 0.5. Discount = 0.5 * 0.5 = 0.25.
            # Marginal risk = 4.0 * (1 - 0.25) = 3.0
            self.assertEqual(res_b["candidate_service_risk"], 4.0)
            self.assertEqual(res_b["marginal_risk_delta"], 3.0)
            
        os.close(fd)
        os.remove(path)
        
    def test_empty_portfolio_behavior(self):
        # The dashboard should not crash when the portfolio is empty
        fd, path = tempfile.mkstemp()
        init_db(path)
        
        with patch('dashboard.DB_PATH', path):
            # Portfolio
            p_resp = self.app.get('/api/portfolio')
            self.assertEqual(p_resp.status_code, 200)
            p_data = p_resp.get_json()
            self.assertEqual(len(p_data["services"]), 0)
            self.assertEqual(p_data["portfolio_score"], 0.0)
            
            # Overlap graph
            g_resp = self.app.get('/api/overlap-graph')
            self.assertEqual(g_resp.status_code, 200)
            g_data = g_resp.get_json()
            self.assertEqual(len(g_data["nodes"]), 0)
            self.assertEqual(len(g_data["edges"]), 0)
            
        os.close(fd)
        os.remove(path)

if __name__ == '__main__':
    unittest.main()
