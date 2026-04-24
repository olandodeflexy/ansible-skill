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
