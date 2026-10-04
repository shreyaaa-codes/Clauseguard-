import unittest
import os
import sys
import tempfile
import sqlite3

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from scoring import ScoringEngine
from marginal import MarginalRiskEngine
from db import init_db
from canonicalize import DatabaseLoader, EntityCanonicalizer

class TestScoringInvariants(unittest.TestCase):
    
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp()
        init_db(self.temp_db_path)
        self.loader = DatabaseLoader(self.temp_db_path)
        self.canonicalizer = EntityCanonicalizer()

    def tearDown(self):
        os.close(self.temp_db_fd)
        os.remove(self.temp_db_path)

    def test_single_clause(self):
        engine = ScoringEngine(w1=1.0, w2=1.0)
        score = engine.calculate_clause_score(3.0, 2.0)
        self.assertEqual(score, 5.0)

    def test_multiple_clauses(self):
        engine = ScoringEngine(w1=1.0, w2=1.0)
        clauses = [
            {'severity_score': 3.0, 'specificity_score': 2.0},
            {'severity_score': 4.0, 'specificity_score': 1.0}
        ]
        score = engine.calculate_service_score_from_clauses(clauses)
        self.assertEqual(score, 10.0)

    def test_multiple_services(self):
        # Load two services
        self.loader.load_extraction({
            "service_name": "ServiceA",
            "clauses": [{"text": "text", "severity_score": 1.0, "specificity_score": 1.0}]
        }, self.canonicalizer)
        
        self.loader.load_extraction({
            "service_name": "ServiceB",
            "clauses": [{"text": "text", "severity_score": 2.0, "specificity_score": 2.0}]
        }, self.canonicalizer)
        
        engine = ScoringEngine(w1=1.0, w2=1.0)
        data = engine.get_portfolio_data(self.temp_db_path)
        # Service A: 2.0. Service B: 4.0. Total: 6.0
        self.assertEqual(data["portfolio_score"], 6.0)

    def test_empty_portfolio(self):
        engine = ScoringEngine(w1=1.0, w2=1.0)
        data = engine.get_portfolio_data(self.temp_db_path)
        self.assertEqual(data["portfolio_score"], 0.0)

    def test_weight_parameter_behavior(self):
        engine_default = ScoringEngine(w1=1.0, w2=1.0)
        engine_tuned = ScoringEngine(w1=2.0, w2=0.5)
        
        # default = 3.0 + 2.0 = 5.0
        score_default = engine_default.calculate_clause_score(3.0, 2.0)
        # tuned = 2.0*3.0 + 0.5*2.0 = 6.0 + 1.0 = 7.0
        score_tuned = engine_tuned.calculate_clause_score(3.0, 2.0)
        
        self.assertEqual(score_default, 5.0)
        self.assertEqual(score_tuned, 7.0)

    def test_repeatability(self):
        engine = ScoringEngine(w1=1.0, w2=1.0)
        score1 = engine.calculate_clause_score(4.0, 4.0)
        score2 = engine.calculate_clause_score(4.0, 4.0)
        self.assertEqual(score1, score2)

    def test_empty_portfolio_plus_candidate(self):
        marginal_engine = MarginalRiskEngine(self.temp_db_path, w1=1.0, w2=1.0)
        candidate = {
            "service_name": "Candidate",
            "clauses": [{"text": "text", "entities": ["Location"], "severity_score": 3.0, "specificity_score": 3.0}]
        }
        res = marginal_engine.calculate_marginal_risk(candidate)
        self.assertEqual(res["baseline_portfolio_risk"], 0.0)
        self.assertEqual(res["candidate_service_risk"], 6.0)
        self.assertEqual(res["marginal_risk_delta"], 6.0)

    def test_existing_portfolio_plus_candidate(self):
        # Load existing service
        self.loader.load_extraction({
            "service_name": "Existing",
            "clauses": [{"text": "text", "entities": ["Email"], "severity_score": 1.0, "specificity_score": 1.0}]
        }, self.canonicalizer)
        
        marginal_engine = MarginalRiskEngine(self.temp_db_path, w1=1.0, w2=1.0)
        candidate = {
            "service_name": "Candidate",
            "clauses": [{"text": "text", "entities": ["Email"], "severity_score": 3.0, "specificity_score": 3.0}]
        }
        res = marginal_engine.calculate_marginal_risk(candidate)
        
        # Baseline = 2.0. Candidate = 6.0. Delta = 6.0 (because of additive formula, overlap does not discount yet)
        self.assertEqual(res["baseline_portfolio_risk"], 2.0)
        self.assertEqual(res["candidate_service_risk"], 6.0)
        self.assertEqual(res["marginal_risk_delta"], 3.0)

    def test_overlap_and_new_entity(self):
        self.loader.load_extraction({
            "service_name": "Existing",
            "clauses": [{"text": "text", "entities": ["Location Data"], "severity_score": 1.0, "specificity_score": 1.0}]
        }, self.canonicalizer)
        
        marginal_engine = MarginalRiskEngine(self.temp_db_path, w1=1.0, w2=1.0)
        candidate = {
            "service_name": "Candidate",
            "clauses": [{"text": "text", "entities": ["Location Data", "Email Address"], "severity_score": 1.0, "specificity_score": 1.0}]
        }
        res = marginal_engine.calculate_marginal_risk(candidate)
        
        self.assertIn("Location", res["overlapping_entities"])
        self.assertNotIn("Location", res["newly_introduced_entities"])
        
        self.assertIn("Email", res["newly_introduced_entities"])
        self.assertNotIn("Email", res["overlapping_entities"])

    def test_no_db_mutation(self):
        marginal_engine = MarginalRiskEngine(self.temp_db_path, w1=1.0, w2=1.0)
        candidate = {
            "service_name": "Candidate",
            "clauses": [{"text": "text", "entities": ["Location"], "severity_score": 1.0, "specificity_score": 1.0}]
        }
        marginal_engine.calculate_marginal_risk(candidate)
        
        conn = sqlite3.connect(self.temp_db_path)
        count = conn.execute("SELECT COUNT(*) FROM services").fetchone()[0]
        self.assertEqual(count, 0)
        conn.close()

if __name__ == '__main__':
    unittest.main()
