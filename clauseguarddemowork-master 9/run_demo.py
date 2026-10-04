import os
import sys
import json
import tempfile
from dotenv import load_dotenv

load_dotenv()

# Ensure src is in path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from extraction.prefilter import PrivacyPrefilter
from extraction.llm_extractor import LLMExtractor
from extract import extract_pipeline
from canonicalize import EntityCanonicalizer, DatabaseLoader
from db import init_db
from scoring import ScoringEngine
from marginal import MarginalRiskEngine

def run_end_to_end_demo():
    print("========================================")
    print("CLAUSEGUARD END-TO-END DEMO")
    print("========================================")
    
    # 0. Setup Temporary DB
    temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db", prefix="clauseguard_demo_")
    try:
        init_db(temp_db_path)
        
        # 1. C1 - EXTRACTION
        print("\n[1] C1 — EXTRACTION")
        raw_path = os.path.join('data', 'raw', 'spotify.txt')
        if not os.path.exists(raw_path):
            raise FileNotFoundError(f"Missing input file: {raw_path}")
            
        with open(raw_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()
            
        print("Service: Spotify")
        # Explicitly clear GEMINI_API_KEY for the demo to force Mock mode unless user really wants it
        # Actually, let's just indicate Mock mode if it's missing
        mode = "REAL" if "GEMINI_API_KEY" in os.environ else "MOCK/DEV"
        print(f"Mode: {mode}")
        
        spotify_extracted = extract_pipeline(raw_text, "Spotify", "Streaming")
        print(f"Clauses extracted: {len(spotify_extracted.get('clauses', []))}")
        
        # 2. C2 - CANONICALIZATION
        print("\n[2] C2 — CANONICALIZATION")
        canonicalizer = EntityCanonicalizer()
        loader = DatabaseLoader(temp_db_path)
        
        # Load into temp db
        loader.load_extraction(spotify_extracted, canonicalizer)
        
        # Get canonical entities just to show
        all_canonical = set()
        for clause in spotify_extracted.get("clauses", []):
            for e in clause.get("entities", []):
                all_canonical.add(canonicalizer.canonicalize(e))
                
        print("Canonical entities:")
        for entity in sorted(list(all_canonical)):
            print(f"  * {entity}")

        # 3. PORTFOLIO
        print("\n[3] PORTFOLIO")
        scoring = ScoringEngine()
        portfolio_data = scoring.get_portfolio_data(temp_db_path)
        print("Services:")
        for s in portfolio_data.get("services", []):
            print(f"  * {s['service_name']}")

        # 4. C4 - SCORING
        print("\n[4] C4 — SCORING")
        print(f"Portfolio risk: {portfolio_data['portfolio_score']}")

        # 5. C5 - MARGINAL RISK
        print("\n[5] C5 — MARGINAL RISK")
        google_candidate_path = os.path.join('data', 'extracted', 'google_candidate.json')
        if not os.path.exists(google_candidate_path):
            raise FileNotFoundError(f"Missing candidate file: {google_candidate_path}")
            
        with open(google_candidate_path, 'r', encoding='utf-8') as f:
            google_candidate = json.load(f)
            
        marginal_engine = MarginalRiskEngine(temp_db_path)
        marginal_result = marginal_engine.calculate_marginal_risk(google_candidate)
        
        print(f"Candidate: {marginal_result['candidate_name']}")
        print(f"Candidate risk: {marginal_result['candidate_service_risk']}")
        print(f"Marginal risk: {marginal_result['marginal_risk_delta']}")
        
        print("\nOverlapping entities:")
        for oe in marginal_result['overlapping_entities']:
            print(f"  * {oe}")
            
        print("\nNewly introduced entities:")
        for ne in marginal_result['newly_introduced_entities']:
            print(f"  * {ne}")

        print("\n========================================")
        print("DEMO COMPLETE")
        print("========================================")
        
        # Build structured result
        structured_result = {
            "existing_service": "Spotify",
            "candidate_service": marginal_result['candidate_name'],
            "extracted_clause_count": len(spotify_extracted.get('clauses', [])),
            "canonical_entities": list(all_canonical),
            "baseline_portfolio_risk": portfolio_data['portfolio_score'],
            "candidate_service_risk": marginal_result['candidate_service_risk'],
            "marginal_risk": marginal_result['marginal_risk_delta'],
            "overlapping_entities": marginal_result['overlapping_entities'],
            "newly_introduced_entities": marginal_result['newly_introduced_entities']
        }
        
        return structured_result

    except Exception as e:
        print(f"\n[!] DEMO FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise e
    finally:
        # Cleanup temporary database
        os.close(temp_db_fd)
        try:
            os.remove(temp_db_path)
        except OSError:
            pass

if __name__ == "__main__":
    run_end_to_end_demo()
