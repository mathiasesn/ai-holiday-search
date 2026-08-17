# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-08-04

### Changed

- Restructured the repository so it works simultaneously as a Claude Code plugin and
  as a standalone clone. `commands/` and `skills/` moved to the repo root, with
  tracked symlinks left at `.claude/commands` and `.claude/skills` so a plain clone
  continues to work exactly as before.
- Added `.claude-plugin/plugin.json`, declaring the repo as an installable Claude
  Code plugin (`ai-holiday-search`), relying on default discovery of the top-level
  `commands/`, `skills/`, and `.mcp.json`.
- Added `.claude-plugin/marketplace.json`, declaring this repository as a
  single-plugin marketplace so it can be added directly via its `./` source.
