# ansible-skill

Diagnose-first Ansible guidance for Claude Code. Encodes ansible-core idempotency patterns, blast-radius controls, inventory/variable precedence rules, Vault handling, Molecule/ansible-test workflows, collection supply-chain hygiene, and execution-environment usage as a version-controlled skill.

## What it does

Every Ansible response from Claude emits a two-axis Response Contract:

1. **Assumptions & version floor** — ansible-core version, collections, Python interpreter, connection plugin
2. **Idempotency evidence** — why each task reports `changed=True` only when the world changed
3. **Blast-radius controls** — `serial`, `max_fail_percentage`, `any_errors_fatal`, `--check --diff`
4. **Risk category** — which of the 9 failure modes is being addressed
5. **Chosen remediation & tradeoffs**
6. **Validation plan** — exact `ansible-lint`, `--syntax-check`, `--check --diff`, Molecule, ansible-test commands
7. **Rollback notes** — how to undo any destructive play

## Install

### Codex

```bash
codex plugin marketplace add olandodeflexy/ansible-skill
```

For local development from a checkout:

```bash
mkdir -p ~/.codex/skills
ln -s "$(pwd)/skills/ansible-skill" ~/.codex/skills/ansible-skill
```

### Claude Code

```bash
claude plugin marketplace add olandodeflexy/ansible-skill
claude plugin install ansible-skill@olandodeflexy
```

From inside an active Claude Code session:

```text
/plugin install github:olandodeflexy/ansible-skill
```

## Use

### Codex

Use the skill name in the prompt when you want Ansible-specific review, generation, or debugging:

```text
Use $ansible-skill to review this playbook for idempotency, blast radius, validation, and rollback.
Use $ansible-skill to write a Molecule-tested role for nginx with safe production rollout controls.
```

### Claude Code

Reference the installed skill directly in Claude Code, or ask an Ansible question after installing it:

```text
Use $ansible-skill to debug why this task reports changed=True on every run.
Use $ansible-skill to design a CI pipeline with ansible-lint, Molecule, --check --diff, and a gated apply.
```

You can also ask:

- "Write an idempotent playbook that installs nginx on a group of hosts"
- "Review this playbook for blast-radius safety"
- "Why is this task reporting `changed=True` every run?"
- "Set up Molecule testing for this role"
- "Pin our collections for production"

The agent loads only the reference files relevant to your query.

## Covered failure categories

| Category | Topic |
| --- | --- |
| Idempotency drift | `changed=True` loops, `command`/`shell` without guards, handler misfires |
| Blast radius | `serial`, `max_fail_percentage`, `--limit` safety, fact-gathering scope |
| Secret exposure | Vault, `no_log`, external secret backends, log leakage |
| Variable precedence bugs | 22-level chain collisions |
| Inventory correctness | Static/dynamic drift, group membership |
| Handler/ordering | `meta: flush_handlers`, `listen` topics |
| Check-mode blind spots | `--check` compatibility, `ignore_errors` pitfalls |
| Collection supply chain | Galaxy pinning, Automation Hub signing |
| Execution environment / runtime | EE images, `ansible-navigator`, connection, become, performance |

## License

Apache-2.0. Copyright © 2026 sadicabubakari.
