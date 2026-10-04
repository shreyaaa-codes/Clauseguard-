import requests
import time
import subprocess
import os

# Start the Flask app
flask_process = subprocess.Popen(["python", "src/dashboard.py"])
time.sleep(3)

try:
    # Clear db for clean test
    db_path = os.path.abspath('data/db/portfolio.db')
    if os.path.exists(db_path):
        os.remove(db_path)
    
    import sys
    sys.path.insert(0, os.path.abspath('src'))
    from db import init_db
    init_db(db_path)
    
    # 1. Save Service A
    sa_payload = {
        "service_name": "Service A",
        "mode": "MOCK",
        "clauses": [
            {
                "text": "Location clause",
                "entities": ["Location Data"],
                "severity_score": 1,
                "specificity_score": 1,
                "risk_category": "Cat",
                "canonical_entities": ["Location"]
            },
            {
                "text": "IP clause",
                "entities": ["IP"],
                "severity_score": 1,
                "specificity_score": 1,
                "risk_category": "Cat",
                "canonical_entities": ["IP Address"]
            }
        ],
        "canonical_entities": ["Location", "IP Address"]
    }
    requests.post('http://127.0.0.1:5050/api/save-service', json=sa_payload)

    # 2. Save Service B
    sb_payload = {
        "service_name": "Service B",
        "mode": "MOCK",
        "clauses": [
            {
                "text": "IP clause B",
                "entities": ["IP"],
                "severity_score": 1,
                "specificity_score": 1,
                "risk_category": "Cat",
                "canonical_entities": ["IP Address"]
            },
            {
                "text": "Email clause",
                "entities": ["Email Address"],
                "severity_score": 1,
                "specificity_score": 1,
                "risk_category": "Cat",
                "canonical_entities": ["Email"]
            }
        ],
        "canonical_entities": ["IP Address", "Email"]
    }
    requests.post('http://127.0.0.1:5050/api/save-service', json=sb_payload)

    # 3. Check portfolio
    r = requests.get('http://127.0.0.1:5050/api/portfolio')
    names = [s['service_name'] for s in r.json()['services']]
    assert 'Service A' in names
    assert 'Service B' in names

    # 4. Compare
    comp_payload = {
        "candidate_a": "Service B",
        "candidate_b": "Service A"
    }
    r = requests.post('http://127.0.0.1:5050/api/compare-services', json=comp_payload)
    res = r.json()
    
    ca = res["candidate_a"]
    assert ca["candidate_name"] == "Service B"
    assert "IP Address" in ca["overlapping_entities"]
    
    # Since Service B is excluded from the baseline during calculation,
    # "Email" should be recognized as newly introduced, not overlapping.
    assert "Email" in ca["newly_introduced_entities"]
    assert "Email" not in ca["overlapping_entities"]
    
    print("End-to-end Phase 2B test passed!")

finally:
    flask_process.terminate()
    flask_process.wait()
