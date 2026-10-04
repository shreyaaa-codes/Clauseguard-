import unittest
import os
import sys
import tempfile
import sqlite3

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from scoring import ScoringEngine
from marginal import MarginalRiskEngine
from db import init_db
from canonicalize import DatabaseLoader, EntityCanonicalizer

class TestScoringAndMarginalRisk(unittest.TestCase):
    
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp()
        init_db(self.temp_db_path)
        self.loader = DatabaseLoader(self.temp_db_path)
        self.canonicalizer = EntityCanonicalizer()
        
        self.scoring_engine = ScoringEngine(w1=1.0, w2=1.0)
        self.marginal_engine = MarginalRiskEngine(self.temp_db_path, w1=1.0, w2=1.0)

    def tearDown(self):
        os.close(self.temp_db_fd)
        os.remove(self.temp_db_path)

    def test_single_clause_score(self):
        score = self.scoring_engine.calculate_clause_score(3.0, 2.0)
        self.assertEqual(score, 5.0)

    def test_multiple_clauses_aggregation(self):
        clauses = [
            {'severity_score': 3.0, 'specificity_score': 2.0}, # score = 5.0
            {'severity_score': 4.0, 'specificity_score': 1.0}  # score = 5.0
        ]
        score = self.scoring_engine.calculate_service_score_from_clauses(clauses)
        self.assertEqual(score, 10.0)

    def test_empty_portfolio(self):
        data = self.scoring_engine.get_portfolio_data(self.temp_db_path)
        self.assertEqual(data["portfolio_score"], 0.0)
        self.assertEqual(len(data["services"]), 0)
        self.assertEqual(len(data["all_canonical_entities"]), 0)

    def test_overlap_and_new_entities(self):
        # 1. Setup existing portfolio
        existing_data = {
            "service_name": "Spotify",
            "clauses": [
                {
                    "text": "Location info.",
                    "entities": ["Location Data"],
                    "severity_score": 2.0,
                    "specificity_score": 1.0
                },
                {
                    "text": "IP address logged.",
                    "entities": ["IP"],
                    "severity_score": 1.0,
                    "specificity_score": 1.0
                }
            ]
        }
        self.loader.load_extraction(existing_data, self.canonicalizer)
        
        # 2. Candidate data
        candidate_data = {
            "service_name": "Google",
            "clauses": [
                {
                    "text": "Location tracked.",
                    "entities": ["User Location"], # Canonicalizes to "Location"
                    "severity_score": 3.0,
                    "specificity_score": 3.0
                },
                {
                    "text": "Email shared.",
                    "entities": ["Email Address"], # Canonicalizes to "Email"
                    "severity_score": 4.0,
                    "specificity_score": 2.0
                }
            ]
        }
        
        # 3. Calculate Marginal Risk
        result = self.marginal_engine.calculate_marginal_risk(candidate_data)
        
        self.assertIn("Location", result["overlapping_entities"])
        self.assertNotIn("Location", result["newly_introduced_entities"])
        
        self.assertIn("Email", result["newly_introduced_entities"])
        self.assertNotIn("Email", result["overlapping_entities"])
        
        # Baseline score: (2+1) + (1+1) = 5.0
        self.assertEqual(result["baseline_portfolio_risk"], 5.0)
        
        # Candidate score: (3+3) + (4+2) = 12.0
        self.assertEqual(result["candidate_service_risk"], 12.0)
        
        # Marginal Delta (sum assumption) = 12.0 - discounted to 9.0
        self.assertEqual(result["marginal_risk_delta"], 9.0)

    def test_no_database_mutation(self):
        # Ensure marginal risk doesn't save to DB
        candidate_data = {
            "service_name": "Google",
            "clauses": [{"text": "Email", "entities": ["Email"], "severity_score": 1, "specificity_score": 1}]
        }
        self.marginal_engine.calculate_marginal_risk(candidate_data)
        
        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM services")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 0)
        conn.close()

    def test_repeatability(self):
        candidate_data = {
            "service_name": "Google",
            "clauses": [{"text": "Email", "entities": ["Email"], "severity_score": 1, "specificity_score": 1}]
        }
        result1 = self.marginal_engine.calculate_marginal_risk(candidate_data)
        result2 = self.marginal_engine.calculate_marginal_risk(candidate_data)
        self.assertEqual(result1, result2)

if __name__ == '__main__':
    unittest.main()
