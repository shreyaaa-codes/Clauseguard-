import os
import sys
import logging
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scoring import ScoringEngine
from src.marginal import MarginalRiskEngine
from src.extract import extract_pipeline
from src.canonicalize import EntityCanonicalizer

app = Flask(__name__, static_folder='static')

# Minimal CORS for extension development
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'db', 'portfolio.db'))

@app.route('/api/portfolio', methods=['GET'])
def get_portfolio():
    if not os.path.exists(DB_PATH):
        return jsonify({"error": "Portfolio database not found"}), 404
        
    engine = ScoringEngine()
    try:
        data = engine.get_portfolio_data(DB_PATH)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/marginal-risk', methods=['POST'])
def calculate_marginal_risk():
    if not os.path.exists(DB_PATH):
        return jsonify({"error": "Portfolio database not found"}), 404
        
    candidate = request.json
    if not candidate or 'service_name' not in candidate or 'clauses' not in candidate:
        return jsonify({"error": "Invalid candidate JSON structure"}), 400
        
    engine = MarginalRiskEngine(DB_PATH)
    try:
        result = engine.calculate_marginal_risk(candidate)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze-policy', methods=['POST', 'OPTIONS'])
def analyze_policy():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    data = request.json
    if not data or 'text' not in data:
        return jsonify({"error": "Missing 'text' in request body"}), 400
        
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Policy text is empty"}), 400
        
    url = data.get("url", "")
    title = data.get("title", "")
    
    # Always prioritize domain name so everything doesn't get grouped as "Privacy Policy"
    service_name = ""
    if url:
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc:
            service_name = parsed.netloc.replace('www.', '').split('.')[0].capitalize()
            
    if not service_name and title:
        service_name = title.split('-')[0].strip()
        
    if not service_name:
        service_name = "Unknown Web Service"

    try:
        # C1 Extraction
        extracted = extract_pipeline(text, service_name)
        
        # C2 Canonicalization (in-memory)
        canonicalizer = EntityCanonicalizer()
        all_canonical_entities = set()
        for clause in extracted.get("clauses", []):
            canon_list = [c_e for e in clause.get("entities", []) if (c_e := canonicalizer.canonicalize(e)) is not None]
            clause["canonical_entities"] = canon_list
            all_canonical_entities.update(canon_list)
            
        # C4 Scoring
        scoring_engine = ScoringEngine()
        risk = scoring_engine.calculate_service_score_from_clauses(extracted.get("clauses", []))
        
        mode = extracted.get("mode", "UNKNOWN")
        
        # Assemble Response
        response_data = {
            "service_name": extracted.get("service_name"),
            "mode": mode,
            "clauses": extracted.get("clauses", []),
            "canonical_entities": sorted(list(all_canonical_entities)),
            "risk": risk,
            "policy_url": url
        }
        return jsonify(response_data)
        
    except Exception as e:
        logging.error(f"Analysis failed: {e}")
        return jsonify({"error": f"Extraction failed: {str(e)}"}), 500

@app.route('/api/save-service', methods=['POST', 'OPTIONS'])
def save_service():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.json
    if not data or 'service_name' not in data or 'clauses' not in data:
        return jsonify({"error": "Invalid analysis result data"}), 400

    try:
        from src.canonicalize import DatabaseLoader
        canonicalizer = EntityCanonicalizer()
        loader = DatabaseLoader(DB_PATH)
        loader.load_extraction(data, canonicalizer)
        return jsonify({"status": "success", "message": "Service added to portfolio"}), 201
    except Exception as e:
        logging.error(f"Save failed: {e}")
        return jsonify({"error": f"Failed to save service: {str(e)}"}), 500

@app.route('/api/service/<path:name>', methods=['DELETE', 'OPTIONS'])
def delete_service(name):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    if not os.path.exists(DB_PATH):
        return jsonify({"error": "Portfolio database not found"}), 404
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        row = conn.execute("SELECT id FROM services WHERE name = ?", (name,)).fetchone()
        if not row:
            return jsonify({"error": f"Service not found: {name}"}), 404
        conn.execute("DELETE FROM services WHERE id = ?", (row[0],))
        conn.commit()
        return jsonify({"status": "success", "message": f"{name} removed from portfolio"})
    finally:
        conn.close()


@app.route('/api/overlap-graph', methods=['GET'])
def get_overlap_graph():
    if not os.path.exists(DB_PATH):
        return jsonify({"error": "Portfolio database not found"}), 404
        
    engine = ScoringEngine()
    try:
        data = engine.get_portfolio_data(DB_PATH)
        
        nodes = []
        edges = []
        
        # Add service nodes
        for service in data.get("services", []):
            nodes.append({"id": service["service_name"], "group": "service"})
            
        # Add entity nodes and edges
        added_entities = set()
        for service in data.get("services", []):
            s_name = service["service_name"]
            for ent in service.get("entities", []):
                if ent not in added_entities:
                    nodes.append({"id": ent, "group": "entity"})
                    added_entities.add(ent)
                # Deduplicate edges conceptually
                edge_id = f"{s_name}->{ent}"
                edges.append({"source": s_name, "target": ent, "id": edge_id})
        
        # Deduplicate edges list
        unique_edges = {e["id"]: e for e in edges}.values()
        
        return jsonify({
            "nodes": nodes,
            "edges": list(unique_edges)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/compare-services', methods=['POST'])
def compare_services():
    if not os.path.exists(DB_PATH):
        return jsonify({"error": "Portfolio database not found"}), 404
        
    req_data = request.json
    if not req_data or 'candidate_a' not in req_data or 'candidate_b' not in req_data:
        return jsonify({"error": "Must provide candidate_a and candidate_b"}), 400

    def get_candidate(candidate_data):
        if isinstance(candidate_data, dict):
            return candidate_data
            
        # Fetch from DB if string
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM services WHERE name = ?", (candidate_data,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise ValueError(f"Service not found: {candidate_data}")
            
        service_id = row[0]
        cursor.execute("SELECT id, text, severity_score, specificity_score, risk_category FROM clauses WHERE service_id = ?", (service_id,))
        clauses = []
        for c_id, text, sev, spec, cat in cursor.fetchall():
            cursor.execute("""
                SELECT ce.name 
                FROM canonical_entities ce
                JOIN clause_entity_mapping cem ON ce.id = cem.entity_id
                WHERE cem.clause_id = ?
            """, (c_id,))
            ents = [r[0] for r in cursor.fetchall()]
            clauses.append({
                "text": text,
                "severity_score": sev,
                "specificity_score": spec,
                "risk_category": cat,
                "entities": ents
            })
        conn.close()
        return {
            "service_name": candidate_data,
            "clauses": clauses
        }
        
    try:
        cand_a = get_candidate(req_data["candidate_a"])
        cand_b = get_candidate(req_data["candidate_b"])
        
        engine = MarginalRiskEngine(DB_PATH)
        res_a = engine.calculate_marginal_risk(cand_a)
        res_b = engine.calculate_marginal_risk(cand_b)
        return jsonify({
            "candidate_a": res_a,
            "candidate_b": res_b
        })
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------------
# Shelf: sites analysed in the browser extension, waiting to be compared on the dashboard
# ---------------------------------------------------------------------------
REQUIRED_REPORT_KEYS = ("service_name", "rating", "band", "entities", "practices", "avg_severity", "summary")


def _shelf_conn():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS shelf (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, url TEXT,
        created_at TEXT NOT NULL, report TEXT NOT NULL)""")
    return conn


def _load_shelf_report(shelf_id):
    import json as _json
    conn = _shelf_conn()
    try:
        row = conn.execute("SELECT report FROM shelf WHERE id = ?", (shelf_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return _json.loads(row[0])


def _shelf_add(report):
    """Put an analysis on the dashboard shelf (one entry per site; adding again replaces it). Returns the shelf id."""
    import json as _json
    import datetime
    payload = _json.dumps(report)
    if len(payload) > 3_000_000:
        raise ValueError("Analysis is too large to store.")
    url = ""
    for src in report.get("sources") or []:
        if src.get("url"):
            url = src["url"]
            break
    conn = _shelf_conn()
    try:
        conn.execute("DELETE FROM shelf WHERE lower(name) = lower(?)", (report["service_name"],))
        cur = conn.execute("INSERT INTO shelf (name, url, created_at, report) VALUES (?, ?, ?, ?)",
                           (report["service_name"], url or report.get("policy_url", ""),
                            datetime.datetime.now(datetime.timezone.utc).isoformat(), payload))
        conn.execute("DELETE FROM shelf WHERE id NOT IN (SELECT id FROM shelf ORDER BY id DESC LIMIT 20)")
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


@app.route('/api/shelf', methods=['GET', 'POST', 'OPTIONS'])
def shelf():
    """GET: list analysed sites. POST: add one (body is a report from /api/summarize, optionally {"report": ...})."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    import json as _json
    import datetime
    if request.method == 'POST':
        body = request.get_json(silent=True) or {}
        report = body.get("report", body)
        if not isinstance(report, dict) or any(k not in report for k in REQUIRED_REPORT_KEYS):
            return jsonify({"error": "That is not a ClauseGuard analysis. Summarize the site again, then add it."}), 400
        try:
            return jsonify({"status": "success", "id": _shelf_add(report)}), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 413
    conn = _shelf_conn()
    try:
        rows = conn.execute("SELECT id, name, url, created_at, report FROM shelf ORDER BY id DESC").fetchall()
    finally:
        conn.close()
    items = []
    for sid, name, url, created, rep in rows:
        r = _json.loads(rep)
        items.append({"id": sid, "name": name, "url": url, "created_at": created, "rating": r.get("rating"),
                      "band": r.get("band"), "tldr": (r.get("summary") or {}).get("tldr", ""),
                      "clause_count": r.get("clause_count"), "mode": r.get("mode")})
    return jsonify({"items": items})


@app.route('/api/shelf/<int:shelf_id>', methods=['DELETE', 'OPTIONS'])
def shelf_delete(shelf_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    conn = _shelf_conn()
    try:
        cur = conn.execute("DELETE FROM shelf WHERE id = ?", (shelf_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "That analysis was already removed."}), 404
        return jsonify({"status": "success"})
    finally:
        conn.close()


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"app": "ClauseGuard", "status": "ok", "version": 2})


@app.route('/api/summarize', methods=['POST', 'OPTIONS'])
def summarize_site():
    """
    Used by the browser extension.
    Body: {"url": "...", "text": "(page text, optional)", "title": "(optional)", "include_terms": true}
    Returns a full report (rating, plain-language summary, practices, data types) for one site.
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    from analyzer import analyze_site, portfolio_impact, AnalysisError
    body = request.get_json(silent=True) or {}
    url, text = (body.get("url") or "").strip(), (body.get("text") or "").strip()
    if not url and not text:
        return jsonify({"error": "Send the page link, the policy text, or both."}), 400
    try:
        report = analyze_site(url or None, text or None, body.get("name"), include_terms=bool(body.get("include_terms")))
    except AnalysisError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        logging.error(f"Summarize failed: {e}")
        return jsonify({"error": f"Analysis failed: {e}"}), 500
    report["portfolio_impact"] = portfolio_impact(report, DB_PATH)
    if body.get("add_to_dashboard"):
        try:
            report["shelf_id"] = _shelf_add(report)
            report["on_dashboard"] = True
        except Exception as e:
            logging.error(f"Could not add to dashboard shelf: {e}")
            report["on_dashboard"] = False
    return jsonify(report)


@app.route('/api/compare-websites', methods=['POST', 'OPTIONS'])
def compare_websites():
    """
    Compare 2 to 6 websites and recommend one.
    Body: {"sites": [ {"url": "...", "text": "(optional pasted policy)", "name": "(optional)"} or {"shelf_id": 3}, ... ]}
    The older {"a": {...}, "b": {...}} form still works.
    Each site is read (or loaded from the dashboard shelf), scored, and ranked.
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    from analyzer import analyze_site, compare_many, portfolio_impact, AnalysisError, MAX_COMPARE_SITES

    body = request.get_json(silent=True) or {}
    raw_sites = body.get("sites")
    if raw_sites is None:
        raw_sites = [body.get("a"), body.get("b")]
    if not isinstance(raw_sites, list) or len(raw_sites) < 2:
        return jsonify({"error": "Choose at least two websites to compare."}), 400
    if len(raw_sites) > MAX_COMPARE_SITES:
        return jsonify({"error": f"You can compare up to {MAX_COMPARE_SITES} websites at a time."}), 400

    letter = lambda i: chr(ord("a") + i)       # error positions: "a", "b", "c", ...
    label = lambda i: f"Website {letter(i).upper()}"

    sites = []
    for i, side in enumerate(raw_sites):
        if isinstance(side, str):
            side = {"url": side}
        if isinstance(side, dict) and side.get("shelf_id") is not None:
            sites.append(side)
            continue
        if not isinstance(side, dict) or not (side.get("url") or side.get("text")):
            return jsonify({"error": f"{label(i)}: enter a link or paste the policy text.", "side": letter(i)}), 400
        sites.append(side)

    shelf_ids = [s_.get("shelf_id") for s_ in sites if s_.get("shelf_id") is not None]
    if len(shelf_ids) != len(set(shelf_ids)):
        return jsonify({"error": "Pick each site only once.", "side": letter(len(sites) - 1)}), 400

    reports = []
    for i, side in enumerate(sites):
        if side.get("shelf_id") is not None:
            try:
                rep = _load_shelf_report(int(side["shelf_id"]))
            except (TypeError, ValueError):
                rep = None
            if rep is None:
                return jsonify({"error": f"{label(i)}: that analysis is no longer on the dashboard. Add it again from the extension.", "side": letter(i)}), 404
            reports.append(rep)
            continue
        try:
            reports.append(analyze_site(side.get("url"), side.get("text"), side.get("name"),
                                        include_terms=bool(side.get("include_terms"))))
        except AnalysisError as e:
            return jsonify({"error": f"{label(i)}: {e}", "side": letter(i)}), 422
        except Exception as e:
            logging.error(f"Website analysis failed ({letter(i)}): {e}")
            return jsonify({"error": f"{label(i)}: analysis failed ({e})", "side": letter(i)}), 500

    # Make names unique so they can be told apart in the report.
    seen = {}
    for r in reports:
        key = r["service_name"].lower()
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            r["service_name"] += f" ({seen[key]})"
    firsts = [k for k, v in seen.items() if v > 1]
    for r in reports:
        if r["service_name"].lower() in firsts and "(" not in r["service_name"]:
            r["service_name"] += " (1)"

    for r in reports:
        r["portfolio_impact"] = portfolio_impact(r, DB_PATH)
    verdict = compare_many(reports)
    out = {"sites": reports, "verdict": verdict}
    if len(reports) == 2:          # keep the original two-site fields for older callers
        out["a"], out["b"] = reports
    return jsonify(out)


@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    print("Starting ClauseGuard Dashboard...")
    # Port 5000 is taken by AirPlay Receiver on macOS, so ClauseGuard uses 5050 by default.
    port = int(os.environ.get("PORT", "5050"))
    print(f"Open http://127.0.0.1:{port} in your browser.")
    app.run(host='127.0.0.1', port=port, debug=True)
