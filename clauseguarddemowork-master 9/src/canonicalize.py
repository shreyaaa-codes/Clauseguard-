import json
import sqlite3
import os

class EntityCanonicalizer:
    def __init__(self):
        # A small explicit canonical mapping for demo purposes.
        self.mapping = {
            "location data": "Location",
            "location information": "Location",
            "user location": "Location",
            "location": "Location",
            "geolocation": "Location",
            "gps location": "Location",
            "gps": "Location",
            "precise location": "Precise Location",
            "exact location": "Precise Location",
            "precise location data": "Precise Location",
            
            "ip address": "IP Address",
            "ip": "IP Address",
            "internet protocol address": "IP Address",
            "internet protocol": "IP Address",
            "ip addresses": "IP Address",
            
            "email address": "Email",
            "e-mail address": "Email",
            "e-mail": "Email",
            "email": "Email",
            
            "phone number": "Phone Number",
            "phone": "Phone Number",
            "telephone number": "Phone Number",
            "telephone": "Phone Number",
            "mobile number": "Phone Number",
            "mobile": "Phone Number",
            
            "device information": "Device Information",
            "device": "Device Information",
            "device id": "Device Information",
            "hardware model": "Device Information",
            "mac address": "Device Information",
            "operating system": "Device Information",
            "os": "Device Information",
            
            "browser information": "Browser Information",
            "browser": "Browser Information",
            "browser type": "Browser Information",
            "user agent": "Browser Information",
            
            "cookie": "Cookies",
            "cookies": "Cookies",
            "web beacon": "Cookies",
            "web beacons": "Cookies",
            "pixel tag": "Cookies",
            "pixel tags": "Cookies",
            
            "usage data": "Usage Data",
            "log data": "Usage Data",
            "interaction": "Usage Data",
            "interactions": "Usage Data",
            "click": "Usage Data",
            "clicks": "Usage Data",
            "page view": "Usage Data",
            "page views": "Usage Data",
            
            "identifier": "Identifiers",
            "identifiers": "Identifiers",
            "unique identifier": "Identifiers",
            "unique identifiers": "Identifiers",
            "id": "Identifiers",
            
            "account information": "Account Information",
            "account": "Account Information",
            "password": "Account Information",
            "username": "Account Information",
            "profile": "Account Information",
            
            "payment information": "Payment Information",
            "payment": "Payment Information",
            "credit card": "Payment Information",
            "billing": "Payment Information",
            "financial information": "Payment Information",
            
            "contact information": "Contact Information",
            "contact": "Contact Information",
            "address": "Contact Information",
            "postal": "Contact Information",
            "postal address": "Contact Information",
            
            "biometric data": "Biometric Data",
            "biometric": "Biometric Data",
            "face": "Biometric Data",
            "fingerprint": "Biometric Data",
            "voiceprint": "Biometric Data",
            
            "advertising data": "Advertising Data",
            "advertising": "Advertising Data",
            "marketing": "Advertising Data",
            "ad": "Advertising Data",
            "ads": "Advertising Data",
            
            "analytics data": "Analytics Data",
            "analytics": "Analytics Data",
            "measure": "Analytics Data",
            "measurement": "Analytics Data",
            "performance": "Analytics Data",
            
            "communications": "Communications",
            "communication": "Communications",
            "message": "Communications",
            "messages": "Communications",
            "chat": "Communications",
            "chats": "Communications",
            "correspondence": "Communications",
            
            "name": "Name",
            "first name": "Name",
            "last name": "Name",
            "full name": "Name",
            
            "general data": "General Data"
        }

    def canonicalize(self, raw_entity):
        """
        Normalize and map raw entity to canonical entity.
        """
        if not raw_entity:
            return None
            
        # Trim whitespace and convert to lowercase for matching
        normalized_input = " ".join(raw_entity.split()).strip().lower()
        
        if not normalized_input:
            return None
        
        # Check explicit mapping
        if normalized_input in self.mapping:
            return self.mapping[normalized_input]
            
        # Do not silently convert unknown entities into misleading canonical names.
        # Leave them identifiable as unknown mapping.
        return f"Unknown: {raw_entity.strip()}"


class DatabaseLoader:
    def __init__(self, db_path):
        self.db_path = db_path

    def load_extraction(self, extraction_data, canonicalizer):
        """
        Idempotent load of extraction JSON into SQLite database.
        """
        service_name = extraction_data.get("service_name")
        category = extraction_data.get("category")
        clauses = extraction_data.get("clauses", [])

        if not service_name:
            raise ValueError("Missing service_name in extraction data")

        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()

        try:
            # 1. Insert or get Service
            cursor.execute("INSERT OR IGNORE INTO services (name, category) VALUES (?, ?)", (service_name, category))
            cursor.execute("SELECT id FROM services WHERE name = ?", (service_name,))
            service_row = cursor.fetchone()
            if not service_row:
                raise RuntimeError("Failed to retrieve service_id")
            service_id = service_row[0]

            # Clear existing clauses for this service to ensure idempotence
            cursor.execute("DELETE FROM clauses WHERE service_id = ?", (service_id,))

            # 2. Process Clauses
            for clause in clauses:
                text = clause.get("text")
                severity = clause.get("severity_score")
                specificity = clause.get("specificity_score")
                risk_category = clause.get("risk_category")
                raw_entities = clause.get("entities", [])

                if not text:
                    continue

                # Idempotency check for clause (prevent duplicate clauses for same service)
                cursor.execute("""
                    SELECT id FROM clauses 
                    WHERE service_id = ? AND text = ?
                """, (service_id, text))
                clause_row = cursor.fetchone()

                if not clause_row:
                    cursor.execute("""
                        INSERT INTO clauses (service_id, text, severity_score, specificity_score, risk_category)
                        VALUES (?, ?, ?, ?, ?)
                    """, (service_id, text, severity, specificity, risk_category))
                    clause_id = cursor.lastrowid
                else:
                    clause_id = clause_row[0]

                # 3. Canonicalize and Insert Entities + Mapping
                for raw_entity in raw_entities:
                    canon_name = canonicalizer.canonicalize(raw_entity)
                    if not canon_name:
                        continue
                    
                    # Insert or get Canonical Entity
                    cursor.execute("INSERT OR IGNORE INTO canonical_entities (name) VALUES (?)", (canon_name,))
                    cursor.execute("SELECT id FROM canonical_entities WHERE name = ?", (canon_name,))
                    entity_row = cursor.fetchone()
                    if not entity_row:
                        raise RuntimeError("Failed to retrieve entity_id")
                    entity_id = entity_row[0]

                    # Insert mapping
                    cursor.execute("""
                        INSERT OR IGNORE INTO clause_entity_mapping (clause_id, entity_id)
                        VALUES (?, ?)
                    """, (clause_id, entity_id))
                    
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

def process_canonicalization(input_json_path, db_path):
    with open(input_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    canonicalizer = EntityCanonicalizer()
    loader = DatabaseLoader(db_path)
    loader.load_extraction(data, canonicalizer)
    
    print(f"Canonicalization and DB loading complete for {input_json_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Canonicalize entities and load to DB.")
    parser.add_argument("input_json", help="Path to extracted JSON file")
    
    args = parser.parse_args()
    
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    db_file_path = os.path.join(base_dir, 'data', 'db', 'portfolio.db')
    
    process_canonicalization(args.input_json, db_file_path)
