#!/usr/bin/env python3
"""lint_skills.py — validate SKILL.md / command frontmatter and cross-links.

Checks (stdlib only, no PyYAML):
  1. Every `.claude/skills/**/SKILL.md` and `.agents/skills/**/SKILL.md` has
     parseable YAML-ish frontmatter with non-empty `name` and `description`,
     and `name` matches its parent directory name.
  2. Every `.claude/commands/*.md` has frontmatter with a non-empty `description`.
  3. Every relative Markdown link/reference in those files resolves to an
     existing path (relative to the linked-from file's directory).
  4. Every `.agents/skills/*/` directory contains both a `SKILL.md` and an
     executable `search.py`.

Exit 0 on success; non-zero with actionable per-file messages on failure.
"""
import os
import re
import stat
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def find_files(patterns_root, filename):
    """Yield paths under patterns_root matching exactly `filename`, any depth."""
    results = []
    if not os.path.isdir(patterns_root):
        return results
    for dirpath, _dirnames, filenames in os.walk(patterns_root):
        if filename in filenames:
            results.append(os.path.join(dirpath, filename))
    return results


def parse_frontmatter(path):
    """Hand-rolled minimal YAML frontmatter parser: returns dict of top-level
    scalar string keys, or None if no frontmatter block is present.

    Only handles simple `key: value` pairs (values may be quoted). Good enough
    for the flat frontmatter used by SKILL.md / command files in this repo.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    if not text.startswith("---"):
        return None, text

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None, text

    fm = {}
    for line in lines[1:end_idx]:
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        fm[key] = value

    body = "\n".join(lines[end_idx + 1 :])
    return fm, body


def check_skill_file(path, errors):
    fm, body = parse_frontmatter(path)
    dir_name = os.path.basename(os.path.dirname(path))
    rel = os.path.relpath(path, REPO_ROOT)

    if fm is None:
        errors.append(f"{rel}: missing or malformed YAML frontmatter (expected leading '---' block)")
        return body

    name = fm.get("name", "")
    description = fm.get("description", "")

    if not name:
        errors.append(f"{rel}: frontmatter missing non-empty 'name'")
    elif name != dir_name:
        errors.append(f"{rel}: frontmatter name '{name}' does not match parent directory name '{dir_name}'")

    if not description:
        errors.append(f"{rel}: frontmatter missing non-empty 'description'")

    return body


def check_command_file(path, errors):
    fm, body = parse_frontmatter(path)
    rel = os.path.relpath(path, REPO_ROOT)

    if fm is None:
        errors.append(f"{rel}: missing or malformed YAML frontmatter (expected leading '---' block)")
        return body

    description = fm.get("description", "")
    if not description:
        errors.append(f"{rel}: frontmatter missing non-empty 'description'")

    return body


def check_links(path, body, errors):
    rel = os.path.relpath(path, REPO_ROOT)
    base_dir = os.path.dirname(path)
    for match in MD_LINK_RE.finditer(body):
        target = match.group(1).strip()
        # Skip external links, anchors, and mailto/absolute-url schemes.
        if not target or target.startswith("#"):
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
            continue
        if target.startswith("mailto:"):
            continue
        # Strip a trailing #anchor fragment.
        target_path = target.split("#", 1)[0]
        if not target_path:
            continue
        resolved = os.path.normpath(os.path.join(base_dir, target_path))
        if not os.path.exists(resolved):
            errors.append(f"{rel}: relative link target does not exist: '{target}' (resolved to {os.path.relpath(resolved, REPO_ROOT)})")


def check_agents_skills_structure(errors):
    agents_skills_dir = os.path.join(REPO_ROOT, ".agents", "skills")
    if not os.path.isdir(agents_skills_dir):
        errors.append(".agents/skills/: directory does not exist")
        return
    for entry in sorted(os.listdir(agents_skills_dir)):
        entry_path = os.path.join(agents_skills_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        rel = os.path.relpath(entry_path, REPO_ROOT)
        skill_md = os.path.join(entry_path, "SKILL.md")
        search_py = os.path.join(entry_path, "search.py")
        if not os.path.isfile(skill_md):
            errors.append(f"{rel}: missing SKILL.md")
        if not os.path.isfile(search_py):
            errors.append(f"{rel}: missing search.py")
        elif not os.access(search_py, os.X_OK):
            errors.append(f"{rel}/search.py: not executable (chmod +x)")


def main():
    errors = []

    skill_files = find_files(os.path.join(REPO_ROOT, ".claude", "skills"), "SKILL.md")
    skill_files += find_files(os.path.join(REPO_ROOT, ".agents", "skills"), "SKILL.md")

    for path in sorted(set(skill_files)):
        body = check_skill_file(path, errors)
        check_links(path, body, errors)

    commands_dir = os.path.join(REPO_ROOT, ".claude", "commands")
    if os.path.isdir(commands_dir):
        for name in sorted(os.listdir(commands_dir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(commands_dir, name)
            body = check_command_file(path, errors)
            check_links(path, body, errors)

    check_agents_skills_structure(errors)

    if errors:
        sys.stderr.write("lint_skills.py: FAILED\n")
        for e in errors:
            sys.stderr.write(f"  - {e}\n")
        sys.stderr.write(f"\n{len(errors)} issue(s) found.\n")
        return 1

    print("lint_skills.py: OK — all SKILL.md / command frontmatter and links valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
