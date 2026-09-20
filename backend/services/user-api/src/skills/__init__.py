"""Strands-format agent skills: spec, validation and frontmatter (de)serialization.

A skill is a YAML frontmatter block followed by a markdown body:

    ---
    name: pdf-processing
    description: Extract text and tables from PDF files
    allowed-tools: file_read shell
    ---
    # PDF processing

    You are a PDF processing expert...

The frontmatter fields are stored in their own database columns so an agent can
read the cheap metadata first and only pull the full body when it decides the
skill applies. ``render_skill_markdown`` re-assembles the exact strands format.
"""

from src.skills.catalog import entries as catalog_entries
from src.skills.fetch import FetchError
from src.skills.frontmatter import parse_skill_markdown, render_skill_markdown
from src.skills.importer import load as load_imported_skill
from src.skills.registry import search_registry
from src.skills.repo_resolver import RepoError, resolve as resolve_repo
from src.skills.spec import (
    DEFAULT_TOOLS,
    MAX_ALLOWED_TOOLS,
    MAX_DESCRIPTION_LENGTH,
    MAX_SKILLS_PER_USER,
    MAX_SKILL_CONTENT_BYTES,
    SKILL_NAME_MAX,
    SKILL_NAME_MIN,
    normalize_allowed_tools,
    validate_skill_name,
)

__all__ = [
    "DEFAULT_TOOLS",
    "FetchError",
    "MAX_ALLOWED_TOOLS",
    "MAX_DESCRIPTION_LENGTH",
    "MAX_SKILLS_PER_USER",
    "MAX_SKILL_CONTENT_BYTES",
    "RepoError",
    "SKILL_NAME_MAX",
    "SKILL_NAME_MIN",
    "catalog_entries",
    "load_imported_skill",
    "normalize_allowed_tools",
    "parse_skill_markdown",
    "render_skill_markdown",
    "resolve_repo",
    "search_registry",
    "validate_skill_name",
]
