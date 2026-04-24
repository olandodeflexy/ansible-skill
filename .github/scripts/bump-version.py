#!/usr/bin/env python3
"""Compute next semver given current version and commit messages since last tag."""
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
SKILL = ROOT / "skills" / "ansible-skill" / "SKILL.md"
CHANGELOG = ROOT / "CHANGELOG.md"


def current_version() -> tuple[int, int, int]:
    mp = json.loads(MARKETPLACE.read_text())
    return tuple(int(x) for x in mp["version"].split("."))


def last_tag() -> str | None:
    res = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "--match", "v*"],
        capture_output=True, text=True,
    )
    return res.stdout.strip() or None if res.returncode == 0 else None


def commits_since(tag: str | None) -> list[str]:
    range_arg = f"{tag}..HEAD" if tag else "HEAD"
    res = subprocess.run(
        ["git", "log", range_arg, "--format=%s", "--no-merges"],
        capture_output=True, text=True, check=True,
    )
    return [l for l in res.stdout.splitlines() if l.strip()]


def classify(commits: list[str]) -> str:
    bump = "patch"
    for msg in commits:
        if "BREAKING CHANGE" in msg or re.match(r"^[a-z]+!:", msg):
            return "major"
        if msg.startswith("feat:") or msg.startswith("feat("):
            bump = "minor" if bump != "major" else bump
    return bump


def next_version(cur: tuple[int, int, int], bump: str) -> tuple[int, int, int]:
    major, minor, patch = cur
    if bump == "major":
        return (major + 1, 0, 0)
    if bump == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def sync_versions(new: str) -> None:
    mp = json.loads(MARKETPLACE.read_text())
    mp["version"] = new
    mp["plugins"][0]["version"] = new
    MARKETPLACE.write_text(json.dumps(mp, indent=2) + "\n")

    content = SKILL.read_text()
    parts = content.split("---", 2)
    fm = yaml.safe_load(parts[1])
    fm["metadata"]["version"] = new
    new_fm = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False)
    SKILL.write_text(f"---\n{new_fm}---{parts[2]}")

    existing = CHANGELOG.read_text()
    entry = f"\n## v{new}\n\nSee commit log for details.\n"
    CHANGELOG.write_text(existing.rstrip() + "\n" + entry)


def main() -> int:
    cur = current_version()
    tag = last_tag()
    commits = commits_since(tag)
    if not commits:
        print("No commits since last tag; skipping release.")
        return 0
    bump = classify(commits)
    new = next_version(cur, bump)
    new_str = f"{new[0]}.{new[1]}.{new[2]}"
    print(f"Current: {'.'.join(str(x) for x in cur)} | Bump: {bump} | Next: {new_str}")
    sync_versions(new_str)
    Path(".release-version").write_text(new_str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
