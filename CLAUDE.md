# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **For End Users:** See [README.md](README.md) for installation and usage.
>
> **This file** is for contributors, maintainers, and skill developers.

## What This Is

A **Claude Code skill** — executable documentation that Claude loads to provide Ansible/ansible-core expertise. It encodes diagnose-first Ansible patterns into Claude's context as version-controlled AI instructions.

## Repository Structure

```
ansible-skill/
├── .codex-plugin/plugin.json        # Codex plugin metadata
├── .claude-plugin/marketplace.json  # Plugin metadata (version synced automatically)
├── .claude-plugin/plugin.json       # Claude plugin metadata
├── scripts/validate_skill.py        # Local/CI package validation
├── skills/
│   └── ansible-skill/               # Skill autodiscovered by Claude Code plugin system
│       ├── SKILL.md                 # Core skill file (<300 lines)
│       └── references/              # Reference files loaded on demand
│           ├── idempotency-patterns.md
│           ├── inventory-and-variables.md
│           ├── security-and-vault.md
│           ├── execution-and-runtime.md
│           ├── testing-frameworks.md
│           ├── ci-cd-workflows.md
│           ├── collections-and-supply-chain.md
│           └── quick-reference.md
└── .github/workflows/
    ├── validate.yml                 # PR validation (frontmatter, size, links, lint)
    └── automated-release.yml        # Auto-release on master push via conventional commits
```

## Development Workflow

**This is documentation, not code.** No build, no compiled tests.

### Validation

CI runs automatically on PRs and pushes to `master`. To check locally:

```bash
python3 scripts/validate_skill.py
```

### Testing Changes

No automated suite. Manual flow:
1. Edit `SKILL.md` or a `references/*.md` file
2. Reload the skill in Claude Code
3. Run real Ansible queries (e.g., "Write an idempotent playbook that installs nginx across 50 hosts")
4. Confirm Claude emits the Response Contract and loads the right reference file(s)

## Commit Conventions & Releases

Releases are **fully automated** from conventional commits on `master`:

| Commit prefix | Version bump |
|---------------|-------------|
| `feat!:` / `feat(scope)!:` / `BREAKING CHANGE:` footer | Major |
| `feat:` / `feat(scope):` | Minor |
| `fix:` | Patch |
| Other | Patch (default) |

The release workflow automatically:
- Bumps the version in `CHANGELOG.md`
- Syncs versions across **five places** (must stay in sync):
  1. `.claude-plugin/marketplace.json` → `version` (root)
  2. `.claude-plugin/marketplace.json` → `plugins[0].version`
  3. `skills/ansible-skill/SKILL.md` YAML frontmatter → `metadata.version`
  4. `.claude-plugin/plugin.json` → `version`
  5. `.codex-plugin/plugin.json` → `version`
- Creates a GitHub Release for the new tag using generated notes from commits since the previous tag

**Never manually edit version numbers** — the CI handles this.

## SKILL.md Architecture

### Plugin Structure

The skill lives at `skills/ansible-skill/SKILL.md` — Claude Code autodiscovers any `skills/<name>/SKILL.md`. Reference files sit next to it under `skills/ansible-skill/references/` so relative links keep working.

### YAML Frontmatter (required fields)

```yaml
---
name: ansible-skill             # letters, numbers, hyphens only
description: Use when...         # < 1024 chars, starts with "Use when"
license: Apache-2.0
metadata:
  author: sadicabubakari
  version: X.Y.Z                 # Auto-synced by CI
---
```

### Progressive Disclosure Pattern

SKILL.md is the entry point. Reference files load on demand. Cross-links inside the skill use paths relative to the skill directory, such as `references/testing-frameworks.md`.

When adding content, ask: **decision framework or key pattern → SKILL.md; detailed example or template → reference file.**

### Content Standards

- **Imperative voice:** "Use X" not "You should consider X"
- **Scannable format:** tables > bullets > prose
- **✅ DO / ❌ DON'T** side-by-side for non-obvious patterns
- **Version-specific features** clearly marked (e.g., `ansible-core 2.17+`)
- **Token budget:** SKILL.md target <300 lines

### LLM Consumption Rules (enforce in every PR review)

These rules tune content for the **primary reader: an LLM retrieving facts to answer a user query**, not a human reading the guide end-to-end. They are **mandatory** for every addition to `SKILL.md` and `references/*.md`. Reviewers must reject PRs that violate them.

**1. Shape — decision table before playbook.** The LLM retrieval path is: classify intent → pick branch → execute. When a topic has multiple viable approaches, open the section with a decision table (`Goal | Use | Tradeoff`) before any phase steps or default procedure.

**2. Cut human scaffolding.** Before/after config diffs, "Why this matters" paragraphs, and pedagogical asides are human-only signal. If the phase steps already name the required action, a before/after diff is redundant and must be dropped.

**3. Compress prose → ❌/✅ Rules.** Any sentence starting with "You should...", "Note that...", "Keep in mind..." — rewrite as terse imperative ❌/✅ bullet. One fact per bullet. Direct verbs only: `Keep`, `Remove`, `Run`, `Confirm`, `Use`, `Avoid`, `Scope`.

**4. Every artifact earns its tokens.** Every code block, table, and example must add a fact not present in the prose. If it only restates, cut it.

**5. Anchor stability.** SKILL.md routes to specific `#anchor` headings in reference files. Rewrites may restructure subsections, but must preserve the top-level `### Heading` that the SKILL.md diagnose table points to.

**6. Retrieval-first ordering.** Within a section, order content by what the LLM needs first: (a) decision table, (b) default procedure, (c) alternatives, (d) rules/gotchas as ❌/✅.

**Token target per reference subsection:** under 400 tokens (~1,600 chars). If larger, split or compress.

**Pre-merge checklist for any content PR:**

- [ ] Decision table precedes playbook (if multiple approaches exist)
- [ ] No before/after diff that merely restates the phase steps
- [ ] No paragraph starting with "Why this matters" / "Note" / "Keep in mind"
- [ ] Every code block / table adds a fact not in surrounding prose
- [ ] Subsection under 400 tokens
- [ ] Anchors referenced from SKILL.md remain stable

## What Belongs Where

| Content type | Location |
|-------------|----------|
| Decision frameworks, core patterns | `SKILL.md` |
| Detailed guides, templates, examples | `references/*.md` |
| Installation/usage docs | `README.md` |
| Contributor process details | `CONTRIBUTING.md` |
