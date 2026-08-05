#!/usr/bin/env python3
"""_repo.py — shared git/repo helpers for tools/lint_skills.py and tools/security_guards.py.

Repo-local only: this module is never copied into `.agents/skills/*` forks,
which must stay self-contained. It exists purely to give the two lint/guard
scripts a single source of truth for "where is the repo root", "what's
tracked", and "what does git consider ignored" instead of each re-deriving
(and subtly disagreeing on) the same facts.
"""
import os
import subprocess

# Personal-data path names shared by tools/security_guards.py and
# tools/lint_skills.py, so the same five names aren't independently encoded
# (as a list of representative sample paths vs. a regex alternation) in two
# files that could silently drift apart.
PERSONAL_DIRS = ("profile", "itineraries", "watchlist", "trip_scraper")
PERSONAL_FILES = ("trip_tracker.csv",)

# Adapter credential env var names shared by tools/lint_skills.py,
# tools/security_guards.py, and (via a derivation step) .github/workflows/ci.yml.
ADAPTER_CRED_VARS = (
    "AMADEUS_API_KEY",
    "AMADEUS_API_SECRET",
    "STAYS_API_KEY",
    "STAYS_API_URL",
    "PACKAGES_API_KEY",
    "PACKAGES_API_URL",
)


def repo_root():
    """Return the absolute repo root.

    Prefers `git rev-parse --show-toplevel` (correct even from within a
    worktree); falls back to a `__file__`-relative guess if git is
    unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            top = result.stdout.strip()
            if top:
                return top
    except (OSError, FileNotFoundError):
        pass
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def tracked_files(root=None):
    """Return the list of `git ls-files` paths (relative to root), or raise."""
    root = root or repo_root()
    result = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr}")
    return [line for line in result.stdout.splitlines() if line]


def tracked_modes(paths=None, root=None):
    """Return {path: git-index-mode} from `git ls-files -s [paths...]`.

    Mode "120000" means a tracked symlink. Handles the tab-separated
    `"<mode> <sha> <stage>\\t<path>"` output format once, shared by any
    caller that needs to know how a path is tracked (e.g. verifying
    `.claude/commands` / `.claude/skills` are tracked as symlinks).
    """
    root = root or repo_root()
    cmd = ["git", "ls-files", "-s"]
    if paths:
        cmd += list(paths)
    result = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files -s failed: {result.stderr.strip()}")

    modes = {}
    for line in result.stdout.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if parts and path:
            modes[path] = parts[0]
    return modes


def ignored_paths(paths, root=None, no_index=False):
    """Return the subset of `paths` whose .gitignore patterns match.

    Batches everything into a single `git check-ignore --stdin` call rather
    than spawning one subprocess per path. Exit codes: 0 = at least one path
    ignored, 1 = none ignored, anything else = error. A git failure raises
    rather than silently behaving as "nothing ignored".

    `no_index=True` passes `--no-index`, which is REQUIRED when asking about
    paths that are already tracked. By default `git check-ignore` reports
    nothing for a tracked file — tracking wins over .gitignore — so a caller
    checking "is this tracked file one that should have been ignored?" gets
    an empty set and silently concludes all is well. That is exactly the
    leak `check_personal_paths_not_tracked` exists to catch, so it must pass
    `no_index=True`. Callers asking about untracked paths (e.g. whether
    .gitignore *would* cover a hypothetical file) should leave it False.
    """
    paths = list(paths)
    if not paths:
        return set()
    root = root or repo_root()
    cmd = ["git", "check-ignore", "--stdin", "-v"]
    if no_index:
        cmd.append("--no-index")
    result = subprocess.run(
        cmd,
        cwd=root,
        input="\n".join(paths) + "\n",
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git check-ignore failed: {result.stderr.strip()}")

    ignored = set()
    for line in result.stdout.splitlines():
        if not line:
            continue
        # -v output: "<source>:<linenum>:<pattern>\t<pathname>"
        source, _, pathname = line.partition("\t")
        if not pathname:
            ignored.add(line)
            continue
        # git reports the LAST pattern that matched, which may be a negation
        # (`!documents/README.md`). A negated match means the path is
        # explicitly re-included — i.e. NOT ignored. Without this, every
        # deliberately-tracked scaffold file (.gitkeep, documents/README.md)
        # is misreported as ignored.
        pattern = source.rpartition(":")[2]
        if pattern.startswith("!"):
            continue
        ignored.add(pathname)
    return ignored
