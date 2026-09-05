"""
Deterministic AI Evaluation Harness Template
Demonstrates schema conformance, constraint checking, and deterministic scoring.
"""

import json
import unittest
from typing import List, Literal


class LLMStructuredOutput:
    """Lightweight data contract validator."""

    def __init__(self, summary: str, sentiment: str, key_entities: List[str], confidence_score: float):
        if not (10 <= len(summary) <= 500):
            raise ValueError("Summary must be between 10 and 500 characters")
        if sentiment not in ("positive", "neutral", "negative"):
            raise ValueError(f"Invalid sentiment: {sentiment}")
        if not (0.0 <= confidence_score <= 1.0):
            raise ValueError("Confidence score must be between 0.0 and 1.0")

        self.summary = summary
        self.sentiment = sentiment
        self.key_entities = key_entities
        self.confidence_score = confidence_score


def mock_ai_pipeline(prompt: str) -> str:
    """Mock representing the actual LLM call or agent response."""
    return json.dumps({
        "summary": "The system design review concluded that PostgreSQL is optimal.",
        "sentiment": "positive",
        "key_entities": ["PostgreSQL", "System Design"],
        "confidence_score": 0.95
    })


class TestAIPipelineEvals(unittest.TestCase):
    """Deterministic evaluation test suite."""

    def test_structural_schema_conformance(self):
        raw_output = mock_ai_pipeline("Evaluate database choices.")
        data = json.loads(raw_output)
        validated = LLMStructuredOutput(
            summary=data["summary"],
            sentiment=data["sentiment"],
            key_entities=data["key_entities"],
            confidence_score=data["confidence_score"]
        )
        self.assertGreaterEqual(validated.confidence_score, 0.8)
        self.assertIn("PostgreSQL", validated.key_entities)

    def test_invariant_constraints(self):
        raw_output = mock_ai_pipeline("Evaluate database choices.")
        data = json.loads(raw_output)
        
        # Verify no forbidden leakages
        forbidden_terms = ["password", "secret_key", "undefined"]
        for term in forbidden_terms:
            self.assertNotIn(term, json.dumps(data).lower(), f"Forbidden term '{term}' leaked in output!")


if __name__ == "__main__":
    unittest.main()
