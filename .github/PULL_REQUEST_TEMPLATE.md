## Summary

<!-- One paragraph describing what this PR changes and why. -->

## Conventional commit

<!-- Confirm the PR title/commit uses one of: feat:, fix:, chore:, docs:, refactor:, feat!:, BREAKING CHANGE: -->

## Content PR checklist (LLM consumption rules)

- [ ] Decision table precedes playbook (if multiple approaches exist)
- [ ] No before/after diffs that merely restate phase steps
- [ ] No "Why this matters" / "Note" / "Keep in mind" paragraphs — all converted to ❌/✅
- [ ] Every code block / table adds a fact not in surrounding prose
- [ ] Subsection under 400 tokens (~1,600 chars)
- [ ] Anchors referenced from `SKILL.md` remain stable
- [ ] `SKILL.md` under 300 lines (or justified if exceeded)

## Validation

- [ ] Local frontmatter check passes
- [ ] Local line-count check passes
- [ ] Local broken-link check passes
- [ ] Reloaded skill in Claude Code and confirmed at least one query routes correctly

## Notes for reviewer

<!-- Anything the reviewer needs to know. -->
