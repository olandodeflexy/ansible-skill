---
name: ansible-skill
description: "Use when writing, reviewing, or debugging Ansible playbooks, roles,\
  \ collections, inventory, Vault, Molecule, execution environments, or CI \u2014\
  \ diagnoses failure mode (idempotency drift, blast radius, secret exposure, variable\
  \ precedence, inventory correctness, handler ordering, check-mode blind spots, collection\
  \ supply chain, execution environment) with two-axis risk framing."
license: Apache-2.0
metadata:
  author: sadicabubakari
  version: 0.0.2
---

# Ansible Skill for Claude

Diagnose-first guidance for Ansible and ansible-core. Core file is a workflow; depth lives in reference files loaded on demand.

## Response Contract

Every Ansible response must include:

1. **Assumptions & version floor** — `ansible-core` version, collections in `requirements.yml` with versions, Python interpreter target (`ansible_python_interpreter`), connection plugin (ssh/winrm/local), control node vs execution-environment runtime. State explicitly when the user did not provide them.
2. **Idempotency evidence** — for each task introduced or modified: why `changed=True` only when the world actually changed. Name the module's idempotency contract (native module idempotent; `command`/`shell` requires `creates`/`removes`/`changed_when`).
3. **Blast-radius controls** — inventory target (hosts/groups/limit), `serial` / `max_fail_percentage` / `any_errors_fatal` decision, `--check` + `--diff` coverage, whether this is safe to run against prod as-is.
4. **Risk category addressed** — one or more of the 9 diagnose-table categories below.
5. **Chosen remediation & tradeoffs** — what was chosen, what was traded off, why.
6. **Validation plan** — exact commands tailored to runtime and risk tier: `ansible-lint`, `ansible-playbook --syntax-check`, `--check --diff`, Molecule scenario, `ansible-test sanity/units/integration`.
7. **Rollback notes** — for any destructive or state-mutating play: how to undo (inverse play, restore from backup, `state: absent`), what evidence to keep (registered var output, command logs, diff artifacts).

Never recommend running a play against production without `--check --diff` first **and** an explicit `--limit` or a reviewed inventory pattern.

## Workflow

1. **Capture execution context** — `ansible-core` version, collections, Python interpreter, connection plugin, execution path (local/CI/EE/AWX-free), environment criticality.
2. **Diagnose failure mode(s)** using the routing table below. If intent spans categories, load all matching references.
3. **Load only the matching reference file(s)** — do not preload depth the task does not need.
4. **Propose fix with risk controls** — why this addresses the mode, what could still go wrong, guardrails (lint rules / Molecule / `--check --diff` / approval gates / rollback).
5. **Generate artifacts** — playbook YAML, role skeleton, `requirements.yml`, Molecule scenario, CI workflow, Vault usage.
6. **Validate before finalizing** — run validation commands tailored to risk tier.
7. **Emit the Response Contract** at the end.

## Diagnose Before You Generate

| Failure category | Symptoms | Primary references |
|------------------|----------|--------------------|
| **Idempotency drift** | Tasks report `changed=True` every run, `command`/`shell` without `creates`/`changed_when`, non-native modules, handlers firing spuriously | [Idempotency Patterns](references/idempotency-patterns.md) |
| **Blast radius** | Missing `serial`, no `max_fail_percentage`, `any_errors_fatal` misused, no `--limit` in CI, fact-gathering against whole fleet | [Execution & Runtime](references/execution-and-runtime.md), [CI/CD Workflows](references/ci-cd-workflows.md) |
| **Secret exposure** | Plaintext in vars, `no_log` missing, Vault key handling, secrets in stdout/stderr, `ansible-vault` vs external secret managers | [Security & Vault](references/security-and-vault.md) |
| **Variable precedence bugs** | 22-level chain surprises, `set_fact` vs `vars` vs `vars_files`, group_vars / host_vars collisions, extra-vars overrides | [Inventory & Variables](references/inventory-and-variables.md) |
| **Inventory correctness** | Static/dynamic drift, group membership bugs, `ansible_host` vs `inventory_hostname`, missing `--limit` safety | [Inventory & Variables](references/inventory-and-variables.md) |
| **Handler/ordering issues** | Handlers not firing on failure, `meta: flush_handlers`, `listen` topics, notify ordering | [Idempotency Patterns](references/idempotency-patterns.md) |
| **Check-mode blind spots** | Tasks break under `--check`, `ignore_errors` / `failed_when` hiding real failures, modules that don't support check mode | [Idempotency Patterns](references/idempotency-patterns.md) |
| **Collection/role supply chain** | Galaxy pinning, `requirements.yml` hygiene, version drift, private Automation Hub, signature verification | [Collections & Supply Chain](references/collections-and-supply-chain.md) |
| **Execution environment / runtime** | EE image pinning, `ansible-navigator` vs `ansible-playbook`, Python interpreter discovery, connection plugin, become escalation, forks/pipelining/fact caching | [Execution & Runtime](references/execution-and-runtime.md) |

## When to Use This Skill

**Activate when:** creating or reviewing Ansible playbooks, roles, or collections; setting up or debugging Molecule / ansible-test; structuring multi-environment inventory; implementing Ansible CI/CD; choosing role patterns or collection organization; configuring Vault or external secret backends; building or pinning execution environments.

**Don't use for:** basic YAML syntax Claude already knows; module API reference (point users at the `ansible-doc` CLI or `docs.ansible.com`); AAP / AWX / Tower platform-specific questions (job templates, surveys, RBAC, workflows); cloud-provider SDK questions unrelated to Ansible modules.

## Core Principles

### Unit Hierarchy

| Unit | When to Use | Scope |
|------|-------------|-------|
| **Task** | One action | Install a package, write a file |
| **Role** | Reusable bundle of related tasks | Web server config, database setup |
| **Playbook** | Orchestrates roles across hosts | Full stack deploy, one environment |
| **Collection** | Distributable unit of roles, modules, plugins | Shared across teams, versioned, on Galaxy or Automation Hub |

Flow: task → role → playbook → collection.

### Directory Layout

```text
inventories/
  prod/      hosts, group_vars/, host_vars/
  staging/   hosts, group_vars/, host_vars/
  dev/
roles/       # local reusable roles
collections/ # requirements.yml, installed collections
playbooks/   # deploy.yml, site.yml, one-off ops plays
molecule/    # per-role scenarios
```

Separate **inventories** from **roles**. Keep roles single-responsibility. Keep all `group_vars/` and `host_vars/` **inside each `inventories/<env>/` directory** — never at repo root. Repo-root `group_vars/`/`host_vars/` apply to every environment's plays and leak prod values into dev runs.

### Naming Conventions

- Role names: short, hyphenated, purpose-based (`nginx-site`, not `my_role`)
- Variable names: prefix with role scope to avoid global collisions (`nginx_site_port`, not `port`)
- Task names: imperative sentence — appears in logs (`"Install nginx"`, not `"nginx"`)
- Tags: purpose-based, not task-name-based (`tags: [config, tls]` vs `tags: [install_nginx]`)

### Task Ordering (within a task block)

`name` → `module` → module args → `register` → `when` → `loop` → `notify` → `tags`

```yaml
- name: Install nginx
  ansible.builtin.package:
    name: nginx
    state: present
  register: nginx_install
  when: ansible_os_family == 'Debian'
  notify: restart nginx
  tags: [install]
```

## Idempotency — Quick Rule

| Situation | Use | Why |
|-----------|-----|-----|
| Native module available | `ansible.builtin.<module>` / fqcn module | Idempotent by contract |
| Must shell out, stateful output file | `ansible.builtin.command` with `creates:` / `removes:` | `changed=True` only if file missing |
| Must shell out, no clear file marker | `ansible.builtin.command` with `changed_when:` based on stdout/rc | Explicit change detection |
| Must shell out, needs shell features (pipes, redirects) | `ansible.builtin.shell` + `changed_when` | Last resort — harder to make safe |

**Never:** run `ansible.builtin.shell` without `changed_when` unless the task is genuinely informational and you also set `changed_when: false`.

See [Idempotency Patterns](references/idempotency-patterns.md) for module idempotency contracts, handler patterns, and check-mode coverage.

## Blast Radius — Quick Rule

| Target fleet size | Pattern | Play config |
|-------------------|---------|-------------|
| 1–5 hosts | Serial small batches | `serial: 1` or `serial: [1, 2]` |
| 10–50 hosts, canary first | Canary + rolling | `serial: [1, "25%"]` with `max_fail_percentage: 10` |
| 50+ hosts | Rolling with fail cap | `serial: "10%"`, `max_fail_percentage: 5` |
| Critical state-change on many hosts | Fail fast | `any_errors_fatal: true` |
| Independent tasks, no cascade | Free strategy | `strategy: free` (hosts run independently) |

**Never** run against production without an explicit `--limit` or a reviewed inventory pattern. **Never** set `any_errors_fatal: true` on rolling deploys where partial completion is worse than full failure.

See [Execution & Runtime](references/execution-and-runtime.md) for serial/max-fail combinations and [CI/CD Workflows](references/ci-cd-workflows.md) for CI-level blast-radius gates.

## Variable Precedence — Quick Rule

Abbreviated precedence (lowest → highest):

1. Role defaults (`roles/<role>/defaults/main.yml`)
2. Inventory `group_vars/all`
3. Inventory `group_vars/<group>`
4. Inventory `host_vars/<host>`
5. Play vars
6. Block vars
7. Task vars
8. `set_fact`
9. `--extra-vars` (always wins)

**Most common bugs:**

- `set_fact` values persist across plays in the same run — unexpected when debugging
- `group_vars/all` silently overridden by `host_vars/<host>` — confusing when the same host appears in multiple groups
- `--extra-vars` with `@file.yml` beats everything — a stray flag in CI can override protected config

See [Inventory & Variables](references/inventory-and-variables.md) for the full 22-level ladder and collision examples.

## Testing Strategy

### Decision Matrix

| Situation | Approach | Tools | Cost |
|-----------|----------|-------|------|
| Syntax check | Static | `ansible-playbook --syntax-check`, `ansible-lint` | Free |
| Role unit test | Scenario-based | Molecule + docker/podman driver | Free–Low |
| Collection unit test | Module/plugin tests | `ansible-test units` | Free |
| Collection sanity | Import + schema | `ansible-test sanity` | Free |
| Integration — role | Molecule against real target | Molecule + delegated/vagrant driver | Med |
| Integration — collection | Live-run modules | `ansible-test integration` | Med |
| End-to-end, multi-host | Staged apply | `--check --diff` against staging | High |

**Rules:**

- Never skip `ansible-lint` — it catches fqcn, `no_log`, `changed_when` misuse at PR time.
- Use `--check --diff` as the last gate before any production play.
- Molecule for roles; `ansible-test` for collections. They're not interchangeable.

See [Testing Frameworks](references/testing-frameworks.md) for Molecule scenario structure, ansible-test usage, and argument-specs for role input validation.

## CI/CD

Pipeline stages: **lint → syntax-check → Molecule (or ansible-test) → staged `--check --diff` → gated apply**.

**Rules:**

- Pin `ansible-core` to a currently supported minor in CI (e.g. `ansible-core>=2.18,<2.19`); cross-check the [Version Matrix](references/quick-reference.md#version-matrix) before each release cycle and bump off any minor that is past EOL.
- Pin collections in `requirements.yml` with exact versions for prod branches.
- Inject vault password via OIDC or masked secret — never a file in the repo.
- Treat the reviewed `--check --diff` output as an approval artifact, not a replayable plan. The apply job must re-evaluate current state — optionally re-run `--check --diff` against live infrastructure and compare to the approved artifact before executing.

See [CI/CD Workflows](references/ci-cd-workflows.md) for GitHub Actions + GitLab CI templates and blast-radius approval gates.

## Security & Vault

**Don't:**

- Store secrets in plaintext vars or unencrypted `vars_files`
- Omit `no_log: true` on tasks that pass secrets as module args
- Commit vault password files — use OIDC, system keyring, or external key providers
- Use `--verbose` in CI on tasks handling secrets (output leaks to logs)

**Do:**

- Use `ansible-vault encrypt_string` for inline single-value secrets
- Use Vault-id strategy to support per-environment keys
- Prefer external secret backends (HashiCorp Vault, AWS Secrets Manager, 1Password) via lookup plugins over static vault files
- Set `no_log: true` on any task whose module args include secrets — and remember `register` + `loop` still leak unless you also strip in the loop item

See [Security & Vault](references/security-and-vault.md) for vault-id patterns, external-backend lookups, and secrets-in-logs hardening.

## Collections & Supply Chain

| Pin strategy | Prod | Dev |
|--------------|------|-----|
| `requirements.yml` collection version | Exact (`version: "5.1.2"`) | Range (`version: ">=5.1.0,<6.0.0"`) |
| Galaxy vs Automation Hub | Automation Hub for certified | Galaxy OK for experimental |
| Signature verification | Required | Optional for dev |

**Rules:**

- Use fully-qualified collection names (`ansible.builtin.copy`, not `copy`) — ansible-lint `fqcn` rule enforces.
- Pin all collections in `requirements.yml`; do not rely on the ansible community package version for prod.
- Mirror critical collections internally (private Automation Hub or git) for supply-chain control.

See [Collections & Supply Chain](references/collections-and-supply-chain.md) for `requirements.yml` syntax, signature verification, and private-hub auth.

## Execution Environments

| Situation | Use | Why |
|-----------|-----|-----|
| Local dev, fast iteration | Bare `ansible-playbook` + venv | No image build overhead |
| CI reproducibility | EE image with `ansible-navigator` | Pinned ansible-core + collections + deps |
| Production run | EE image, pulled by digest | Deterministic runs, rollback by image tag |

**Rules:**

- Pin EE images by digest (`@sha256:...`), not tag, for production.
- Build EEs with `ansible-builder` from an `execution-environment.yml`.
- `ansible-navigator run` is the preferred invocation — it handles EE lifecycle + streams output cleanly.

See [Execution & Runtime](references/execution-and-runtime.md) for EE build patterns, interpreter discovery, connection/become gotchas, and forks/pipelining/fact-caching.

## Version Management

| Component | Strategy | Example |
|-----------|----------|---------|
| `ansible-core` runtime | Pin minor for prod | `ansible-core>=2.17,<2.18` |
| Community `ansible` package | Pin exact or avoid in prod | Prefer pinning `ansible-core` + collections separately |
| Collections (prod) | Exact version in `requirements.yml` | `version: "5.1.2"` |
| Collections (dev) | Allow minor | `version: ">=5.1.0,<6.0.0"` |
| Python interpreter | Explicit `ansible_python_interpreter` | `/usr/bin/python3` (avoid auto-discovery in prod) |

Keep `ansible-core` + collection upgrades in a separate PR from functional changes. The community `ansible` package is a starter bundle; production teams pin collections individually.

## Modern Ansible Features (2.11+)

| Feature | Min `ansible-core` | Common use |
|---------|---------------------|------------|
| `argument_specs` in `meta/` | 2.11+ | Role input validation |
| `ansible.builtin.import_role` with `vars_from` | 2.14+ | Load alt var files per import |
| `validate` parameter on `template`/`copy` | 2.15+ | Run shell validator before applying |
| Role handler `listen` topic inheritance | 2.16+ | Cross-role handler topics |
| Structured `changed_when` with dict returns | 2.17+ | Clean branching on module result |
| `ansible-navigator` stable workflow | n/a (packaging) | Default for EE-based runs |

Verify the runtime floor before emitting a feature. Version-specific behavior (esp. `validate` and handler inheritance) is a frequent LLM mistake.

## Reference Files

Progressive disclosure — essentials here, depth on demand.

- [Idempotency Patterns](references/idempotency-patterns.md) — module contracts, `command`/`shell` guards, handlers, check-mode
- [Inventory & Variables](references/inventory-and-variables.md) — full 22-level precedence, dynamic inventory, `set_fact` vs vars
- [Security & Vault](references/security-and-vault.md) — vault-id, external secret backends, `no_log`, log hardening
- [Execution & Runtime](references/execution-and-runtime.md) — serial/max-fail, execution environments, interpreter, connection/become, performance
- [Testing Frameworks](references/testing-frameworks.md) — ansible-lint, Molecule, ansible-test, argument_specs
- [CI/CD Workflows](references/ci-cd-workflows.md) — GitHub Actions, GitLab CI, blast-radius gates, secret handling in CI
- [Collections & Supply Chain](references/collections-and-supply-chain.md) — `requirements.yml`, fqcn, signature verification, private hubs
- [Quick Reference](references/quick-reference.md) — command cheatsheet, troubleshooting flowchart, module recipes, version matrix

## License

Apache-2.0. See LICENSE.

Copyright © 2026 sadicabubakari.
