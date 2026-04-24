# Execution & Runtime

Detail for the `Blast radius` and `Execution environment / runtime` routing-table categories.

## Serial and max_fail

Pick the row matching the run's tolerance for partial completion.

| Fleet scenario | `serial` | `max_fail_percentage` | `any_errors_fatal` | Notes |
|----------------|----------|------------------------|---------------------|-------|
| 1-host dev | `1` (or omit) | n/a | `false` | Dev/debug; default linear strategy fine |
| Small canary (≤5) | `[1, 2]` | `20` | `false` | 1 host first, then 2; abort if >20% fail |
| Rolling 10% (50–500 hosts) | `"10%"` | `5` | `false` | Standard production rollout |
| Rolling 25% (fast, larger tolerance) | `"25%"` | `10` | `false` | When per-host convergence is cheap and safe |
| Fail-fast critical change | `1` | `0` | `true` | Schema migration, bootstrap — partial is catastrophic |
| Independent tasks across fleet | n/a | n/a | `false` | `strategy: free` — each host races ahead on its own |

```yaml
- hosts: webservers
  serial:
    - 1
    - "25%"
  max_fail_percentage: 10
  any_errors_fatal: false
  tasks:
    - name: Drain, deploy, verify, re-add
      # ...
```

Rules:

- ❌ `serial: "10%"` with `any_errors_fatal: true` → failure in the first batch halts the rollout globally; usually **not** what you want on rolling.
- ❌ `max_fail_percentage` without `serial:` → percentage is evaluated against the *entire* play host group, not a batch.
- ❌ `strategy: free` on a play where later tasks depend on all hosts having completed earlier tasks → ✅ Use `linear` (default) or add explicit barriers.
- ❌ Omit `--limit` in CI on "production" jobs → ✅ Enforce `--limit` via a CI gate (see ci-cd-workflows.md).
- ❌ Gather facts against the full fleet when the play touches 10 hosts → ✅ Set `gather_facts: false` at play level (there is no `--gather_facts` CLI flag), or scope with `hosts:` tightly, and pass `--limit` to narrow further.

## Execution Environments

| Artifact | Tool | Purpose |
|----------|------|---------|
| `execution-environment.yml` | ansible-builder input | Declares base image + collections + Python deps |
| EE container image | `ansible-builder build` output | Runtime image for plays |
| `ansible-navigator.yml` | ansible-navigator config | Declares which EE to use and how to render logs |
| `ansible-navigator run site.yml` | ansible-navigator | Runs a play inside the EE |
| `ansible-runner` | Lower-level runtime | What AAP uses under the hood; typically you don't invoke directly |

Minimal `execution-environment.yml` (builder v3 schema):

```yaml
# execution-environment.yml
version: 3
images:
  base_image:
    name: quay.io/ansible/creator-ee:v24.7.0
dependencies:
  ansible_core:
    package_pip: ansible-core==2.17.5
  galaxy: requirements.yml
  python: requirements.txt
  system: bindep.txt
```

Rules:

- ❌ Pin EE images by tag (`:latest`, `:v24`) → ✅ Pin by digest: `image@sha256:<hash>` — tags are mutable, digests are not.
- ❌ Bake collections directly into `ansible-builder` Dockerfile step → ✅ Put them in `requirements.yml` and reference from the EE definition; keeps versions auditable.
- ❌ Use different EEs in CI vs prod → ✅ Same image, same digest, everywhere.
- ❌ Run `ansible-playbook` directly when you've declared an EE → ✅ `ansible-navigator run` handles the EE lifecycle.
- ❌ Omit `bindep.txt` when a collection needs OS packages → ✅ Add build-time + runtime system deps to `bindep.txt`.

## Python Interpreter Discovery

| Target OS | Recommended `ansible_python_interpreter` | Discovery mode |
|-----------|---------------------------------------------|----------------|
| RHEL 9, Rocky 9, Alma 9 | `/usr/bin/python3` | Explicit (don't rely on auto) |
| RHEL 8, Rocky 8, Alma 8 | `/usr/libexec/platform-python` (Red Hat-managed) or `/usr/bin/python3` | Explicit. `platform-python` was introduced in RHEL 8 |
| Ubuntu 22.04+ | `/usr/bin/python3` | Explicit |
| Debian 12+ | `/usr/bin/python3` | Explicit |
| Amazon Linux 2023 | `/usr/bin/python3` | Explicit |
| Older RHEL 7 / CentOS 7 | Explicit absolute path to an installed Python 3 (e.g. `/usr/bin/python3`, `/opt/rh/rh-python38/root/usr/bin/python` from SCL, or whichever path was `yum install`ed). For very old ansible releases that still support Python 2, `/usr/bin/python` works, but ansible-core 2.12+ requires Python 3 on the target. **Not** `/usr/libexec/platform-python` — that path does not exist on RHEL 7 | Explicit |
| Containers / minimal images | Depends on image | Explicit, always |

Ansible has three auto-discovery modes (set via `INTERPRETER_PYTHON`):

- `auto` — picks per-distro default, warns on legacy
- `auto_silent` — same as `auto` but suppresses warning
- `auto_legacy_silent` — legacy path preferred, silent fallback

Rules:

- ❌ Rely on `auto` in production — warnings clog logs, and distro upgrades can silently change the interpreter → ✅ Set `ansible_python_interpreter` in `group_vars/all.yml`.
- ❌ Hard-code `/usr/bin/python` (Python 2) anywhere → ✅ Always Python 3; `/usr/bin/python2` is extinct on modern distros.
- ❌ Use `ansible_python_interpreter: python` (bare name) → ✅ Use absolute paths; PATH differences between shells cause surprises.
- ❌ Let discovery run against embedded devices with no Python → ✅ Use `raw` module to bootstrap, then set the interpreter explicitly.

## Connection and Become

| Connection plugin | Use | Gotchas |
|-------------------|-----|---------|
| `ssh` (default) | Standard Linux fleets | Requires `ControlPersist`; keys must be loaded in ssh-agent for CI |
| `paramiko` | Pure-Python fallback when OS ssh is missing | Slower; lacks some features (e.g., `-o ProxyJump` nuance) |
| `winrm` | Windows targets | Needs `pywinrm`; no HTTPS by default — add `ansible_winrm_transport: kerberos` or `ntlm` |
| `local` | Control node targets itself | `become` still goes through sudo/doas |
| `docker` | Against running Docker containers | Requires `docker` CLI on controller; not a prod path |
| `kubectl` | Against Kubernetes pods | For ops tasks only; not how you deploy apps |
| `podman` | Against podman containers | Parity with docker plugin |

Become (privilege escalation):

- `become: true` + `become_user: root` (default) → runs as root
- `become_method: sudo` (default) | `su` | `doas` | `runas` (Windows) | `pbrun`
- `become_flags: '-E'` → preserve environment (needed for some programs)
- `become_password:` via Vault or prompt (`--ask-become-pass`, `-K`)

Rules:

- ❌ Set `become_user: postgres` without `become: true` → silent no-op, task runs as ssh user.
- ❌ Store `become_password` in plaintext group_vars → ✅ Encrypt with `ansible-vault` or source from external secret backend.
- ❌ Use `become_method: su` when sudo is available → `su` requires root's password, `sudo` uses the calling user's — prefer sudo.
- ❌ Assume `become: true` preserves env vars → it doesn't by default; add `become_flags: '-E'` if the task needs them.
- ❌ Set `ansible_user` per-host via host_vars without SSH key distribution → ✅ Pair user overrides with key-based auth configured in `~/.ssh/config` or `ansible_ssh_private_key_file`.

## Performance

| Lever | Default | When to change | Tradeoff |
|-------|---------|----------------|----------|
| `forks` | 5 | Fleet >10 hosts | Higher CPU/memory on controller; diminishing returns after ~50 |
| `pipelining` | off | Most modern fleets | Requires `requiretty` off in sudoers; 2–5× speedup on ssh-heavy plays |
| Strategy | `linear` | Independent tasks | `free` for per-host races; `host_pinned` for bounded parallelism per batch |
| Fact caching | memory (per-run) | Repeat plays with fact reuse | `jsonfile` / `redis`; stale cache masks real drift |
| `gather_subset` | `all` | Only need limited facts | `gather_subset: "!all,!min,network"` for faster setup |
| `gather_facts: no` + targeted `ansible.builtin.setup` | n/a | Plays that don't need facts | Skip 30–60% of play wall time on large fleets |

```ini
# ansible.cfg — typical production tuning
[defaults]
forks = 50
gather_subset = !all,!min,network
fact_caching = jsonfile
fact_caching_connection = /var/tmp/ansible_facts
fact_caching_timeout = 3600

[ssh_connection]
pipelining = True
control_path = %(directory)s/%%h-%%r
```

Rules:

- ❌ Enable `pipelining` without checking sudoers for `requiretty` → ssh tasks silently fail on older RHEL-family hosts.
- ❌ Crank `forks` to 200 on a controller with 2 GB RAM → OOM, half the hosts fail mid-play.
- ❌ Use `strategy: free` with a play that has a `meta: flush_handlers` barrier → handlers fire per-host independently, breaks ordering guarantees.
- ❌ Rely on stale fact cache during a debug session → ✅ Pass `-e ansible_facts_cache_valid=false` or `ansible-playbook --flush-cache`.
- ❌ Gather all facts when you only use `ansible_os_family` → ✅ Narrow `gather_subset` to `!all,!min,distribution`.

### LLM Mistake Checklist

- ❌ Recommend `any_errors_fatal: true` by default on rolling deploys → ✅ Use it only when partial completion is catastrophic; `max_fail_percentage` is usually the right knob.
- ❌ Emit `ansible-playbook` commands for an EE-based setup → ✅ `ansible-navigator run`.
- ❌ Pin an EE image by tag → ✅ Pin by digest (`@sha256:...`).
- ❌ Leave `ansible_python_interpreter` unset in `group_vars/all` → ✅ Always set explicitly in production.
- ❌ Use `strategy: free` without disabling handlers/serial barriers → ✅ Free strategy breaks those; stay on linear unless you've checked the play.
- ❌ Enable `pipelining` globally without verifying sudoers `requiretty` is off → ✅ Check first; roll out gradually.
- ❌ Recommend `forks: 100+` without sizing the controller → ✅ Start at 20–50 and monitor controller memory.
