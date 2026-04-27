#!/usr/bin/env python3
"""Validate the Ansible skill package without third-party dependencies."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "ansible-skill"
SKILL_MD = SKILL_DIR / "SKILL.md"
REQUIRED_REFS = {
    "ci-cd-workflows.md",
    "collections-and-supply-chain.md",
    "execution-and-runtime.md",
    "idempotency-patterns.md",
    "inventory-and-variables.md",
    "quick-reference.md",
    "security-and-vault.md",
    "testing-frameworks.md",
}
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def fail(message: str) -> None:
    print(f"[ERROR] {message}")
    sys.exit(1)


def parse_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_simple_yaml_mapping(content: str, source: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if "\t" in raw_line:
            fail(f"{source}:{line_number} contains a tab; use spaces for YAML")

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2 != 0:
            fail(f"{source}:{line_number} uses odd indentation")

        line = raw_line.strip()
        if ":" not in line or line.startswith("- "):
            fail(f"{source}:{line_number} must be a key/value mapping")

        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            fail(f"{source}:{line_number} has an empty YAML key")

        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        parent_indent = stack[-1][0]
        expected_indent = 0 if parent_indent == -1 else parent_indent + 2
        if indent != expected_indent:
            fail(f"{source}:{line_number} has indent {indent}; expected {expected_indent}")

        if not value.strip():
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_scalar(value)

    return root


def parse_frontmatter(content: str) -> dict[str, Any]:
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        fail("SKILL.md missing YAML frontmatter")
    return parse_simple_yaml_mapping(match.group(1), "SKILL.md frontmatter")


def require_path(data: dict[str, Any], keys: tuple[str, ...], label: str) -> str:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            fail(f"{label} missing {'.'.join(keys)}")
        value = value[key]
    if not isinstance(value, str) or not value:
        fail(f"{label} field {'.'.join(keys)} must be a non-empty string")
    return value


def slugify(heading: str) -> str:
    slug = heading.strip().lower().replace("&", "")
    slug = re.sub(r"[`*_{}\[\]()<>=!?:,.\"'\\]", "", slug)
    return re.sub(r"\s+", "-", slug)


def heading_slugs(path: Path) -> set[str]:
    slugs: set[str] = set()
    for match in re.finditer(r"^(#{1,6})\s+(.+?)\s*#*$", path.read_text(), re.M):
        slugs.add(slugify(match.group(2)))
    return slugs


def check_exists() -> None:
    required = [
        SKILL_MD,
        ROOT / ".claude-plugin" / "marketplace.json",
        ROOT / ".claude-plugin" / "plugin.json",
        ROOT / ".codex-plugin" / "plugin.json",
        ROOT / ".gitignore",
    ]
    for path in required:
        if not path.exists():
            fail(f"Missing required file: {path.relative_to(ROOT)}")

    refs_dir = SKILL_DIR / "references"
    missing_refs = sorted(REQUIRED_REFS - {path.name for path in refs_dir.glob("*.md")})
    if missing_refs:
        fail(f"Missing references: {', '.join(missing_refs)}")


def check_skill_md() -> dict[str, Any]:
    content = SKILL_MD.read_text()
    lines = content.splitlines()
    if len(lines) > 300:
        fail(f"SKILL.md has {len(lines)} lines; target is <= 300")

    frontmatter = parse_frontmatter(content)
    if frontmatter.get("name") != "ansible-skill":
        fail("SKILL.md frontmatter name must be ansible-skill")
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.startswith("Use when"):
        fail("SKILL.md description must start with 'Use when'")
    if len(description) >= 1024:
        fail(f"SKILL.md description is too long: {len(description)}")
    if frontmatter.get("license") != "Apache-2.0":
        fail("SKILL.md license must be Apache-2.0")
    if "Response Contract" not in content:
        fail("SKILL.md missing Response Contract")
    return frontmatter


def check_links() -> None:
    markdown_files = sorted(path for path in ROOT.rglob("*.md") if ".git" not in path.parts)
    slug_cache: dict[Path, set[str]] = {}

    for path in markdown_files:
        for match in MARKDOWN_LINK_RE.finditer(path.read_text()):
            raw_target = match.group(1).strip()
            if raw_target.startswith("<") and raw_target.endswith(">"):
                raw_target = raw_target[1:-1]
            if raw_target.startswith("#"):
                continue
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", raw_target) or raw_target.startswith("//"):
                continue

            target_name, _, anchor = raw_target.partition("#")
            target_name = target_name.split("?", 1)[0]
            if not target_name.lower().endswith(".md"):
                continue

            target = (path.parent / target_name).resolve()
            try:
                target.relative_to(ROOT.resolve())
            except ValueError:
                fail(f"Markdown link in {path.relative_to(ROOT)} points outside repo: {raw_target}")
            if not target.exists():
                fail(f"Broken Markdown link in {path.relative_to(ROOT)}: {raw_target}")
            if anchor:
                slug_cache.setdefault(target, heading_slugs(target))
                if anchor not in slug_cache[target]:
                    fail(f"Broken Markdown anchor in {path.relative_to(ROOT)}: {raw_target}")


def load_json(rel: str) -> dict[str, Any]:
    path = ROOT / rel
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON in {rel}: {exc}")
    if not isinstance(data, dict):
        fail(f"{rel} must contain a JSON object")
    return data


def check_versions(frontmatter: dict[str, Any]) -> None:
    marketplace = load_json(".claude-plugin/marketplace.json")
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or not plugins or not isinstance(plugins[0], dict):
        fail(".claude-plugin/marketplace.json must contain plugins[0]")

    versions = {
        "SKILL.md metadata.version": require_path(frontmatter, ("metadata", "version"), "SKILL.md"),
        ".claude-plugin/marketplace.json version": require_path(
            marketplace, ("version",), ".claude-plugin/marketplace.json"
        ),
        ".claude-plugin/marketplace.json plugins[0].version": require_path(
            plugins[0], ("version",), ".claude-plugin/marketplace.json plugins[0]"
        ),
        ".claude-plugin/plugin.json version": require_path(
            load_json(".claude-plugin/plugin.json"), ("version",), ".claude-plugin/plugin.json"
        ),
        ".codex-plugin/plugin.json version": require_path(
            load_json(".codex-plugin/plugin.json"), ("version",), ".codex-plugin/plugin.json"
        ),
    }

    if len(set(versions.values())) != 1:
        details = ", ".join(f"{name}={version}" for name, version in versions.items())
        fail(f"Version mismatch: {details}")


def check_gitignore() -> None:
    forbidden_patterns = {
        "*.json",
        "*.md",
        "*.yaml",
        "*.yml",
        ".claude-plugin/",
        ".codex-plugin/",
        ".github/",
        "scripts/",
        "skills/",
    }
    patterns = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    blocked = sorted(forbidden_patterns & patterns)
    if blocked:
        fail(f".gitignore excludes package source files: {', '.join(blocked)}")


def main() -> int:
    check_exists()
    frontmatter = check_skill_md()
    check_links()
    check_versions(frontmatter)
    check_gitignore()
    print("[OK] Ansible skill validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
