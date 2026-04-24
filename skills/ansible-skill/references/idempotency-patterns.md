# Idempotency Patterns

Detail for the `Idempotency drift`, `Handler/ordering`, and `Check-mode blind spots` routing-table categories.

## Module Idempotency Contracts

| Module | Idempotent? | How it detects change | Gotcha |
|--------|-------------|-----------------------|--------|
| `ansible.builtin.copy` | Yes | Checksum (sha1) of src vs dest | Backup file names include timestamps — never idempotent if you diff them |
| `ansible.builtin.template` | Yes | Rendered content checksum vs dest | Trailing-newline differences silently re-render |
| `ansible.builtin.file` | Yes | Final state (present/absent/dir/link) matches | `state: touch` always reports `changed=True` |
| `ansible.builtin.lineinfile` | Yes | Regex/line already present at position | Without `regexp:` it only looks for exact match, may add duplicates |
| `ansible.builtin.blockinfile` | Yes | Markers delimit managed region | Changing `marker:` between runs produces two blocks |
| `ansible.builtin.replace` | Yes | Regex substitution produced no change | Non-matching regex still reports `ok`, not failure — use `failed_when` |
| `ansible.builtin.package` | Yes | Package manager reports already-installed | `state: latest` always re-resolves; heavier than `present` |
| `ansible.builtin.service` / `systemd` | Yes | Running state + enabled state already match | `state: restarted` always reports `changed=True` |
| `ansible.builtin.cron` | Yes | Matches on `name:` in crontab comment | Changing only `minute:` without `name:` creates a duplicate |
| `ansible.builtin.user` / `group` | Yes | Attribute diff against `/etc/passwd`/`/etc/group` | `password:` always re-hashes unless `update_password: on_create` |
| `ansible.posix.mount` | Yes | fstab entry + mount state both match | `state: remounted` not idempotent; use `mounted`. Lives in the `ansible.posix` collection, not `ansible.builtin` |
| `ansible.builtin.uri` | Partial | Only if server is idempotent for the method | `POST` to a non-idempotent endpoint loops forever on retry |
| `ansible.builtin.command` | **No** | None — always runs unless guarded | Requires `creates:` / `removes:` / `changed_when:` |
| `ansible.builtin.shell` | **No** | None — always runs unless guarded | Same as `command`, plus shell interpolation risks |
| `ansible.builtin.raw` | **No** | Runs via ssh without Python | Fallback for bootstrapping; never idempotent |
| `ansible.builtin.script` | **No** | Script always executes | Add `creates:` / `removes:` or wrap logic in `command` |

**Rules:**

- ✅ Prefer the native module over `command`/`shell` whenever one exists.
- ❌ Never assume `command` / `shell` / `raw` / `script` is idempotent.
- ✅ Treat `state: latest`, `state: restarted`, `state: touch`, `state: remounted` as explicitly non-idempotent by design.

## Command and Shell Guards

| Guard | Field | Semantic | Example |
|-------|-------|----------|---------|
| File-creates | `creates:` | Skip if path already exists | `creates: /opt/app/installed.marker` |
| File-removes | `removes:` | Skip if path does not exist | `removes: /tmp/leftover.lock` |
| Output match | `changed_when:` stdout/stderr | Change only if regex matches | `changed_when: "'added' in result.stdout"` |
| Return code | `changed_when:` on `rc` | Change only on specific rc values | `changed_when: result.rc == 2` |
| Non-changing | `changed_when: false` | Informational task, never changes | Status-probe commands |

```yaml
- name: Install custom binary once
  ansible.builtin.command: /opt/installer/run.sh --quiet
  args:
    creates: /opt/app/bin/custom-binary
```

Rules:

- ❌ `ansible.builtin.shell: "curl -s https://api.example.com | jq .status"` → ✅ `ansible.builtin.uri: url=https://api.example.com return_content=yes` then `set_fact` from the JSON.
- ❌ `ansible.builtin.command: rm -rf /tmp/build` (no guard) → ✅ `ansible.builtin.file: path=/tmp/build state=absent`.
- ❌ `ansible.builtin.shell: "psql -c 'CREATE USER x'"` (runs every time, fails on 2nd run) → ✅ `community.postgresql.postgresql_user: name=x state=present`.
- ❌ `ansible.builtin.command: systemctl restart nginx` → ✅ `ansible.builtin.systemd: name=nginx state=restarted` (and only when a handler fires).
- ❌ `ansible.builtin.shell` with pipes where `command` would work → ✅ Split into two tasks or use the correct module per step.
- ❌ Omitting `changed_when` on any `command`/`shell` → ✅ Always set it, use `changed_when: false` for status probes.

## Handler Patterns

| Pattern | When to use | Example |
|---------|-------------|---------|
| Single `notify` | One task triggers one handler | `notify: restart nginx` |
| Multi `notify` (list) | One task triggers several | `notify: [reload nginx, purge cache]` |
| `listen:` topic | Many tasks triggering one handler | `notify: "nginx-needs-reload"` + handler with `listen: "nginx-needs-reload"` |
| `meta: flush_handlers` | Force handlers to run before next task | Mid-play when later tasks depend on the restart |
| `force_handlers: true` | Run pending handlers even if a later task fails | Play-level — ensures cleanup/restore handlers still fire |

```yaml
- name: Update config
  ansible.builtin.template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
  notify: "nginx-needs-reload"

- ansible.builtin.meta: flush_handlers

- name: Verify nginx is serving
  ansible.builtin.uri:
    url: https://localhost/
```

Rules:

- ❌ Relying on natural end-of-play handler firing when your play has `serial:` batches and a batch fails mid-run — remaining batches still run but failed-batch handlers never fire unless `force_handlers: true`.
- ❌ Calling `notify:` on a name that has a typo → ✅ Prefer `listen:` topics; typos are caught once per topic, not per notify.
- ❌ Notifying multiple handlers that modify the same resource serially → ✅ Collapse into one handler or use `listen:` topic.
- ❌ Expecting handler to run on a host that was already marked failed → ✅ It won't, without `force_handlers`.
- ✅ Use `meta: flush_handlers` only when a later task genuinely depends on the handler running first; otherwise Ansible's end-of-play flush is fine.

## Check-mode Coverage

| Module category | `--check` safe? | Workaround |
|-----------------|------------------|------------|
| File-manipulation (`copy`, `template`, `file`, `lineinfile`) | Yes | None |
| Package (`package`, `dnf`, `apt`, `yum`) | Yes | None |
| Service (`service`, `systemd`) | Yes | None — but `state: restarted` always reports would-change |
| `command` / `shell` | **No by default** | For read-only probes: `check_mode: no` + `changed_when: false`. For mutating commands: gate with `when: not ansible_check_mode`. **Never** force `check_mode: yes` on a `command`/`shell` — it makes the task check-mode in *real* runs too, silently skipping execution and leaving `register` output undefined |
| Custom modules | Depends on module | Support is implemented in the module code itself — pass `supports_check_mode=True` to `AnsibleModule(...)` in the module's Python source. (Role `meta/argument_specs.yml` is unrelated — that validates role inputs, not module check-mode behavior.) Otherwise the task is skipped silently under `--check` |
| API / `uri` to external | Depends on endpoint | Wrap in `when: not ansible_check_mode` for mutating calls |

Rules:

- ❌ `ignore_errors: true` on a task that fails under `--check` → ✅ Fix the check-mode gap (add `check_mode: no` with a guard) so the failure is real when apply runs.
- ❌ `check_mode: no` on a mutating task — bypasses the dry-run → ✅ Only use `check_mode: no` on read-only probes (e.g., `ansible.builtin.command: systemctl is-active foo` with `changed_when: false`).
- ❌ Assuming a custom module honors `--check` without verifying → ✅ Grep the module source for `supports_check_mode=True`.
- ❌ Using `failed_when:` to hide a real check-mode failure → ✅ `failed_when` is for reinterpreting return codes, not for silencing check-mode incompatibility.
- ✅ For `uri` against a mutating endpoint, gate with `when: not ansible_check_mode` so the diff is preserved but the call is skipped in dry-run.

### LLM Mistake Checklist

- ❌ Emit `ansible.builtin.shell: "rm -rf {{ path }}"` with no guard → ✅ `ansible.builtin.file: path="{{ path }}" state=absent`.
- ❌ Recommend `command: systemctl restart X` at the top of a play → ✅ `ansible.builtin.systemd` in a handler, notified by the config task.
- ❌ Treat `uri` as always idempotent → ✅ `POST` is only idempotent if the server guarantees it; default to GET/PUT where possible.
- ❌ Skip `changed_when` on an `ansible.builtin.command` "because it's informational" → ✅ Set `changed_when: false` explicitly.
- ❌ Add `notify:` in another handler's block expecting chaining → ✅ Handlers cannot notify other handlers; use `listen:` topics.
- ❌ Assume `--check` caught a regression in a custom module → ✅ Check `supports_check_mode`; absent → the module is silently skipped under `--check`, not validated.
- ❌ Use `ignore_errors: true` to "make the play pass in CI" → ✅ Fix the underlying failure or use `failed_when` to reinterpret rc, never mask real failures.
