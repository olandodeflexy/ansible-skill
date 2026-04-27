#!/usr/bin/env python3
"""Compute next semver and release notes from commits since the last tag."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
CLAUDE_PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
CODEX_PLUGIN = ROOT / ".codex-plugin" / "plugin.json"
SKILL = ROOT / "skills" / "ansible-skill" / "SKILL.md"
CHANGELOG = ROOT / "CHANGELOG.md"
RELEASE_VERSION = ROOT / ".release-version"
RELEASE_NOTES = ROOT / ".release-notes.md"

FEAT_RE = re.compile(r"^feat(?:\([^)]+\))?:")
BREAKING_RE = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)


def current_version() -> tuple[int, int, int]:
    mp = json.loads(MARKETPLACE.read_text())
    return tuple(int(x) for x in mp["version"].split("."))


def last_tag() -> str | None:
    res = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "--match", "v*"],
        capture_output=True, text=True,
    )
    return res.stdout.strip() or None if res.returncode == 0 else None


def commits_since(tag: str | None) -> list[dict[str, str]]:
    range_arg = f"{tag}..HEAD" if tag else "HEAD"
    res = subprocess.run(
        ["git", "log", range_arg, "--format=%H%x1f%s%x1f%B%x1e", "--no-merges"],
        capture_output=True, text=True, check=True,
    )
    commits: list[dict[str, str]] = []
    for record in res.stdout.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        sha, subject, body = record.split("\x1f", 2)
        commits.append({"sha": sha, "subject": subject.strip(), "body": body.strip()})
    return commits


def classify(commits: list[dict[str, str]]) -> str:
    bump = "patch"
    for commit in commits:
        subject = commit["subject"]
        message = commit["body"]
        if BREAKING_RE.search(message) or re.match(r"^[a-z]+(?:\([^)]+\))?!:", subject):
            return "major"
        if FEAT_RE.match(subject):
            bump = "minor"
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

    for path in (CLAUDE_PLUGIN, CODEX_PLUGIN):
        if path.exists():
            data = json.loads(path.read_text())
            data["version"] = new
            path.write_text(json.dumps(data, indent=2) + "\n")

    content = SKILL.read_text()
    updated = re.sub(r"^  version: .*$", f"  version: {new}", content, count=1, flags=re.M)
    if updated == content:
        raise RuntimeError("Could not find SKILL.md metadata.version to update")
    SKILL.write_text(updated)


def write_release_notes(new: str, commits: list[dict[str, str]]) -> None:
    subjects = [commit["subject"] for commit in commits]
    if not subjects:
        subjects = ["Release maintenance updates."]

    lines = [f"## v{new}", "", "Changes:"]
    lines.extend(f"- {subject}" for subject in subjects)
    RELEASE_NOTES.write_text("\n".join(lines) + "\n")

    existing = CHANGELOG.read_text()
    entry = "\n".join(["", f"## v{new}", "", *[f"- {subject}" for subject in subjects], ""])
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
    write_release_notes(new_str, commits)
    RELEASE_VERSION.write_text(new_str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
