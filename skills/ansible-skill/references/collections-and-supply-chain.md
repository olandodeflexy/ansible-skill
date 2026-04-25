# Collections & Supply Chain

Detail for the `Collection/role supply chain` routing-table category.

## requirements.yml

```yaml
# requirements.yml — all five source types
collections:
  # 1. Ansible Galaxy (default source)
  - name: community.general
    version: "8.6.1"

  # 2. Red Hat Automation Hub (certified content)
  - name: redhat.rhel_system_roles
    version: "1.22.0"
    source: https://console.redhat.com/api/automation-hub/content/published/

  # 3. Git repository (tag/commit ref)
  - name: https://github.com/example/mycollection.git
    type: git
    version: v2.1.0

  # 4. Git repository (branch)
  - name: git@github.com:internal/ops-collection.git
    type: git
    version: main

  # 5. URL tarball
  - name: https://example.com/artifacts/mycollection-1.0.0.tar.gz

roles:
  - name: geerlingguy.postgresql
    version: "3.5.2"
```

| Source type | Syntax | When to use |
|-------------|--------|-------------|
| Galaxy | `name: namespace.collection` + `version:` | Community content, public |
| Automation Hub | Galaxy syntax + `source: https://console.redhat.com/...` | Red Hat certified, regulated envs |
| Git (tag) | `type: git`, `version: <tag>` | Internal/unreleased collections, audit-friendly |
| Git (branch) | `type: git`, `version: <branch>` | Dev only; never prod |
| URL tarball | `name:` is a URL | Air-gapped mirrors, artifact servers |

Install commands. The `collections:` and `roles:` sections are processed by **different installers** — `ansible-galaxy collection install -r` reads only `collections:` and silently skips `roles:` (and vice versa). Run both:

```bash
# Collections — into a project-local path so CI sees them
ansible-galaxy collection install -r requirements.yml \
  --collections-path ./collections \
  --force-with-deps

# Roles — separate invocation; no `--collections-path` flag here
ansible-galaxy role install -r requirements.yml \
  --roles-path ./roles
```

Rules:

- ❌ Mix collections and roles in the same `requirements.yml` list without the `collections:`/`roles:` top-level keys → Ansible parses the wrong format.
- ❌ Use `version: main` or `version: latest` in prod → ✅ Always a tag/SHA/exact semver.
- ❌ Omit `--collections-path ./collections` → collections install to the user's home dir, invisible to CI.
- ❌ Depend on `ansible-galaxy role install` for content that's shipped as a collection → collection-format roles don't install via the legacy role installer.

## FQCN required

Fully-qualified collection names prevent clashes when two collections ship modules with the same short name.

| ❌ Short name | ✅ FQCN |
|--------------|---------|
| `copy:` | `ansible.builtin.copy:` |
| `template:` | `ansible.builtin.template:` |
| `service:` | `ansible.builtin.service:` (or `ansible.builtin.systemd:` for systemd-specific) |
| `ec2_instance:` | `amazon.aws.ec2_instance:` |
| `postgresql_user:` | `community.postgresql.postgresql_user:` |
| `docker_container:` | `community.docker.docker_container:` |
| `k8s:` | `kubernetes.core.k8s:` |

The ansible-lint rule `fqcn` enforces this. Grandfathered exceptions:

- `ansible.builtin.*` is the correct FQCN for built-in modules. `ansible.legacy.*` is a backwards-compatibility namespace that lets short names resolve to built-ins; don't rely on it in new code.
- `block:` is a genuine language construct and does not need (or accept) an FQCN.
- `import_tasks`, `include_tasks`, `import_role`, `include_role`, `include_vars`, `import_playbook`, `meta`, `debug`, etc. **are** built-in modules — the ansible-lint `fqcn` rule flags their short forms. Write them as `ansible.builtin.import_tasks`, `ansible.builtin.include_role`, and so on.

Rules:

- ❌ Suppress `fqcn` lint rule globally → ✅ Add FQCNs; the short-name approach breaks silently when two collections collide.
- ❌ Assume `ansible.legacy.*` is safe → it's a migration aid and eligible for removal in future ansible-core versions.
- ❌ Use short module names in generated playbooks → always FQCN-prefix when creating new content.

## Signature Verification

| Registry | Signing | How to verify |
|----------|---------|---------------|
| Ansible Galaxy (public) | No built-in signing | Trust-on-first-use; verify tarball hash manually if needed |
| Red Hat Automation Hub (certified) | GPG signatures on collection artifacts | `ansible-galaxy collection verify` + keyring |
| Private Automation Hub | Optional GPG; configurable | Same as Red Hat AH if enabled |
| Git sources | Via git tag signing (`git tag -s`) | `git verify-tag` manually; ansible-galaxy doesn't check |

```ini
# ansible.cfg — require signature verification on install
[galaxy]
server_list = automation_hub, galaxy
# point ansible-galaxy at the keyring holding accepted signing keys
gpg_keyring = /etc/pki/ansible/automation-hub-signing.gpg

[galaxy_server.automation_hub]
url = https://console.redhat.com/api/automation-hub/content/published/
auth_url = https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token
token = <from keyring>
```

```bash
# verify after install — fail unless at least 1 valid signature is present
ansible-galaxy collection verify redhat.rhel_system_roles \
  --server automation_hub \
  --keyring /etc/pki/ansible/automation-hub-signing.gpg \
  --required-valid-signature-count 1
```

Rules:

- ❌ Skip signature verification in CI "to save time" → ✅ Signing defends against a compromised registry; the check is milliseconds per collection.
- ❌ Store signing keys in the repo → ✅ Controller's keyring or a mounted read-only volume.
- ❌ Accept `--ignore-signature-status-code` in CI → it defeats the purpose of signing.

## Private Hubs

Typical setup: mirror public collections + host internal ones.

```ini
# ansible.cfg
[galaxy]
server_list = internal_hub, galaxy

[galaxy_server.internal_hub]
url = https://automation-hub.internal.example.com/api/galaxy/content/published/
token = <from env/keyring>
validate_certs = true
```

```yaml
# requirements.yml — force a collection through internal_hub
collections:
  - name: internal.tooling
    version: "1.4.2"
    source: https://automation-hub.internal.example.com/api/galaxy/content/published/
```

Rules:

- ❌ Rely on public Galaxy in an air-gapped environment → ✅ Mirror through internal AH; pin to mirror's URL.
- ❌ Store hub tokens in a committed `ansible.cfg` → ✅ Inject via `ANSIBLE_GALAXY_SERVER_<ID>_TOKEN` env var.
- ❌ Rotate hub tokens only on compromise → ✅ Scheduled rotation (90 days), alert on staleness.
- ❌ Give every team the same hub token → ✅ Per-team tokens so audit logs attribute activity.

## Version Strategy

| Environment | Pin style | Example |
|-------------|-----------|---------|
| Production | Exact | `version: "8.6.1"` |
| Staging | Exact (match prod unless testing upgrade) | `version: "8.6.1"` or next candidate |
| Development | Minor range | `version: ">=8.6,<8.7"` |
| Bleeding-edge test | Major range | `version: ">=8.0,<9.0"` |

Upgrade workflow (one collection at a time):

1. Branch: `chore(deps): bump community.general 8.6.1 → 8.7.0`
2. Update `requirements.yml` + install locally
3. Run full Molecule matrix — any red, stop and investigate
4. Staged `--check --diff` — verify no unexpected task-level changes
5. PR review; link to collection changelog
6. Merge, deploy staging, run smoke tests, promote

Rules:

- ❌ Batch multiple collection upgrades in one PR → ✅ One at a time; easier to bisect a regression.
- ❌ Skip changelog review on patch bumps → ✅ Some "patch" bumps change behavior in practice.
- ❌ Upgrade without a Molecule run → ✅ The matrix catches breaking changes the changelog missed.
- ❌ Pin in `requirements.yml` but `--upgrade` on every CI run → ✅ Pin takes effect only if you don't override it at install time.

### LLM Mistake Checklist

- ❌ Recommend `ansible-galaxy install` without `--collections-path` → ✅ Always scope install to a project-local `collections/` dir.
- ❌ Suggest `version: latest` or a branch in prod `requirements.yml` → ✅ Exact tag/semver only.
- ❌ Use short module names in generated tasks → ✅ Always FQCN.
- ❌ Batch collection upgrades into one PR → ✅ One per PR for bisectability.
- ❌ Store hub tokens / vault keys in committed `ansible.cfg` → ✅ Env vars, injected by the runner.
- ❌ Skip signature verification when Automation Hub is available → ✅ `signing_keys` + `verify` in install step.
- ❌ Mix `collections:` and `roles:` entries without the top-level keys → ✅ Use the structured format even when you only have one type.
