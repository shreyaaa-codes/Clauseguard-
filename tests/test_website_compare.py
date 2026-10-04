import os
import sys
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
os.environ["CLAUSEGUARD_ALLOW_PRIVATE"] = "1"   # tests talk to a local server

import analyzer
from dashboard import app

INVASIVE = (
    "We collect your precise location, fingerprint and face data, payment information, phone number, "
    "email address and contact information. We sell personal data to advertising partners. "
    "We share your location data and device information with third parties and marketing partners. "
    "We track your browsing with cookies, web beacons and unique identifiers across other websites. "
    "We retain your information indefinitely and transfer it to other countries. "
    "We collect your messages and communications and use profiling to personalise advertising. "
) * 4

GENTLE = (
    "We collect your email address to create your account. "
    "We do not sell personal data to anyone. "
    "You can delete your account and your data at any time from your privacy settings. "
    "You may opt out of analytics cookies and download a copy of your personal information. "
    "We use encryption to protect your information and comply with the GDPR. "
    "We keep log data about page views for performance analytics. "
) * 4


def page(body, links=""):
    return f"<html><head><title>T</title></head><body>{body}<footer>{links}</footer></body></html>"


PAGES = {
    "/invasive": page("<p>" + INVASIVE.replace(". ", ".</p><p>") + "</p>"),
    "/gentle/privacy": page("<p>" + GENTLE.replace(". ", ".</p><p>") + "</p>"),
    "/gentle": page("<h1>Welcome</h1><p>Great music.</p>", '<a href="/gentle/privacy">Privacy Policy</a>'),
    "/blocked": None,
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path)
        if self.path == "/blocked":
            self.send_response(403)
            self.end_headers()
            return
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class TestWebsiteCompare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.client = app.test_client()
        os.environ.pop("GEMINI_API_KEY", None)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_finds_policy_from_home_page_footer_link(self):
        res = analyzer.fetch_policy(self.base + "/gentle")
        self.assertEqual(res["sources"][0]["url"], self.base + "/gentle/privacy")
        self.assertIn("GDPR", res["text"])

    def test_direct_policy_page(self):
        res = analyzer.fetch_policy(self.base + "/invasive")
        self.assertIn("sell personal data", res["text"])

    def test_invasive_policy_rates_riskier_than_gentle(self):
        a = analyzer.analyze_site(self.base + "/invasive")
        b = analyzer.analyze_site(self.base + "/gentle")
        self.assertGreater(a["rating"], b["rating"] + 15)
        self.assertIn("Biometric Data", a["canonical_entities"])
        keys_a = {p["key"] for p in a["practices"] if p["present"]}
        keys_b = {p["key"] for p in b["practices"] if p["present"]}
        self.assertIn("sells_data", keys_a)
        self.assertIn("no_sale", keys_b)
        self.assertNotIn("sells_data", keys_b)
        verdict = analyzer.compare_reports(a, b)
        self.assertEqual(verdict["winner"], "b")
        self.assertTrue(verdict["reasons"])

    def test_identical_reports_tie(self):
        a = analyzer.analyze_site(None, GENTLE, "One")
        b = analyzer.analyze_site(None, GENTLE, "Two")
        self.assertEqual(analyzer.compare_reports(a, b)["winner"], "tie")

    def test_api_end_to_end_and_does_not_touch_db(self):
        import dashboard
        before = os.path.getmtime(dashboard.DB_PATH) if os.path.exists(dashboard.DB_PATH) else None
        r = self.client.post("/api/compare-websites", json={
            "a": {"url": self.base + "/invasive", "name": "Snoopy"},
            "b": {"text": GENTLE, "name": "Gentle"}})
        self.assertEqual(r.status_code, 200, r.data)
        data = json.loads(r.data)
        self.assertEqual(data["verdict"]["winner"], "b")
        self.assertEqual(data["a"]["service_name"], "Snoopy")
        after = os.path.getmtime(dashboard.DB_PATH) if os.path.exists(dashboard.DB_PATH) else None
        self.assertEqual(before, after)

    def test_errors_are_clear(self):
        r = self.client.post("/api/compare-websites", json={"a": {"url": ""}, "b": {"url": "x.com"}})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/compare-websites", json={
            "a": {"url": self.base + "/blocked"}, "b": {"text": GENTLE}})
        self.assertEqual(r.status_code, 422)
        self.assertIn("paste", json.loads(r.data)["error"])

    def test_private_addresses_blocked_by_default(self):
        os.environ.pop("CLAUSEGUARD_ALLOW_PRIVATE")
        try:
            with self.assertRaises(analyzer.AnalysisError):
                analyzer.fetch_policy(self.base + "/gentle")
        finally:
            os.environ["CLAUSEGUARD_ALLOW_PRIVATE"] = "1"

    def test_empty_portfolio_hides_impact_and_service_can_be_removed(self):
        import tempfile
        from unittest.mock import patch
        from db import init_db
        fd, path = tempfile.mkstemp(); os.close(fd)
        try:
            init_db(path)
            with patch('dashboard.DB_PATH', path):
                r = json.loads(self.client.post("/api/compare-websites", json={
                    "a": {"text": GENTLE, "name": "One"}, "b": {"text": INVASIVE, "name": "Two"}}).data)
                self.assertIsNone(r["a"]["portfolio_impact"])
                saved = self.client.post("/api/save-service", json={
                    "service_name": "One", "clauses": r["a"]["clauses"]})
                self.assertEqual(saved.status_code, 201)
                r2 = json.loads(self.client.post("/api/compare-websites", json={
                    "a": {"text": GENTLE, "name": "Three"}, "b": {"text": INVASIVE, "name": "Four"}}).data)
                self.assertIsNotNone(r2["a"]["portfolio_impact"])
                self.assertEqual(self.client.delete("/api/service/One").status_code, 200)
                self.assertEqual(self.client.delete("/api/service/One").status_code, 404)
                self.assertEqual(json.loads(self.client.get("/api/portfolio").data)["services"], [])
        finally:
            os.remove(path)

    def test_health_and_extension_summarize_endpoint(self):
        h = json.loads(self.client.get("/api/health").data)
        self.assertEqual(h["app"], "ClauseGuard")
        # Home page link: backend finds the policy itself
        r = self.client.post("/api/summarize", json={"url": self.base + "/gentle"})
        self.assertEqual(r.status_code, 200, r.data)
        rep = json.loads(r.data)
        self.assertEqual(len(rep["summary"]["key_points"]), 5)
        self.assertIn("tldr", rep["summary"])
        # Page text from the extension
        r = self.client.post("/api/summarize", json={"text": INVASIVE, "name": "Snoopy"})
        rep = json.loads(r.data)
        self.assertIn("Sells or monetises personal data", rep["summary"]["red_flags"])
        self.assertEqual(self.client.post("/api/summarize", json={}).status_code, 400)

    def test_terms_and_conditions_practices_detected(self):
        txt = GENTLE + (" We may change these terms at any time. Any dispute is subject to binding arbitration."
                        " Your plan will automatically renew each month. You grant us a perpetual, worldwide,"
                        " royalty-free licence to use your content.")
        rep = analyzer.analyze_site(None, txt, "T")
        present = {p["key"] for p in rep["practices"] if p["present"]}
        self.assertTrue({"arbitration", "unilateral_changes", "auto_renew", "content_license"} <= present)
        self.assertIn("Terms to watch", rep["summary"]["key_points"][4]["text"])

    def test_terms_page_is_read_alongside_privacy_page(self):
        PAGES["/acme/privacy"] = page("<p>" + GENTLE.replace(". ", ".</p><p>") + "</p>",
                                            '<a href="/acme/terms">Terms and Conditions of Use</a>')
        PAGES["/acme/terms"] = page("<p>" + (GENTLE + " Disputes go to binding arbitration. ").replace(". ", ".</p><p>") + "</p>")
        res = analyzer.fetch_policy(self.base + "/acme/privacy")
        self.assertEqual(len(res["sources"]), 2)
        self.assertTrue(res["sources"][1]["url"].endswith("/acme/terms"))

    def test_extension_summaries_land_on_the_shelf_and_compare_by_id(self):
        import tempfile
        from unittest.mock import patch
        from db import init_db
        fd, path = tempfile.mkstemp(); os.close(fd)
        try:
            init_db(path)
            with patch('dashboard.DB_PATH', path):
                self.assertEqual(json.loads(self.client.get("/api/shelf").data)["items"], [])
                ids = {}
                for name, txt in (("Snoopy", INVASIVE), ("Gentle", GENTLE)):
                    r = json.loads(self.client.post("/api/summarize", json={
                        "text": txt, "name": name, "add_to_dashboard": True}).data)
                    self.assertTrue(r["on_dashboard"])
                    ids[name] = r["shelf_id"]
                # a summary without the flag is not shelved
                self.client.post("/api/summarize", json={"text": GENTLE, "name": "Hidden"})
                items = json.loads(self.client.get("/api/shelf").data)["items"]
                self.assertEqual({i["name"] for i in items}, {"Snoopy", "Gentle"})
                # adding the same site again replaces it
                rep = json.loads(self.client.post("/api/summarize", json={"text": GENTLE, "name": "Gentle"}).data)
                self.assertEqual(self.client.post("/api/shelf", json=rep).status_code, 201)
                self.assertEqual(len(json.loads(self.client.get("/api/shelf").data)["items"]), 2)
                items = json.loads(self.client.get("/api/shelf").data)["items"]
                ids = {i["name"]: i["id"] for i in items}
                # compare by shelf id, no links
                r = self.client.post("/api/compare-websites", json={
                    "a": {"shelf_id": ids["Snoopy"]}, "b": {"shelf_id": ids["Gentle"]}})
                self.assertEqual(r.status_code, 200, r.data)
                self.assertEqual(json.loads(r.data)["verdict"]["winner"], "b")
                # the shelf never touches the portfolio
                self.assertEqual(json.loads(self.client.get("/api/portfolio").data)["services"], [])
                self.assertEqual(self.client.delete(f"/api/shelf/{ids['Snoopy']}").status_code, 200)
                self.assertEqual(self.client.delete(f"/api/shelf/{ids['Snoopy']}").status_code, 404)
        finally:
            os.remove(path)

    MID = GENTLE + (" We share your location data and device information with third parties and advertising partners."
                    " We use cookies and track your browsing. ") * 2

    def test_compare_three_or_more_sites_ranks_and_recommends_one(self):
        sites = [{"text": INVASIVE, "name": "Snoopy"}, {"text": self.MID, "name": "Midway"}, {"text": GENTLE, "name": "Gentle"}]
        r = self.client.post("/api/compare-websites", json={"sites": sites})
        self.assertEqual(r.status_code, 200, r.data)
        d = json.loads(r.data)
        v = d["verdict"]
        self.assertEqual(len(d["sites"]), 3)
        self.assertNotIn("a", d)                       # two-site fields only for exactly two sites
        self.assertEqual(v["winner"], "Gentle")
        self.assertEqual(v["winner_indices"], [2])
        self.assertEqual([x["service_name"] for x in v["ranking"]], ["Gentle", "Midway", "Snoopy"])
        self.assertEqual([x["rank"] for x in v["ranking"]], [1, 2, 3])
        self.assertIn("most private of the 3", v["headline"])
        # order of input must not change the answer
        d2 = json.loads(self.client.post("/api/compare-websites", json={"sites": sites[::-1]}).data)
        self.assertEqual(d2["verdict"]["winner"], "Gentle")
        # six is allowed, seven is not
        six = sites + [{"text": GENTLE, "name": f"G{i}"} for i in range(3)]
        self.assertEqual(self.client.post("/api/compare-websites", json={"sites": six}).status_code, 200)
        self.assertEqual(self.client.post("/api/compare-websites", json={"sites": six + [{"text": GENTLE}]}).status_code, 400)
        self.assertEqual(self.client.post("/api/compare-websites", json={"sites": sites[:1]}).status_code, 400)

    def test_many_sites_tie_at_the_top_and_duplicate_names(self):
        sites = [{"text": INVASIVE, "name": "Snoopy"}, {"text": GENTLE, "name": "Same"}, {"text": GENTLE, "name": "Same"}]
        d = json.loads(self.client.post("/api/compare-websites", json={"sites": sites}).data)
        names = [x["service_name"] for x in d["sites"]]
        self.assertEqual(len(set(names)), 3)           # duplicates get told apart
        self.assertEqual(d["verdict"]["winner"], "tie")
        self.assertEqual(len(d["verdict"]["winner_indices"]), 2)
        self.assertIn("equally private", d["verdict"]["headline"])

    def test_error_position_points_at_the_failing_site(self):
        sites = [{"text": GENTLE, "name": "A"}, {"text": GENTLE, "name": "B"}, {"url": self.base + "/blocked"}]
        r = self.client.post("/api/compare-websites", json={"sites": sites})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(json.loads(r.data)["side"], "c")
        self.assertIn("Website C", json.loads(r.data)["error"])

    def test_shelf_sites_can_be_compared_in_any_number(self):
        import tempfile
        from unittest.mock import patch
        from db import init_db
        fd, path = tempfile.mkstemp(); os.close(fd)
        try:
            init_db(path)
            with patch('dashboard.DB_PATH', path):
                for n, t in (("Snoopy", INVASIVE), ("Midway", self.MID), ("Gentle", GENTLE)):
                    self.client.post("/api/summarize", json={"text": t, "name": n, "add_to_dashboard": True})
                ids = [i["id"] for i in json.loads(self.client.get("/api/shelf").data)["items"]]
                r = self.client.post("/api/compare-websites", json={"sites": [{"shelf_id": i} for i in ids]})
                self.assertEqual(r.status_code, 200, r.data)
                self.assertEqual(json.loads(r.data)["verdict"]["winner"], "Gentle")
                dup = self.client.post("/api/compare-websites", json={"sites": [{"shelf_id": ids[0]}, {"shelf_id": ids[0]}]})
                self.assertEqual(dup.status_code, 400)
        finally:
            os.remove(path)

    def test_site_name_from_host(self):
        self.assertEqual(analyzer.site_name_from_host("www.spotify.com"), "Spotify")
        self.assertEqual(analyzer.site_name_from_host("policies.google.com"), "Google")
        self.assertEqual(analyzer.site_name_from_host("www.bbc.co.uk"), "Bbc")


if __name__ == "__main__":
    unittest.main()
