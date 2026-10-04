import os
import json
import argparse
from extraction.prefilter import PrivacyPrefilter
from extraction.llm_extractor import LLMExtractor
from extraction.validator import validate_extraction_output

def extract_pipeline(raw_text, service_name, category=None):
    """
    The canonical single path for extraction.
    """
    # 1. Split into simple clauses/sentences (naive split for demo)
    # A real implementation might use nltk or spacy.
    raw_clauses = [c.strip() for c in raw_text.split('.') if len(c.strip()) > 10]
    
    # 2. Prefilter
    prefilter = PrivacyPrefilter()
    candidate_clauses = prefilter.filter_candidates(raw_clauses)
    
    # 3. LLM Extraction
    extractor = LLMExtractor(service_name=service_name, category=category)
    extracted_json = extractor.extract(candidate_clauses)
    
    # 4. Validate output
    validate_extraction_output(extracted_json)
    
    return extracted_json

def process_file(input_path, service_name, category=None):
    with open(input_path, 'r', encoding='utf-8') as f:
        raw_text = f.read()
        
    result = extract_pipeline(raw_text, service_name, category)
    
    # Ensure output directory exists
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    out_dir = os.path.join(base_dir, 'data', 'extracted')
    os.makedirs(out_dir, exist_ok=True)
    
    out_filename = f"{service_name.lower().replace(' ', '_')}.json"
    out_path = os.path.join(out_dir, out_filename)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
        
    print(f"Extraction complete. Output written to {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract privacy clauses from raw text.")
    parser.add_argument("input_file", help="Path to raw policy text file")
    parser.add_argument("service_name", help="Name of the service (e.g., Spotify)")
    parser.add_argument("--category", help="Optional service category", default=None)
    
    args = parser.parse_args()
    process_file(args.input_file, args.service_name, args.category)
