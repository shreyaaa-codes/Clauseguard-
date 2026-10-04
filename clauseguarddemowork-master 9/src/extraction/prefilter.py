import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import numpy as np

class PrivacyPrefilter:
    def __init__(self):
        self.vectorizer = TfidfVectorizer()
        self.classifier = LogisticRegression(random_state=42)
        self.is_trained = False
        
    def train(self, texts, labels):
        """
        Train the prefilter with a small labelled dataset.
        labels: 1 for privacy-relevant, 0 for not privacy-relevant.
        """
        X = self.vectorizer.fit_transform(texts)
        self.classifier.fit(X, labels)
        self.is_trained = True

    def train_with_minimal_fixture(self):
        """
        Loads a minimal hardcoded training set for baseline initialization.
        NOTE: This is a DEVELOPMENT/DEMO fallback. It is not a production ML classifier.
        It exists solely to allow the pipeline to run locally without a real trained model.
        In a production environment, a properly trained serialized model (e.g., joblib/pickle)
        should be loaded instead of training on 8 sentences.
        """
        texts = [
            "We share your location data with marketing partners.",
            "You can opt out of data sharing in your account settings.",
            "We collect cookies to improve site performance.",
            "Click here to reset your password.",
            "The app requires an internet connection to stream music.",
            "Welcome to the user manual.",
            "Your IP address is logged for security purposes.",
            "Contact customer support if the app crashes."
        ]
        labels = [1, 1, 1, 0, 0, 0, 1, 0]
        self.train(texts, labels)

    def filter_candidates(self, clauses):
        """
        Filters a list of clauses, returning only those predicted as privacy-relevant.
        """
        if not self.is_trained:
            self.train_with_minimal_fixture()
            
        if not clauses:
            return []
            
        X = self.vectorizer.transform(clauses)
        predictions = self.classifier.predict(X)
        
        return [clause for clause, pred in zip(clauses, predictions) if pred == 1]
