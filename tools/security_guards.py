#!/usr/bin/env python3
"""security_guards.py — guard against committed secrets and untracked-personal-data leaks.

Checks (stdlib only):
  1. No tracked file matches secret patterns (API keys, tokens,
     `AMADEUS_API_SECRET=<value>`, private keys, .env-style assignments), with
     an allowlist for the documented env-var NAMES appearing in docs (e.g.
     `AMADEUS_API_KEY` mentioned in a SKILL.md without a real value attached).
  2. Clone-mode `.gitignore` coverage: `.gitignore` exists and covers each
     personal path (`profile/`, `itineraries/`, `watchlist/`, `trip_scraper/`,
     `trip_tracker.csv`, `documents/` contents, `.env`) — verified via
     `git check-ignore` on representative sample paths. This check is scoped
     to clone mode on purpose: in plugin mode, personal data is written under
     `~/.ai-holiday-search`, entirely outside any git repository, so there is
     no `.gitignore` for it to cover and no equivalent check is meaningful
     there. It is NOT a no-op — it still fails if THIS repo's `.gitignore`
     (the one clone-mode users rely on) stops covering any personal path.
  3. No tracked file lives under those personal paths.
  4. `commands/setup.md` still instructs creating `<DATA_ROOT>/.gitignore`
     (contents `*`) before writing any profile file, in plugin mode. This
     guards against a real leak vector: `~/.ai-holiday-search` sits outside
     any git repo, but `$HOME` itself may be a tracked repo (e.g. dotfiles),
     so without that step's `.gitignore` running first, personal profile
     data written there could get swept into an unrelated commit.

Exit 0 on success; non-zero with actionable messages on failure.
"""
import os
import re
import sys

from _repo import (
    ADAPTER_CRED_VARS,
    PERSONAL_DIRS,
    PERSONAL_FILES,
    repo_root,
    ignored_paths,
    tracked_files as _tracked_files,
)

REPO_ROOT = repo_root()

MAX_SCANNED_FILE_BYTES = 1024 * 1024  # 1 MB; skip larger tracked files (e.g. binaries).

# Env var NAMES that are fine to mention in docs/code as long as no value is attached.
ALLOWED_ENV_VAR_NAMES = set(ADAPTER_CRED_VARS)

# Secret-shaped patterns: NAME=value or NAME: value where NAME looks like a
# credential. The value is captured once, quotes and all; callers strip
# surrounding quotes with `strip_quotes` before evaluating it.
SECRET_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:API_KEY|API_SECRET|SECRET|TOKEN|PASSWORD|ACCESS_KEY))\s*[:=]\s*"
    r"(\"[^\"]*\"|'[^']*'|`[^`]*`|[^\s\"'`]+)"
)

PRIVATE_KEY_RE = re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----")

PLACEHOLDER_VALUES = {
    "",
    "...",
    "<value>",
    "<key>",
    "your-key-here",
    "changeme",
    "xxx",
    "your_api_key",
    "example",
}

# Looser placeholder heuristics: values that are clearly template text rather
# than a real secret (e.g. `your_key_here`, `<your-secret>`, `xxx-xxx-xxx`).
PLACEHOLDER_PATTERN_RE = re.compile(
    r"^[<\"']?your[_-].*(key|secret|token|here)[>\"']?$|^[<\"'].*[>\"']$", re.IGNORECASE
)


def strip_quotes(value):
    """Strip one layer of matching surrounding quote characters, if present."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'`":
        return value[1:-1]
    return value


def looks_like_placeholder(value):
    stripped = value.strip(".,")
    if stripped.lower() in PLACEHOLDER_VALUES:
        return True
    return bool(PLACEHOLDER_PATTERN_RE.match(stripped))

# Representative sample paths under each shared personal-data name (dirs get
# one plausible file inside them; PERSONAL_FILES entries are used as-is),
# plus two paths that aren't part of the shared PERSONAL_DIRS/PERSONAL_FILES
# constants (documents/ contents and .env).
_PERSONAL_DIR_SAMPLES = {
    "profile": "some-file.md",
    "itineraries": "some-trip/itinerary.md",
    "watchlist": "some-trip.json",
    "trip_scraper": "seen.json",
}
PERSONAL_PATHS = (
    [f"{d}/{_PERSONAL_DIR_SAMPLES[d]}" for d in PERSONAL_DIRS]
    + list(PERSONAL_FILES)
    + [
        "documents/past-trips/some-file.md",  # representative sample under documents/
        ".env",
    ]
)


def git_ls_files():
    try:
        return _tracked_files(root=REPO_ROOT)
    except RuntimeError as e:
        sys.stderr.write(f"security_guards.py: {e}\n")
        sys.exit(1)


def check_secret_patterns(tracked_files, errors):
    for relpath in tracked_files:
        full_path = f"{REPO_ROOT}/{relpath}"
        try:
            if os.path.getsize(full_path) > MAX_SCANNED_FILE_BYTES:
                continue
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except (OSError, IsADirectoryError):
            continue

        for match in SECRET_ASSIGNMENT_RE.finditer(text):
            var_name = match.group(1)
            value = strip_quotes(match.group(2))

            if looks_like_placeholder(value):
                continue

            if var_name in ALLOWED_ENV_VAR_NAMES:
                # A documented var name followed by a real-looking value is still
                # suspicious — flag it rather than silently trust the allowlist.
                errors.append(
                    f"{relpath}: possible secret value assigned to documented env var '{var_name}' "
                    f"(value: '{value[:4]}...' truncated) — use a placeholder in docs"
                )
                continue

            errors.append(f"{relpath}: possible secret assignment matching '{var_name}'")

        if PRIVATE_KEY_RE.search(text):
            errors.append(f"{relpath}: contains what looks like a private key block")


def check_personal_paths_not_tracked(tracked_files, errors):
    # A tracked file that matches a .gitignore pattern (e.g. force-added with
    # `git add -f`) is exactly the leak this check exists to catch. Ask git
    # directly rather than restating .gitignore's prefixes here — .gitignore
    # is the single source of truth, and its README/.gitkeep negation
    # patterns already exempt the documented scaffolding.
    # `no_index=True` is essential: without it git reports nothing for a
    # tracked path (tracking beats .gitignore), so this check would pass
    # unconditionally and catch no leaks at all.
    for relpath in sorted(ignored_paths(tracked_files, root=REPO_ROOT, no_index=True)):
        errors.append(f"{relpath}: tracked file matches a .gitignore pattern — should be gitignored (untrack it)")


def check_gitignore_coverage(errors):
    """Clone-mode only: this repo's `.gitignore` must keep covering the
    personal paths for anyone who forks/clones it and runs the framework
    in-place. Plugin-mode installs write personal data to
    `~/.ai-holiday-search`, outside any git repo, so there is nothing for a
    `.gitignore` to cover there — that mode needs no equivalent check, and
    deliberately has none. This check must still fail loudly if this repo's
    own `.gitignore` regresses."""
    gitignore_path = f"{REPO_ROOT}/.gitignore"

    if not os.path.isfile(gitignore_path):
        errors.append(".gitignore: file does not exist — must cover personal paths (profile/, itineraries/, watchlist/, trip_scraper/, trip_tracker.csv, documents/ contents, .env)")
        return

    covered = ignored_paths(PERSONAL_PATHS, root=REPO_ROOT)
    for sample in PERSONAL_PATHS:
        if sample not in covered:
            errors.append(f".gitignore: does not ignore personal path '{sample}' (git check-ignore reported not ignored)")


SETUP_MD_PATH = f"{REPO_ROOT}/commands/setup.md"

# Anchor text for the plugin-mode `<DATA_ROOT>/.gitignore` step in setup.md,
# and for the profile-writing step it must precede.
SETUP_GITIGNORE_STEP_TEXT = "Ensure `<DATA_ROOT>` is gitignored (plugin mode only)"
SETUP_GITIGNORE_CONTENT_TEXT = "containing a single line: `*`"
SETUP_PROFILE_WRITE_STEP_TEXT = "Write profile files."


def check_setup_gitignore_step(errors):
    """commands/setup.md must still instruct creating `<DATA_ROOT>/.gitignore`
    containing `*`, before the step that writes profile files.

    Deliberately a prose pin, not a filesystem check: CI never has a real
    `~/.ai-holiday-search`, so a check that skipped when that directory is
    absent would read as coverage while asserting nothing on every run. The
    observable regression is textual — the instruction deleted, or reordered
    after profile files are already written. Anchored on stable phrases
    rather than line numbers.
    """
    if not os.path.isfile(SETUP_MD_PATH):
        errors.append("commands/setup.md: file does not exist — cannot verify the DATA_ROOT/.gitignore step")
        return

    with open(SETUP_MD_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    gitignore_idx = text.find(SETUP_GITIGNORE_STEP_TEXT)
    if gitignore_idx == -1:
        errors.append(
            "commands/setup.md: missing the plugin-mode DATA_ROOT/.gitignore step "
            f"(expected text: '{SETUP_GITIGNORE_STEP_TEXT}') — /setup must create "
            "<DATA_ROOT>/.gitignore before writing any profile file, since $HOME may itself be a tracked repo"
        )
        return

    profile_write_idx = text.find(SETUP_PROFILE_WRITE_STEP_TEXT)
    if profile_write_idx == -1:
        errors.append(
            "commands/setup.md: missing the profile-writing step "
            f"(expected text: '{SETUP_PROFILE_WRITE_STEP_TEXT}') — cannot verify ordering against the DATA_ROOT/.gitignore step"
        )
        return

    # Scope the content assertion to the gitignore step's own span (from its
    # anchor to the start of the next numbered step) rather than searching the
    # whole file — otherwise the '*' phrase migrating elsewhere in setup.md
    # would still satisfy `in text` even if the step itself lost it.
    step_span = text[gitignore_idx:profile_write_idx] if profile_write_idx > gitignore_idx else text[gitignore_idx:]

    if SETUP_GITIGNORE_CONTENT_TEXT not in step_span:
        errors.append(
            "commands/setup.md: the DATA_ROOT/.gitignore step no longer specifies writing "
            f"'{SETUP_GITIGNORE_CONTENT_TEXT}' — the step must create the file with contents '*'"
        )
        return

    if gitignore_idx > profile_write_idx:
        errors.append(
            "commands/setup.md: the DATA_ROOT/.gitignore step appears AFTER the profile-writing step — "
            "it must run before any profile file is written, or personal data could be written unprotected first"
        )


def main():
    errors = []

    tracked_files = git_ls_files()
    check_secret_patterns(tracked_files, errors)
    check_setup_gitignore_step(errors)
    try:
        check_personal_paths_not_tracked(tracked_files, errors)
        check_gitignore_coverage(errors)
    except RuntimeError as e:
        # A git failure means ignore-status could not be determined — treat
        # that as a hard error, never as a silent pass.
        errors.append(f"could not determine git-ignore status: {e}")

    if errors:
        sys.stderr.write("security_guards.py: FAILED\n")
        for e in errors:
            sys.stderr.write(f"  - {e}\n")
        sys.stderr.write(f"\n{len(errors)} issue(s) found.\n")
        return 1

    print("security_guards.py: OK — no secrets or untracked-personal-data leaks detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
