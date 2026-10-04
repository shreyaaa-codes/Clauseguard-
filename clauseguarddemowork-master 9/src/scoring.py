import sqlite3

class ScoringEngine:
    def __init__(self, w1=1.0, w2=1.0):
        # Default weights. Plan states uniform starting assumption.
        self.w1 = w1
        self.w2 = w2

    def calculate_clause_score(self, severity, specificity):
        """
        Calculates the deterministic risk score for a single clause.
        Formula: (w1 * severity) + (w2 * specificity)
        """
        sev = float(severity) if severity is not None else 0.0
        spec = float(specificity) if specificity is not None else 0.0
        return (self.w1 * sev) + (self.w2 * spec)

    def calculate_service_score_from_clauses(self, clauses):
        """
        Calculates the risk score for a service by aggregating its clauses.
        Assumption: Sum aggregation (as the Mean vs Sum decision is explicitly deferred to Phase 2).
        """
        return sum(self.calculate_clause_score(c['severity_score'], c['specificity_score']) for c in clauses)

    def get_portfolio_data(self, db_path, exclude_service_name=None):
        """
        Extracts the portfolio structure and calculates baseline risk.
        Returns a structured dictionary of the portfolio.
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all services
        cursor.execute("SELECT id, name FROM services")
        services = cursor.fetchall()
        
        portfolio_score = 0.0
        service_details = []
        portfolio_entities = set()
        
        for service_id, service_name in services:
            if exclude_service_name and service_name == exclude_service_name:
                continue
                
            # Get clauses for service
            cursor.execute("SELECT id, severity_score, specificity_score FROM clauses WHERE service_id = ?", (service_id,))
            clauses = cursor.fetchall()
            
            clause_dicts = [{'severity_score': c[1], 'specificity_score': c[2]} for c in clauses]
            svc_score = self.calculate_service_score_from_clauses(clause_dicts)
            portfolio_score += svc_score
            
            # Get entities for service
            cursor.execute("""
                SELECT ce.name 
                FROM canonical_entities ce
                JOIN clause_entity_mapping cem ON ce.id = cem.entity_id
                JOIN clauses c ON cem.clause_id = c.id
                WHERE c.service_id = ?
            """, (service_id,))
            entities = {row[0] for row in cursor.fetchall()}
            portfolio_entities.update(entities)
            
            service_details.append({
                "service_name": service_name,
                "service_score": svc_score,
                "entities": list(entities)
            })
            
        conn.close()
        
        return {
            "portfolio_score": portfolio_score,
            "services": service_details,
            "all_canonical_entities": list(portfolio_entities)
        }
