"""
tests/test_classifier.py
────────────────────────
Unit tests for the Prompt Intent Classifier.
"""

import unittest
from core.classifier import PromptClassifier


class TestPromptClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = PromptClassifier(mode="auto")

    def test_direct_greetings(self):
        for msg in ["hi", "hello there", "good morning", "hey", "who are you"]:
            route, _ = self.classifier.classify(msg)
            self.assertEqual(route, "DIRECT", f"Failed on: {msg}")

    def test_direct_questions(self):
        for msg in [
            "what is python?",
            "explain recursion in simple terms",
            "tell me how i can multiply 2 matrices.",
            "summarize this paragraph",
            "difference between sql and nosql",
        ]:
            route, _ = self.classifier.classify(msg)
            self.assertEqual(route, "DIRECT", f"Failed on: {msg}")

    def test_planning_triggers(self):
        for msg in [
            "refactor the entire auth module",
            "build a new web scraping pipeline",
            "find and fix all failing unit tests",
            "deploy the application to production step by step",
        ]:
            route, _ = self.classifier.classify(msg)
            self.assertEqual(route, "PLAN", f"Failed on: {msg}")

    def test_mode_overrides(self):
        always_plan = PromptClassifier(mode="always_plan")
        route, _ = always_plan.classify("hello")
        self.assertEqual(route, "PLAN")

        direct_only = PromptClassifier(mode="direct_only")
        route, _ = direct_only.classify("refactor everything and build a new service")
        self.assertEqual(route, "DIRECT")


if __name__ == "__main__":
    unittest.main()
