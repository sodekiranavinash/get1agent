"""Unit tests for the dependency-free JSON Schema validator."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))

from src import schema  # noqa: E402


class SchemaValidationTests(unittest.TestCase):
    def test_required_and_types(self) -> None:
        spec = {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "days": {"type": "integer"},
            },
            "required": ["city"],
        }
        self.assertEqual(schema.validate({"city": "Paris", "days": 3}, spec), [])
        self.assertEqual(len(schema.validate({"days": 3}, spec)), 1)
        errors = schema.validate({"city": 5}, spec)
        self.assertTrue(any("city" in error for error in errors))

    def test_boolean_is_not_integer(self) -> None:
        errors = schema.validate(True, {"type": "integer"})
        self.assertEqual(len(errors), 1)

    def test_enum(self) -> None:
        spec = {"type": "string", "enum": ["a", "b"]}
        self.assertEqual(schema.validate("a", spec), [])
        self.assertEqual(len(schema.validate("c", spec)), 1)

    def test_array_items(self) -> None:
        spec = {"type": "array", "items": {"type": "string"}}
        self.assertEqual(schema.validate(["a", "b"], spec), [])
        self.assertEqual(len(schema.validate(["a", 2], spec)), 1)

    def test_unknown_type_is_lenient(self) -> None:
        self.assertEqual(schema.validate("anything", {"type": "mystery"}), [])

    def test_normalize_schema(self) -> None:
        self.assertEqual(
            schema.normalize_schema(None), {"type": "object", "properties": {}}
        )


if __name__ == "__main__":
    unittest.main()
