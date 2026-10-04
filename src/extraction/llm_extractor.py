import os
import json
import urllib.request
import urllib.error

class LLMExtractor:
    def __init__(self, service_name, category=None):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
        self.service_name = service_name
        self.category = category

    def extract(self, candidate_clauses):
        """
        Sends candidate clauses to the LLM (or mock) and returns structured JSON.
        """
        if not candidate_clauses:
            return self._build_empty_response()
            
        if self.api_key:
            return self._call_real_llm(candidate_clauses)
        else:
            return self._call_mock_llm(candidate_clauses)

    def _build_empty_response(self):
        return {
            "service_name": self.service_name,
            "category": self.category or "Unknown",
            "mode": "EMPTY",
            "clauses": []
        }

    def _call_mock_llm(self, candidate_clauses):
        """
        Deterministic mock mode for local verification.
        """
        import re
        
        patterns = {
            "IP Address": r'\b(ip|ip address(?:es)?|internet protocol)\b',
            "Location": r'\b(location|gps|geolocation|coordinates)\b',
            "Email Address": r'\b(email|e-mail|email address(?:es)?)\b',
            "Phone Number": r'\b(phone|telephone|mobile(?: number)?|phone number(?:s)?)\b',
            "Name": r'\b(name|first name|last name|full name)\b',
            "Device Information": r'\b(device|device id|mac address|hardware model|operating system|os)\b',
            "Browser Information": r'\b(browser|browser type|user agent)\b',
            "Cookies": r'\b(cookie|cookies|web beacon(?:s)?|pixel tag(?:s)?)\b',
            "Usage Data": r'\b(usage data|log data|interaction|click(?:s)?|page view(?:s)?)\b',
            "Identifiers": r'\b(identifier|unique identifier(?:s)?|id)\b',
            "Account Information": r'\b(account|password|username|profile)\b',
            "Payment Information": r'\b(payment|credit card|billing|financial(?: information)?)\b',
            "Contact Information": r'\b(contact(?: information)?|address|postal)\b',
            "Biometric Data": r'\b(biometric|face|fingerprint|voiceprint)\b',
            "Precise Location": r'\b(precise location|exact location)\b',
            "Advertising Data": r'\b(advertis\w*|ad(?:s)?|marketing)\b',
            "Analytics Data": r'\b(analytic(?:s)?|measure(?:ment)?|performance)\b',
            "Communications": r'\b(message(?:s)?|communication(?:s)?|chat(?:s)?|correspondence)\b'
        }
        
        extracted_clauses = []
        for i, text in enumerate(candidate_clauses):
            # Deterministic dummy scoring
            severity = 3.0 + (i % 3)
            specificity = 2.0 + (i % 2)
            
            entities = []
            lower_text = text.lower()
            
            for entity_name, pattern in patterns.items():
                if re.search(pattern, lower_text):
                    entities.append(entity_name)
                    
            if not entities: 
                entities.append("General Data")
            
            extracted_clauses.append({
                "text": text,
                "entities": entities,
                "severity_score": float(severity),
                "specificity_score": float(specificity),
                "risk_category": "Mock Category"
            })
            
        return {
            "service_name": self.service_name,
            "category": self.category or "Unknown",
            "mode": "MOCK/DEV",
            "clauses": extracted_clauses
        }

    def _call_real_llm(self, candidate_clauses):
        """
        Real LLM implementation using Google Gemini API with fallback support.
        """
        system_prompt = (
            "Analyze the following privacy policy clauses. Synthesize and extract ONLY the top 15 most severe privacy risks. "
            "Do not return more than 15 clauses. Group similar concepts together to avoid repetition. "
            "For each clause, assign a severity (1-5), specificity (1-5), and a risk category. "
            "CRITICAL: For the 'entities' array, you MUST ONLY pick from this exact list, word-for-word: "
            "[Location, Precise Location, IP Address, Email, Phone Number, Device Information, Browser Information, Cookies, "
            "Usage Data, Identifiers, Account Information, Payment Information, Contact Information, Biometric Data, Advertising Data, "
            "Analytics Data, Communications]. Do not invent new entities like 'childrens data' or 'personal data'.\n"
            "Return strict JSON matching this schema:\n"
            "The JSON must have a single root key 'clauses' which is an array of objects. "
            "Each object must have 'text' (string), 'entities' (array of strings from the allowed list), "
            "'severity_score' (number), 'specificity_score' (number), and 'risk_category' (string)."
        )
        
        prompt = system_prompt + "\n\nInput Clauses:\n" + json.dumps(candidate_clauses)
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.0
            }
        }
        
        fallback_models = [
            "gemini-flash-lite-latest",
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-flash-latest",
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash"
        ]
        
        # If env var is explicitly set, try it first
        primary_model = os.environ.get("GEMINI_MODEL")
        if primary_model and primary_model not in fallback_models:
            fallback_models.insert(0, primary_model)

        last_error = None

        for current_model in fallback_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={self.api_key}"
            print(f"Calling Gemini API with URL: https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key=***")
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json"}
            )
            
            try:
                with urllib.request.urlopen(req) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    
                    try:
                        content = result['candidates'][0]['content']['parts'][0]['text']
                        parsed_content = json.loads(content)
                    except (KeyError, IndexError, json.JSONDecodeError):
                        raise RuntimeError(f"Malformed response from {current_model}.")
                    
                    if "clauses" not in parsed_content or not isinstance(parsed_content["clauses"], list):
                        raise RuntimeError(f"Missing required 'clauses' field in Gemini output from {current_model}.")
                        
                    parsed_content["service_name"] = self.service_name
                    if self.category:
                        parsed_content["category"] = self.category
                    parsed_content["mode"] = f"GEMINI ({current_model})"
                    return parsed_content
            except urllib.error.HTTPError as e:
                err_body = e.read().decode()
                last_error = f"HTTP {e.code} - {err_body}"
                if e.code in [503, 429, 404]:
                    print(f"Model {current_model} failed with {e.code}. Falling back to next...")
                    continue
                else:
                    raise RuntimeError(f"Gemini API HTTP error on {current_model}: {e.code} - {err_body}")
            except Exception as e:
                last_error = str(e)
                print(f"Model {current_model} exception: {e}. Falling back to next...")
                continue
                
        raise RuntimeError(f"All Gemini models exhausted. Last error: {last_error}")
