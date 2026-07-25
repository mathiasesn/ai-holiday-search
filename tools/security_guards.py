#!/usr/bin/env python3
"""security_guards.py — guard against committed secrets and untracked-personal-data leaks.

Checks (stdlib only):
  1. No tracked file matches secret patterns (API keys, tokens,
     `AMADEUS_API_SECRET=<value>`, private keys, .env-style assignments), with
     an allowlist for the documented env-var NAMES appearing in docs (e.g.
     `AMADEUS_API_KEY` mentioned in a SKILL.md without a real value attached).
  2. `.gitignore` exists and covers each personal path (`profile/`,
     `itineraries/`, `watchlist/`, `trip_scraper/`, `trip_tracker.csv`,
     `documents/` contents, `.env`) — verified via `git check-ignore` on
     representative sample paths.
  3. No tracked file lives under those personal paths.

Exit 0 on success; non-zero with actionable messages on failure.
"""
import re
import subprocess
import sys

REPO_ROOT = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()

# Env var NAMES that are fine to mention in docs/code as long as no value is attached.
ALLOWED_ENV_VAR_NAMES = {
    "AMADEUS_API_KEY",
    "AMADEUS_API_SECRET",
    "STAYS_API_KEY",
    "STAYS_API_URL",
    "PACKAGES_API_KEY",
    "PACKAGES_API_URL",
}

# Secret-shaped patterns: NAME=value or NAME: value where NAME looks like a
# credential and value is a non-empty, non-placeholder token.
SECRET_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:API_KEY|API_SECRET|SECRET|TOKEN|PASSWORD|ACCESS_KEY))\s*[:=]\s*"
    r"(?:\"([^\"]*)\"|'([^']*)'|`([^`]*)`|([^\s\"'`]+))"
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


def looks_like_placeholder(value):
    stripped = value.strip("\"'.,")
    if stripped.lower() in PLACEHOLDER_VALUES:
        return True
    return bool(PLACEHOLDER_PATTERN_RE.match(stripped))

PERSONAL_PATHS = [
    "profile/some-file.md",
    "itineraries/some-trip/itinerary.md",
    "watchlist/some-trip.json",
    "trip_scraper/seen.json",
    "trip_tracker.csv",
    "documents/past-trips/some-file.md",  # representative sample under documents/
    ".env",
]


def run(cmd):
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)


def git_ls_files():
    result = run(["git", "ls-files"])
    if result.returncode != 0:
        sys.stderr.write(f"security_guards.py: git ls-files failed: {result.stderr}\n")
        sys.exit(1)
    return [line for line in result.stdout.splitlines() if line]


def check_secret_patterns(tracked_files, errors):
    for relpath in tracked_files:
        try:
            with open(f"{REPO_ROOT}/{relpath}", "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except (OSError, IsADirectoryError):
            continue

        for match in SECRET_ASSIGNMENT_RE.finditer(text):
            var_name = match.group(1)
            value = next(g for g in match.groups()[1:] if g is not None)
            if var_name in ALLOWED_ENV_VAR_NAMES and looks_like_placeholder(value):
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
    personal_prefixes = ("profile/", "itineraries/", "watchlist/", "trip_scraper/", "documents/")
    for relpath in tracked_files:
        if relpath == "trip_tracker.csv":
            errors.append(f"{relpath}: personal tracker file is tracked in git — should be gitignored")
            continue
        if relpath == ".env":
            errors.append(f"{relpath}: .env is tracked in git — should be gitignored")
            continue
        for prefix in personal_prefixes:
            if relpath.startswith(prefix):
                # Allow documented scaffolding: READMEs and .gitkeep placeholders.
                base = relpath.rsplit("/", 1)[-1]
                if base in {"README.md", ".gitkeep"}:
                    continue
                errors.append(f"{relpath}: tracked file under personal path '{prefix}' — should be gitignored")


def check_gitignore_coverage(errors):
    gitignore_path = f"{REPO_ROOT}/.gitignore"
    import os

    if not os.path.isfile(gitignore_path):
        errors.append(".gitignore: file does not exist — must cover personal paths (profile/, itineraries/, watchlist/, trip_scraper/, trip_tracker.csv, documents/ contents, .env)")
        return

    for sample in PERSONAL_PATHS:
        result = run(["git", "check-ignore", "-q", sample])
        # check-ignore exit codes: 0 = ignored, 1 = not ignored, 128 = error (e.g. path doesn't exist is fine, check-ignore doesn't require existence)
        if result.returncode == 1:
            errors.append(f".gitignore: does not ignore personal path '{sample}' (git check-ignore reported not ignored)")
        elif result.returncode not in (0, 1):
            errors.append(f".gitignore: git check-ignore errored on '{sample}': {result.stderr.strip()}")


def main():
    errors = []

    tracked_files = git_ls_files()
    check_secret_patterns(tracked_files, errors)
    check_personal_paths_not_tracked(tracked_files, errors)
    check_gitignore_coverage(errors)

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
