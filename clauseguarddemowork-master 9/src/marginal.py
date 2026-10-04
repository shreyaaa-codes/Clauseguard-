from scoring import ScoringEngine
from canonicalize import EntityCanonicalizer

class MarginalRiskEngine:
    def __init__(self, db_path, w1=1.0, w2=1.0):
        self.db_path = db_path
        self.scoring_engine = ScoringEngine(w1, w2)
        self.canonicalizer = EntityCanonicalizer()

    def calculate_marginal_risk(self, candidate_json):
        """
        Determines the additional risk introduced by adding a candidate service.
        Performs an in-memory/structured calculation without mutating the real database.
        """
        candidate_name = candidate_json.get("service_name", "Unknown Candidate")

        # 1. Get baseline portfolio (excluding candidate if it already exists in DB)
        portfolio_data = self.scoring_engine.get_portfolio_data(self.db_path, exclude_service_name=candidate_name)
        baseline_score = portfolio_data["portfolio_score"]
        existing_entities = set(portfolio_data["all_canonical_entities"])
        
        # 2. Analyze candidate service
        candidate_clauses = candidate_json.get("clauses", [])
        
        # Calculate candidate score
        candidate_score = self.scoring_engine.calculate_service_score_from_clauses(candidate_clauses)
        
        # Determine candidate entities (canonicalized)
        candidate_entities = set()
        for clause in candidate_clauses:
            for raw_entity in clause.get("entities", []):
                canon_entity = self.canonicalizer.canonicalize(raw_entity)
                candidate_entities.add(canon_entity)
                
        # 3. Calculate Overlap and New Entities
        overlapping_entities = candidate_entities.intersection(existing_entities)
        new_entities = candidate_entities.difference(existing_entities)
        
        # 4. Calculate Marginal Risk
        # The model distinguishes between new privacy risk and overlapping risk at the clause level.
        # W_overlap = 0.5: An overlap discount weight. Even if data is already collected by the portfolio,
        # providing it to a NEW service increases the attack surface (breach risk, secondary sharing).
        # Therefore, fully overlapping entities reduce a clause's risk by 50%, not 100%.
        
        W_overlap = 0.5
        marginal_risk_delta = 0.0
        
        for clause in candidate_clauses:
            clause_score = self.scoring_engine.calculate_clause_score(
                clause.get('severity_score'), 
                clause.get('specificity_score')
            )
            
            clause_canon_entities = set()
            for raw_entity in clause.get("entities", []):
                clause_canon_entities.add(self.canonicalizer.canonicalize(raw_entity))
                
            num_entities = len(clause_canon_entities)
            if num_entities == 0:
                # If a clause has no extracted entities, it represents fully new unmapped risk
                marginal_risk_delta += clause_score
            else:
                num_overlapping = len(clause_canon_entities.intersection(existing_entities))
                overlap_ratio = num_overlapping / num_entities
                discount = W_overlap * overlap_ratio
                marginal_risk_delta += clause_score * (1.0 - discount)

        new_portfolio_score = baseline_score + marginal_risk_delta
        
        explanation = (
            f"Candidate standalone risk is {candidate_score:.1f}. "
            f"Found {len(overlapping_entities)} overlapping and {len(new_entities)} new entities. "
            f"Marginal risk is calculated at {marginal_risk_delta:.1f} after applying a maximum 50% discount to clauses with overlapping data."
        )
        
        return {
            "candidate_name": candidate_name,
            "baseline_portfolio_risk": baseline_score,
            "candidate_service_risk": candidate_score,
            "new_portfolio_risk": new_portfolio_score,
            "marginal_risk_delta": marginal_risk_delta,
            "overlapping_entities": list(overlapping_entities),
            "newly_introduced_entities": list(new_entities),
            "marginal_risk_explanation": explanation
        }

if __name__ == "__main__":
    import json
    import sys
    import os
    
    if len(sys.argv) < 2:
        print("Usage: python marginal.py <path_to_candidate.json>")
        sys.exit(1)
        
    candidate_path = sys.argv[1]
    with open(candidate_path, 'r', encoding='utf-8') as f:
        candidate_data = json.load(f)
        
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    db_file_path = os.path.join(base_dir, 'data', 'db', 'portfolio.db')
    
    engine = MarginalRiskEngine(db_file_path)
    result = engine.calculate_marginal_risk(candidate_data)
    
    print(json.dumps(result, indent=2))
