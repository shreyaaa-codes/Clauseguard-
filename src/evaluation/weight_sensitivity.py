import json
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from extraction.prefilter import PrivacyPrefilter
from scoring import ScoringEngine

def generate_weight_sensitivity():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    
    # Example hypothetical clause parameters
    hypothetical_clause = {
        "text": "We continuously collect and share your precise GPS location.",
        "severity": 4.0,
        "specificity": 2.0
    }
    
    weights_to_test = [
        {"w1": 1.0, "w2": 1.0},
        {"w1": 2.0, "w2": 1.0},
        {"w1": 1.0, "w2": 2.0},
        {"w1": 0.5, "w2": 1.0},
        {"w1": 1.0, "w2": 0.5},
        {"w1": 0.0, "w2": 1.0},
        {"w1": 1.0, "w2": 0.0}
    ]
    
    analysis = {
        "title": "Weight Sensitivity Analysis \u2014 Illustrative Only",
        "description": "This analysis demonstrates how the calculated risk score for a single clause shifts under different hypothetical weight configurations. Because independent human-rated score ground truth is currently unavailable, this is not an optimization or a claim that any particular weight is scientifically 'better'.",
        "hypothetical_clause": hypothetical_clause,
        "results": []
    }
    
    for w in weights_to_test:
        engine = ScoringEngine(w1=w["w1"], w2=w["w2"])
        score = engine.calculate_clause_score(
            hypothetical_clause["severity"],
            hypothetical_clause["specificity"]
        )
        analysis["results"].append({
            "weights": {"w1": w["w1"], "w2": w["w2"]},
            "calculated_clause_risk": score,
            "note": f"Risk = ({w['w1']} * {hypothetical_clause['severity']}) + ({w['w2']} * {hypothetical_clause['specificity']})"
        })
        
    out_path = os.path.join(base_dir, 'data', 'evaluation', 'weight_sensitivity.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2)
        
    return analysis

if __name__ == "__main__":
    res = generate_weight_sensitivity()
    print("Weight sensitivity analysis generated.")
