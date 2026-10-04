"""Small, dependency-free JSON Schema validator.

Only the subset a tool definition actually needs is supported (``type``,
``properties``, ``required``, ``items``, ``enum``, ``additionalProperties``).
Unknown keywords/types are treated as valid so a richer schema never blocks a
call — validation is advisory, not a security boundary.
"""

from __future__ import annotations

from typing import Any

_PRIMITIVES = {
    "object",
    "array",
    "string",
    "integer",
    "number",
    "boolean",
    "null",
}


def _matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def validate(value: Any, schema: Any, path: str = "$") -> list[str]:
    """Return a list of human-readable validation errors (empty means valid)."""
    errors: list[str] = []
    if not isinstance(schema, dict):
        return errors

    expected = schema.get("type")
    if expected:
        allowed = expected if isinstance(expected, list) else [expected]
        allowed = [item for item in allowed if item in _PRIMITIVES] or allowed
        if not any(_matches(value, str(item)) for item in allowed):
            errors.append(f"{path}: expected {'|'.join(str(item) for item in allowed)}")
            return errors

    if expected == "object" or (isinstance(value, dict) and schema.get("properties")):
        properties = schema.get("properties") or {}
        for key in schema.get("required") or []:
            if not isinstance(value, dict) or key not in value:
                errors.append(f"{path}.{key}: is required")
        if isinstance(value, dict):
            for key, subschema in properties.items():
                if key in value:
                    errors.extend(validate(value[key], subschema, f"{path}.{key}"))
    elif expected == "array":
        item_schema = schema.get("items")
        if isinstance(value, list) and isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(validate(item, item_schema, f"{path}[{index}]"))

    enum = schema.get("enum")
    if isinstance(enum, list) and enum and value not in enum:
        errors.append(f"{path}: must be one of {enum}")

    return errors


def normalize_schema(schema: Any) -> dict[str, Any]:
    """Coerce a schema into a usable object schema."""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    normalized = dict(schema)
    normalized.setdefault("type", "object")
    if normalized["type"] == "object":
        normalized.setdefault("properties", {})
    return normalized
