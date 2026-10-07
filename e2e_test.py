import requests
import json
import time
import subprocess
import os

# Start the Flask app
flask_process = subprocess.Popen(["python", "src/dashboard.py"])
time.sleep(3) # wait for server to start

try:
    # 1. Hit analyze-policy
    analyze_payload = {
        "text": "Your IP address is logged for security purposes.",
        "url": "https://example.com/privacy",
        "title": "MyNewApp Privacy Policy"
    }
    r = requests.post('http://127.0.0.1:5000/api/analyze-policy', json=analyze_payload)
    print("Analyze Status:", r.status_code)
    analysis_result = r.json()
    
    # 2. Save the service
    r = requests.post('http://127.0.0.1:5000/api/save-service', json=analysis_result)
    print("Save Status:", r.status_code)
    
    # 3. Check portfolio
    r = requests.get('http://127.0.0.1:5000/api/portfolio')
    portfolio = r.json()
    names = [s['service_name'] for s in portfolio['services']]
    print("Portfolio Services:", names)
    assert 'MyNewApp Privacy Policy' in names, "Service not found in portfolio"
    
    # 4. Check graph
    r = requests.get('http://127.0.0.1:5000/api/overlap-graph')
    graph = r.json()
    nodes = [n['id'] for n in graph['nodes']]
    assert 'MyNewApp Privacy Policy' in nodes, "Service not found in graph nodes"
    print("Graph contains service:", 'MyNewApp Privacy Policy' in nodes)
    
    print("End-to-end HTTP API check passed!")

finally:
    flask_process.terminate()
    flask_process.wait()
