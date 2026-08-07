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
     existing path. A `<FRAMEWORK_ROOT>/...` target resolves against the
     repo root; a `<DATA_ROOT>` or other `<...>` placeholder is a runtime
     path and is skipped; every other target — Markdown `[]()` link or
     backticked literal path alike — resolves against the linked-from
     file's own directory.
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
     valid JSON, declare the same `version` and `description`, that version
     has a matching `CHANGELOG.md` entry, the marketplace plugin entry's
     `name` matches plugin.json's `name`, and that name is valid kebab-case.
  8. `.claude/commands` and `.claude/skills` are tracked as git symlinks
     (mode 120000) resolving to the top-level `commands/`/`skills/` dirs,
     via a same-machine-relative symlink target text (not absolute).
  9. `.mcp.json` declares exactly `playwright` / `playwright-headed`, both
     pinned to the identical `@playwright/mcp@<version>`, consistent with
     whatever `.claude-plugin/plugin.json` declares for `mcpServers`.
  10. Every `<FRAMEWORK_ROOT>`-rooted path in `commands/reset.md`'s
      protect-list actually exists on disk.

Exit 0 on success; non-zero with actionable per-file messages on failure.
"""
import json
import os
import re
import subprocess
import sys

from _repo import (
    ADAPTER_CRED_VARS,
    DESTRUCTIVE_SHELL_VERBS,
    FRAMEWORK_DIRS,
    FRAMEWORK_FILES,
    GUARDED_SHELL_VERBS,
    PERSONAL_DIRS,
    PERSONAL_FILES,
    repo_root,
    ignored_paths,
    tracked_modes,
)

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
FRAMEWORK_ROOT_PROTECT_RE = re.compile(r"`<FRAMEWORK_ROOT>/([\w./-]+)`")
PLACEHOLDER_TOKEN_RE = re.compile(r"<[A-Za-z_]+>")

PATH_BLOCK_HEADER = "## Path resolution (framework root and data root)"
PROTECT_LIST_HEADER = "## Explicit protect-list (never delete)"
MODE_DELETES_HEADER = "## What each mode deletes"


def find_markdown(root, *, name=None, recursive=True):
    """Return paths under `root` matching `name` exactly (or every `.md`
    file if `name` is None), pruning symlinked subdirectories so this never
    wanders into a `.claude/` alias and hands a beyond-a-symlink path to
    git. `recursive=False` lists only `root`'s immediate children (and
    refuses a symlinked `root` itself)."""
    if not os.path.isdir(root):
        return []
    if not recursive:
        if os.path.islink(root):
            return []
        results = []
        for entry in sorted(os.listdir(root)):
            matched = entry == name if name else entry.endswith(".md")
            if matched:
                results.append(os.path.join(root, entry))
        return results

    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for fname in filenames:
            matched = fname == name if name else fname.endswith(".md")
            if matched:
                results.append(os.path.join(dirpath, fname))
    return results


EXPECTED_COMMAND_NAMES = ("setup", "scrape", "plan", "watch", "reset")
EXPECTED_AGENTS_SKILLS = ("flights-search", "stays-search", "packages-search")


def load_json(path, errors):
    """Read and parse `path` as JSON exactly once, appending an error and
    returning None on a missing file or invalid JSON."""
    rel = os.path.relpath(path, REPO_ROOT)
    if not os.path.isfile(path):
        errors.append(f"{rel}: file does not exist")
        return None
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"{rel}: invalid JSON: {e}")
            return None


def parse_frontmatter(text, rel, errors):
    """Hand-rolled minimal YAML frontmatter parser.

    Returns `(fm, body, body_start)`: `fm` is a dict of top-level scalar
    string keys (or None if no frontmatter block is present), `body` is the
    text after the closing `---`, and `body_start` is the char offset in
    `text` where `body` begins (0 when there is no frontmatter) — this lets
    callers blank out exactly the frontmatter span for other scans without a
    second scanner.

    Only handles simple `key: value` pairs (values may be quoted). Good
    enough for the flat frontmatter used by SKILL.md / command files here.
    Pass a throwaway list as `errors` to suppress malformed-line reporting
    (e.g. for files where frontmatter is optional and not being validated).
    """
    if not text.startswith("---"):
        return None, text, 0

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text, 0

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None, text, 0

    fm = {}
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

    body = "\n".join(lines[end_idx + 1:])
    keepend_lines = text.splitlines(keepends=True)
    body_start = sum(len(l) for l in keepend_lines[: end_idx + 1])
    return fm, body, body_start


def _validate_frontmatter_keys(rel, path, fm, errors, required_keys):
    for key in required_keys:
        value = fm.get(key, "")
        if not value:
            errors.append(f"{rel}: frontmatter missing non-empty '{key}'")
        elif key == "name":
            dir_name = os.path.basename(os.path.dirname(path))
            if value != dir_name:
                errors.append(f"{rel}: frontmatter name '{value}' does not match parent directory name '{dir_name}'")


def resolve_target_path(base_dir, target_path):
    """Shared resolution model for Markdown `[]()` links and backticked
    literal paths, keyed on string shape, not markup form: `<FRAMEWORK_ROOT>/...`
    resolves against the repo root; everything else resolves against the
    linked-from file's own directory."""
    if target_path.startswith("<FRAMEWORK_ROOT>/"):
        remainder = target_path[len("<FRAMEWORK_ROOT>/"):]
        return os.path.normpath(os.path.join(REPO_ROOT, remainder))
    return os.path.normpath(os.path.join(base_dir, target_path))


def _report_missing(errors, rel, label, target, resolved):
    if not os.path.exists(resolved):
        errors.append(f"{rel}: {label}: '{target}' (resolved to {os.path.relpath(resolved, REPO_ROOT)})")


def check_links(rel, base_dir, body, errors):
    """Check Markdown-link and `<FRAMEWORK_ROOT>`-rooted backtick targets
    immediately. Bare backticked literal-path targets are returned as
    `(target, resolved)` pairs instead of checked here, so the caller can
    batch the `.gitignore` exemption lookup (`git check-ignore`) across
    every file in a single subprocess call rather than one per file."""
    literal_pairs = []

    for match in MD_LINK_RE.finditer(body):
        target = match.group(1).strip()
        # Skip external links, anchors, and mailto/absolute-url schemes.
        if not target or target.startswith("#"):
            continue
        if URL_SCHEME_RE.match(target) or target.startswith("mailto:"):
            continue
        # Strip a trailing #anchor fragment.
        target_path = target.split("#", 1)[0]
        if not target_path:
            continue
        if not target_path.startswith("<FRAMEWORK_ROOT>/") and PLACEHOLDER_TOKEN_RE.search(target_path):
            # <DATA_ROOT>/... (runtime-generated) or any other placeholder
            # notation is not a literal repo path — nothing to check.
            continue
        resolved = resolve_target_path(base_dir, target_path)
        _report_missing(errors, rel, "relative link target does not exist", target, resolved)

    for match in BACKTICK_PATH_RE.finditer(body):
        target = match.group(1)
        rooted = FRAMEWORK_ROOT_BACKTICK_RE.match(target)
        if rooted:
            resolved = resolve_target_path(base_dir, target)
            _report_missing(errors, rel, "backticked <FRAMEWORK_ROOT>-rooted path does not exist", target, resolved)
            continue
        if PLACEHOLDER_TOKEN_RE.search(target):
            # <DATA_ROOT>/... or any other placeholder — runtime path, skip.
            continue
        # Only validate backticked strings that look like literal paths
        # (word/dot/slash/dash chars, contains '/', ends .md/.py); glob/
        # placeholder notation (`foo/*.md`, `{a,b}.py`, `...`) is left alone.
        if "/" not in target or not LITERAL_PATH_RE.fullmatch(target):
            continue
        resolved = resolve_target_path(base_dir, target)
        literal_pairs.append((target, resolved))

    return literal_pairs


def check_discovery_completeness(command_files, skill_files, adapter_dir_names, errors):
    """Assert the file sets the rest of this script iterates are actually
    populated and complete, so a renamed/missing directory produces a loud
    failure instead of every downstream check silently no-oping over an
    empty list (the vacuous-pass class of bug this script used to have)."""
    found_command_names = {
        os.path.splitext(os.path.basename(p))[0] for p in command_files
    }
    missing_commands = [n for n in EXPECTED_COMMAND_NAMES if n not in found_command_names]
    if missing_commands:
        errors.append(
            f"commands/: missing expected command file(s): "
            f"{', '.join(sorted(n + '.md' for n in missing_commands))} "
            f"(found {sorted(found_command_names) or 'none'} — is commands/ missing or renamed?)"
        )
    extra_commands = found_command_names - set(EXPECTED_COMMAND_NAMES)
    if extra_commands:
        errors.append(
            f"commands/: unexpected command file(s) not in the known set "
            f"{EXPECTED_COMMAND_NAMES}: {sorted(extra_commands)}"
        )

    if not skill_files:
        errors.append(
            "skills/: found zero SKILL.md files under skills/ "
            "(expected at least one — is skills/ missing or renamed?)"
        )

    # A missing .agents/skills/ directory is reported once, by
    # check_agents_skills_structure — nothing to do here in that case.
    if adapter_dir_names is not None:
        missing_adapters = [n for n in EXPECTED_AGENTS_SKILLS if n not in set(adapter_dir_names)]
        if missing_adapters:
            errors.append(
                f".agents/skills/: missing expected adapter directory(ies): "
                f"{', '.join(sorted(missing_adapters))} "
                f"(found {sorted(adapter_dir_names) or 'none'})"
            )


def check_agents_skills_structure(agents_skills_dir, adapter_dir_names, errors):
    if adapter_dir_names is None:
        errors.append(".agents/skills/: directory does not exist")
        return
    for entry in adapter_dir_names:
        entry_path = os.path.join(agents_skills_dir, entry)
        rel = os.path.relpath(entry_path, REPO_ROOT)
        skill_md = os.path.join(entry_path, "SKILL.md")
        search_py = os.path.join(entry_path, "search.py")
        if not os.path.isfile(skill_md):
            errors.append(f"{rel}: missing SKILL.md")
        if not os.path.isfile(search_py):
            errors.append(f"{rel}: missing search.py")
        elif not os.access(search_py, os.X_OK):
            errors.append(f"{rel}/search.py: not executable (chmod +x)")


def check_adapter_contract(agents_skills_dir, adapter_dir_names, errors):
    """Assert the three .agents/skills/*/search.py adapters agree on their
    no-credentials contract (a shared module was deliberately rejected, so
    the near-duplicated adapters are guarded instead of deduplicated): each
    adapter's `--json` no-credentials path (credential env vars unset) must
    exit 2, print exactly one JSON object, and every adapter must agree on
    the same top-level key set, `status` == "no_credentials", and
    `fallback` == "web_search"."""
    if adapter_dir_names is None:
        return

    contracts = []  # list of (rel, keys_set, status, fallback)
    for entry in adapter_dir_names:
        search_py = os.path.join(agents_skills_dir, entry, "search.py")
        if not os.path.isfile(search_py):
            continue
        rel = os.path.relpath(search_py, REPO_ROOT)
        env = {k: v for k, v in os.environ.items() if k not in ADAPTER_CRED_VARS}
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


def extract_section(text, header):
    """Return `(block_text, start, end)` for the section starting at the
    given `## `-style `header` and running until the next `## ` heading (or
    end of file), or None if `header` isn't present."""
    idx = text.find(header)
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


# Substrings that must survive in the path-resolution block for it to still
# express the essential contract — pins the block's *content*, not merely
# its self-consistency across files. An edit that changes all five files
# identically (e.g. quietly swapping the DATA_ROOT location) still fails
# unless it happens to preserve every one of these tokens.
REQUIRED_PATH_BLOCK_TOKENS = (
    "${CLAUDE_PLUGIN_ROOT}",
    "~/.ai-holiday-search",
    "FRAMEWORK_ROOT",
    "DATA_ROOT",
)


def check_path_resolution_block(command_files, texts, errors):
    """All five commands/*.md must carry a byte-identical
    '## Path resolution (framework root and data root)' block, and that
    block must still mention the essential contract tokens."""
    blocks = {}  # rel -> block text
    for path in command_files:
        rel = os.path.relpath(path, REPO_ROOT)
        found = extract_section(texts[path], PATH_BLOCK_HEADER)
        if found is None:
            errors.append(f"{rel}: missing '{PATH_BLOCK_HEADER}' section")
            continue
        blocks[rel] = found[0]

    if not blocks:
        errors.append(
            f"commands/: no file carries a '{PATH_BLOCK_HEADER}' section to check "
            f"(expected all of {EXPECTED_COMMAND_NAMES})"
        )
        return

    counts = {}
    for rel, block in blocks.items():
        counts.setdefault(block, []).append(rel)

    if len(counts) > 1:
        # No majority vote: disagreement is reported as disagreement, not
        # attributed to whichever variant happens to be less common.
        summary = "; ".join(
            f"{', '.join(sorted(files))} agree with each other" for files in counts.values()
        )
        for rel in sorted(blocks):
            errors.append(
                f"{rel}: '{PATH_BLOCK_HEADER}' block is not byte-identical across all "
                f"command files — groups found: {summary}"
            )
        return

    # All blocks agree with each other — now pin the content itself.
    ((only_block, only_files),) = counts.items()
    missing_tokens = [t for t in REQUIRED_PATH_BLOCK_TOKENS if t not in only_block]
    if missing_tokens:
        for rel in sorted(only_files):
            errors.append(
                f"{rel}: '{PATH_BLOCK_HEADER}' block is identical across command files but "
                f"no longer mentions required token(s): {', '.join(missing_tokens)}"
            )


CLAUDE_DIR_RE = re.compile(r"\.claude/")
SEARCH_PY_RE = re.compile(r"\.agents/skills/([^/\s`)]+)/search\.py")
_PERSONAL_DIR_ALT = "|".join(re.escape(d) for d in PERSONAL_DIRS)
_PERSONAL_FILE_ALT = "|".join(re.escape(f) for f in PERSONAL_FILES)
# Matches either a bare personal directory reference (`profile/`, ...) or a
# bare personal filename (`trip_tracker.csv`, not followed by `.example`).
BARE_PERSONAL_PATH_RE = re.compile(
    rf"\b(?:({_PERSONAL_DIR_ALT})/|({_PERSONAL_FILE_ALT})\b(?!\.example))"
)
# A <DATA_ROOT>/... or <FRAMEWORK_ROOT>/... span is already rooted — blank
# out just that span (not the whole line) before scanning for bare personal
# paths, so a rooted mention earlier in a line no longer exempts an
# unrelated unrooted mention later on the same line. (Also fully subsumes
# the narrower "<FRAMEWORK_ROOT>/.agents/skills/*/search.py" case, since its
# character class already matches that whole span.)
ROOT_TOKENS = ("<FRAMEWORK_ROOT>", "<DATA_ROOT>")
ROOTED_SPAN_RE = re.compile(
    "(?:" + "|".join(re.escape(t) for t in ROOT_TOKENS) + r")/[\w./-]*"
)
_FRAMEWORK_DIR_ALT = "|".join(re.escape(d) for d in FRAMEWORK_DIRS)
_FRAMEWORK_FILE_ALT = "|".join(re.escape(f) for f in FRAMEWORK_FILES)
# An unrooted reference to a framework file — either under a framework
# directory (`skills/x.md`, `commands/x.md`) or a bare framework filename
# with no directory to anchor on (`trip_tracker.csv.example`) — is a runtime
# read target that should be rooted at <FRAMEWORK_ROOT>, same class as the
# .agents/skills/*/search.py case. Built from the shared _repo tuples so the
# guarded set is data, not a regex per file.
#
# Requiring a .md/.py suffix on the directory form (rather than any
# skills/commands/ mention) keeps it from flagging bare structural prose like
# "the `commands/` directory" or glob notation like `skills/*/SKILL.md` (the
# `*` breaks the [\w.-]+ segment match, same rationale as LITERAL_PATH_RE
# elsewhere in this file). The `.agents/` lookbehind leaves the adapter case
# to SEARCH_PY_RE, which knows the correct rooted form for it — without it,
# one bad adapter path draws two errors, the second naming a wrong fix.
UNROOTED_FRAMEWORK_FILE_RE = re.compile(
    rf"(?<![\w.-])(?<!\.agents/)"
    rf"(?:(?:{_FRAMEWORK_DIR_ALT})/[\w.-]+(?:/[\w.-]+)*\.(?:md|py)"
    rf"|(?:{_FRAMEWORK_FILE_ALT}))\b"
)


def _mask(text, pattern):
    """Replace every regex match with same-length filler so line/column
    positions of the surrounding text are preserved for later scans."""
    return pattern.sub(lambda m: "#" * len(m.group(0)), text)


def _rooting_check_claude_dir(m, rel, line_no, line):
    return f"{rel}:{line_no}: repo-relative reference to '.claude/' — use <FRAMEWORK_ROOT> instead"


def _rooting_check_search_py(m, rel, line_no, line):
    adapter_name = m.group(1)
    if "*" in adapter_name:
        return None  # glob prose (e.g. `.agents/skills/*/search.py`), not an invocation
    return f"{rel}:{line_no}: '.agents/skills/{adapter_name}/search.py' invocation not rooted at <FRAMEWORK_ROOT>"


def _rooting_check_personal_path(m, rel, line_no, line):
    if m.group(1):
        return f"{rel}:{line_no}: unrooted personal-data path (should be <DATA_ROOT>/...): {line.strip()!r}"
    return f"{rel}:{line_no}: unrooted 'trip_tracker.csv' reference (should be <DATA_ROOT>/trip_tracker.csv): {line.strip()!r}"


def _rooting_check_framework_file(m, rel, line_no, line):
    """Shared by every regex whose whole match is the path that should have
    been rooted — `skills/x.md`, `commands/x.md`, `trip_tracker.csv.example`."""
    return (
        f"{rel}:{line_no}: unrooted framework-file reference '{m.group(0)}' "
        f"(should be <FRAMEWORK_ROOT>/{m.group(0)}): {line.strip()!r}"
    )


# One (regex, handler) table drives every "must be rooted at <FRAMEWORK_ROOT>
# or <DATA_ROOT>" check, so all of them are handled the same way and none
# needs a bespoke string comparison.
ROOTING_CHECKS = (
    (CLAUDE_DIR_RE, _rooting_check_claude_dir),
    (SEARCH_PY_RE, _rooting_check_search_py),
    (BARE_PERSONAL_PATH_RE, _rooting_check_personal_path),
    (UNROOTED_FRAMEWORK_FILE_RE, _rooting_check_framework_file),
)


def check_no_repo_relative_paths(files, errors):
    """No framework Markdown under commands/ or skills/ may reintroduce a
    repo-relative reference to `.claude/`, an unrooted
    `.agents/skills/*/search.py` invocation, an unrooted `skills/...`/
    `commands/...` file reference, or an unrooted write target under
    profile/, itineraries/, watchlist/, trip_scraper/, trip_tracker.csv.

    `files` is an iterable of `(path, text, body_start)` — `body_start` is
    the char offset from `parse_frontmatter` marking where a leading
    frontmatter block ends (0 if none), blanked out here without a second
    frontmatter scanner. `.agents/skills/` is deliberately excluded by the
    caller: those adapters are designed to be copied out standalone and
    legitimately document a bare `search.py` invocation for themselves.

    Frontmatter and (for commands/*.md) the canonical "## Path resolution"
    block legitimately name these directories in prose, so both are blanked
    to same-length filler (preserving line numbers) before scanning. Every
    `<DATA_ROOT>/xxx` / `<FRAMEWORK_ROOT>/xxx` span is also blanked (not the
    whole line) before the bare-path checks run, so a rooted mention earlier
    on a line never exempts an unrelated bare mention later on it — tested
    empirically (removing this exemption changes no lint outcome on this
    repo's current docs) rather than kept as a speculative false-negative.

    Known blind spot: this is a textual heuristic, not a parser — it cannot
    catch a reference split across a line wrap, hidden behind an HTML
    entity, or embedded in a fenced code block pasting the block/frontmatter
    verbatim.
    """
    for path, text, body_start in files:
        rel = os.path.relpath(path, REPO_ROOT)

        if body_start:
            text = ("\n" * text[:body_start].count("\n")) + text[body_start:]

        found = extract_section(text, PATH_BLOCK_HEADER)
        if found is not None:
            _, start, end = found
            text = text[:start] + ("\n" * text[start:end].count("\n")) + text[end:]

        for line_no, line in enumerate(text.splitlines(), start=1):
            # Blank out rooted <DATA_ROOT>/... / <FRAMEWORK_ROOT>/... spans
            # before scanning for bare (unrooted) mentions.
            bare_scan_line = _mask(line, ROOTED_SPAN_RE)

            for regex, handler in ROOTING_CHECKS:
                for m in regex.finditer(bare_scan_line):
                    msg = handler(m, rel, line_no, line)
                    if msg:
                        errors.append(msg)


KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def check_manifest_consistency(plugin, marketplace, errors):
    changelog_path = os.path.join(REPO_ROOT, "CHANGELOG.md")

    if plugin is None or marketplace is None:
        return  # already reported by load_json

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
        entry_desc = entry.get("description")
        plugin_desc = plugin.get("description")
        if entry_desc != plugin_desc:
            errors.append(
                f"marketplace.json: plugin entry '{entry.get('name')}' description {entry_desc!r} "
                f"does not match plugin.json's description {plugin_desc!r}"
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
    expected_target = {
        ".claude/commands": "commands",
        ".claude/skills": "skills",
    }
    expected_readlink = {
        ".claude/commands": "../commands",
        ".claude/skills": "../skills",
    }

    try:
        modes = tracked_modes(list(expected_target.keys()), root=REPO_ROOT)
    except RuntimeError as e:
        errors.append(str(e))
        return

    for rel_link, rel_target in expected_target.items():
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

        # Compare the literal symlink target text, not just where it
        # resolves to: os.path.realpath on an ABSOLUTE symlink still
        # resolves "correctly" on the machine that created it, but an
        # absolute link is broken on a fresh clone elsewhere. Requiring the
        # relative text catches that locally instead of only via a
        # separate-clone CI test.
        actual_readlink = os.readlink(full_link)
        if actual_readlink != expected_readlink[rel_link]:
            errors.append(
                f"{rel_link}: symlink target text is {actual_readlink!r}, expected "
                f"{expected_readlink[rel_link]!r} (must be a same-machine-relative link, not absolute)"
            )

        resolved = os.path.realpath(full_link)
        expected_resolved = os.path.realpath(os.path.join(REPO_ROOT, rel_target))
        if resolved != expected_resolved:
            errors.append(f"{rel_link}: resolves to {resolved!r}, expected {expected_resolved!r}")
            continue
        # os.path.realpath on a dangling symlink still returns the expected
        # string (it does not require the target to exist), so a renamed-away
        # commands/ or skills/ dir would otherwise pass silently. Require the
        # resolved target to actually exist as a directory with content.
        if not os.path.isdir(resolved):
            errors.append(
                f"{rel_link}: resolves to {resolved!r} but that path is not an existing "
                f"directory (dangling symlink — is '{rel_target}' missing or renamed?)"
            )
            continue
        if not os.listdir(resolved):
            errors.append(f"{rel_link}: resolves to {resolved!r} but that directory is empty")


PINNED_PLAYWRIGHT_MCP_RE = re.compile(r"^@playwright/mcp@(?!latest\b)\S+$")


def _pinned_arg(server_name, server_def, errors):
    args = server_def.get("args") if isinstance(server_def, dict) else None
    if not isinstance(args, list):
        errors.append(f".mcp.json: server '{server_name}' has no 'args' list")
        return None
    candidates = [a for a in args if isinstance(a, str) and a.startswith("@playwright/mcp")]
    if len(candidates) != 1:
        errors.append(
            f".mcp.json: server '{server_name}' args do not contain exactly one "
            f"'@playwright/mcp@<version>' entry: {candidates}"
        )
        return None
    pin = candidates[0]
    if not PINNED_PLAYWRIGHT_MCP_RE.match(pin):
        errors.append(
            f".mcp.json: server '{server_name}' uses unpinned/'@latest' playwright mcp "
            f"version: '{pin}' — pin an exact version"
        )
        return None
    return pin


def check_mcp_consistency(mcp, plugin, errors):
    """`.mcp.json` must define exactly `playwright` and `playwright-headed`,
    both pinned to the identical `@playwright/mcp@<version>` package (no
    `@latest`/unpinned form). If `.claude-plugin/plugin.json` also declares
    `mcpServers`, it must point at `./.mcp.json` — an inline object is not
    supported, so the two distribution modes cannot silently drift apart."""
    if mcp is None:
        return  # already reported by load_json

    servers = mcp.get("mcpServers")
    if not isinstance(servers, dict):
        errors.append(".mcp.json: missing or non-object 'mcpServers'")
        return

    expected_names = {"playwright", "playwright-headed"}
    found_names = set(servers.keys())
    if found_names != expected_names:
        errors.append(
            f".mcp.json: 'mcpServers' keys {sorted(found_names)} do not match expected "
            f"{sorted(expected_names)}"
        )

    pins = {}
    for name in sorted(found_names & expected_names):
        pin = _pinned_arg(name, servers[name], errors)
        if pin is not None:
            pins[name] = pin

    if len(set(pins.values())) > 1:
        errors.append(f".mcp.json: playwright mcp version pins differ across servers: {pins}")

    if plugin is None:
        return  # missing/invalid already reported by check_manifest_consistency's load

    plugin_mcp = plugin.get("mcpServers")
    if plugin_mcp is None:
        return

    if isinstance(plugin_mcp, str):
        if plugin_mcp not in ("./.mcp.json", ".mcp.json"):
            errors.append(
                f"plugin.json: 'mcpServers' string {plugin_mcp!r} does not point at "
                f"'./.mcp.json' — plugin mode would use a different MCP config than clone mode"
            )
        return

    if isinstance(plugin_mcp, dict):
        errors.append(
            "plugin.json: 'mcpServers' must delegate to './.mcp.json' — inline mcp server "
            "definitions are unsupported"
        )
        return

    errors.append("plugin.json: 'mcpServers' is neither a string nor an object")


# A plain backticked-span extractor — deliberately NOT a path matcher (that
# judgement is PROTECT_LIST_PATH_LIKE_RE's job below). Named for what it
# extracts so it isn't mistaken for a bullet-scoped sibling of
# BACKTICK_PATH_RE, which pins .md/.py and means something different.
BACKTICK_SPAN_RE = re.compile(r"`([^`]+)`")
# Same "does this look like a path" bar as LITERAL_PATH_RE/BACKTICK_PATH_RE
# Branch (b)'s `\.example` suffix is load-bearing, not redundant with the
# `csv` alternative: `[\w-]+` cannot consume a dot, so `trip_tracker.csv.example`
# matches only via that suffix. `*` is allowed so a glob entry
# (`<FRAMEWORK_ROOT>/skills/holiday-planner/*.md`) is still checked for rooting.
PROTECT_LIST_PATH_LIKE_RE = re.compile(
    r"^(?:<[A-Za-z_]+>)?[\w.*-]*(?:/[\w.*-]*)+$"
    r"|^[\w-]+\.(?:md|py|toml|csv(?:\.example)?)$"
)


def check_reset_protect_list(reset_text, errors):
    """Three assertions over commands/reset.md's deletion guards:

    1. Every `<FRAMEWORK_ROOT>`-rooted protect-list path exists on disk.
    2. Every protect-list bullet is rooted at `<FRAMEWORK_ROOT>` or
       `<DATA_ROOT>`. These are execution-time targets read by an agent with
       no doc-relative base, so `../tools/`, a bare `tools/`, or a
       `[text](../README.md)` link is a bug, not a style nit. Only path-like
       backticked spans are checked (see PROTECT_LIST_PATH_LIKE_RE), so a
       bullet mentioning `.env` in passing does not false-positive.
    3. The per-mode Deletes/Preserves bullets carry no `../` targets — same
       property, narrower rule, because those bullets legitimately name bare
       files in prose.

    Doc-navigation links elsewhere in the file stay relative by design
    (`<FRAMEWORK_ROOT>` is reserved for execution-time paths), so both
    rootedness rules are scoped to these two sections only."""
    if reset_text is None:
        errors.append("commands/reset.md: file does not exist (cannot check protect-list)")
        return

    found = extract_section(reset_text, PROTECT_LIST_HEADER)
    if found is None:
        errors.append(f"commands/reset.md: missing '{PROTECT_LIST_HEADER}' section")
        return

    block, _, _ = found
    for m in FRAMEWORK_ROOT_PROTECT_RE.finditer(block):
        remainder = m.group(1)
        resolved = os.path.normpath(os.path.join(REPO_ROOT, remainder))
        if not os.path.exists(resolved):
            errors.append(
                f"commands/reset.md: protect-list path does not exist: '<FRAMEWORK_ROOT>/{remainder}' "
                f"(resolved to {os.path.relpath(resolved, REPO_ROOT)})"
            )

    def unrooted(what, shown):
        errors.append(
            f"commands/reset.md: {what} is not rooted: {shown} (execution-time "
            "target has no doc-relative base; use `<FRAMEWORK_ROOT>/...` or `<DATA_ROOT>/...`)"
        )

    # Every bullet line's backticked spans and Markdown link targets must be
    # rooted. Restricted to bullet lines (`- ...`) so this never flags the
    # section's explanatory prose paragraphs.
    for line in block.splitlines():
        if not line.strip().startswith("- "):
            continue
        for path in BACKTICK_SPAN_RE.findall(line):
            if PROTECT_LIST_PATH_LIKE_RE.match(path) and not path.startswith(ROOT_TOKENS):
                unrooted("protect-list entry", f"`{path}`")
        for target in MD_LINK_RE.findall(line):
            if not target.startswith(ROOT_TOKENS):
                unrooted("protect-list entry", f"[{target}] link")

    # The per-mode "Deletes:"/"Preserves:" bullets assert the same
    # execution-time property as the protect-list and were previously
    # unchecked, so reset.md could contradict itself while linting clean.
    # Only `../`-prefixed paths are flagged here: these bullets legitimately
    # name bare files in prose (`01-traveler-profile.md`), so the broader
    # path-like rule used above would false-positive on them.
    modes = extract_section(reset_text, MODE_DELETES_HEADER)
    if modes is None:
        errors.append(f"commands/reset.md: missing '{MODE_DELETES_HEADER}' section")
        return
    for line in modes[0].splitlines():
        if not line.strip().startswith("- "):
            continue
        for path in BACKTICK_SPAN_RE.findall(line):
            if path.startswith("../"):
                unrooted("mode delete/preserve target", f"`{path}`")
        for target in MD_LINK_RE.findall(line):
            if target.startswith("../"):
                unrooted("mode delete/preserve target", f"[{target}] link")


# Matches a single qualified grant like `Bash(rm:*)`, capturing the verb.
ALLOWED_TOOLS_BASH_RE = re.compile(r"^Bash\((\w+):\*\)$")
# One `destructive-tools-justification` entry: `Bash(<verb>:*) — <reason>`.
# Accepts a plain hyphen too, not just the em/en dash shown in the spec
# example, so a human retyping the key doesn't get bounced on punctuation.
JUSTIFICATION_ENTRY_RE = re.compile(r"^Bash\((\w+):\*\)\s*[-–—]\s*(.*)$")


# Membership-lookup views of the _repo.py tuples, which stay tuples there to
# match FRAMEWORK_DIRS / ADAPTER_CRED_VARS and to keep the subset relation
# between them literal.
GUARDED_VERB_SET = frozenset(GUARDED_SHELL_VERBS)
DESTRUCTIVE_VERB_SET = frozenset(DESTRUCTIVE_SHELL_VERBS)


def _line_no(text, char_offset):
    return text.count("\n", 0, char_offset) + 1


def _backtick_leading_tokens(body):
    """Return `(first_token, match)` for every backticked span in `body` whose
    leading whitespace-delimited token looks like a bare shell verb (non-empty,
    containing neither `/` nor `.`, which excludes paths and filenames).

    Kept as one function because it is the single definition of "what counts as
    a backticked invocation" for both directions of
    `check_allowed_tools_match_body`; inlining it into each would let the two
    directions drift on which spans they consider.
    """
    tokens = []
    for m in BACKTICK_SPAN_RE.finditer(body):
        parts = m.group(1).split(None, 1)
        if not parts:
            continue
        first_token = parts[0]
        if "/" in first_token or "." in first_token:
            continue
        tokens.append((first_token, m))
    return tokens


def check_allowed_tools_match_body(command_files, texts, parsed, errors):
    """Cross-check each commands/*.md `allowed-tools` grant list against what
    the command body actually backtick-invokes, in two directions:

    1. Body -> grant (under-permission), all `_repo.GUARDED_SHELL_VERBS`. This
       is the `reset.md` step-2 failure from e0d76ae: the body said `ls` and
       the frontmatter withheld `Bash(ls:*)`.
    2. Grant -> body (over-permission), `_repo.DESTRUCTIVE_SHELL_VERBS` only —
       satisfied by a backticked invocation or a `destructive-tools-justification`
       entry. This is the direction that would have caught the `Bash(find:*)`
       over-grant from the same PR. An unused *non*-destructive grant is not an
       error: forcing prose rewrites to use up a harmless grant isn't worth it.

    KNOWN LIMITATION, DELIBERATE: `plan.md`, `scrape.md`, and `watch.md` grant
    unqualified `Bash`, which satisfies both directions implicitly, so this
    check is a no-op for those three today. Narrowing that grant is a
    permissions audit, tracked separately — a green run here does NOT mean
    those three are permission-audited.

    KNOWN LIMITATION, LEXICAL: this is a scan of backticked spans, not a shell
    parser, and is approximate both ways. A backticked span starting with a
    guarded word that isn't an invocation is a possible false positive (only
    partly mitigated by rejecting first tokens containing `/` or `.`), and an
    instruction given in prose alone carries no backticks and is invisible.
    It catches the class of defect that occurred, not all of them.
    """
    for path in command_files:
        rel = os.path.relpath(path, REPO_ROOT)
        text = texts[path]
        fm, body, body_start = parsed[path]
        if fm is None:
            continue

        allowed_raw = fm.get("allowed-tools", "")
        bare_bash = False
        granted_verbs = set()
        for token in allowed_raw.split(","):
            token = token.strip()
            if not token:
                continue
            if token == "Bash":
                bare_bash = True
                continue
            m = ALLOWED_TOOLS_BASH_RE.match(token)
            if m:
                granted_verbs.add(m.group(1))

        # Single shared scan of the body's backticked spans, used by both
        # directions below.
        leading_tokens = _backtick_leading_tokens(body)

        # --- Direction 1: body -> grant, all guarded verbs ---
        for first_token, m in leading_tokens:
            if first_token not in GUARDED_VERB_SET:
                continue
            if bare_bash or first_token in granted_verbs:
                continue
            line_no = _line_no(text, body_start + m.start())
            errors.append(
                f"{rel}:{line_no}: body invokes `{first_token}` but 'allowed-tools' grants "
                f"neither bare 'Bash' nor 'Bash({first_token}:*)' — add the missing grant"
            )

        # --- destructive-tools-justification frontmatter key ---
        justification_raw = fm.get("destructive-tools-justification")
        justified_verbs = set()
        if justification_raw:
            for entry in justification_raw.split(";"):
                entry = entry.strip()
                if not entry:
                    continue
                jm = JUSTIFICATION_ENTRY_RE.match(entry)
                if not jm:
                    errors.append(
                        f"{rel}: malformed 'destructive-tools-justification' entry "
                        f"(expected 'Bash(<verb>:*) — <reason>'): {entry!r}"
                    )
                    continue
                verb, reason = jm.group(1), jm.group(2).strip()
                justified_verbs.add(verb)
                if verb not in granted_verbs:
                    errors.append(
                        f"{rel}: 'destructive-tools-justification' names 'Bash({verb}:*)' "
                        "which is not in 'allowed-tools' — stale justification"
                    )
                elif len(reason.split()) < 2:
                    errors.append(
                        f"{rel}: 'destructive-tools-justification' reason for 'Bash({verb}:*)' "
                        f"is empty or a single word: {reason!r}"
                    )

        destructive_grants = granted_verbs & DESTRUCTIVE_VERB_SET

        if justification_raw and not destructive_grants:
            errors.append(
                f"{rel}: 'destructive-tools-justification' is set but 'allowed-tools' grants "
                "no destructive verb — remove the key"
            )

        # --- Direction 2: grant -> body, destructive verbs only ---
        invoked_verbs = {first_token for first_token, _ in leading_tokens}

        for verb in sorted(destructive_grants):
            if verb in invoked_verbs:
                continue
            if verb in justified_verbs:
                continue
            errors.append(
                f"{rel}: 'allowed-tools' grants destructive 'Bash({verb}:*)' but the body never "
                f"invokes `{verb}` — add a 'destructive-tools-justification' entry or drop the grant"
            )


def main():
    errors = []

    skills_root = os.path.join(REPO_ROOT, "skills")
    agents_skills_dir = os.path.join(REPO_ROOT, ".agents", "skills")
    commands_dir = os.path.join(REPO_ROOT, "commands")

    # Walk skills/ exactly once and partition into SKILL.md files vs. other
    # reference Markdown, instead of walking it twice and set-differencing.
    all_skills_md = find_markdown(skills_root)
    top_skill_files = sorted(p for p in all_skills_md if os.path.basename(p) == "SKILL.md")
    other_skill_md = sorted(p for p in all_skills_md if os.path.basename(p) != "SKILL.md")

    agents_skill_files = sorted(find_markdown(agents_skills_dir, name="SKILL.md"))
    skill_files = sorted(set(top_skill_files) | set(agents_skill_files))

    command_files = find_markdown(commands_dir, recursive=False)

    # Read each file exactly once.
    texts = {}
    for path in top_skill_files + other_skill_md + command_files:
        with open(path, "r", encoding="utf-8") as f:
            texts[path] = f.read()

    literal_by_file = {}
    body_start_by_file = {}
    # path -> (fm, body, body_start), so downstream checks consume the one
    # parse done here instead of re-running parse_frontmatter themselves.
    parsed_by_file = {}

    # SKILL.md needs `name` too; commands take theirs from the filename. The
    # required-key tuple is the only difference, so the per-file bookkeeping
    # below stays in one place rather than being kept in sync by hand.
    for paths, required_keys in (
        (top_skill_files, ("name", "description")),
        (command_files, ("description",)),
    ):
        for path in paths:
            rel = os.path.relpath(path, REPO_ROOT)
            fm, body, body_start = parse_frontmatter(texts[path], rel, errors)
            if fm is None:
                errors.append(f"{rel}: missing or malformed YAML frontmatter (expected leading '---' block)")
            else:
                _validate_frontmatter_keys(rel, path, fm, errors, required_keys)
            body_start_by_file[path] = body_start
            parsed_by_file[path] = (fm, body, body_start)
            literal_by_file[path] = check_links(rel, os.path.dirname(path), body, errors)

    # Non-SKILL.md reference docs (skills/holiday-planner/01-*.md …
    # 06-*.md, skills/trip-scraper/search-queries.md) get no frontmatter
    # requirement, but must still get link checking and the
    # no-repo-relative-paths scan — they are the files /setup and /scrape
    # read most, and were previously an unchecked coverage hole.
    for path in other_skill_md:
        rel = os.path.relpath(path, REPO_ROOT)
        text = texts[path]
        _, _, body_start = parse_frontmatter(text, rel, [])  # discard: no frontmatter requirement here
        body_start_by_file[path] = body_start
        literal_by_file[path] = check_links(rel, os.path.dirname(path), text, errors)

    # Batch the .gitignore exemption lookup for bare backticked literal
    # paths across every file into a single `git check-ignore --stdin` call.
    all_git_rel = {
        os.path.relpath(resolved, REPO_ROOT)
        for pairs in literal_by_file.values()
        for _, resolved in pairs
    }
    ignored = ignored_paths(all_git_rel, root=REPO_ROOT) if all_git_rel else set()
    for path, pairs in literal_by_file.items():
        rel = os.path.relpath(path, REPO_ROOT)
        for target, resolved in pairs:
            git_rel = os.path.relpath(resolved, REPO_ROOT)
            if git_rel in ignored:
                # Personal-data dirs are runtime paths written by /setup,
                # /scrape, /watch, /plan, never tracked in git.
                continue
            _report_missing(errors, rel, "backticked repo-relative path does not exist", target, resolved)

    adapter_dir_names = None
    if os.path.isdir(agents_skills_dir):
        adapter_dir_names = sorted(
            d for d in os.listdir(agents_skills_dir) if os.path.isdir(os.path.join(agents_skills_dir, d))
        )

    check_discovery_completeness(command_files, skill_files, adapter_dir_names, errors)
    check_agents_skills_structure(agents_skills_dir, adapter_dir_names, errors)
    check_adapter_contract(agents_skills_dir, adapter_dir_names, errors)
    check_path_resolution_block(command_files, texts, errors)
    check_allowed_tools_match_body(command_files, texts, parsed_by_file, errors)

    # .agents/skills/*/SKILL.md deliberately excluded: those adapters are
    # designed to be copied out standalone and legitimately document a bare
    # `.agents/skills/<name>/search.py` CLI invocation for themselves.
    check_no_repo_relative_paths(
        [(p, texts[p], body_start_by_file[p]) for p in top_skill_files + other_skill_md + command_files],
        errors,
    )

    plugin = load_json(os.path.join(REPO_ROOT, ".claude-plugin", "plugin.json"), errors)
    marketplace = load_json(os.path.join(REPO_ROOT, ".claude-plugin", "marketplace.json"), errors)
    check_manifest_consistency(plugin, marketplace, errors)

    check_symlink_integrity(errors)

    mcp = load_json(os.path.join(REPO_ROOT, ".mcp.json"), errors)
    check_mcp_consistency(mcp, plugin, errors)

    reset_path = os.path.join(commands_dir, "reset.md")
    if reset_path in texts:
        reset_text = texts[reset_path]
    elif os.path.isfile(reset_path):
        with open(reset_path, "r", encoding="utf-8") as f:
            reset_text = f.read()
    else:
        reset_text = None
    check_reset_protect_list(reset_text, errors)

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
