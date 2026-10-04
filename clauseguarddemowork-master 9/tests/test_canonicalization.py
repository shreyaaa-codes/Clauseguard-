import unittest
import os
import sys
import sqlite3
import tempfile

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from canonicalize import EntityCanonicalizer, DatabaseLoader
from db import init_db

class TestCanonicalization(unittest.TestCase):
    
    def setUp(self):
        # Create a temporary database for testing
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp()
        # Initialize schema using the existing db.py logic
        init_db(self.temp_db_path)
        self.loader = DatabaseLoader(self.temp_db_path)
        self.canonicalizer = EntityCanonicalizer()

    def tearDown(self):
        os.close(self.temp_db_fd)
        os.remove(self.temp_db_path)

    def test_canonicalizer_mappings(self):
        c = self.canonicalizer
        self.assertEqual(c.canonicalize("Location Data"), "Location")
        self.assertEqual(c.canonicalize("  user location  "), "Location")
        self.assertEqual(c.canonicalize("IP"), "IP Address")
        self.assertEqual(c.canonicalize("Email Address"), "Email")
        
        # Unknown entity preservation
        self.assertEqual(c.canonicalize("Browser Fingerprint"), "Unknown: Browser Fingerprint")
        self.assertEqual(c.canonicalize("  weird   SPACING "), "Unknown: weird   SPACING")

    def test_db_loading_and_relationships(self):
        data = {
            "service_name": "TestService",
            "category": "TestCategory",
            "clauses": [
                {
                    "text": "We share your location data.",
                    "entities": ["location data"],
                    "severity_score": 4.0,
                    "specificity_score": 2.0,
                    "risk_category": "Data Sharing"
                }
            ]
        }
        
        self.loader.load_extraction(data, self.canonicalizer)
        
        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()
        
        # Check service
        cursor.execute("SELECT name, category FROM services")
        service = cursor.fetchone()
        self.assertIsNotNone(service)
        self.assertEqual(service[0], "TestService")
        
        # Check canonical entity
        cursor.execute("SELECT name FROM canonical_entities")
        entity = cursor.fetchone()
        self.assertIsNotNone(entity)
        self.assertEqual(entity[0], "Location")
        
        # Check clause
        cursor.execute("SELECT text, severity_score FROM clauses")
        clause = cursor.fetchone()
        self.assertIsNotNone(clause)
        self.assertEqual(clause[0], "We share your location data.")
        self.assertEqual(clause[1], 4.0)
        
        # Check mapping
        cursor.execute("SELECT * FROM clause_entity_mapping")
        mapping = cursor.fetchone()
        self.assertIsNotNone(mapping)
        
        conn.close()

    def test_idempotency(self):
        data = {
            "service_name": "TestService",
            "category": "TestCategory",
            "clauses": [
                {
                    "text": "We share your location data.",
                    "entities": ["location data"]
                }
            ]
        }
        
        # Run twice
        self.loader.load_extraction(data, self.canonicalizer)
        self.loader.load_extraction(data, self.canonicalizer)
        
        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()
        
        # Check for duplicates
        cursor.execute("SELECT COUNT(*) FROM services")
        self.assertEqual(cursor.fetchone()[0], 1)
        
        cursor.execute("SELECT COUNT(*) FROM canonical_entities")
        self.assertEqual(cursor.fetchone()[0], 1)
        
        cursor.execute("SELECT COUNT(*) FROM clauses")
        self.assertEqual(cursor.fetchone()[0], 1)
        
        cursor.execute("SELECT COUNT(*) FROM clause_entity_mapping")
        self.assertEqual(cursor.fetchone()[0], 1)
        
        conn.close()

    def test_cross_service_shared_entities(self):
        data1 = {
            "service_name": "Spotify",
            "clauses": [
                {"text": "Location info used.", "entities": ["Location Data"]}
            ]
        }
        data2 = {
            "service_name": "Google",
            "clauses": [
                {"text": "User location tracked.", "entities": ["User Location"]}
            ]
        }
        
        self.loader.load_extraction(data1, self.canonicalizer)
        self.loader.load_extraction(data2, self.canonicalizer)
        
        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()
        
        # Should be two services
        cursor.execute("SELECT COUNT(*) FROM services")
        self.assertEqual(cursor.fetchone()[0], 2)
        
        # Should be exactly ONE canonical entity "Location"
        cursor.execute("SELECT name FROM canonical_entities")
        entities = cursor.fetchall()
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0][0], "Location")
        
        conn.close()

if __name__ == '__main__':
    unittest.main()
