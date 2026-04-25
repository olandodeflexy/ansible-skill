# Quick Reference

Cheatsheet and lookup tables for day-to-day Ansible work. Load this when the query is "what's the command for X" or "which module should I use for Y".

## Command Cheatsheet

| Goal | Command | Notes |
|------|---------|-------|
| Run a playbook | `ansible-playbook -i inventories/prod playbooks/site.yml` | Implicit `--check` is a common foot-gun — `--check` must be explicit |
| Lint | `ansible-lint` | Reads `.ansible-lint` from project root |
| Syntax check only | `ansible-playbook --syntax-check site.yml` | Parses YAML and validates module names; no execution |
| Dry-run with diffs | `ansible-playbook site.yml --check --diff --limit prod` | Last gate before real apply |
| Limit to group | `ansible-playbook site.yml --limit web` | `--limit` accepts group names, host patterns, and negations (`--limit '!db'`) |
| Limit to named list | `ansible-playbook site.yml --limit @hosts.txt` | `@file` loads newline-separated host list |
| Tag filter | `ansible-playbook site.yml --tags config,tls` | Only tasks with those tags |
| Skip tags | `ansible-playbook site.yml --skip-tags slow,heavy` | Inverse of `--tags` |
| Encrypt single value inline | `ansible-vault encrypt_string 'secret' --name 'db_password'` | Use for scalar secrets; leaves rest of file diffable |
| Encrypt whole file | `ansible-vault encrypt group_vars/prod/secrets.yml` | Use when whole file is sensitive |
| Edit vaulted file | `ansible-vault edit group_vars/prod/secrets.yml` | Decrypts to tmpfile, encrypts on save |
| Rekey vault | `ansible-vault rekey --new-vault-id prod@new_file secrets.yml` | Rotate the encryption key |
| Install collections | `ansible-galaxy collection install -r requirements.yml --collections-path ./collections` | Project-local install path |
| Verify collection signatures | `ansible-galaxy collection verify mycoll --keyring /etc/pki/ansible/keys.gpg --required-valid-signature-count 1` | Fails install if fewer than 1 valid signature found |
| Run via EE | `ansible-navigator run site.yml -i inventories/prod --mode stdout` | `--mode stdout` for CI (no TUI) |
| Inspect inventory | `ansible-inventory -i inventories/prod --graph --limit web` | See what `--limit` will actually match |
| List hosts that match | `ansible-playbook site.yml --list-hosts --limit web` | Confirm scope before running |
| ansible-test sanity | `ansible-test sanity --docker` | Inside a collection repo |
| ansible-test units | `ansible-test units --docker` | Module/plugin unit tests |
| Molecule test one scenario | `molecule test -s default` | Inside a role directory |
| Molecule converge once | `molecule converge -s default` | Skip teardown, useful for iteration |
| Ad-hoc command | `ansible -i inventories/prod web -m ansible.builtin.ping` | Fire one module across matched hosts |
| Gather facts once | `ansible -i inventories/prod all -m ansible.builtin.setup -a 'filter=ansible_distribution*'` | Debug helper |

## Troubleshooting Flowchart

When a play fails, walk this tree top-down.

- **Play failed**
  - **Unreachable host**
    - → Inspect with `ansible -i <inv> <host> -m ping`
    - → Check SSH: `ssh -vvv <host>`, confirm key in agent, confirm `ansible_host` IP
    - → For dynamic inventory: `ansible-inventory --graph --limit=<group>` — is the group populated?
  - **"command not found" inside a task**
    - → Wrong `ansible_python_interpreter`; set explicit path in `group_vars/all.yml`
    - → Missing system dep in the EE — add to `bindep.txt` and rebuild
  - **Module failure with stack trace**
    - → Re-run with `-vvv` (mind `no_log`) to see module stdin/stdout
    - → Check collection version in `requirements.yml`; recent "patch" bumps sometimes regress
    - → Confirm target has the Python modules the Ansible module needs (e.g. `community.postgresql` needs `psycopg2` on target)
  - **"Vault decrypt failed"**
    - → Wrong vault-id for the file's label; `head -1 file.yml` shows the label
    - → `ANSIBLE_VAULT_PASSWORD_FILE` unset or pointing at the wrong file
    - → File was encrypted with one key, decrypted with another; `ansible-vault rekey` if mid-rotation
  - **Idempotency warning / `changed=True` on every run**
    - → See `references/idempotency-patterns.md#module-idempotency-contracts`
    - → Most common culprits: `command`/`shell` without `changed_when`, `state: touch`, `state: restarted`, `state: latest`
  - **Handler didn't fire**
    - → Typo in `notify:` vs handler name → prefer `listen:` topics
    - → Play failed mid-run and no `force_handlers: true` on the play
    - → Handlers fire once per play at end; for mid-play needs use `meta: flush_handlers`
  - **`--check` passes but real apply fails**
    - → A task has `check_mode: no` or custom module without `supports_check_mode`
    - → `ignore_errors: true` is masking a real failure under `--check`
    - → See `references/idempotency-patterns.md#check-mode-coverage`
  - **Fact gathering hangs or times out**
    - → Fleet too large with default `forks: 5`; bump forks or narrow `hosts:`
    - → `gather_subset: all` on slow-fact hosts; scope to `!all,!min,network`
  - **Wrong variable value**
    - → See precedence ladder: `references/inventory-and-variables.md#variable-precedence-ladder`
    - → `ansible -m ansible.builtin.debug -a "var=<name>" <host>` to see what Ansible actually resolves
    - → Check for `--extra-vars` stray override in the invocation

## Module Recipe Lookup

| Goal | Preferred module | Minimal example |
|------|------------------|-----------------|
| Install package (any distro) | `ansible.builtin.package` | `ansible.builtin.package: name=nginx state=present` |
| Start/enable a systemd unit | `ansible.builtin.systemd` | `ansible.builtin.systemd: name=nginx state=started enabled=true` |
| Copy a file (with backup) | `ansible.builtin.copy` | `ansible.builtin.copy: src=nginx.conf dest=/etc/nginx/nginx.conf backup=yes` |
| Render a template | `ansible.builtin.template` | `ansible.builtin.template: src=app.conf.j2 dest=/etc/app.conf mode=0640` |
| Create/write a small file | `ansible.builtin.file` + `ansible.builtin.copy` | `ansible.builtin.file: path=/opt/app state=directory mode=0755` then `ansible.builtin.copy: content='...' dest=/opt/app/version` |
| Install or update Python deps | `ansible.builtin.pip` | `ansible.builtin.pip: requirements=/opt/app/requirements.txt virtualenv=/opt/app/venv` |
| Add/remove a cron job | `ansible.builtin.cron` | `ansible.builtin.cron: name='rotate logs' minute=0 hour=3 job='/usr/bin/logrotate -f'` |
| Create a local user | `ansible.builtin.user` | `ansible.builtin.user: name=app state=present shell=/bin/bash` |
| Open a firewall port (firewalld) | `ansible.posix.firewalld` | `ansible.posix.firewalld: port=443/tcp permanent=yes state=enabled` |
| Open a firewall port (UFW) | `community.general.ufw` | `community.general.ufw: rule=allow port=443 proto=tcp` |
| Mount a filesystem | `ansible.posix.mount` | `ansible.posix.mount: path=/data src=/dev/sdb1 fstype=ext4 state=mounted` |
| Download a file with checksum | `ansible.builtin.get_url` | `ansible.builtin.get_url: url=https://... dest=/tmp/... checksum=sha256:...` |
| Call a REST API | `ansible.builtin.uri` | `ansible.builtin.uri: url=https://api/... method=GET return_content=yes` |
| Manage a git repo on the target | `ansible.builtin.git` | `ansible.builtin.git: repo=... dest=/srv/app version=v1.2.3` |
| Manage a Docker container | `community.docker.docker_container` | `community.docker.docker_container: name=app image=app:1.2.3 state=started` |
| Apply a Kubernetes manifest | `kubernetes.core.k8s` | `kubernetes.core.k8s: state=present definition='{{ lookup("file","deploy.yml") \| from_yaml }}'` |
| Configure a PostgreSQL user (secret-bearing) | `community.postgresql.postgresql_user` | `community.postgresql.postgresql_user: name=app password='{{ db_password }}'` — set `no_log: true` at task level (sibling of the module key, not inside its args) |
| Create an S3 object | `amazon.aws.s3_object` | `amazon.aws.s3_object: bucket=my-bucket object=key src=/tmp/file mode=put` |

## Version Matrix

| `ansible-core` | Community `ansible` pkg | Release | EOL | EE image tag (OpenShift / creator-ee) |
|-----------------|--------------------------|---------|-----|---------------------------------------|
| 2.14 | 7.x | 2022-11 | 2024-05 (EOL) | `creator-ee:v0.21.0` |
| 2.15 | 8.x | 2023-05 | 2024-11 (EOL) | `creator-ee:v0.22.0` |
| 2.16 | 9.x | 2023-11 | 2025-05 | `creator-ee:v24.3.0` |
| 2.17 | 10.x | 2024-05 | 2025-11 | `creator-ee:v24.7.0` |
| 2.18 | 11.x | 2024-11 | 2026-05 | `creator-ee:v24.12.0` |

Rules:

- ❌ Pin to an EOL `ansible-core` for production → ✅ Upgrade at least one release before EOL; plan migration per `ansible-core` changelog.
- ❌ Rely on the community `ansible` bundle for production pinning → ✅ Pin `ansible-core` + individual collections via `requirements.yml`.
- ❌ Skip EE image upgrades "because collections are pinned" → ✅ EE also ships Python, pip packages, and OS libs; bump the image on each `ansible-core` bump.

### LLM Mistake Checklist

- ❌ Suggest `ansible-playbook --check` as a general safety net without `--diff` → ✅ Always pair: `--check --diff`; `--check` alone only tells you something would change, not what.
- ❌ Recommend `ansible-galaxy role install` for a collection-format role → ✅ `ansible-galaxy collection install`; the two are different installers.
- ❌ Use `ansible` ad-hoc for anything beyond one-shot diagnosis → ✅ Codify in a playbook; ad-hoc has no review trail.
- ❌ Guess the module name from short form → ✅ `ansible-doc -l | grep <keyword>` finds the FQCN.
- ❌ Trust an EOL `ansible-core` version in production → ✅ Check the support matrix in this file and upgrade before EOL.
- ❌ Use `--tags` without `--list-tags` to verify coverage → ✅ `ansible-playbook --list-tags site.yml` confirms tags exist before running.
- ❌ Assume `--limit` matches a group that's dynamically populated → ✅ `ansible-inventory --graph --limit=<pattern>` first.
