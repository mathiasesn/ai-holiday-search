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
import json
import os
import re
import subprocess
import sys

from _repo import repo_root, ignored_paths

REPO_ROOT = repo_root()

MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
BACKTICK_PATH_RE = re.compile(r"`([^`\s]+\.(?:md|py))`")
# Only treat a backticked string as a literal repo-relative path reference if
# it looks like one: word/dot/slash/dash characters only, at least one path
# separator, ending in .md or .py. Anything else (placeholder syntax like
# `<name>`, `foo/*.md`, `{a,b}.py`, `...`) is left alone rather than
# special-cased — new doc notations no longer need a matching lint update.
LITERAL_PATH_RE = re.compile(r"^[\w./-]+\.(?:md|py)$")


def find_files(patterns_root, filename):
    """Yield paths under patterns_root matching exactly `filename`, any depth."""
    results = []
    if not os.path.isdir(patterns_root):
        return results
    for dirpath, _dirnames, filenames in os.walk(patterns_root):
        if filename in filenames:
            results.append(os.path.join(dirpath, filename))
    return results


def parse_frontmatter(path, errors):
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
    rel = os.path.relpath(path, REPO_ROOT)
    last_key = None
    for offset, line in enumerate(lines[1:end_idx]):
        line_no = offset + 2  # 1-indexed, line 1 is the opening '---'
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in line and not line[:1].isspace():
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
                value = value[1:-1]
            fm[key] = value
            last_key = key
            continue
        if line[:1].isspace() and last_key is not None:
            # Continuation of the previous value (e.g. wrapped multi-line text).
            continue
        errors.append(f"{rel}:{line_no}: malformed frontmatter line (not 'key: value', a comment, blank, or a continuation): {stripped!r}")

    body = "\n".join(lines[end_idx + 1 :])
    return fm, body


def check_frontmatter_file(path, errors, required_keys):
    """Validate a file's frontmatter has non-empty values for `required_keys`.

    If `name` is among the required keys, it must also match the parent
    directory name (SKILL.md convention). Used for both SKILL.md and command
    files — they differ only in which keys are required.
    """
    fm, body = parse_frontmatter(path, errors)
    rel = os.path.relpath(path, REPO_ROOT)

    if fm is None:
        errors.append(f"{rel}: missing or malformed YAML frontmatter (expected leading '---' block)")
        return body

    for key in required_keys:
        value = fm.get(key, "")
        if not value:
            errors.append(f"{rel}: frontmatter missing non-empty '{key}'")
        elif key == "name":
            dir_name = os.path.basename(os.path.dirname(path))
            if value != dir_name:
                errors.append(f"{rel}: frontmatter name '{value}' does not match parent directory name '{dir_name}'")

    return body


def check_links(path, body, errors):
    rel = os.path.relpath(path, REPO_ROOT)
    base_dir = os.path.dirname(path)
    for match in MD_LINK_RE.finditer(body):
        target = match.group(1).strip()
        # Skip external links, anchors, and mailto/absolute-url schemes.
        if not target or target.startswith("#"):
            continue
        if URL_SCHEME_RE.match(target):
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

    backtick_targets = []
    for match in BACKTICK_PATH_RE.finditer(body):
        target = match.group(1)
        # Only validate backticked strings that look like literal
        # repo-relative paths (word/dot/slash/dash chars, contains a '/',
        # ends .md/.py). Placeholder notation (`<name>`, `foo/*.md`,
        # `{a,b}.py`, `...`) doesn't match and is left alone.
        if "/" not in target or not LITERAL_PATH_RE.fullmatch(target):
            continue
        backtick_targets.append(target)

    if backtick_targets:
        ignored = ignored_paths(backtick_targets, root=REPO_ROOT)
        for target in backtick_targets:
            # Skip paths under gitignored personal-data dirs — these are
            # runtime paths written by /setup, /scrape, /watch, /plan, never
            # tracked in git.
            if target in ignored:
                continue
            resolved = os.path.normpath(os.path.join(REPO_ROOT, target))
            if not os.path.exists(resolved):
                errors.append(f"{rel}: backticked repo-relative path does not exist: '{target}' (resolved to {os.path.relpath(resolved, REPO_ROOT)})")


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


def check_adapter_contract(errors):
    """Assert the three .agents/skills/*/search.py adapters agree on their
    no-credentials contract.

    A shared adapter module was deliberately rejected (it would break the
    documented copy-a-folder fork workflow), so the three adapters stay
    intentionally near-duplicated. This guards the duplication instead:
    each adapter's `--json` no-credentials path (run with credentials env
    vars unset) must exit 2, print exactly one JSON object, and every
    adapter must agree on the same top-level key set, `status` ==
    "no_credentials", and `fallback` == "web_search".
    """
    agents_skills_dir = os.path.join(REPO_ROOT, ".agents", "skills")
    if not os.path.isdir(agents_skills_dir):
        return

    env_vars_to_unset = (
        "AMADEUS_API_KEY",
        "AMADEUS_API_SECRET",
        "STAYS_API_KEY",
        "STAYS_API_URL",
        "PACKAGES_API_KEY",
        "PACKAGES_API_URL",
    )

    contracts = []  # list of (rel, keys_set, status, fallback)
    for entry in sorted(os.listdir(agents_skills_dir)):
        search_py = os.path.join(agents_skills_dir, entry, "search.py")
        if not os.path.isfile(search_py):
            continue
        rel = os.path.relpath(search_py, REPO_ROOT)

        env = {k: v for k, v in os.environ.items() if k not in env_vars_to_unset}
        try:
            result = subprocess.run(
                [sys.executable, search_py, "--json"],
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            errors.append(f"{rel}: failed to execute no-credentials path: {e}")
            continue

        if result.returncode != 2:
            errors.append(f"{rel}: no-credentials path exited {result.returncode}, expected 2")
            continue

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            errors.append(f"{rel}: no-credentials path did not print one JSON object: {e}")
            continue

        if not isinstance(payload, dict):
            errors.append(f"{rel}: no-credentials JSON output is not an object")
            continue

        contracts.append((rel, frozenset(payload.keys()), payload.get("status"), payload.get("fallback")))

    if not contracts:
        return

    ref_rel, ref_keys, ref_status, ref_fallback = contracts[0]
    if ref_status != "no_credentials":
        errors.append(f"{ref_rel}: no-credentials JSON 'status' is {ref_status!r}, expected 'no_credentials'")
    if ref_fallback != "web_search":
        errors.append(f"{ref_rel}: no-credentials JSON 'fallback' is {ref_fallback!r}, expected 'web_search'")

    for rel, keys, status, fallback in contracts[1:]:
        if keys != ref_keys:
            errors.append(
                f"{rel}: no-credentials JSON keys {sorted(keys)} differ from {ref_rel}'s {sorted(ref_keys)}"
            )
        if status != "no_credentials":
            errors.append(f"{rel}: no-credentials JSON 'status' is {status!r}, expected 'no_credentials'")
        if fallback != "web_search":
            errors.append(f"{rel}: no-credentials JSON 'fallback' is {fallback!r}, expected 'web_search'")


def main():
    errors = []

    skill_files = find_files(os.path.join(REPO_ROOT, ".claude", "skills"), "SKILL.md")
    skill_files += find_files(os.path.join(REPO_ROOT, ".agents", "skills"), "SKILL.md")

    for path in sorted(set(skill_files)):
        body = check_frontmatter_file(path, errors, required_keys=("name", "description"))
        check_links(path, body, errors)

    commands_dir = os.path.join(REPO_ROOT, ".claude", "commands")
    if os.path.isdir(commands_dir):
        for name in sorted(os.listdir(commands_dir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(commands_dir, name)
            body = check_frontmatter_file(path, errors, required_keys=("description",))
            check_links(path, body, errors)

    check_agents_skills_structure(errors)
    check_adapter_contract(errors)

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
