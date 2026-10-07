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

    def test_site_name_from_host(self):
        self.assertEqual(analyzer.site_name_from_host("www.spotify.com"), "Spotify")
        self.assertEqual(analyzer.site_name_from_host("policies.google.com"), "Google")
        self.assertEqual(analyzer.site_name_from_host("www.bbc.co.uk"), "Bbc")


if __name__ == "__main__":
    unittest.main()
