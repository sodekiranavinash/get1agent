"""Unit tests for the AgentSkills plugin builder (progressive disclosure)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow.skills import build_skills_plugin  # noqa: E402

try:  # The plugin builder imports Strands lazily; skip when it isn't installed.
    import strands  # noqa: F401

    HAS_STRANDS = True
except Exception:  # noqa: BLE001
    HAS_STRANDS = False


class BuildSkillsPluginTests(unittest.TestCase):
    def test_empty_returns_none(self) -> None:
        self.assertIsNone(build_skills_plugin([]))
        self.assertIsNone(build_skills_plugin([{"name": ""}]))

    @unittest.skipUnless(HAS_STRANDS, "strands is not installed")
    def test_builds_plugin_that_exposes_metadata_only(self) -> None:
        plugin = build_skills_plugin(
            [
                {
                    "id": "s1",
                    "name": "email-composer",
                    "description": "",
                    "allowedTools": ["http-fetch"],
                    "content": "Draft a professional email.",
                }
            ]
        )
        self.assertIsNotNone(plugin)

        skills = plugin.get_available_skills()
        self.assertEqual([skill.name for skill in skills], ["email-composer"])
        skill = skills[0]
        self.assertEqual(skill.instructions, "Draft a professional email.")
        self.assertEqual(skill.allowed_tools, ["http-fetch"])
        # A skill saved without a description still gets a non-empty one, because
        # the plugin renders it into the system prompt.
        self.assertTrue(skill.description)

        # Progressive disclosure: the system-prompt block carries the metadata but
        # never the instructions — those load only when the agent calls `skills`.
        xml = plugin._generate_skills_xml()
        self.assertIn("email-composer", xml)
        self.assertNotIn("Draft a professional email.", xml)


if __name__ == "__main__":
    unittest.main()
