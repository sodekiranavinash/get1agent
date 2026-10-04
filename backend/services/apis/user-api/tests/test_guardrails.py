"""Unit tests for the Bedrock guardrail policy mapping (pure functions).

Run with: ``make -C backend/services/apis/user-api test``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from core import guardrails  # noqa: E402


class DefaultPolicyTests(unittest.TestCase):
    def test_default_has_all_content_filters(self) -> None:
        config = guardrails.default_policy_config()
        types = {item["type"] for item in config["contentFilters"]}
        self.assertEqual(types, set(guardrails.CONTENT_FILTER_TYPES))

    def test_default_prompt_attack_only_filters_input(self) -> None:
        config = guardrails.default_policy_config()
        prompt_attack = next(
            item for item in config["contentFilters"] if item["type"] == "PROMPT_ATTACK"
        )
        self.assertEqual(prompt_attack["outputStrength"], "NONE")


class PolicyMappingTests(unittest.TestCase):
    def test_empty_config_maps_to_nothing(self) -> None:
        self.assertEqual(guardrails.policy_config_kwargs({}), {})
        self.assertEqual(guardrails.policy_config_kwargs(None), {})

    def test_prompt_attack_output_strength_is_none(self) -> None:
        kwargs = guardrails.policy_config_kwargs(
            {
                "contentFilters": [
                    {
                        "type": "PROMPT_ATTACK",
                        "inputStrength": "HIGH",
                        "outputStrength": "HIGH",
                    }
                ]
            }
        )
        filters = kwargs["contentPolicyConfig"]["filtersConfig"]
        self.assertEqual(filters[0]["outputStrength"], "NONE")

    def test_unknown_content_filter_is_dropped(self) -> None:
        kwargs = guardrails.policy_config_kwargs(
            {"contentFilters": [{"type": "NOT_A_FILTER"}]}
        )
        self.assertNotIn("contentPolicyConfig", kwargs)

    def test_denied_topics_require_name_and_definition(self) -> None:
        kwargs = guardrails.policy_config_kwargs(
            {
                "deniedTopics": [
                    {
                        "name": "Medical",
                        "definition": "Give medical advice",
                        "examples": ["a", "b", "c", "d", "e", "f"],
                    },
                    {"name": "", "definition": "ignored"},
                ]
            }
        )
        topics = kwargs["topicPolicyConfig"]["topicsConfig"]
        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]["type"], "DENY")
        self.assertEqual(len(topics[0]["examples"]), 5)

    def test_word_policy_profanity_and_words(self) -> None:
        kwargs = guardrails.policy_config_kwargs(
            {"wordFilters": {"profanity": True, "words": ["xyz"]}}
        )
        self.assertEqual(kwargs["wordPolicyConfig"]["wordsConfig"], [{"text": "xyz"}])
        self.assertEqual(
            kwargs["wordPolicyConfig"]["managedWordListsConfig"],
            [{"type": "PROFANITY"}],
        )

    def test_sensitive_information(self) -> None:
        kwargs = guardrails.policy_config_kwargs(
            {
                "sensitiveInfo": {
                    "pii": [
                        {"type": "EMAIL", "action": "ANONYMIZE"},
                        {"type": "NAME", "action": "BOGUS"},
                    ],
                    "regexes": [
                        {"name": "acct", "pattern": r"\d{4}", "action": "BLOCK"},
                        {"name": "", "pattern": "x"},
                    ],
                }
            }
        )
        sensitive = kwargs["sensitiveInformationPolicyConfig"]
        pii = sensitive["piiEntitiesConfig"]
        self.assertEqual(pii[0], {"type": "EMAIL", "action": "ANONYMIZE"})
        self.assertEqual(pii[1]["action"], "ANONYMIZE")
        regexes = sensitive["regexesConfig"]
        self.assertEqual(len(regexes), 1)
        self.assertEqual(regexes[0]["action"], "BLOCK")

    def test_contextual_grounding_threshold_clamped(self) -> None:
        kwargs = guardrails.policy_config_kwargs(
            {
                "contextualGrounding": [
                    {"type": "GROUNDING", "threshold": 3.5, "action": "BLOCK"},
                    {"type": "NOPE", "threshold": 0.5},
                    {"type": "RELEVANCE", "threshold": "bad", "action": "NONE"},
                ]
            }
        )
        filters = kwargs["contextualGroundingPolicyConfig"]["filtersConfig"]
        self.assertEqual(len(filters), 2)
        self.assertEqual(filters[0]["threshold"], 0.99)
        self.assertEqual(filters[1]["threshold"], 0.7)
        self.assertEqual(filters[1]["action"], "NONE")


if __name__ == "__main__":
    unittest.main()
