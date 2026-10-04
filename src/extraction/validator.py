class ValidationError(Exception):
    pass

def validate_extraction_output(data):
    """
    Validates the structured JSON against the Stage 1 data contract.
    Throws ValidationError if invalid.
    """
    if not isinstance(data, dict):
        raise ValidationError("Top-level output must be a dictionary.")
        
    if "service_name" not in data or not isinstance(data["service_name"], str):
        raise ValidationError("Missing or invalid 'service_name' string.")
        
    if "clauses" not in data or not isinstance(data["clauses"], list):
        raise ValidationError("Missing or invalid 'clauses' array.")
        
    for i, clause in enumerate(data["clauses"]):
        if not isinstance(clause, dict):
            raise ValidationError(f"Clause at index {i} must be a dictionary.")
            
        if "text" not in clause or not isinstance(clause["text"], str):
            raise ValidationError(f"Clause at index {i} missing valid 'text' string.")
            
        if "entities" not in clause or not isinstance(clause["entities"], list):
            raise ValidationError(f"Clause at index {i} missing valid 'entities' array.")
            
        for entity in clause["entities"]:
            if not isinstance(entity, str):
                raise ValidationError(f"Clause at index {i} contains non-string entity.")
                
        if "severity_score" in clause:
            if not isinstance(clause["severity_score"], (int, float)):
                raise ValidationError(f"Clause at index {i} has non-numeric 'severity_score'.")
                
        if "specificity_score" in clause:
            if not isinstance(clause["specificity_score"], (int, float)):
                raise ValidationError(f"Clause at index {i} has non-numeric 'specificity_score'.")
                
        if "risk_category" in clause:
            if not isinstance(clause["risk_category"], str):
                raise ValidationError(f"Clause at index {i} has non-string 'risk_category'.")
                
    return True
