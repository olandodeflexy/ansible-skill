# Testing Frameworks

Detail for the `Testing Strategy` section in SKILL.md.

## Decision Matrix

| Goal | Tool | Cost | Speed | Scope |
|------|------|------|-------|-------|
| Is the YAML valid? | `ansible-playbook --syntax-check site.yml` | Free | <1 s | Playbook/role syntax only |
| Does the code smell right? | `ansible-lint` | Free | 1–5 s | Static rules (fqcn, no-changed-when, risky-shell-pipe, yaml formatting) |
| Does a role converge on a fresh host? | Molecule + docker/podman | Free | 30–120 s | Role integration against a container |
| Does a collection's module/plugin work? | `ansible-test units` | Free | 5–30 s | Unit tests for modules + plugins (collection-only) |
| Does a collection import cleanly? | `ansible-test sanity` | Free | 10–60 s | Import, schema, ignores, pylint/pep8 style |
| Does a collection module behave against real infra? | `ansible-test integration` | Med | Minutes | Full module runs against real services |
| Does the whole stack converge end-to-end? | `--check --diff` against staging inventory | High | Minutes | Real plan/diff without applying |

Rules:

- ❌ Skip `ansible-lint` "because tests pass" → lint catches fqcn misses, `changed_when` omissions, Jinja2 mistakes tests don't exercise.
- ❌ Use Molecule to test a collection's modules → ✅ Molecule tests roles; `ansible-test units/integration` tests collection internals.
- ❌ Rely on `--syntax-check` as "testing" → it only parses YAML and validates task module names; no behavior is executed.

## ansible-lint

| Rule category | Key rules | Fires on |
|---------------|-----------|----------|
| Structure | `fqcn`, `name[play]`, `name[casing]` | Any task using a short module name (`copy:` instead of `ansible.builtin.copy:`); missing play/task names |
| Safety — `command`/`shell` | `no-changed-when`, `command-instead-of-shell`, `command-instead-of-module` | `command:` / `shell:` task without `changed_when:`; `shell:` used where `command:` would suffice; shelling out where a native module exists |
| Safety — shell pipes only | `risky-shell-pipe` | **`shell:` tasks containing `\|` without `pipefail` set** — does NOT fire on `template:`, `copy:`, `uri:`, or any non-shell module |
| Safety — module misuse | `no-free-form` | `module: foo=bar baz=qux` style instead of structured args |
| Variables | `var-naming`, `jinja` | Role vars missing role-name prefix, malformed Jinja2 expressions |
| YAML | `yaml[*]` | Indent, trailing spaces, document-start |
| Secrets | `no-log-password`, `risky-file-permissions` | Module arg whose name matches a secret-like pattern (`*pass*`, `*token*`, `*key*`, `*secret*`) without `no_log: true`; `mode:` set to `0777` or other world-writable values |

**Common LLM misattributions to avoid:**

- `risky-shell-pipe` only fires on `ansible.builtin.shell:` tasks. It does **not** apply to `template:`, `copy:`, `uri:`, or any module that doesn't shell out. Cite it only when discussing actual shell-pipe constructs.
- `no-log-password` matches by argument name, not module type. It catches `community.postgresql.postgresql_user: password=...` and `ansible.builtin.uri: body: { api_key: ... }` (the `api_key` field), but not arbitrary unnamed secret values.
- `command-instead-of-shell` and `command-instead-of-module` are different rules — the first warns when `shell:` is used without shell features; the second warns when a native module would do the job.

Minimal `.ansible-lint`:

```yaml
# .ansible-lint (project root)
profile: production
exclude_paths:
  - .cache/
  - collections/
skip_list:
  - yaml[line-length]        # too noisy; markdownlint handles docs
warn_list:
  - experimental             # don't fail on rules still in dev
```

```yaml
# Idempotent one-shot: `creates:` skips the task once the marker exists.
# Do NOT add `changed_when: false` here — the first run genuinely changes
# state (creates the marker + performs the restart), and suppressing that
# hides handler notifications and audit evidence.
- name: Restart worker once, then skip on subsequent runs
  ansible.builtin.command: /usr/local/bin/worker-restart.sh
  args:
    creates: /var/run/worker.restarted
```

```yaml
# Informational status probe (never mutates state).
# Here `changed_when: false` is correct because the task is read-only.
- name: Probe worker status
  ansible.builtin.command: systemctl is-active worker
  register: worker_status
  changed_when: false
  failed_when: false
```

Rules:

- ❌ Add rules to `skip_list` without a comment explaining why → ✅ Document each skip; `yaml[line-length]` is the one common exception, everything else needs justification.
- ❌ Blanket-ignore with `# noqa` on every task → ✅ `# noqa rule-id` targeted at the specific rule and task only.
- ❌ Run ansible-lint only in CI → ✅ Local pre-commit hook; CI repeats as safety net.
- ❌ Use `profile: basic` in production → ✅ `profile: production` catches security and idempotency rules `basic` skips.

## Molecule

| Driver | Use | Tradeoff |
|--------|-----|----------|
| `docker` | Most roles; fast | Requires Docker daemon on controller; not a systemd-friendly target without privileged |
| `podman` | Rootless equivalent of docker | Slightly less ecosystem coverage; systemd works with `--systemd` |
| `delegated` | Test against an already-running target (VM, bare metal) | No lifecycle management; useful for manual CI integration |
| `vagrant` | Full-VM integration | Slow; use only when the role requires a real kernel (kernel modules, etc.) |

```yaml
# molecule/default/molecule.yml
# `pre_build_image: true` tells Molecule the image is already Ansible-ready
# (Python + sudo present). Vanilla `rockylinux:9` and `ubuntu:22.04` are NOT —
# the first task fails on fact-gathering. Pick an Ansible-ready image (e.g.
# geerlingguy/docker-*-ansible) or build your own and pin it by digest.
dependency:
  name: galaxy
driver:
  name: docker
platforms:
  - name: rocky9
    image: geerlingguy/docker-rockylinux9-ansible:latest
    pre_build_image: true
    command: ""           # use the image's default; many ansible-ready images need no override
    privileged: true       # required if the role manages systemd units
  - name: ubuntu2204
    image: geerlingguy/docker-ubuntu2204-ansible:latest
    pre_build_image: true
    command: ""
    privileged: true
provisioner:
  name: ansible
  config_options:
    defaults:
      callbacks_enabled: profile_tasks    # plural; `callback_whitelist` is the deprecated older name
verifier:
  name: ansible
```

```yaml
# molecule/default/converge.yml
- name: Converge
  hosts: all
  roles:
    - role: nginx_site
```

```yaml
# molecule/default/verify.yml
- name: Verify
  hosts: all
  tasks:
    - name: Confirm nginx is listening
      ansible.builtin.wait_for:
        port: 80
        timeout: 5
```

Rules:

- ❌ Skip the idempotence test (`molecule test` runs converge twice by default) → ✅ Keep it; a role that isn't idempotent fails the second converge.
- ❌ Use `driver: docker` without `pre_build_image: true` for every run → layer rebuild is costly; pre-built images cache the base.
- ❌ Verify with a shell task instead of a module → `verifier:` should assert module results, not arbitrary shell.
- ❌ Pile all matrix platforms into one scenario → split into scenarios (`molecule/rhel/`, `molecule/debian/`) when tests diverge.

## ansible-test

| Test type | Command | Validates |
|-----------|---------|-----------|
| `sanity` | `ansible-test sanity --docker` | Import, schema compliance, pep8/pylint, ignore-file correctness |
| `units` | `ansible-test units --docker` | Unit tests for modules (`tests/unit/`) and plugins |
| `integration` | `ansible-test integration --docker <target>` | End-to-end module runs — may require credentials and real services |

Layout inside a collection:

```text
my-collection/
  plugins/
    modules/
      foo.py
  tests/
    unit/
      plugins/
        modules/
          test_foo.py
    integration/
      targets/
        foo/
          tasks/main.yml
          aliases     # names tests that need specific env (e.g. `aws`, `needs/root`)
    sanity/
      ignore-2.17.txt  # ignored rules, per ansible-core version
```

Rules:

- ❌ Confuse Molecule and ansible-test — Molecule is for roles, ansible-test is for collections.
- ❌ Commit large `ignore-*.txt` files without plan to shrink → ✅ Each ignore is technical debt; add an issue per line.
- ❌ Skip `ansible-test sanity` on a collection PR → it's cheap and catches schema regressions.
- ❌ Run integration tests that hit real cloud APIs on every PR → gate behind labels or scheduled jobs; expensive.

## Argument Specs

`meta/argument_specs.yml` validates role inputs at invocation time. Use `profile: production` in ansible-lint to enforce.

```yaml
# roles/nginx_site/meta/argument_specs.yml
---
argument_specs:
  main:
    short_description: Configure an nginx vhost
    options:
      nginx_site_server_name:
        type: str
        required: true
      nginx_site_port:
        type: int
        default: 80
      nginx_site_ssl:
        type: bool
        default: false
      nginx_site_upstreams:
        type: list
        elements: dict
        options:
          host:
            type: str
            required: true
          port:
            type: int
            required: true
        required: false
```

Rules:

- ❌ Declare `type: raw` on everything → defeats the point; use concrete types (`str`, `int`, `list`, `dict`, `bool`).
- ❌ Omit `required: true` on vars the role will fail on if missing → ✅ Mark required inputs so failure happens at invocation, not deep in a handler.
- ❌ Use free-form role vars with no spec → ✅ Every reusable role gets `argument_specs.yml`; it's the role's type signature.
- ❌ Document choices via role README instead of `choices:` → ✅ `choices: [http, https]` validates + documents simultaneously.
- ❌ Skip entry-point specs for `tasks/setup.yml`-style multi-entry roles → each entry point (`main`, `setup`, `teardown`) gets its own spec block.

### LLM Mistake Checklist

- ❌ Propose Molecule to test a collection → ✅ Molecule tests roles; `ansible-test` tests collections.
- ❌ Skip `ansible-lint` in favor of `--syntax-check` → ✅ Syntax-check validates grammar; lint catches actual anti-patterns.
- ❌ Add `# noqa` without a rule id → ✅ Always scope: `# noqa command-instead-of-shell`.
- ❌ Verify Molecule scenarios with shell commands → ✅ Use module-based assertions in `verify.yml`.
- ❌ Ship a role without `argument_specs.yml` → ✅ Every reusable role needs one; it's the role's input contract.
- ❌ Run integration tests unconditionally on every collection PR → ✅ Gate behind labels or scheduled jobs.
- ❌ Leave `ignore-*.txt` entries in a collection without follow-up issues → each is technical debt.
