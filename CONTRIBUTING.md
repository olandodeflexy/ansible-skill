# Contributing

## Before you start

Read [CLAUDE.md](CLAUDE.md). It covers repo structure, LLM consumption rules (mandatory for content PRs), and commit conventions. Every content PR is reviewed against those rules.

## Workflow

1. Fork, branch from `master`
2. Edit `SKILL.md` or `references/*.md` following the LLM consumption rules
3. Reload the skill in Claude Code and run real Ansible queries to confirm behavior
4. Run the local validation commands in CLAUDE.md (line count, frontmatter, broken links)
5. Open a PR — CI runs the same checks plus markdown lint
6. Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`. Release cut is automatic.

## What NOT to do

- Don't hand-edit version numbers — CI owns them.
- Don't add before/after config diffs that restate phase steps.
- Don't write "Why this matters" paragraphs — compress to ❌/✅.
- Don't ship a reference subsection over ~400 tokens.
- Don't break anchors referenced from `SKILL.md`.

## Questions

Open an issue. Small edits welcome; larger structural changes, open a discussion first.
