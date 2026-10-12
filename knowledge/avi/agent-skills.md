---
id: agent-skills
title: Agent skills
route: "/agent-skills"
group: Resources
audience: user
source: docs
tags: [docs, resources]
---

## Agent skills

Reusable instructions in Strands format, with marketplace and registry discovery and an importer.

A skill is a markdown document with YAML frontmatter — name, description and allowed-tools — plus a body of instructions. The body is only loaded when the agent decides a skill applies (progressive disclosure), so a workspace can hold many skills without bloating every prompt. The allowed-tools field lists whole MCP servers, not individual tools.

The page has three tabs: All (your skills), Marketplace (the curated One Agent Marketplace) and Skills Registry (the public registry). A kind filter narrows results to Prompt-only or Tool-based skills.

## Agent skills

1. To author your own, create a skill in the editor: set the name, description and allowed MCP servers (the built-ins code-interpreter, web-search, http-fetch and storage are always offered), then write the body — or upload an existing .md file and let the parser fill the fields.
2. To browse, open the Marketplace or Skills Registry tab, optionally filter by kind, and search.
3. To import, click Import on a card. An import preview fetches and parses the skill; choose the name and which MCP servers to grant, then confirm.
4. To import from a repository, use resolve-repo with an owner/repo reference to list the SKILL.md files it contains, then preview and import.
5. Edit or delete your skills from the All tab. Editing opens the same editor with the frontmatter in separate fields.
6. Attach skills in the Agent builder’s Skills card. Selecting a skill auto-adds the servers it declares.

## Agent skills

- Names are lowercase-hyphen, 1–64 characters and unique per user.
- Imported registry skills are third-party instructions; the editor shows a prompt-injection warning.
- The body is never sent to the model up front — only the skill name and description are injected until the agent activates it.

**Limits** — Up to 50 skills per user and 100 KB per skill.
