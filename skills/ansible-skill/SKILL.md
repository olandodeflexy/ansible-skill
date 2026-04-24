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
| **Idempotency drift** | Tasks report `changed=True` every run, `command`/`shell` without `creates`/`changed_when`, non-native modules, handlers firing spuriously | `references/idempotency-patterns.md` |
| **Blast radius** | Missing `serial`, no `max_fail_percentage`, `any_errors_fatal` misused, no `--limit` in CI, fact-gathering against whole fleet | `references/execution-and-runtime.md`, `references/ci-cd-workflows.md` |
| **Secret exposure** | Plaintext in vars, `no_log` missing, Vault key handling, secrets in stdout/stderr, `ansible-vault` vs external secret managers | `references/security-and-vault.md` |
| **Variable precedence bugs** | 23-level chain surprises, `set_fact` vs `vars` vs `vars_files`, group_vars / host_vars collisions, extra-vars overrides | `references/inventory-and-variables.md` |
| **Inventory correctness** | Static/dynamic drift, group membership bugs, `ansible_host` vs `inventory_hostname`, missing `--limit` safety | `references/inventory-and-variables.md` |
| **Handler/ordering issues** | Handlers not firing on failure, `meta: flush_handlers`, `listen` topics, notify ordering | `references/idempotency-patterns.md` |
| **Check-mode blind spots** | Tasks break under `--check`, `ignore_errors` / `failed_when` hiding real failures, modules that don't support check mode | `references/idempotency-patterns.md` |
| **Collection/role supply chain** | Galaxy pinning, `requirements.yml` hygiene, version drift, private Automation Hub, signature verification | `references/collections-and-supply-chain.md` |
| **Execution environment / runtime** | EE image pinning, `ansible-navigator` vs `ansible-playbook`, Python interpreter discovery, connection plugin, become escalation, forks/pipelining/fact caching | `references/execution-and-runtime.md` |

## When to Use This Skill

**Activate when:** creating or reviewing Ansible playbooks, roles, or collections; setting up or debugging Molecule / ansible-test; structuring multi-environment inventory; implementing Ansible CI/CD; choosing role patterns or collection organization; configuring Vault or external secret backends; building or pinning execution environments.

**Don't use for:** basic YAML syntax Claude already knows; module API reference (point users at ansible-docs); AAP / AWX / Tower platform-specific questions (job templates, surveys, RBAC, workflows); cloud-provider SDK questions unrelated to Ansible modules.

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

```
inventories/
  prod/      hosts, group_vars/, host_vars/
  staging/   hosts, group_vars/, host_vars/
  dev/
roles/       # local reusable roles
collections/ # requirements.yml, installed collections
playbooks/   # deploy.yml, site.yml, one-off ops plays
molecule/    # per-role scenarios
group_vars/  # cross-inventory group vars (if shared)
host_vars/   # cross-inventory host vars (if shared)
```

Separate **inventories** from **roles**. Keep roles single-responsibility. Prefer per-inventory `group_vars`/`host_vars` over top-level to avoid leak between environments.

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

See `references/idempotency-patterns.md` for module idempotency contracts, handler patterns, and check-mode coverage.

## Blast Radius — Quick Rule

| Target fleet size | Pattern | Play config |
|-------------------|---------|-------------|
| 1–5 hosts | Serial small batches | `serial: 1` or `serial: [1, 2]` |
| 10–50 hosts, canary first | Canary + rolling | `serial: [1, "25%"]` with `max_fail_percentage: 10` |
| 50+ hosts | Rolling with fail cap | `serial: "10%"`, `max_fail_percentage: 5` |
| Critical state-change on many hosts | Fail fast | `any_errors_fatal: true` |
| Independent tasks, no cascade | Free strategy | `strategy: free` (hosts run independently) |

**Never** run against production without an explicit `--limit` or a reviewed inventory pattern. **Never** set `any_errors_fatal: true` on rolling deploys where partial completion is worse than full failure.

See `references/execution-and-runtime.md` for serial/max-fail combinations and `references/ci-cd-workflows.md` for CI-level blast-radius gates.

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

See `references/inventory-and-variables.md` for the full 23-level ladder and collision examples.

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

See `references/testing-frameworks.md` for Molecule scenario structure, ansible-test usage, and argument-specs for role input validation.

## CI/CD

Pipeline stages: **lint → syntax-check → Molecule (or ansible-test) → staged `--check --diff` → gated apply**.

**Rules:**

- Pin `ansible-core` version in CI (`ansible-core>=2.17,<2.18`).
- Pin collections in `requirements.yml` with exact versions for prod branches.
- Inject vault password via OIDC or masked secret — never a file in the repo.
- Apply the reviewed `--check` diff on approval; do not re-run planning logic inside the apply job.

See `references/ci-cd-workflows.md` for GitHub Actions + GitLab CI templates and blast-radius approval gates.
