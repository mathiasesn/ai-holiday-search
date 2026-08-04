#!/usr/bin/env python3
"""lint_skills.py — validate SKILL.md / command frontmatter and cross-links.

Scans the real top-level `commands/` and `skills/` directories (never the
`.claude/commands` / `.claude/skills` symlinks that alias them for clone
mode — walking into a symlinked directory and handing the resulting paths to
`git check-ignore` fails with "beyond a symbolic link"), plus the portable
`.agents/skills/`.

Checks (stdlib only, no PyYAML):
  1. Every `skills/**/SKILL.md` and `.agents/skills/**/SKILL.md` has
     parseable YAML-ish frontmatter with non-empty `name` and `description`,
     and `name` matches its parent directory name.
  2. Every `commands/*.md` has frontmatter with a non-empty `description`.
  3. Every relative Markdown link/reference in those files resolves to an
     existing path (relative to the linked-from file's directory). Targets
     containing a `<FRAMEWORK_ROOT>/...` placeholder are checked against the
     repo root (FRAMEWORK_ROOT == repo root in clone mode); targets
     containing `<DATA_ROOT>` or any other `<...>` placeholder are runtime
     paths and are skipped.
  4. Every `.agents/skills/*/` directory contains both a `SKILL.md` and an
     executable `search.py`.
  5. All five `commands/*.md` carry a byte-identical
     "## Path resolution (framework root and data root)" block.
  6. No framework Markdown under `commands/`/`skills/` reintroduces a
     repo-relative reference to `.claude/`, an unrooted
     `.agents/skills/*/search.py` invocation, or an unrooted write target
     under `profile/`, `itineraries/`, `watchlist/`, `trip_scraper/`, or
     `trip_tracker.csv`.
  7. `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` are
     valid JSON, declare the same `version`, that version has a matching
     `CHANGELOG.md` entry, the marketplace plugin entry's `name` matches
     plugin.json's `name`, and that name is valid kebab-case.
  8. `.claude/commands` and `.claude/skills` are tracked as git symlinks
     (mode 120000) resolving to the top-level `commands/`/`skills/` dirs.

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
FRAMEWORK_ROOT_BACKTICK_RE = re.compile(r"^<FRAMEWORK_ROOT>/([\w./-]+\.(?:md|py))$")
PLACEHOLDER_TOKEN_RE = re.compile(r"<[A-Za-z_]+>")

PATH_BLOCK_HEADER = "## Path resolution (framework root and data root)"


def find_files(patterns_root, filename):
    """Yield paths under patterns_root matching exactly `filename`, any depth.

    Prunes symlinked subdirectories during traversal so this never wanders
    into a `.claude/` alias (or any other symlinked tree) and hands a
    beyond-a-symlink path to git.
    """
    results = []
    if not os.path.isdir(patterns_root):
        return results
    for dirpath, dirnames, filenames in os.walk(patterns_root):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        if filename in filenames:
            results.append(os.path.join(dirpath, filename))
    return results


def find_command_files(commands_dir):
    if not os.path.isdir(commands_dir) or os.path.islink(commands_dir):
        return []
    return [
        os.path.join(commands_dir, name)
        for name in sorted(os.listdir(commands_dir))
        if name.endswith(".md")
    ]


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

        if target_path.startswith("<FRAMEWORK_ROOT>/"):
            remainder = target_path[len("<FRAMEWORK_ROOT>/") :]
            resolved = os.path.normpath(os.path.join(REPO_ROOT, remainder))
        elif PLACEHOLDER_TOKEN_RE.search(target_path):
            # <DATA_ROOT>/... (runtime-generated) or any other placeholder
            # notation is not a literal repo path — nothing to check.
            continue
        else:
            resolved = os.path.normpath(os.path.join(base_dir, target_path))

        if not os.path.exists(resolved):
            errors.append(f"{rel}: relative link target does not exist: '{target}' (resolved to {os.path.relpath(resolved, REPO_ROOT)})")

    literal_targets = []
    rooted_targets = []  # (original, remainder-relative-to-repo-root)
    for match in BACKTICK_PATH_RE.finditer(body):
        target = match.group(1)
        rooted = FRAMEWORK_ROOT_BACKTICK_RE.match(target)
        if rooted:
            rooted_targets.append((target, rooted.group(1)))
            continue
        if PLACEHOLDER_TOKEN_RE.search(target):
            # <DATA_ROOT>/... or any other placeholder — runtime path, skip.
            continue
        # Only validate backticked strings that look like literal
        # repo-relative paths (word/dot/slash/dash chars, contains a '/',
        # ends .md/.py). Placeholder notation (`<name>`, `foo/*.md`,
        # `{a,b}.py`, `...`) doesn't match and is left alone.
        if "/" not in target or not LITERAL_PATH_RE.fullmatch(target):
            continue
        literal_targets.append(target)

    for target, remainder in rooted_targets:
        resolved = os.path.normpath(os.path.join(REPO_ROOT, remainder))
        if not os.path.exists(resolved):
            errors.append(f"{rel}: backticked <FRAMEWORK_ROOT>-rooted path does not exist: '{target}' (resolved to {os.path.relpath(resolved, REPO_ROOT)})")

    # Never hand a path under a symlinked directory (e.g. `.claude/...`) to
    # `git check-ignore` — it errors "beyond a symbolic link" (the same
    # class of failure this tool's own traversal used to hit). Those paths
    # are never gitignored anyway, so just check existence directly.
    checkable_targets = [t for t in literal_targets if not t.startswith(".claude/")]
    for target in literal_targets:
        if not target.startswith(".claude/"):
            continue
        resolved = os.path.normpath(os.path.join(REPO_ROOT, target))
        if not os.path.exists(resolved):
            errors.append(f"{rel}: backticked repo-relative path does not exist: '{target}' (resolved to {os.path.relpath(resolved, REPO_ROOT)})")

    if checkable_targets:
        ignored = ignored_paths(checkable_targets, root=REPO_ROOT)
        for target in checkable_targets:
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


def _frontmatter_span(text):
    """Return the (start, end) char offsets of a leading '---' frontmatter
    block, or None. Used to blank it out for check_no_repo_relative_paths
    without disturbing line numbers of the rest of the file."""
    if not text.startswith("---"):
        return None
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    offset = len(lines[0])
    for line in lines[1:]:
        offset_end = offset + len(line)
        if line.strip() == "---":
            return (0, offset_end)
        offset = offset_end
    return None


def extract_path_block(text):
    """Return (block_text, start, end) for the canonical Path-resolution
    section, or None if the file has no such heading."""
    idx = text.find(PATH_BLOCK_HEADER)
    if idx == -1:
        return None
    rest = text[idx:]
    lines = rest.splitlines(keepends=True)
    block_lines = [lines[0]]
    for line in lines[1:]:
        if line.startswith("## "):
            break
        block_lines.append(line)
    block = "".join(block_lines)
    return block, idx, idx + len(block)


def check_path_resolution_block(command_files, errors):
    """All five commands/*.md must carry a byte-identical
    '## Path resolution (framework root and data root)' block. Expected text
    is derived from majority agreement among the files themselves (not
    hardcoded), so an intentional edit applied to all five still passes."""
    blocks = {}  # rel -> block text
    for path in command_files:
        rel = os.path.relpath(path, REPO_ROOT)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        found = extract_path_block(text)
        if found is None:
            errors.append(f"{rel}: missing '{PATH_BLOCK_HEADER}' section")
            continue
        blocks[rel] = found[0]

    if not blocks:
        return

    counts = {}
    for rel, block in blocks.items():
        counts.setdefault(block, []).append(rel)
    majority_block, majority_files = max(counts.items(), key=lambda kv: len(kv[1]))

    if len(counts) > 1:
        for block, files in counts.items():
            if block is majority_block:
                continue
            for rel in files:
                errors.append(
                    f"{rel}: '{PATH_BLOCK_HEADER}' block differs from the other "
                    f"{len(majority_files)} command file(s) (byte-for-byte mismatch)"
                )


CLAUDE_DIR_RE = re.compile(r"\.claude/")
SEARCH_PY_RE = re.compile(r"\.agents/skills/([^/\s`)]+)/search\.py")
FRAMEWORK_ROOTED_SEARCH_PY_RE = re.compile(r"<FRAMEWORK_ROOT>/\.agents/skills/[^/\s`)]+/search\.py")
BARE_PERSONAL_DIR_RE = re.compile(r"\b(?:profile|itineraries|watchlist|trip_scraper)/")
BARE_TRIP_TRACKER_RE = re.compile(r"\btrip_tracker\.csv\b(?!\.example)")
DATA_ROOT_TOKEN = "<DATA_ROOT>"


def _mask(text, pattern):
    """Replace every regex match with same-length filler so line/column
    positions of the surrounding text are preserved for later scans."""
    return pattern.sub(lambda m: "#" * len(m.group(0)), text)


def check_no_repo_relative_paths(md_files, path_blocks, errors):
    """No framework Markdown under commands/ or skills/ may reintroduce a
    repo-relative reference to `.claude/`, an unrooted
    `.agents/skills/*/search.py` invocation, or an unrooted write target
    under profile/, itineraries/, watchlist/, trip_scraper/,
    trip_tracker.csv.

    Heuristic: only `commands/*.md` and `skills/**/SKILL.md` (not
    `.agents/skills/`, whose adapters are *designed* to be copied out
    standalone and legitimately document a bare `.agents/skills/<name>/
    search.py` CLI invocation for themselves) are scanned. Frontmatter
    (`description:` legitimately names these six directories in prose) and,
    for commands/*.md, the canonical "## Path resolution" block (which
    legitimately lists all six as backticked prose) are blanked out — same
    line count, so remaining matches still report a useful line number —
    before scanning. A line that already contains a `<DATA_ROOT>` token
    elsewhere is skipped entirely for the bare-personal-path checks: this
    repo's convention is to root the first mention on a line and then
    repeat a bare filename/pattern afterwards for readability (e.g.
    "Deletes: `<DATA_ROOT>/watchlist/` (all `watchlist/<slug>.json`
    files)") — that repeat is not a reintroduced unrooted path, it is the
    same, already-rooted one restated.

    Known blind spot: this is a textual heuristic, not a parser — it cannot
    catch a repo-relative reference split across a line wrap, hidden behind
    an HTML entity, embedded in a fenced code block that itself pastes the
    block/frontmatter, or a genuinely unrooted personal path that happens to
    share a line with an unrelated `<DATA_ROOT>` mention.
    """
    for path in md_files:
        rel = os.path.relpath(path, REPO_ROOT)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        fm_span = _frontmatter_span(text)
        if fm_span:
            start, end = fm_span
            text = text[:start] + ("\n" * text[start:end].count("\n")) + text[end:]

        block = path_blocks.get(path)
        if block is not None:
            found = extract_path_block(text)
            if found is not None:
                _, start, end = found
                text = text[:start] + ("\n" * text[start:end].count("\n")) + text[end:]

        masked = _mask(text, FRAMEWORK_ROOTED_SEARCH_PY_RE)

        for line_no, line in enumerate(masked.splitlines(), start=1):
            if CLAUDE_DIR_RE.search(line):
                errors.append(f"{rel}:{line_no}: repo-relative reference to '.claude/' — use <FRAMEWORK_ROOT> instead")
            for m in SEARCH_PY_RE.finditer(line):
                adapter_name = m.group(1)
                if "*" in adapter_name:
                    continue  # glob prose (e.g. `.agents/skills/*/search.py`), not an invocation
                errors.append(f"{rel}:{line_no}: '.agents/skills/{adapter_name}/search.py' invocation not rooted at <FRAMEWORK_ROOT>")
            if DATA_ROOT_TOKEN in line:
                continue
            if BARE_PERSONAL_DIR_RE.search(line):
                errors.append(f"{rel}:{line_no}: unrooted personal-data path (should be <DATA_ROOT>/...): {line.strip()!r}")
            if BARE_TRIP_TRACKER_RE.search(line):
                errors.append(f"{rel}:{line_no}: unrooted 'trip_tracker.csv' reference (should be <DATA_ROOT>/trip_tracker.csv): {line.strip()!r}")


KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def check_manifest_consistency(errors):
    plugin_path = os.path.join(REPO_ROOT, ".claude-plugin", "plugin.json")
    marketplace_path = os.path.join(REPO_ROOT, ".claude-plugin", "marketplace.json")
    changelog_path = os.path.join(REPO_ROOT, "CHANGELOG.md")

    plugin = None
    marketplace = None

    for label, path, holder in (
        ("plugin.json", plugin_path, "plugin"),
        ("marketplace.json", marketplace_path, "marketplace"),
    ):
        rel = os.path.relpath(path, REPO_ROOT)
        if not os.path.isfile(path):
            errors.append(f"{rel}: file does not exist")
            continue
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            errors.append(f"{rel}: invalid JSON: {e}")
            continue
        if holder == "plugin":
            plugin = data
        else:
            marketplace = data

    if plugin is None or marketplace is None:
        return

    plugin_name = plugin.get("name")
    plugin_version = plugin.get("version")

    if not plugin_name:
        errors.append("plugin.json: missing 'name'")
    elif not KEBAB_CASE_RE.match(plugin_name):
        errors.append(f"plugin.json: 'name' {plugin_name!r} is not valid kebab-case")

    if not plugin_version:
        errors.append("plugin.json: missing 'version'")

    entries = marketplace.get("plugins")
    if not isinstance(entries, list) or not entries:
        errors.append("marketplace.json: missing or empty 'plugins' list")
        entries = []

    matching = [e for e in entries if isinstance(e, dict) and e.get("name") == plugin_name]
    if plugin_name and not matching:
        errors.append(f"marketplace.json: no plugin entry with name matching plugin.json's '{plugin_name}'")

    for entry in matching:
        entry_version = entry.get("version")
        if entry_version != plugin_version:
            errors.append(
                f"marketplace.json: plugin entry '{entry.get('name')}' version {entry_version!r} "
                f"does not match plugin.json's version {plugin_version!r}"
            )

    if plugin_version:
        if not os.path.isfile(changelog_path):
            errors.append("CHANGELOG.md: file does not exist")
        else:
            with open(changelog_path, "r", encoding="utf-8") as f:
                changelog = f.read()
            if f"[{plugin_version}]" not in changelog:
                errors.append(f"CHANGELOG.md: no entry found for version '{plugin_version}'")


def check_symlink_integrity(errors):
    """`.claude/commands` and `.claude/skills` must be tracked as git
    symlinks (mode 120000) resolving to the top-level commands/ and skills/
    directories — this is what keeps clone-mode discovery working instead
    of silently regressing into duplicated files."""
    expected = {
        ".claude/commands": "commands",
        ".claude/skills": "skills",
    }

    try:
        result = subprocess.run(
            ["git", "ls-files", "-s", *expected.keys()],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except OSError as e:
        errors.append(f"could not run git ls-files to check symlinks: {e}")
        return

    if result.returncode != 0:
        errors.append(f"git ls-files -s failed: {result.stderr.strip()}")
        return

    modes = {}
    for line in result.stdout.splitlines():
        # "<mode> <sha> <stage>\t<path>"
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if parts and path:
            modes[path] = parts[0]

    for rel_link, rel_target in expected.items():
        full_link = os.path.join(REPO_ROOT, rel_link)
        mode = modes.get(rel_link)
        if mode is None:
            errors.append(f"{rel_link}: not tracked by git")
            continue
        if mode != "120000":
            errors.append(f"{rel_link}: tracked with mode {mode}, expected 120000 (symlink)")
            continue
        if not os.path.islink(full_link):
            errors.append(f"{rel_link}: not a symlink on disk")
            continue
        resolved = os.path.realpath(full_link)
        expected_resolved = os.path.realpath(os.path.join(REPO_ROOT, rel_target))
        if resolved != expected_resolved:
            errors.append(f"{rel_link}: resolves to {resolved!r}, expected {expected_resolved!r}")


def main():
    errors = []

    top_skill_files = sorted(find_files(os.path.join(REPO_ROOT, "skills"), "SKILL.md"))
    agents_skill_files = sorted(find_files(os.path.join(REPO_ROOT, ".agents", "skills"), "SKILL.md"))
    skill_files = sorted(set(top_skill_files) | set(agents_skill_files))

    for path in skill_files:
        body = check_frontmatter_file(path, errors, required_keys=("name", "description"))
        check_links(path, body, errors)

    command_files = find_command_files(os.path.join(REPO_ROOT, "commands"))
    for path in command_files:
        body = check_frontmatter_file(path, errors, required_keys=("description",))
        check_links(path, body, errors)

    check_agents_skills_structure(errors)
    check_adapter_contract(errors)
    check_path_resolution_block(command_files, errors)

    # .agents/skills/*/SKILL.md deliberately excluded: those adapters are
    # designed to be copied out standalone and legitimately document a bare
    # `.agents/skills/<name>/search.py` CLI invocation for themselves.
    path_blocks = {path: True for path in command_files}
    check_no_repo_relative_paths(top_skill_files + command_files, path_blocks, errors)

    check_manifest_consistency(errors)
    check_symlink_integrity(errors)

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
